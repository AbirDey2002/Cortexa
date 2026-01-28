import json
import logging
import time
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from uuid import UUID

from deps import get_db
from models.usecase.usecase import UsecaseMetadata
from services.scenarios.scenarios_service import (
    extract_scenarios_from_requirement,
    persist_scenario,
)
from models.generator.requirement import Requirement
from models.generator.scenario import Scenario
from db.session import get_db_context
from core.auth import verify_token
from typing import Dict, Any


router = APIRouter()

logger = logging.getLogger(__name__)

def _blue(text: str) -> str:
    try:
        return f"\033[34m{text}\033[0m"
    except Exception:
        return text


def _run_scenarios_generation(usecase_id: UUID):
    logger.info("scenarios_extraction: background generation started for usecase=%s", str(usecase_id))
    try:
        with get_db_context() as db:
            record = db.query(UsecaseMetadata).filter(
                UsecaseMetadata.usecase_id == usecase_id,
                UsecaseMetadata.is_deleted == False,
            ).first()
            if not record:
                logger.error("scenarios_extraction: usecase not found %s", str(usecase_id))
                return
            
            # Check requirement_generation status
            req_gen_status = record.requirement_generation or "Not Started"
            if req_gen_status != "Completed":
                logger.error("scenarios_extraction: requirement_generation not completed for usecase=%s status=%s", str(usecase_id), req_gen_status)
                record.scenario_generation = "Failed"
                db.commit()
                return
            
            record.scenario_generation = "In Progress"
            db.commit()

            # Get the selected model from usecase, fallback to default
            from core.model_registry import get_default_model
            selected_model = record.selected_model or get_default_model()
            user_id = record.user_id
            logger.info(_blue(f"scenarios_extraction: using model={selected_model} for usecase={usecase_id}, user_id={user_id}"))

            # Fetch all requirements for usecase (ordered by display_id)
            requirements = db.query(Requirement).filter(
                Requirement.usecase_id == usecase_id,
                Requirement.is_deleted == False,
            ).order_by(Requirement.display_id.asc()).all()
            
            total_requirements = len(requirements)
            logger.info(_blue(f"scenarios_extraction: processing {total_requirements} requirements"))

            inserted = 0
            for idx, req in enumerate(requirements, start=1):
                try:
                    req_text = req.requirement_text or {}
                    req_name = req_text.get("name", f"Requirement {req.display_id}")
                    
                    # Log polling status: starting requirement processing
                    logger.info(_blue(f"[SCENARIO-STATUS] usecase={usecase_id} | Processing requirement {idx}/{total_requirements} | Name='{req_name}' | Status=STARTING"))
                    
                    # Extract scenarios from requirement
                    scenarios = extract_scenarios_from_requirement(req_text, user_id=user_id, model_name=selected_model)
                    
                    # Log LLM scenario payload (blue) before storing
                    try:
                        import json as _json
                        _preview = _json.dumps(scenarios)[:2000]
                        if len(_json.dumps(scenarios)) > 2000:
                            _preview += "... [TRUNCATED]"
                        logger.info(_blue(f"[SCENARIO-LLM] usecase={usecase_id} requirement='{req_name}' scenarios_count={len(scenarios)} payload={_preview}"))
                    except Exception:
                        pass
                    
                    # Persist each scenario
                    scenarios_inserted = 0
                    for scenario_json in scenarios:
                        try:
                            persist_scenario(db, req.id, scenario_json)
                            scenarios_inserted += 1
                            inserted += 1
                        except Exception as e:
                            logger.error(_blue(f"[SCENARIO-STATUS] usecase={usecase_id} | Failed to persist scenario for requirement '{req_name}' | Error: {e}"), exc_info=True)
                            # Rollback the failed transaction before continuing
                            try:
                                db.rollback()
                            except Exception:
                                pass
                            continue
                    
                    # Log polling status: requirement completed
                    progress_pct = int((idx / total_requirements) * 100) if total_requirements > 0 else 0
                    logger.info(_blue(f"[SCENARIO-STATUS] usecase={usecase_id} | Completed requirement {idx}/{total_requirements} ({progress_pct}%) | Name='{req_name}' | Scenarios inserted={scenarios_inserted} | Status=COMPLETED | Total scenarios inserted={inserted}"))
                    
                    # Log overall progress summary
                    if idx < total_requirements:
                        remaining = total_requirements - idx
                        next_req = requirements[idx] if idx < len(requirements) else None
                        next_name = (next_req.requirement_text or {}).get('name', 'N/A') if next_req else 'N/A'
                        logger.info(_blue(f"[SCENARIO-PROGRESS] usecase={usecase_id} | Progress: {idx}/{total_requirements} completed ({progress_pct}%) | {remaining} remaining | Next: '{next_name}'"))
                    
                    # Wait 60 seconds between requirements
                    if idx < total_requirements:
                        logger.info(_blue(f"[SCENARIO-STATUS] usecase={usecase_id} | Waiting 60 seconds before processing next requirement..."))
                        time.sleep(60)
                except Exception as e:
                    # Log polling status: requirement failed
                    req_name = (req.requirement_text or {}).get("name", f"Requirement {req.display_id}") if 'req' in locals() else 'N/A'
                    logger.error(_blue(f"[SCENARIO-STATUS] usecase={usecase_id} | Failed requirement {idx}/{total_requirements} | Name='{req_name}' | Status=FAILED | Error: {e}"), exc_info=True)
                    # Rollback on error to prevent database session issues
                    try:
                        db.rollback()
                    except Exception:
                        pass
                    continue

            record = db.query(UsecaseMetadata).filter(UsecaseMetadata.usecase_id == usecase_id).first()
            record.scenario_generation = "Completed" if inserted > 0 else "Failed"
            db.commit()
            
            # Final summary log
            success_rate = int((inserted / (total_requirements * 1.0)) * 100) if total_requirements > 0 else 0
            logger.info(_blue(f"[SCENARIO-SUMMARY] usecase={usecase_id} | FINAL STATUS: {record.scenario_generation} | Total requirements processed: {total_requirements} | Total scenarios inserted: {inserted} | Success rate: {success_rate}%"))
            logger.info(_blue(f"scenarios_extraction: finished status={record.scenario_generation} scenarios_inserted={inserted}"))
    except Exception as e:
        logger.error("scenarios_extraction: background generation error: %s", e, exc_info=True)
    finally:
        # Fail-safe: ensure status is not left hanging in 'In Progress'
        try:
            with get_db_context() as db:
                record = db.query(UsecaseMetadata).filter(
                    UsecaseMetadata.usecase_id == usecase_id,
                    UsecaseMetadata.is_deleted == False,
                ).first()
                if record:
                    # If scenarios exist and status still not Completed/Failed, mark Completed
                    total_inserted = db.query(Scenario).join(Requirement).filter(
                        Requirement.usecase_id == usecase_id,
                        Scenario.is_deleted == False,
                    ).count()
                    current = (record.scenario_generation or "").strip()
                    if total_inserted > 0 and current not in ("Completed", "Failed"):
                        record.scenario_generation = "Completed"
                        db.commit()
                        logger.info(_blue(f"[SCENARIO-GEN FAIL-SAFE] set status=Completed usecase={usecase_id} total_inserted={total_inserted}"))
        except Exception:
            pass


@router.post("/{usecase_id}/generate")
def generate_scenarios(
    usecase_id: UUID,
    background_tasks: BackgroundTasks,
    token_payload: Dict[str, Any] = Depends(verify_token),
    db: Session = Depends(get_db)
):
    try:
        record = db.query(UsecaseMetadata).filter(
            UsecaseMetadata.usecase_id == usecase_id,
            UsecaseMetadata.is_deleted == False,
        ).first()
        if not record:
            raise HTTPException(status_code=404, detail="Usecase not found")
        
        # Check requirement_generation status
        req_gen_status = record.requirement_generation or "Not Started"
        if req_gen_status != "Completed":
            raise HTTPException(
                status_code=400,
                detail=f"Requirement generation must be completed before generating scenarios. Current status: {req_gen_status}"
            )
        
        # Check scenario_generation status
        if record.scenario_generation == "In Progress":
            raise HTTPException(
                status_code=400,
                detail="Scenario generation is already in progress"
            )
        
        # Set status to In Progress and schedule background task
        if record.scenario_generation in (None, "Not Started", "Failed"):
            record.scenario_generation = "In Progress"
        db.commit()
        background_tasks.add_task(_run_scenarios_generation, usecase_id)
        logger.info("scenarios_extraction: background task scheduled for %s", str(usecase_id))
        return {"status": "started", "usecase_id": str(usecase_id)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("generate_scenarios error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error starting scenario generation")


@router.get("/{usecase_id}/status")
def scenarios_status(
    usecase_id: UUID,
    token_payload: Dict[str, Any] = Depends(verify_token),
    db: Session = Depends(get_db)
):
    try:
        record = db.query(UsecaseMetadata).filter(
            UsecaseMetadata.usecase_id == usecase_id,
            UsecaseMetadata.is_deleted == False,
        ).first()
        if not record:
            raise HTTPException(status_code=404, detail="Usecase not found")

        # Count inserted scenarios
        count = db.query(Scenario).join(Requirement).filter(
            Requirement.usecase_id == usecase_id,
            Scenario.is_deleted == False,
        ).count()

        # Normalize status strictly to canonical values
        raw_status = (record.scenario_generation or "Not Started").strip().lower()
        canonical_map = {
            "not started": "Not Started",
            "in progress": "In Progress",
            "completed": "Completed",
            "failed": "Failed",
        }
        norm_status = canonical_map.get(raw_status, "Not Started")

        payload = {
            "usecase_id": str(usecase_id),
            "scenario_generation": norm_status,
            "total_inserted": count,
        }
        logger.info(_blue(f"scenarios_status: usecase={usecase_id} status={norm_status} total_inserted={count}"))
        return payload
    except HTTPException:
        raise
    except Exception as e:
        logger.error("scenarios_status error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error getting scenario status")


@router.get("/{usecase_id}/list")
def list_scenarios(
    usecase_id: UUID,
    token_payload: Dict[str, Any] = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """
    Get all scenarios for a usecase.
    Returns scenarios grouped by requirement.
    """
    try:
        record = db.query(UsecaseMetadata).filter(
            UsecaseMetadata.usecase_id == usecase_id,
            UsecaseMetadata.is_deleted == False,
        ).first()
        if not record:
            raise HTTPException(status_code=404, detail="Usecase not found")

        # Query all non-deleted requirements for the usecase
        requirements = db.query(Requirement).filter(
            Requirement.usecase_id == usecase_id,
            Requirement.is_deleted == False,
        ).order_by(Requirement.display_id.asc()).all()

        # Build response with scenarios grouped by requirement
        requirements_list = []
        for req in requirements:
            req_text = req.requirement_text or {}
            scenarios = db.query(Scenario).filter(
                Scenario.requirement_id == req.id,
                Scenario.is_deleted == False,
            ).order_by(Scenario.display_id.asc()).all()
            
            scenarios_list = []
            for scen in scenarios:
                scen_text = scen.scenario_text or {}
                scenarios_list.append({
                    "id": str(scen.id),
                    "display_id": scen.display_id,
                    "scenario_text": scen_text,
                    "created_at": scen.created_at.isoformat() if scen.created_at else None,
                })
            
            requirements_list.append({
                "requirement_id": str(req.id),
                "requirement_display_id": req.display_id,
                "requirement_name": req_text.get("name", ""),
                "scenarios": scenarios_list,
                "scenario_count": len(scenarios_list),
            })

        payload = {
            "requirements": requirements_list,
            "total_scenarios": sum(r["scenario_count"] for r in requirements_list),
            "total_requirements": len(requirements_list),
        }
        logger.info(_blue(f"list_scenarios: usecase={usecase_id} requirements={len(requirements_list)} total_scenarios={payload['total_scenarios']}"))
        return payload
    except HTTPException:
        raise
    except Exception as e:
        logger.error("list_scenarios error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error getting scenarios list")


@router.get("/{usecase_id}/list-flat")
def list_scenarios_flat(
    usecase_id: UUID,
    token_payload: Dict[str, Any] = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """
    Get all scenarios for a usecase as a flat list.
    Returns scenarios in a format suitable for frontend display.
    Similar to list_requirements endpoint.
    """
    try:
        record = db.query(UsecaseMetadata).filter(
            UsecaseMetadata.usecase_id == usecase_id,
            UsecaseMetadata.is_deleted == False,
        ).first()
        if not record:
            raise HTTPException(status_code=404, detail="Usecase not found")

        # Query all non-deleted scenarios for the usecase (via Requirement join)
        scenarios = db.query(Scenario).join(Requirement).filter(
            Requirement.usecase_id == usecase_id,
            Scenario.is_deleted == False,
            Requirement.is_deleted == False,
        ).order_by(Scenario.display_id.asc()).all()

        # Transform scenario_text JSON to match frontend expected format
        scenarios_list = []
        for scen in scenarios:
            scen_text = scen.scenario_text or {}
            
            # Extract fields from scenario_text JSON
            scenario_name = scen_text.get("ScenarioName", f"Scenario {scen.display_id}")
            scenario_description = scen_text.get("ScenarioDescription", "")
            scenario_id = scen_text.get("ScenarioID", "")
            flows = scen_text.get("Flows", [])
            
            # Get requirement display_id
            requirement = db.query(Requirement).filter(Requirement.id == scen.requirement_id).first()
            requirement_display_id = requirement.display_id if requirement else None
            
            scenarios_list.append({
                "id": str(scen.id),
                "display_id": scen.display_id,
                "scenario_name": scenario_name,
                "scenario_description": scenario_description,
                "scenario_id": scenario_id,
                "requirement_id": str(scen.requirement_id),
                "requirement_display_id": requirement_display_id,
                "flows": flows,
                "created_at": scen.created_at.isoformat() if scen.created_at else None,
            })

        payload = {
            "scenarios": scenarios_list,
            "count": len(scenarios_list),
        }
        logger.info(_blue(f"list_scenarios_flat: usecase={usecase_id} count={len(scenarios_list)}"))
        return payload
    except HTTPException:
        raise
    except Exception as e:
        logger.error("list_scenarios_flat error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error getting scenarios list")


@router.get("/{usecase_id}/read/{display_id}")
def read_scenario(
    usecase_id: UUID,
    display_id: int,
    token_payload: Dict[str, Any] = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """
    Read a specific scenario by display_id for agent analysis.
    Returns scenario_text as formatted text (similar to OCR combined_markdown).
    """
    try:
        # Verify usecase exists
        record = db.query(UsecaseMetadata).filter(
            UsecaseMetadata.usecase_id == usecase_id,
            UsecaseMetadata.is_deleted == False,
        ).first()
        if not record:
            raise HTTPException(status_code=404, detail="Usecase not found")

        # Check scenario_generation status
        scenario_gen_status = record.scenario_generation or "Not Started"
        if scenario_gen_status not in ("In Progress", "Completed"):
            raise HTTPException(
                status_code=400,
                detail=f"Scenario generation is '{scenario_gen_status}'. Scenarios are not available yet."
            )

        # Find scenario by usecase_id (via Requirement join) and display_id
        scenario = db.query(Scenario).join(Requirement).filter(
            Requirement.usecase_id == usecase_id,
            Scenario.display_id == display_id,
            Scenario.is_deleted == False,
            Requirement.is_deleted == False,
        ).first()

        if not scenario:
            raise HTTPException(
                status_code=404, 
                detail=f"Scenario with display_id {display_id} not found for this usecase"
            )

        # Get scenario_text JSON
        scen_text = scenario.scenario_text or {}
        
        # Format as readable text (similar to OCR combined_markdown format)
        formatted_text_parts = []
        
        # Add scenario name
        name = scen_text.get("ScenarioName", "")
        if name:
            formatted_text_parts.append(f"## Scenario: {name}\n")
        
        # Add description
        description = scen_text.get("ScenarioDescription", "")
        if description:
            formatted_text_parts.append(f"### Description\n{description}\n")
        
        # Add scenario ID
        scenario_id = scen_text.get("ScenarioID", "")
        if scenario_id:
            formatted_text_parts.append(f"### Scenario ID\n{scenario_id}\n")
        
        # Add flows
        flows = scen_text.get("Flows", [])
        if flows:
            formatted_text_parts.append("### Flows\n")
            for idx, flow in enumerate(flows, start=1):
                formatted_text_parts.append(f"#### Flow {idx}\n")
                
                flow_type = flow.get("Type", "")
                if flow_type:
                    formatted_text_parts.append(f"**Type**: {flow_type}\n")
                
                flow_description = flow.get("Description", "")
                if flow_description:
                    formatted_text_parts.append(f"**Description**: {flow_description}\n")
                
                flow_coverage = flow.get("Coverage", "")
                if flow_coverage:
                    formatted_text_parts.append(f"**Coverage**: {flow_coverage}\n")
                
                flow_expected_results = flow.get("ExpectedResults", "")
                if flow_expected_results:
                    formatted_text_parts.append(f"**Expected Results**: {flow_expected_results}\n")
                
                formatted_text_parts.append("\n")
        
        # Combine all parts
        formatted_text = "\n".join(formatted_text_parts)
        
        total_chars = len(formatted_text)
        
        logger.info(_blue(
            f"read_scenario: usecase={usecase_id} display_id={display_id} "
            f"scenario_id={scenario.id} total_chars={total_chars}"
        ))
        
        return {
            "usecase_id": str(usecase_id),
            "display_id": display_id,
            "scenario_id": str(scenario.id),
            "scenario_text": formatted_text,
            "scenario_json": scen_text,  # Also include raw JSON for reference
            "total_chars": total_chars,
            "message": f"Retrieved scenario TS-{display_id}: {name} ({total_chars} characters)."
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("read_scenario error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error reading scenario")

