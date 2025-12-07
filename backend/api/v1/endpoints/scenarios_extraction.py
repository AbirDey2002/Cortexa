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
            logger.info(_blue(f"scenarios_extraction: using model={selected_model} for usecase={usecase_id}"))

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
                    scenarios = extract_scenarios_from_requirement(req_text, model_name=selected_model)
                    
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
def generate_scenarios(usecase_id: UUID, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
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
def scenarios_status(usecase_id: UUID, db: Session = Depends(get_db)):
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
def list_scenarios(usecase_id: UUID, db: Session = Depends(get_db)):
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

