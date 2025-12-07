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
import importlib
from datetime import datetime
from core.env_config import get_env_variable
from core.config import AgentLogConfigs


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


def _yellow(text: str) -> str:
    try:
        return f"\033[33m{text}\033[0m"
    except Exception:
        return text


def extract_requirement_list(markdown: str, model_name: str = "gemini-2.5-flash") -> List[Dict]:
    # Prefer file-based prompt if provided to ease multiline editing
    prompt_file = get_env_variable("REQUIREMENT_LIST_PROMPT_FILE", "").strip()
    base_prompt: str
    if prompt_file:
        try:
            if os.path.exists(prompt_file):
                with open(prompt_file, "r", encoding="utf-8") as f:
                    base_prompt = f.read()
            else:
                base_prompt = ""
        except Exception:
            base_prompt = ""
    else:
        # Try module-based prompt if configured
        base_prompt = ""
        try:
            mod_path = get_env_variable("REQUIREMENT_LIST_PROMPT_MODULE", "").strip()
            attr_name = (get_env_variable("REQUIREMENT_LIST_PROMPT_ATTR", "requirement_list_prompt") or "requirement_list_prompt").strip()
            if mod_path:
                mod = importlib.import_module(mod_path)
                val = getattr(mod, attr_name, None)
                if val is None:
                    val = getattr(mod, "__doc__", "") or ""
                base_prompt = str(val or "")
        except Exception:
            base_prompt = ""
        if not base_prompt:
            base_prompt = get_env_variable("REQUIREMENT_LIST_PROMPT", "")

    # Log the SYSTEM PROMPT (input) in yellow for debugging
    if AgentLogConfigs.LOG_AGENT_SYSTEM_PROMPT:
        try:
            text = base_prompt or ""
            if len(text) > AgentLogConfigs.LOG_AGENT_SYSTEM_PROMPT_MAX_LENGTH:
                text = text[:AgentLogConfigs.LOG_AGENT_SYSTEM_PROMPT_MAX_LENGTH] + "... [TRUNCATED]"
            logger.info(_yellow("requirements_service: list extractor SYSTEM PROMPT (input):\n%s"), text)
        except Exception:
            pass

    prompt = base_prompt + """Please analyze the following document and extract requirements as a JSON object format given in system instructions.

                Document Context:""" + markdown
    
    logger.info("requirements_service: invoking requirement list extractor, prompt_chars=%d, model=%s", len(prompt), model_name)
    raw = invoke_freeform_prompt(prompt, model_name=model_name)
    # Log COMPLETE raw output from the agent before any parsing (for parser adjustments)
    # Always log complete output, write to file if too long for console
    try:
        text = raw or ""
        if AgentLogConfigs.LOG_AGENT_RAW_OUTPUT:
            if len(text) > AgentLogConfigs.LOG_AGENT_RAW_OUTPUT_MAX_LENGTH:
                # Write complete output to file
                try:
                    base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs", "requirements")
                    os.makedirs(base, exist_ok=True)
                    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
                    output_file = os.path.join(base, f"{ts}-list-extractor-complete-output.txt")
                    with open(output_file, "w", encoding="utf-8") as f:
                        f.write(text)
                    logger.info(_yellow("requirements_service: list extractor COMPLETE output (too long for console, written to file): %s (length=%d)"), output_file, len(text))
                    # Also log a preview in console
                    preview = text[:AgentLogConfigs.LOG_AGENT_RAW_OUTPUT_MAX_LENGTH] + "... [TRUNCATED - see file for complete output]"
                    logger.info(_yellow("requirements_service: list extractor RAW output (preview):\n%s"), preview)
                except Exception as e:
                    logger.warning("requirements_service: failed to write complete list output to file: %s", e)
                    # Fallback: log truncated version
                    preview = text[:AgentLogConfigs.LOG_AGENT_RAW_OUTPUT_MAX_LENGTH] + "... [TRUNCATED]"
                    logger.info(_yellow("requirements_service: list extractor RAW output (truncated):\n%s"), preview)
            else:
                logger.info(_yellow("requirements_service: list extractor RAW output (complete):\n%s"), text)
        else:
            # Even if LOG_AGENT_RAW_OUTPUT is disabled, write complete output to file for debugging
            try:
                base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs", "requirements")
                os.makedirs(base, exist_ok=True)
                ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
                output_file = os.path.join(base, f"{ts}-list-extractor-complete-output.txt")
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(text)
                logger.info("requirements_service: list extractor complete output written to file: %s (length=%d)", output_file, len(text))
            except Exception as e:
                logger.warning("requirements_service: failed to write complete list output to file: %s", e)
    except Exception:
        pass
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
    
    # Log COMPLETE parsed output (all items)
    try:
        import json as _json
        complete_output = _json.dumps(items, indent=2, ensure_ascii=False)
        if len(complete_output) > AgentLogConfigs.LOG_AGENT_RAW_OUTPUT_MAX_LENGTH:
            # Write complete parsed output to file
            try:
                base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs", "requirements")
                os.makedirs(base, exist_ok=True)
                ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
                output_file = os.path.join(base, f"{ts}-list-extractor-parsed-complete.json")
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(complete_output)
                logger.info("\033[34mrequirements_service: list extractor COMPLETE parsed output (written to file): %s (items=%d, length=%d)\033[0m", output_file, len(items), len(complete_output))
                # Also log a preview in console
                preview = complete_output[:2000] + "... [TRUNCATED - see file for complete output]"
                logger.info("\033[34mrequirements_service: list parsed output (preview):\n%s\033[0m", preview)
            except Exception as e:
                logger.warning("requirements_service: failed to write complete parsed list output to file: %s", e)
                # Fallback: log truncated version
                preview = complete_output[:2000] + "... [TRUNCATED]"
                logger.info("\033[34mrequirements_service: list parsed output (truncated):\n%s\033[0m", preview)
        else:
            logger.info("\033[34mrequirements_service: list extractor COMPLETE parsed output:\n%s\033[0m", complete_output)
    except Exception as e:
        logger.warning("requirements_service: failed to log complete parsed list output: %s", e)
        # Fallback: log preview of first few items
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


def extract_requirement_details(markdown: str, name: str, description: str, previously_generated: List[Dict], model_name: str = "gemini-2.5-flash") -> Dict:
    prior_json = json.dumps(previously_generated) if previously_generated else "[]"
    details_prompt_file = get_env_variable("REQUIREMENT_DETAILS_PROMPT_FILE", "").strip()
    if details_prompt_file:
        try:
            if os.path.exists(details_prompt_file):
                with open(details_prompt_file, "r", encoding="utf-8") as f:
                    base_details_prompt = f.read()
            else:
                base_details_prompt = ""
        except Exception:
            base_details_prompt = ""
    else:
        # Try module-based prompt if configured
        base_details_prompt = ""
        try:
            mod_path = get_env_variable("REQUIREMENT_DETAILS_PROMPT_MODULE", "").strip()
            attr_name = (get_env_variable("REQUIREMENT_DETAILS_PROMPT_ATTR", "requirement_details_prompt") or "requirement_details_prompt").strip()
            if mod_path:
                mod = importlib.import_module(mod_path)
                val = getattr(mod, attr_name, None)
                if val is None:
                    val = getattr(mod, "__doc__", "") or ""
                base_details_prompt = str(val or "")
        except Exception:
            base_details_prompt = ""
        if not base_details_prompt:
            base_details_prompt = get_env_variable("REQUIREMENT_DETAILS_PROMPT", "")

    # Log the SYSTEM PROMPT (input) in yellow for debugging
    if AgentLogConfigs.LOG_AGENT_SYSTEM_PROMPT:
        try:
            text = base_details_prompt or ""
            if len(text) > AgentLogConfigs.LOG_AGENT_SYSTEM_PROMPT_MAX_LENGTH:
                text = text[:AgentLogConfigs.LOG_AGENT_SYSTEM_PROMPT_MAX_LENGTH] + "... [TRUNCATED]"
            logger.info(_yellow("requirements_service: details extractor SYSTEM PROMPT (input) for '%s':\n%s"), name, text)
        except Exception:
            pass
    dynamic_parts = (
        f"Requirement: {name}\nDescription: {description}\nPreviously Generated Requirements: {prior_json}\n\n"
        "Explaination:{Explination}\nList :{List_Data}\n\n"
        "Document Markdown (truncated):\n" + markdown
    )
    prompt = base_details_prompt + dynamic_parts
    logger.info("requirements_service: invoking details extractor for '%s', model=%s", name, model_name)
    raw = invoke_freeform_prompt(prompt, model_name=model_name)
    # Log COMPLETE raw output from the agent before any parsing (for parser adjustments)
    # Always log complete output, write to file if too long for console
    try:
        text = raw or ""
        if AgentLogConfigs.LOG_AGENT_RAW_OUTPUT:
            if len(text) > AgentLogConfigs.LOG_AGENT_RAW_OUTPUT_MAX_LENGTH:
                # Write complete output to file
                try:
                    base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs", "requirements")
                    os.makedirs(base, exist_ok=True)
                    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
                    # Sanitize name for filename
                    safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()[:50]
                    output_file = os.path.join(base, f"{ts}-details-extractor-{safe_name}-complete-output.txt")
                    with open(output_file, "w", encoding="utf-8") as f:
                        f.write(text)
                    logger.info(_yellow("requirements_service: details extractor COMPLETE output for '%s' (too long for console, written to file): %s (length=%d)"), name, output_file, len(text))
                    # Also log a preview in console
                    preview = text[:AgentLogConfigs.LOG_AGENT_RAW_OUTPUT_MAX_LENGTH] + "... [TRUNCATED - see file for complete output]"
                    logger.info(_yellow("requirements_service: details extractor RAW output (preview) for '%s':\n%s"), name, preview)
                except Exception as e:
                    logger.warning("requirements_service: failed to write complete details output to file for '%s': %s", name, e)
                    # Fallback: log truncated version
                    preview = text[:AgentLogConfigs.LOG_AGENT_RAW_OUTPUT_MAX_LENGTH] + "... [TRUNCATED]"
                    logger.info(_yellow("requirements_service: details extractor RAW output (truncated) for '%s':\n%s"), name, preview)
            else:
                logger.info(_yellow("requirements_service: details extractor RAW output (complete) for '%s':\n%s"), name, text)
        else:
            # Even if LOG_AGENT_RAW_OUTPUT is disabled, write complete output to file for debugging
            try:
                base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs", "requirements")
                os.makedirs(base, exist_ok=True)
                ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
                # Sanitize name for filename
                safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()[:50]
                output_file = os.path.join(base, f"{ts}-details-extractor-{safe_name}-complete-output.txt")
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(text)
                logger.info("requirements_service: details extractor complete output for '%s' written to file: %s (length=%d)", name, output_file, len(text))
            except Exception as e:
                logger.warning("requirements_service: failed to write complete details output to file for '%s': %s", name, e)
    except Exception:
        pass
    parsed = _safe_parse_json(raw)
    details = parsed.get("requirement_entities", {}) if isinstance(parsed, dict) else {}
    
    # Log COMPLETE parsed output
    try:
        import json as _json
        complete_output = _json.dumps(details, indent=2, ensure_ascii=False)
        if len(complete_output) > AgentLogConfigs.LOG_AGENT_RAW_OUTPUT_MAX_LENGTH:
            # Write complete parsed output to file
            try:
                base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs", "requirements")
                os.makedirs(base, exist_ok=True)
                ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
                # Sanitize name for filename
                safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()[:50]
                output_file = os.path.join(base, f"{ts}-details-extractor-{safe_name}-parsed-complete.json")
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(complete_output)
                logger.info("\033[34mrequirements_service: details extractor COMPLETE parsed output for '%s' (written to file): %s (length=%d)\033[0m", name, output_file, len(complete_output))
                # Also log a preview in console
                preview = complete_output[:1500] + "... [TRUNCATED - see file for complete output]"
                logger.info("\033[34mrequirements_service: details parsed output (preview) for '%s':\n%s\033[0m", name, preview)
            except Exception as e:
                logger.warning("requirements_service: failed to write complete parsed details output to file for '%s': %s", name, e)
                # Fallback: log truncated version
                preview = complete_output[:1500] + "... [TRUNCATED]"
                logger.info("\033[34mrequirements_service: details parsed output (truncated) for '%s':\n%s\033[0m", name, preview)
        else:
            logger.info("\033[34mrequirements_service: details extractor COMPLETE parsed output for '%s':\n%s\033[0m", name, complete_output)
    except Exception as e:
        logger.warning("requirements_service: failed to log complete parsed details output for '%s': %s", name, e)
        # Fallback: log preview
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
    # Create requirement first
    rec = Requirement(
        usecase_id=usecase_id,
        requirement_text=requirement_json,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    
    # Calculate display_id based on creation time order (ascending)
    # Query all non-deleted requirements for this usecase, ordered by created_at
    all_requirements = db.query(Requirement).filter(
        Requirement.usecase_id == usecase_id,
        Requirement.is_deleted == False,
    ).order_by(Requirement.created_at.asc()).all()
    
    # Assign display_id based on position in the ordered list (starting from 1)
    for idx, req in enumerate(all_requirements, start=1):
        req.display_id = idx
    
    db.commit()
    db.refresh(rec)
    
    # Get the display_id for the newly created requirement
    display_id = rec.display_id
    logger.info("requirements_service: persisted requirement id=%s display_id=%d", str(rec.id), display_id)
    return rec.id


