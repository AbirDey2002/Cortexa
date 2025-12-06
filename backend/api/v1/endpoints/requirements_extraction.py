import asyncio
import json
import logging
import time
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from uuid import UUID

from deps import get_db
from models.usecase.usecase import UsecaseMetadata
from services.requirements.requirements_service import (
    get_usecase_documents_markdown,
    extract_requirement_list,
    extract_requirement_details,
    persist_requirement,
)
from models.generator.requirement import Requirement
from db.session import get_db_context


router = APIRouter()

logger = logging.getLogger(__name__)

def _blue(text: str) -> str:
    try:
        return f"\033[34m{text}\033[0m"
    except Exception:
        return text


def _run_requirements_generation(usecase_id: UUID):
    logger.info("requirements_extraction: background generation started for usecase=%s", str(usecase_id))
    try:
        with get_db_context() as db:
            record = db.query(UsecaseMetadata).filter(
                UsecaseMetadata.usecase_id == usecase_id,
                UsecaseMetadata.is_deleted == False,
            ).first()
            if not record:
                logger.error("requirements_extraction: usecase not found %s", str(usecase_id))
                return
            record.requirement_generation = "In Progress"
            db.commit()

            files, combined_md = get_usecase_documents_markdown(db, usecase_id)
            req_list = extract_requirement_list(combined_md)
            total_requirements = len(req_list)
            logger.info(_blue(f"requirements_extraction: list count={total_requirements}"))

            inserted = 0
            prior: list[dict] = []
            for idx, item in enumerate(req_list, start=1):
                try:
                    name = str(item.get("name") or "").strip()
                    desc = str(item.get("description") or "").strip()
                    if not name:
                        logger.warning(_blue(f"requirements_extraction: skipping item {idx}/{total_requirements} - empty name"))
                        continue
                    
                    # Log polling status: starting requirement processing
                    logger.info(_blue(f"[REQ-STATUS] usecase={usecase_id} | Processing requirement {idx}/{total_requirements} | Name='{name}' | Status=STARTING"))
                    
                    details = extract_requirement_details(combined_md, name, desc, prior)
                    
                    # Log LLM requirement payload (blue) before storing
                    try:
                        import json as _json
                        _preview = _json.dumps(details)[:2000]
                        if len(_json.dumps(details)) > 2000:
                            _preview += "... [TRUNCATED]"
                        logger.info(_blue(f"[REQ-LLM] usecase={usecase_id} name='{name}' payload={_preview}"))
                    except Exception:
                        pass
                    
                    persist_requirement(db, usecase_id, {"name": name, "description": desc, "requirement_entities": details})
                    inserted += 1
                    prior.append({"name": name, "description": desc})
                    
                    # Log polling status: requirement completed
                    progress_pct = int((idx / total_requirements) * 100) if total_requirements > 0 else 0
                    logger.info(_blue(f"[REQ-STATUS] usecase={usecase_id} | Completed requirement {idx}/{total_requirements} ({progress_pct}%) | Name='{name}' | Status=COMPLETED | Total inserted={inserted}"))
                    
                    # Log overall progress summary
                    if idx < total_requirements:
                        remaining = total_requirements - idx
                        next_name = req_list[idx].get('name', 'N/A') if idx < len(req_list) else 'N/A'
                        logger.info(_blue(f"[REQ-PROGRESS] usecase={usecase_id} | Progress: {idx}/{total_requirements} completed ({progress_pct}%) | {remaining} remaining | Next: '{next_name}'"))
                    
                    time.sleep(60)
                except Exception as e:
                    # Log polling status: requirement failed
                    logger.error(_blue(f"[REQ-STATUS] usecase={usecase_id} | Failed requirement {idx}/{total_requirements} | Name='{name if 'name' in locals() else 'N/A'}' | Status=FAILED | Error: {e}"), exc_info=True)
                    continue

            record = db.query(UsecaseMetadata).filter(UsecaseMetadata.usecase_id == usecase_id).first()
            record.requirement_generation = "Completed" if inserted > 0 else "Failed"
            db.commit()
            
            # Final summary log
            success_rate = int((inserted / total_requirements) * 100) if total_requirements > 0 else 0
            logger.info(_blue(f"[REQ-SUMMARY] usecase={usecase_id} | FINAL STATUS: {record.requirement_generation} | Total requirements: {total_requirements} | Successfully inserted: {inserted} | Failed: {total_requirements - inserted} | Success rate: {success_rate}%"))
            logger.info(_blue(f"requirements_extraction: finished status={record.requirement_generation} inserted={inserted}"))
    except Exception as e:
        logger.error("requirements_extraction: background generation error: %s", e, exc_info=True)
    finally:
        # Fail-safe: ensure status is not left hanging in 'In Progress'
        try:
            with get_db_context() as db:
                record = db.query(UsecaseMetadata).filter(
                    UsecaseMetadata.usecase_id == usecase_id,
                    UsecaseMetadata.is_deleted == False,
                ).first()
                if record:
                    # If requirements exist and status still not Completed/Failed, mark Completed
                    total_inserted = db.query(Requirement).filter(
                        Requirement.usecase_id == usecase_id,
                        Requirement.is_deleted == False,
                    ).count()
                    current = (record.requirement_generation or "").strip()
                    if total_inserted > 0 and current not in ("Completed", "Failed"):
                        record.requirement_generation = "Completed"
                        db.commit()
                        logger.info(_blue(f"[REQ-GEN FAIL-SAFE] set status=Completed usecase={usecase_id} total_inserted={total_inserted}"))
        except Exception:
            pass


@router.post("/{usecase_id}/generate")
def generate_requirements(usecase_id: UUID, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    try:
        record = db.query(UsecaseMetadata).filter(
            UsecaseMetadata.usecase_id == usecase_id,
            UsecaseMetadata.is_deleted == False,
        ).first()
        if not record:
            raise HTTPException(status_code=404, detail="Usecase not found")
        # Mark consent and schedule background task; set status if currently Not Started/Failed
        if record.requirement_generation in (None, "Not Started", "Failed"):
            record.requirement_generation = "In Progress"
        # Persist one-time consent
        try:
            # If column exists, set True; if not, ignore (for pre-migration runs)
            setattr(record, "requirement_generation_confirmed", True)
        except Exception:
            pass
        db.commit()
        background_tasks.add_task(_run_requirements_generation, usecase_id)
        logger.info("requirements_extraction: background task scheduled for %s", str(usecase_id))
        return {"status": "started", "usecase_id": str(usecase_id)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("generate_requirements error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error starting requirement generation")


@router.get("/{usecase_id}/list")
def list_requirements(usecase_id: UUID, db: Session = Depends(get_db)):
    """
    Get all requirements for a usecase.
    Returns requirements in a format suitable for frontend display.
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
        ).order_by(Requirement.created_at.asc()).all()

        # Transform requirement_text JSON to match frontend expected format
        requirements_list = []
        for req in requirements:
            req_text = req.requirement_text or {}
            requirements_list.append({
                "id": str(req.id),
                "display_id": req.display_id,
                "name": req_text.get("name", ""),
                "description": req_text.get("description", ""),
                "requirement_entities": req_text.get("requirement_entities", {}),
                "created_at": req.created_at.isoformat() if req.created_at else None,
            })

        payload = {
            "requirements": requirements_list,
            "count": len(requirements_list),
        }
        logger.info(_blue(f"list_requirements: usecase={usecase_id} count={len(requirements_list)}"))
        return payload
    except HTTPException:
        raise
    except Exception as e:
        logger.error("list_requirements error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error getting requirements list")


@router.get("/{usecase_id}/read/{display_id}")
def read_requirement(usecase_id: UUID, display_id: int, db: Session = Depends(get_db)):
    """
    Read a specific requirement by display_id for agent analysis.
    Returns requirement_json as formatted text (similar to OCR combined_markdown).
    """
    try:
        # Verify usecase exists
        record = db.query(UsecaseMetadata).filter(
            UsecaseMetadata.usecase_id == usecase_id,
            UsecaseMetadata.is_deleted == False,
        ).first()
        if not record:
            raise HTTPException(status_code=404, detail="Usecase not found")

        # Find requirement by usecase_id and display_id
        requirement = db.query(Requirement).filter(
            Requirement.usecase_id == usecase_id,
            Requirement.display_id == display_id,
            Requirement.is_deleted == False,
        ).first()

        if not requirement:
            raise HTTPException(
                status_code=404, 
                detail=f"Requirement with display_id {display_id} not found for this usecase"
            )

        # Get requirement_text JSON
        req_text = requirement.requirement_text or {}
        
        # Format as readable text (similar to OCR combined_markdown format)
        # Convert JSON to structured markdown-like text
        formatted_text_parts = []
        
        # Add requirement name
        name = req_text.get("name", "")
        if name:
            formatted_text_parts.append(f"## Requirement: {name}\n")
        
        # Add description
        description = req_text.get("description", "")
        if description:
            formatted_text_parts.append(f"### Description\n{description}\n")
        
        # Add requirement_entities
        req_entities = req_text.get("requirement_entities", {})
        if req_entities:
            formatted_text_parts.append("### Requirement Entities\n")
            # Handle both list and dict structures
            if isinstance(req_entities, list):
                # If it's a list, iterate through each entity object
                for entity_obj in req_entities:
                    if isinstance(entity_obj, dict):
                        # Process each key in the entity object
                        for entity_type, entity_data in entity_obj.items():
                            formatted_text_parts.append(f"#### {entity_type.replace('_', ' ').title()}\n")
                            if isinstance(entity_data, list):
                                for item in entity_data:
                                    if isinstance(item, str):
                                        formatted_text_parts.append(f"- {item}\n")
                                    else:
                                        formatted_text_parts.append(f"- {json.dumps(item, indent=2)}\n")
                            elif isinstance(entity_data, dict):
                                formatted_text_parts.append(f"{json.dumps(entity_data, indent=2)}\n")
                            else:
                                formatted_text_parts.append(f"{str(entity_data)}\n")
                    else:
                        # If list item is not a dict, just stringify it
                        formatted_text_parts.append(f"- {str(entity_obj)}\n")
            elif isinstance(req_entities, dict):
                # Original dict handling
                for entity_type, entity_data in req_entities.items():
                    formatted_text_parts.append(f"#### {entity_type.replace('_', ' ').title()}\n")
                    if isinstance(entity_data, list):
                        for item in entity_data:
                            if isinstance(item, str):
                                formatted_text_parts.append(f"- {item}\n")
                            else:
                                formatted_text_parts.append(f"- {json.dumps(item, indent=2)}\n")
                    elif isinstance(entity_data, dict):
                        formatted_text_parts.append(f"{json.dumps(entity_data, indent=2)}\n")
                    else:
                        formatted_text_parts.append(f"{str(entity_data)}\n")
        
        # Combine all parts
        formatted_text = "\n".join(formatted_text_parts)
        
        total_chars = len(formatted_text)
        
        logger.info(_blue(
            f"read_requirement: usecase={usecase_id} display_id={display_id} "
            f"requirement_id={requirement.id} total_chars={total_chars}"
        ))
        
        return {
            "usecase_id": str(usecase_id),
            "display_id": display_id,
            "requirement_id": str(requirement.id),
            "requirement_text": formatted_text,
            "requirement_json": req_text,  # Also include raw JSON for reference
            "total_chars": total_chars,
            "message": f"Retrieved requirement REQ-{display_id}: {name} ({total_chars} characters)."
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("read_requirement error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error reading requirement")


@router.get("/{usecase_id}/status")
def requirements_status(usecase_id: UUID, db: Session = Depends(get_db)):
    try:
        record = db.query(UsecaseMetadata).filter(
            UsecaseMetadata.usecase_id == usecase_id,
            UsecaseMetadata.is_deleted == False,
        ).first()
        if not record:
            raise HTTPException(status_code=404, detail="Usecase not found")

        # Count inserted requirements
        count = db.query(Requirement).filter(
            Requirement.usecase_id == usecase_id,
            Requirement.is_deleted == False,
        ).count()

        # Normalize status strictly to canonical values
        raw_status = (record.requirement_generation or "Not Started").strip().lower()
        canonical_map = {
            "not started": "Not Started",
            "in progress": "In Progress",
            "completed": "Completed",
            "failed": "Failed",
        }
        norm_status = canonical_map.get(raw_status, "Not Started")

        payload = {
            "usecase_id": str(usecase_id),
            "requirement_generation": norm_status,
            "total_inserted": count,
            # expose consent flag if available (optional)
            "requirement_generation_confirmed": getattr(record, "requirement_generation_confirmed", False),
        }
        logger.info(_blue(f"requirements_status: usecase={usecase_id} status={norm_status} total_inserted={count}"))
        return payload
    except HTTPException:
        raise
    except Exception as e:
        logger.error("requirements_status error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error getting requirement status")


