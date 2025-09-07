from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import uuid

from deps import get_db
from services.generator.generator_service import run_generator_workflow
from models.usecase.usecase import UsecaseMetadata


router = APIRouter()


@router.post("/run/{usecase_id}")
def run_generator(usecase_id: uuid.UUID, db: Session = Depends(get_db)):
    usecase = db.query(UsecaseMetadata).filter(UsecaseMetadata.usecase_id == usecase_id, UsecaseMetadata.is_deleted == False).first()
    if not usecase:
        raise HTTPException(status_code=404, detail="Usecase not found")
    result = run_generator_workflow(db, usecase_id)
    db.commit()
    return result


