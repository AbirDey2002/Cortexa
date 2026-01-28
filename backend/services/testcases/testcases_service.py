import logging
import json
from typing import List, Dict
from uuid import UUID

from sqlalchemy.orm import Session

from models.generator.scenario import Scenario
from models.generator.requirement import Requirement
from models.generator.test_case import TestCase
from models.file_processing.ocr_records import OCROutputs
from models.file_processing.file_metadata import FileMetadata
from services.llm.gemini_conversational.gemini_invoker import invoke_freeform_prompt, get_user_gemini_key
from core.config import AgentLogConfigs
import os
import importlib
from datetime import datetime
from core.env_config import get_env_variable


logger = logging.getLogger(__name__)


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
                return []
        return []


def _yellow(text: str) -> str:
    try:
        return f"\033[33m{text}\033[0m"
    except Exception:
        return text


def _blue(text: str) -> str:
    try:
        return f"\033[34m{text}\033[0m"
    except Exception:
        return text


def get_usecase_documents_markdown(db: Session, usecase_id: UUID) -> str:
    """Get combined markdown from all documents in usecase."""
    files = db.query(FileMetadata).filter(
        FileMetadata.usecase_id == usecase_id,
        FileMetadata.is_deleted == False,
    ).order_by(FileMetadata.created_at.asc()).all()
    
    combined_parts: List[str] = []
    for f in files:
        outputs = db.query(OCROutputs).filter(
            OCROutputs.file_id == f.file_id,
            OCROutputs.is_deleted == False,
        ).order_by(OCROutputs.page_number.asc()).all()
        md = "\n".join([(o.page_text or "") for o in outputs])
        if md.strip():
            combined_parts.append(f"## {f.file_name}\n\n{md}\n")
    
    combined_markdown = "\n".join(combined_parts).strip()
    logger.info("testcases_service: combined_markdown chars=%d", len(combined_markdown))
    return combined_markdown


def extract_test_cases_from_scenario(
    scenario_json: Dict, 
    requirement_json: Dict,
    extracted_text: str,
    user_id: UUID = None,
    model_name: str = "gemini-2.5-flash"
) -> List[Dict]:
    """
    Extract test cases from a scenario JSON using the test case generator prompt.
    
    Args:
        scenario_json: The scenario JSON containing ScenarioID, ScenarioName, Flows, etc.
        requirement_json: The requirement JSON for context
        extracted_text: The original extracted text from documents
        user_id: User UUID to fetch API key from database
        model_name: Model name to use
    
    Returns:
        List of test case dictionaries
    """
    # Get user's API key from database
    api_key = None
    if user_id:
        api_key = get_user_gemini_key(user_id)
        if not api_key:
            logger.error("testcases_service: No API key found for user %s", user_id)
            return []
    
    # Load prompt from testcase_generator_prompt.py
    prompt_file = get_env_variable("TESTCASE_GENERATOR_PROMPT_FILE", "").strip()
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
        # Try module-based prompt
        base_prompt = ""
        try:
            mod_path = get_env_variable("TESTCASE_GENERATOR_PROMPT_MODULE", "").strip()
            attr_name = (get_env_variable("TESTCASE_GENERATOR_PROMPT_ATTR", "testcase_generator_prompt") or "testcase_generator_prompt").strip()
            if mod_path:
                mod = importlib.import_module(mod_path)
                val = getattr(mod, attr_name, None)
                if val is None:
                    val = getattr(mod, "__doc__", "") or ""
                base_prompt = str(val or "")
        except Exception:
            base_prompt = ""
        if not base_prompt:
            # Default to the prompt module path
            try:
                from services.llm.prompts.testcase_generator_prompt import __doc__ as prompt_doc
                base_prompt = prompt_doc or ""
            except Exception:
                base_prompt = get_env_variable("TESTCASE_GENERATOR_PROMPT", "")

    # Log the SYSTEM PROMPT
    if AgentLogConfigs.LOG_AGENT_SYSTEM_PROMPT:
        try:
            text = base_prompt or ""
            if len(text) > AgentLogConfigs.LOG_AGENT_SYSTEM_PROMPT_MAX_LENGTH:
                text = text[:AgentLogConfigs.LOG_AGENT_SYSTEM_PROMPT_MAX_LENGTH] + "... [TRUNCATED]"
            scen_name = scenario_json.get("ScenarioName", "Unknown")
            logger.info(_yellow("testcases_service: test case generator SYSTEM PROMPT (input) for '%s':\n%s"), scen_name, text)
        except Exception:
            pass

    # Format inputs for the prompt
    scenario_json_str = json.dumps(scenario_json, indent=2, ensure_ascii=False)
    requirement_json_str = json.dumps(requirement_json, indent=2, ensure_ascii=False)
    
    dynamic_parts = (
        f"\n\n### Test Scenario:\n{scenario_json_str}\n\n"
        f"### Requirement Context:\n{requirement_json_str}\n\n"
        f"### Supporting Context (Extracted Text):\n{extracted_text[:5000]}\n"  # Truncate to avoid token limits
    )
    prompt = base_prompt + dynamic_parts
    
    scen_name = scenario_json.get("ScenarioName", "Unknown")
    logger.info("testcases_service: invoking test case generator for scenario '%s', model=%s", scen_name, model_name)
    raw = invoke_freeform_prompt(prompt, model_name=model_name, api_key=api_key)
    
    # Log COMPLETE raw output from the agent before any parsing
    try:
        text = raw or ""
        if AgentLogConfigs.LOG_AGENT_RAW_OUTPUT:
            if len(text) > AgentLogConfigs.LOG_AGENT_RAW_OUTPUT_MAX_LENGTH:
                # Write complete output to file
                try:
                    base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs", "testcases")
                    os.makedirs(base, exist_ok=True)
                    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
                    # Sanitize name for filename
                    safe_name = "".join(c for c in scen_name if c.isalnum() or c in (' ', '-', '_')).strip()[:50]
                    output_file = os.path.join(base, f"{ts}-testcase-generator-{safe_name}-complete-output.txt")
                    with open(output_file, "w", encoding="utf-8") as f:
                        f.write(text)
                    logger.info(_yellow("testcases_service: test case generator COMPLETE output for '%s' (too long for console, written to file): %s (length=%d)"), scen_name, output_file, len(text))
                    # Also log a preview in console
                    preview = text[:AgentLogConfigs.LOG_AGENT_RAW_OUTPUT_MAX_LENGTH] + "... [TRUNCATED - see file for complete output]"
                    logger.info(_yellow("testcases_service: test case generator RAW output (preview) for '%s':\n%s"), scen_name, preview)
                except Exception as e:
                    logger.warning("testcases_service: failed to write complete test case output to file for '%s': %s", scen_name, e)
                    # Fallback: log truncated version
                    preview = text[:AgentLogConfigs.LOG_AGENT_RAW_OUTPUT_MAX_LENGTH] + "... [TRUNCATED]"
                    logger.info(_yellow("testcases_service: test case generator RAW output (truncated) for '%s':\n%s"), scen_name, preview)
            else:
                logger.info(_yellow("testcases_service: test case generator RAW output (complete) for '%s':\n%s"), scen_name, text)
        else:
            # Even if LOG_AGENT_RAW_OUTPUT is disabled, write complete output to file for debugging
            try:
                base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs", "testcases")
                os.makedirs(base, exist_ok=True)
                ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
                # Sanitize name for filename
                safe_name = "".join(c for c in scen_name if c.isalnum() or c in (' ', '-', '_')).strip()[:50]
                output_file = os.path.join(base, f"{ts}-testcase-generator-{safe_name}-complete-output.txt")
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(text)
                logger.info("testcases_service: test case generator complete output for '%s' written to file: %s (length=%d)", scen_name, output_file, len(text))
            except Exception as e:
                logger.warning("testcases_service: failed to write complete test case output to file for '%s': %s", scen_name, e)
    except Exception:
        pass
    
    # Parse response
    parsed = _safe_parse_json(raw)
    
    # Normalize to list of test cases
    test_cases: List[Dict] = []
    if isinstance(parsed, list):
        test_cases = parsed
    elif isinstance(parsed, dict):
        if "test_cases" in parsed and isinstance(parsed["test_cases"], list):
            test_cases = parsed["test_cases"]
        else:
            # Single test case object
            test_cases = [parsed]
    
    logger.info("testcases_service: test case generator returned %d test cases for scenario '%s'", len(test_cases), scen_name)
    
    # Log COMPLETE parsed output
    try:
        import json as _json
        complete_output = _json.dumps(test_cases, indent=2, ensure_ascii=False)
        if len(complete_output) > AgentLogConfigs.LOG_AGENT_RAW_OUTPUT_MAX_LENGTH:
            # Write complete parsed output to file
            try:
                base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs", "testcases")
                os.makedirs(base, exist_ok=True)
                ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
                # Sanitize name for filename
                safe_name = "".join(c for c in scen_name if c.isalnum() or c in (' ', '-', '_')).strip()[:50]
                output_file = os.path.join(base, f"{ts}-testcase-generator-{safe_name}-parsed-complete.json")
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(complete_output)
                logger.info(_blue("testcases_service: test case generator COMPLETE parsed output for '%s' (written to file): %s (test_cases=%d, length=%d)"), scen_name, output_file, len(test_cases), len(complete_output))
                # Also log a preview in console
                preview = complete_output[:2000] + "... [TRUNCATED - see file for complete output]"
                logger.info(_blue("testcases_service: test cases parsed output (preview) for '%s':\n%s"), scen_name, preview)
            except Exception as e:
                logger.warning("testcases_service: failed to write complete parsed test case output to file for '%s': %s", scen_name, e)
                # Fallback: log truncated version
                preview = complete_output[:2000] + "... [TRUNCATED]"
                logger.info(_blue("testcases_service: test cases parsed output (truncated) for '%s':\n%s"), scen_name, preview)
        else:
            logger.info(_blue("testcases_service: test case generator COMPLETE parsed output for '%s':\n%s"), scen_name, complete_output)
    except Exception as e:
        logger.warning("testcases_service: failed to log complete parsed test case output for '%s': %s", scen_name, e)
        # Fallback: log preview
        try:
            import json as _json
            preview = _json.dumps(test_cases)[:2000]
            if len(_json.dumps(test_cases)) > 2000:
                preview += "... [TRUNCATED]"
            logger.info(_blue("testcases_service: test cases preview for '%s' -> %s"), scen_name, preview)
        except Exception:
            pass
    
    return test_cases


def persist_test_case(db: Session, scenario_id: UUID, test_case_json: Dict) -> UUID:
    """
    Persist a test case to database and assign display_id.
    
    Args:
        db: Database session
        scenario_id: The scenario ID this test case belongs to
        test_case_json: The test case JSON data
    
    Returns:
        The created test case ID
    """
    # Get usecase_id from scenario -> requirement to assign display_id per usecase
    scenario = db.query(Scenario).filter(Scenario.id == scenario_id).first()
    if not scenario:
        raise ValueError(f"Scenario with id {scenario_id} not found")
    
    requirement = db.query(Requirement).filter(Requirement.id == scenario.requirement_id).first()
    if not requirement:
        raise ValueError(f"Requirement not found for scenario {scenario_id}")
    
    usecase_id = requirement.usecase_id
    
    # Create test case first
    rec = TestCase(
        scenario_id=scenario_id,
        test_case_text=json.dumps(test_case_json, ensure_ascii=False),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    
    # Calculate display_id based on creation time order (ascending)
    # Query all non-deleted test cases for this usecase, ordered by created_at
    # Join with scenarios and requirements to get usecase_id
    all_test_cases = db.query(TestCase).join(Scenario).join(Requirement).filter(
        Requirement.usecase_id == usecase_id,
        TestCase.is_deleted == False,
        Scenario.is_deleted == False,
        Requirement.is_deleted == False,
    ).order_by(TestCase.created_at.asc()).all()
    
    # Assign display_id based on position in the ordered list (starting from 1)
    for idx, tc in enumerate(all_test_cases, start=1):
        tc.display_id = idx
    
    db.commit()
    db.refresh(rec)
    
    # Get the display_id for the newly created test case
    display_id = rec.display_id
    logger.info("testcases_service: persisted test case id=%s display_id=%d scenario_id=%s", str(rec.id), display_id, str(scenario_id))
    return rec.id

