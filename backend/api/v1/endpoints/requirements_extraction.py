import asyncio
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
            logger.info("requirements_extraction: list count=%d", len(req_list))

            inserted = 0
            prior: list[dict] = []
            for item in req_list:
                try:
                    name = str(item.get("name") or "").strip()
                    desc = str(item.get("description") or "").strip()
                    if not name:
                        continue
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
                    logger.info(_blue(f"requirements_extraction: inserted requirement '{name}' (total={inserted})"))
                    time.sleep(60)
                except Exception as e:
                    logger.error("requirements_extraction: details failed for '%s': %s", item, e, exc_info=True)
                    continue

            record = db.query(UsecaseMetadata).filter(UsecaseMetadata.usecase_id == usecase_id).first()
            record.requirement_generation = "Completed" if inserted > 0 else "Failed"
            db.commit()
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


