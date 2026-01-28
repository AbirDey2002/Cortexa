import logging
import json
from typing import List, Dict
from uuid import UUID

from sqlalchemy.orm import Session

from models.generator.scenario import Scenario
from models.generator.requirement import Requirement
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


def extract_scenarios_from_requirement(requirement_json: Dict, user_id: UUID = None, model_name: str = "gemini-2.5-flash") -> List[Dict]:
    """
    Extract scenarios from a requirement JSON using the scenario generator prompt.
    
    Args:
        requirement_json: The requirement JSON containing name, description, requirement_entities, etc.
        user_id: User UUID to fetch API key from database
        model_name: Model name to use
    
    Returns:
        List of scenario dictionaries
    """
    # Get user's API key from database
    api_key = None
    if user_id:
        api_key = get_user_gemini_key(user_id)
        if not api_key:
            logger.error("scenarios_service: No API key found for user %s", user_id)
            return []
    
    # Load prompt from scenario_generator_prompt.py (using environment variables like requirements)
    prompt_file = get_env_variable("SCENARIO_GENERATOR_PROMPT_FILE", "").strip()
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
            mod_path = get_env_variable("SCENARIO_GENERATOR_PROMPT_MODULE", "").strip()
            attr_name = (get_env_variable("SCENARIO_GENERATOR_PROMPT_ATTR", "scenario_generator_prompt") or "scenario_generator_prompt").strip()
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
                from services.llm.prompts.scenario_generator_prompt import __doc__ as prompt_doc
                base_prompt = prompt_doc or ""
            except Exception:
                base_prompt = get_env_variable("SCENARIO_GENERATOR_PROMPT", "")

    # Log the SYSTEM PROMPT (input) in yellow for debugging
    if AgentLogConfigs.LOG_AGENT_SYSTEM_PROMPT:
        try:
            text = base_prompt or ""
            if len(text) > AgentLogConfigs.LOG_AGENT_SYSTEM_PROMPT_MAX_LENGTH:
                text = text[:AgentLogConfigs.LOG_AGENT_SYSTEM_PROMPT_MAX_LENGTH] + "... [TRUNCATED]"
            req_name = requirement_json.get("name", "Unknown")
            logger.info(_yellow("scenarios_service: scenario generator SYSTEM PROMPT (input) for '%s':\n%s"), req_name, text)
        except Exception:
            pass

    # Format requirement JSON for the prompt
    requirement_json_str = json.dumps(requirement_json, indent=2, ensure_ascii=False)
    
    dynamic_parts = f"\n\n### Requirement Details:\n{requirement_json_str}"
    prompt = base_prompt + dynamic_parts
    
    req_name = requirement_json.get("name", "Unknown")
    logger.info("scenarios_service: invoking scenario generator for requirement '%s', model=%s", req_name, model_name)
    raw = invoke_freeform_prompt(prompt, model_name=model_name, api_key=api_key)
    
    # Log COMPLETE raw output from the agent before any parsing
    try:
        text = raw or ""
        if AgentLogConfigs.LOG_AGENT_RAW_OUTPUT:
            if len(text) > AgentLogConfigs.LOG_AGENT_RAW_OUTPUT_MAX_LENGTH:
                # Write complete output to file
                try:
                    base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs", "scenarios")
                    os.makedirs(base, exist_ok=True)
                    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
                    # Sanitize name for filename
                    safe_name = "".join(c for c in req_name if c.isalnum() or c in (' ', '-', '_')).strip()[:50]
                    output_file = os.path.join(base, f"{ts}-scenario-generator-{safe_name}-complete-output.txt")
                    with open(output_file, "w", encoding="utf-8") as f:
                        f.write(text)
                    logger.info(_yellow("scenarios_service: scenario generator COMPLETE output for '%s' (too long for console, written to file): %s (length=%d)"), req_name, output_file, len(text))
                    # Also log a preview in console
                    preview = text[:AgentLogConfigs.LOG_AGENT_RAW_OUTPUT_MAX_LENGTH] + "... [TRUNCATED - see file for complete output]"
                    logger.info(_yellow("scenarios_service: scenario generator RAW output (preview) for '%s':\n%s"), req_name, preview)
                except Exception as e:
                    logger.warning("scenarios_service: failed to write complete scenario output to file for '%s': %s", req_name, e)
                    # Fallback: log truncated version
                    preview = text[:AgentLogConfigs.LOG_AGENT_RAW_OUTPUT_MAX_LENGTH] + "... [TRUNCATED]"
                    logger.info(_yellow("scenarios_service: scenario generator RAW output (truncated) for '%s':\n%s"), req_name, preview)
            else:
                logger.info(_yellow("scenarios_service: scenario generator RAW output (complete) for '%s':\n%s"), req_name, text)
        else:
            # Even if LOG_AGENT_RAW_OUTPUT is disabled, write complete output to file for debugging
            try:
                base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs", "scenarios")
                os.makedirs(base, exist_ok=True)
                ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
                # Sanitize name for filename
                safe_name = "".join(c for c in req_name if c.isalnum() or c in (' ', '-', '_')).strip()[:50]
                output_file = os.path.join(base, f"{ts}-scenario-generator-{safe_name}-complete-output.txt")
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(text)
                logger.info("scenarios_service: scenario generator complete output for '%s' written to file: %s (length=%d)", req_name, output_file, len(text))
            except Exception as e:
                logger.warning("scenarios_service: failed to write complete scenario output to file for '%s': %s", req_name, e)
    except Exception:
        pass
    
    # Parse response
    parsed = _safe_parse_json(raw)
    
    # Normalize to list of scenarios
    scenarios: List[Dict] = []
    if isinstance(parsed, list):
        scenarios = parsed
    elif isinstance(parsed, dict):
        if "scenarios" in parsed and isinstance(parsed["scenarios"], list):
            scenarios = parsed["scenarios"]
        else:
            # Single scenario object
            scenarios = [parsed]
    
    logger.info("scenarios_service: scenario generator returned %d scenarios for requirement '%s'", len(scenarios), req_name)
    
    # Log COMPLETE parsed output
    try:
        import json as _json
        complete_output = _json.dumps(scenarios, indent=2, ensure_ascii=False)
        if len(complete_output) > AgentLogConfigs.LOG_AGENT_RAW_OUTPUT_MAX_LENGTH:
            # Write complete parsed output to file
            try:
                base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs", "scenarios")
                os.makedirs(base, exist_ok=True)
                ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
                # Sanitize name for filename
                safe_name = "".join(c for c in req_name if c.isalnum() or c in (' ', '-', '_')).strip()[:50]
                output_file = os.path.join(base, f"{ts}-scenario-generator-{safe_name}-parsed-complete.json")
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(complete_output)
                logger.info(_blue("scenarios_service: scenario generator COMPLETE parsed output for '%s' (written to file): %s (scenarios=%d, length=%d)"), req_name, output_file, len(scenarios), len(complete_output))
                # Also log a preview in console
                preview = complete_output[:2000] + "... [TRUNCATED - see file for complete output]"
                logger.info(_blue("scenarios_service: scenarios parsed output (preview) for '%s':\n%s"), req_name, preview)
            except Exception as e:
                logger.warning("scenarios_service: failed to write complete parsed scenario output to file for '%s': %s", req_name, e)
                # Fallback: log truncated version
                preview = complete_output[:2000] + "... [TRUNCATED]"
                logger.info(_blue("scenarios_service: scenarios parsed output (truncated) for '%s':\n%s"), req_name, preview)
        else:
            logger.info(_blue("scenarios_service: scenario generator COMPLETE parsed output for '%s':\n%s"), req_name, complete_output)
    except Exception as e:
        logger.warning("scenarios_service: failed to log complete parsed scenario output for '%s': %s", req_name, e)
        # Fallback: log preview
        try:
            import json as _json
            preview = _json.dumps(scenarios)[:2000]
            if len(_json.dumps(scenarios)) > 2000:
                preview += "... [TRUNCATED]"
            logger.info(_blue("scenarios_service: scenarios preview for '%s' -> %s"), req_name, preview)
        except Exception:
            pass
    
    return scenarios


def persist_scenario(db: Session, requirement_id: UUID, scenario_json: Dict) -> UUID:
    """
    Persist a scenario to the database and assign display_id.
    
    Args:
        db: Database session
        requirement_id: The requirement ID this scenario belongs to
        scenario_json: The scenario JSON data
    
    Returns:
        The created scenario ID
    """
    # Get usecase_id from requirement to assign display_id per usecase
    requirement = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not requirement:
        raise ValueError(f"Requirement with id {requirement_id} not found")
    
    usecase_id = requirement.usecase_id
    
    # Create scenario first
    rec = Scenario(
        requirement_id=requirement_id,
        scenario_text=scenario_json,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    
    # Calculate display_id based on creation time order (ascending)
    # Query all non-deleted scenarios for this usecase, ordered by created_at
    # Join with requirements to get usecase_id
    all_scenarios = db.query(Scenario).join(Requirement).filter(
        Requirement.usecase_id == usecase_id,
        Scenario.is_deleted == False,
    ).order_by(Scenario.created_at.asc()).all()
    
    # Assign display_id based on position in the ordered list (starting from 1)
    for idx, scen in enumerate(all_scenarios, start=1):
        scen.display_id = idx
    
    db.commit()
    db.refresh(rec)
    
    # Get the display_id for the newly created scenario
    display_id = rec.display_id
    logger.info("scenarios_service: persisted scenario id=%s display_id=%d requirement_id=%s", str(rec.id), display_id, str(requirement_id))
    return rec.id

