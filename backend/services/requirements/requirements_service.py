import logging
import json
import time
from typing import Tuple, List, Dict
from uuid import UUID

from sqlalchemy.orm import Session

from models.file_processing.file_metadata import FileMetadata
from models.file_processing.ocr_records import OCROutputs
from models.generator.requirement import Requirement
from services.llm.gemini_conversational.gemini_invoker import invoke_gemini_chat_with_timeout, invoke_freeform_prompt
from services.llm.gemini_conversational.json_output_parser import parse_llm_response
from core.config import OCRServiceConfigs
import os
from datetime import datetime


logger = logging.getLogger(__name__)


def get_usecase_documents_markdown(db: Session, usecase_id: UUID) -> Tuple[List[Dict], str]:
    files = db.query(FileMetadata).filter(
        FileMetadata.usecase_id == usecase_id,
        FileMetadata.is_deleted == False,
    ).order_by(FileMetadata.created_at.asc()).all()
    result_files: List[Dict] = []
    combined_parts: List[str] = []
    for f in files:
        outputs = db.query(OCROutputs).filter(
            OCROutputs.file_id == f.file_id,
            OCROutputs.is_deleted == False,
        ).order_by(OCROutputs.page_number.asc()).all()
        md = "\n".join([(o.page_text or "") for o in outputs])
        result_files.append({
            "file_id": str(f.file_id),
            "file_name": f.file_name,
            "markdown": md,
        })
        if md.strip():
            combined_parts.append(f"## {f.file_name}\n\n{md}\n")
    combined_markdown = "\n".join(combined_parts).strip()
    logger.info("requirements_service: docs files=%d combined_chars=%d", len(result_files), len(combined_markdown))
    # Write snapshot to disk for debugging
    try:
        base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs", "requirements")
        os.makedirs(base, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
        snap = os.path.join(base, f"{ts}-combined.md")
        with open(snap, "w", encoding="utf-8") as f:
            f.write(combined_markdown)
        logger.info("requirements_service: combined markdown snapshot=%s", snap)
    except Exception as e:
        logger.warning("requirements_service: failed to write combined snapshot: %s", e)
    if OCRServiceConfigs.LOG_OCR_TEXT and combined_markdown:
        snippet = combined_markdown[: min(len(combined_markdown), OCRServiceConfigs.OCR_TEXT_LOG_MAX_LENGTH)]
        logger.info("requirements_service combined markdown (snippet):\n%s", snippet)
    return result_files, combined_markdown


def _safe_parse_json(text: str) -> dict | list:
    try:
        return json.loads(text)
    except Exception:
        # Attempt to extract JSON blob heuristically
        import re
        m = re.search(r"\{[\s\S]*\}|\[[\s\S]*\]", text)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return {}
        return {}


def extract_requirement_list(markdown: str) -> List[Dict]:
    prompt = (
        "You are an intelligent requirement segmentation assistant.  \n"
        "Your task is to analyze the given document (which may contain structured tables or free-flowing sentences) and segment it into logical requirements.\n"
        "Extract all requirements from the document.\n\n"
        "Core Instructions:\n"
        "- Identify and extract each distinct requirement from the document.\n"
        "- Ensure each requirement is represented in JSON format under a unified schema.\n"
        "- Preserve clarity and completeness of requirement meaning.\n"
        "- Do not merge multiple requirements into one; keep them separate.\n"
        "- Do not hallucinate or add information not present in the document.\n"
        "- Extract EVERY row from the table as a SEPARATE requirement.\n\n"
        "\n\nGuidelines for Name and Description:\n"
        "- name: Short identifier from Title column (5-10 words max)\n"
        "- description: Include Req ID, Type, Priority, and full Description in one sentence\n\n"
        "For each requirement row in the table, create one entry.\n\n"
        "Return JSON output with name and description.\n\n\n"
        "Data:{Data}\n\n"
        "Document Markdown (truncated):\n" + markdown
    )
    logger.info("requirements_service: invoking requirement list extractor, prompt_chars=%d", len(prompt))
    raw = invoke_freeform_prompt(prompt)
    # Log raw IO already written by helper
    # Robust parsing
    parsed = None
    errors: list[str] = []
    try:
        parsed = json.loads(raw)
    except Exception as e:
        errors.append(f"json.loads failed: {e}")
        cleaned = raw
        # remove code fences
        cleaned = cleaned.replace("```json", "").replace("```", "")
        # trim to JSON-ish content
        import re
        m = re.search(r"\{[\s\S]*\}|\[[\s\S]*\]", cleaned)
        if m:
            try:
                parsed = json.loads(m.group(0))
            except Exception as e2:
                errors.append(f"fallback parse failed: {e2}")
        if parsed is None:
            logger.error("requirements_service: list parse failed; errors=%s", "; ".join(errors))
            return []

    # Normalize
    items: List[Dict] = []
    if isinstance(parsed, dict):
        if "requirements" in parsed and isinstance(parsed["requirements"], list):
            src = parsed["requirements"]
        elif "requirement_entities" in parsed and isinstance(parsed["requirement_entities"], list):
            src = parsed["requirement_entities"]
        else:
            src = []
        for it in src:
            if isinstance(it, dict):
                name = str(it.get("name") or "").strip()
                desc = str(it.get("description") or "").strip()
                if name and desc:
                    items.append({"name": name, "description": desc})
    elif isinstance(parsed, list):
        for it in parsed:
            if isinstance(it, dict):
                name = str(it.get("name") or "").strip()
                desc = str(it.get("description") or "").strip()
                if name and desc:
                    items.append({"name": name, "description": desc})
    logger.info("requirements_service: list extractor returned %d items", len(items))
    # Blue preview log of list extractor output (first few items)
    try:
        import json as _json
        preview_items = []
        for it in items[: min(5, len(items))]:
            preview_items.append({
                "name": (it.get("name", "") or "")[:120],
                "description": (it.get("description", "") or "")[:240],
            })
        _preview = _json.dumps(preview_items)[:2000]
        if len(_json.dumps(preview_items)) > 2000:
            _preview += "... [TRUNCATED]"
        logger.info("\033[34mrequirements_service: list preview -> %s\033[0m", _preview)
    except Exception:
        pass
    return items


def extract_requirement_details(markdown: str, name: str, description: str, previously_generated: List[Dict]) -> Dict:
    prior_json = json.dumps(previously_generated) if previously_generated else "[]"
    prompt = (
        "## 🔧 System Instruction – Stage 2: Requirement Detail Extraction for Test Case Generation\n\n"
        "We are developing a system that processes requirement documents provided by users. The overall system operates in three key phases:\n\n"
        "1. **Logical Segmentation** – Identifying and extracting independent requirement units.\n"
        "2. **Detailed Requirement Extraction** – (You are here) – For a given requirement name, extract all its supporting content from the document.\n"
        "3. **Test Case Generation** – Using the extracted data to generate functional and scenario-based test cases.\n\n"
        "---\n\n"
        "### 🎯 Current Task – Stage 2\n\n"
        "You are an **expert in the corporate banking domain** ** and API/service integration** familiar with the entire lifecycle of software documentation—FSDs, BRDs, user journeys, integration specs, ** API specifications, service contracts,** billing templates, and more.\n\n"
        "REMEMBER:\n"
        "1. For headings that are crossed / cancelled remove them completely ! \n"
        "2. Also, if there is something under these cancelled / crossed heading discard them completely as well.\n\n"
        "** STEP 1: DETERMINE REQUIREMENT TYPE**  \n"
        "**Before extracting content, analyze the input to determine if this is:**\n"
        "**UI/Functional requirement (existing behavior)**\n"
        "**API/Service requirement (new capability)**\n\n"
        "**API INDICATORS to look for:**\n"
        "**HTTP methods, endpoints, REST/SOAP services**\n"
        "**Request/response specifications, JSON/XML schemas**\n"
        "**Authentication methods, API keys, tokens**\n"
        "**Status codes, error responses, service integrations**\n\n"
        "Your task is to:\n\n"
        "Take as input:\n\n"
        "  * A **requirement name**\n"
        "  * A **requirement description**\n"
        "  * A **source document** ** (which may contain UI specifications, API documentation, or both)**\n"
        "  * Optional: Previously generated requirements and additional user instructions\n"
        "And produce as output:\n\n"
        "  * A **JSON structure containing all details related to that requirement only**, extracted **strictly** from the document content.\n\n"
        "---\n\n"
        "## 🔑 Key Principles\n\n"
        "**Document grounding is mandatory**: All extracted content must come directly from the document. Do not hallucinate or invent.\n"
        "**Do not repeat**: If content is already present in \"Previously Generated Requirements,\" **do not include it again**.\n"
        "**Follow user instructions**: When user provides additional instructions, follow only those relevant to the **requirement extraction phase**. Ignore anything related to later stages.\n"
        "**Output format is fixed**: Always use the specified JSON structure. However, the **internal keys inside requirements must reflect only what is found in the document.**\n\n"
        "---\n\n"
        "### ✅ Deduplication Principle – Include Only New Content\n\n"
        "To ensure correctness and uniqueness, you must:\n\n"
        "**Compare** every extracted sentence, list item, or rule with all content in the \"Previously Generated Requirements.\"\n"
        "**Exclude** any content that:\n\n"
        "  * Appears **exactly the same**\n"
        "  * Is a **paraphrased version** of existing content\n"
        "  * Is **semantically identical** even if worded differently\n"
        "This applies to every section of the output including:\n\n"
        "  * user_stories ** OR api_service_flows**\n"
        "  * All sub-sections inside requirements and dynamic_sections\n"
        "If a section like \"Fee Reversal Scenarios\" ** OR \"Authentication Flow\" OR \"Error Response Handling\"** or \"Client Code Validation\" is already handled in full by a previous requirement, **do not re-add** it unless the document contains **new, unique logic** relevant to the current requirement.\n\n"
        "---\n\n"
        "## ✅ SAMPLE OUTPUT FORMAT\n\n"
        "json\n"
        "{{\n  \"requirement_entities\": [\n    {{\n      \"name\": \"Requirement Name as it given in the specific input requirement by user. Don't give any other name.\",\n      \"description\": \"Detailed description as it is given in the input requirement by user\",\n      \"user_stories\": [\n        \"User story 1 in detail if given in document else generated but grounded to given application content  OR API service interaction 1\",\n        \"User story 2 in detail if given in document else generated but grounded to given application content  OR API service interaction 2\",\n        \"User story 3 in detail if given in document else generated but grounded to given application content  OR API service interaction 3\",\n        \"User story n in detail if given in document else generated but grounded to given application content  OR API service interaction n\"\n      ],\n      \"requirements\": {{\n        \"functional_requirements\": [\n          \"Detailed list of functional requirements or steps  OR API operation specifications.\"\n        ],\n        \"business_rules\": [\n          \"Explicit business rules, validations, error handling, and conditional logics  (applies to both UI and API requirements).\"\n        ],\n        \"data_elements\": [\n          \"Detailed information of data fields, formats, types, validations and other information available for that element  OR API parameter details, data types, constraints.\"\n        ],\n        \"UI/UX_requirements\": [\n          \"Navigation path: Detailed navigation path or workflow.\",\n          \"App name: Name of the application or system.\",\n          \"Interactions: Explicit user or system interactions.\",\n          \"Mockups: References to UI mockups or wireframes.\"\n        ],\n        \" api_specifications\": [\n          \" HTTP Method: GET, POST, PUT, DELETE methods specified\",\n          \" Endpoint: Complete API endpoint URLs and paths\",\n          \" Authentication: API key, Bearer token, OAuth specifications\",\n          \" Request Format: JSON/XML request structure and required fields\",\n          \" Response Format: Expected response structure and data types\",\n          \" Status Codes: Success and error status codes with descriptions\"\n        ],\n        \" request_response_details\": [\n          \" Request Headers: Required and optional header specifications\",\n          \" Request Parameters: Path, query, and body parameter details\",\n          \" Response Structure: Complete response schema and field descriptions\",\n          \" Error Responses: Error codes, messages, and handling specifications\"\n        ],\n        \"integration_requirements\": [\n          \"Interfaces: Explicit external/internal system interfaces and their purposes  OR API service dependencies.\",\n          \"Module dependencies: Explicit internal module dependencies  OR upstream/downstream service dependencies.\"\n        ],\n        \"non_functional_requirements\": [\n          \"Performance: Performance specifications or expectations  OR API response time requirements.\",\n          \"Scalability: Scalability details or expectations  OR API rate limiting specifications.\",\n          \"Security: Explicit security requirements or considerations  OR API security, authentication, authorization.\"\n        ],\n        \"other_requirements\": [\n          \"Any miscellaneous requirements not fitting other categories.\"\n        ],\n        \"pre_conditions\": [\n          \"Explicit conditions that must exist prior to requirement execution  OR API authentication setup, service availability.\"\n        ],\n        \"actions\": [\n          \"Specific actions or triggers related to the requirement  OR API operations and service calls.\"\n        ],\n        \"wireframes\": [\n          \"Detailed descriptions or references to wireframes  OR API documentation, service contracts.\"\n        ],\n        \" authentication_authorization\": [\n          \" Authentication methods: API key, token-based, OAuth flows\",\n          \" Authorization rules: Role-based access, permission specifications\",\n          \" Security protocols: SSL/TLS requirements, encryption specifications\"\n        ],\n        \" error_handling\": [\n          \" Error scenarios: Business validation failures, system errors\",\n          \" Error responses: Error message formats, status codes\",\n          \" Fallback mechanisms: Retry logic, circuit breaker patterns\"\n        ],\n        \" service_integration\": [\n          \" Upstream services: Dependencies on other APIs or services\",\n          \" Downstream impacts: Systems affected by this API\",\n          \" Integration patterns: Synchronous/asynchronous communication\"\n        ],\n        \"other  section mentioned in document\": [\n          \"For any other sections not covered above (e.g.'Client Code validation', 'Specific UI pop-ups/interactions' ,'Test SCenarios', 'Transaction Filed Details', 'status', 'Business Field Details' ,'Product Field Details'  ,'current_functionality', 'expected_change_in_process', 'billing_template', 'charge_events', 'virtual_account_setup', 'validation_rules' , 'api_rate_limiting', 'webhook_specifications', 'callback_urls', 'service_level_agreements'), dynamically create a new key whose value is a list of strings extracted from that section.\"\n        ]\n      }}\n    }}\n  ]\n}}\n\n\n"
        "\n> ⚠️ **Important Clarification:**\n"
        ">\n"
        "* The section keys shown under \"requirements\" above (e.g., functional_requirements, data_elements, ** api_specifications** etc.) are **just examples**.\n"
        "* You must **dynamically generate all keys based on actual content found in the document**.\n"
        "* If a requirement in the document contains a section titled \"Transaction Field Matrix\" ** OR \"API Rate Limiting\" OR \"Webhook Configuration\"** or \"Authorization Rules\", then those must become new keys inside requirements or dynamic_sections accordingly.\n"
        "* Do not assume that every key shown in the sample will be present in every requirement.\n"
        "* All values must be lists of strings.\n"
        "* Do not include any key if the document contains no data for it.\n\n"
        "---\n\n"
        "## 🧠 Extraction Objectives\n\n"
        "Ensure comprehensive extraction of **all unique and requirement-specific content** from the document, such as:\n\n"
        "Functional steps, flows, or logic ** OR API operation workflows**\n"
        "Business rules and conditional handling ** (applies to both UI and API)**\n"
        "Data elements: names, types, formats, validations ** OR API parameters, request/response fields**\n"
        "UI/UX behaviors: navigation paths, visible fields, screen names ** OR API endpoints, methods, authentication flows**\n"
        "System interactions: APIs, modules, interfaces ** OR service integrations, microservice communications**\n"
        "Security, performance, and non-functional details ** OR API security, rate limiting, SLA requirements**\n"
        "Wireframes or mockup references ** OR API documentation, service contracts**\n"
        "** HTTP methods, endpoint specifications, request/response schemas**\n"
        "** Authentication mechanisms, API keys, token management**\n"
        "** Status codes, error handling, exception responses**\n"
        "** Service dependencies, integration patterns**\n"
        "** Rate limiting, throttling, concurrent request handling**\n"
        "Any **explicitly mentioned** test scenarios, validation rules, statuses, field constraints, or process triggers ** OR API test scenarios, validation rules, error conditions**\n\n"
        "---\n\n"
        "## 📘 Special Extraction Cases\n\n"
        "If present and **not duplicated** in previously generated requirements, also extract:\n\n"
        "Date/time validations, cutoffs, and scheduling rules\n"
        "API specs, methods, payloads, error codes ** (enhanced focus for API requirements)**\n"
        "** Request/response schemas, parameter specifications**\n"
        "** Authentication flows, token validation, session management**\n"
        "** HTTP status codes, error response formats**\n"
        "** API versioning, backward compatibility requirements**\n"
        "** Rate limiting policies, throttling mechanisms**\n"
        "** Service availability requirements, uptime specifications**\n"
        "** Webhook configurations, callback URL specifications**\n"
        "** API documentation references, OpenAPI/Swagger specs**\n"
        "** Integration timeouts, retry policies, circuit breaker patterns**\n"
        "Accessibility or compliance requirements\n"
        "Authentication flows (e.g., 2FA) ** (expanded to include API authentication)**\n"
        "Screen access restrictions ** OR API access restrictions, role-based permissions**\n"
        "Download/export formats ** OR API response formats, content types**\n"
        "Default values, mandatory/read-only rules ** OR required/optional API parameters**\n"
        "Field interdependencies (e.g., Product + Account Type) ** OR API parameter dependencies**\n"
        "Reporting configurations ** OR API monitoring, logging requirements**\n"
        "Not-in-scope validations ** OR API scope limitations**\n"
        "PSFC or client code handling\n"
        "Record limits, search filters, status rules, and transaction types ** OR API pagination, filtering, response limits**\n\n"
        "These may be assigned to a predefined key if applicable, or to a new dynamically named key under dynamic_sections.\n\n"
        "---\n\n"
        "## 🚫 Do Not\n\n"
        "❌ Hallucinate content not present in the document\n"
        "❌ Include **any** content that exists in **Previously Generated Requirements**\n"
        "❌ Add similar logic in slightly varied wording if the core logic is already captured\n"
        "❌ Include requirements or flows unrelated to the current input requirement name/description\n\n"
        "---\n\n"
        "## ✅ Always\n\n"
        "✅ Filter out duplicates (verbatim or semantic) by comparing with prior requirement entries\n"
        "✅ Extract only content uniquely related to the current requirement\n"
        "✅ Dynamically generate keys for each section based on document headers and structure ** (including API-specific sections)**\n"
        "✅ Apply user-specific instructions related to **requirement stage only**\n"
        "✅ Format output strictly in the defined JSON schema\n\n"
        f"Requirement: {name}\nDescription: {description}\nPreviously Generated Requirements: {prior_json}\n\n"
        "Explaination:{Explination}\nList :{List_Data}\n\n"
        "Document Markdown (truncated):\n" + markdown
    )
    logger.info("requirements_service: invoking details extractor for '%s'", name)
    raw = invoke_freeform_prompt(prompt)
    parsed = _safe_parse_json(raw)
    details = parsed.get("requirement_entities", {}) if isinstance(parsed, dict) else {}
    try:
        import json as _json
        preview = _json.dumps(details)[:1500]
        if len(_json.dumps(details)) > 1500:
            preview += "... [TRUNCATED]"
        logger.info("\033[34mrequirements_service: details preview for '%s' -> %s\033[0m", name, preview)
    except Exception:
        pass
    logger.info("requirements_service: details extractor returned keys=%s", list(details.keys()) if isinstance(details, dict) else [])
    return details


def persist_requirement(db: Session, usecase_id: UUID, requirement_json: Dict) -> UUID:
    rec = Requirement(
        usecase_id=usecase_id,
        requirement_text=requirement_json,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    logger.info("requirements_service: persisted requirement id=%s", str(rec.id))
    return rec.id


