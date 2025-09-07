from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
import uuid

from deps import get_db
from models.usecase.usecase import UsecaseMetadata


router = APIRouter()


class UsecaseCreate(BaseModel):
    user_id: uuid.UUID
    usecase_name: str
    email: str


class UsecaseUpdate(BaseModel):
    usecase_name: str | None = None
    chat_history: dict | None = None
    text_extraction: str | None = None
    requirement_generation: str | None = None
    scenario_generation: str | None = None
    test_case_generation: str | None = None
    test_script_generation: str | None = None


class UsecaseResponse(BaseModel):
    usecase_id: uuid.UUID
    user_id: uuid.UUID
    usecase_name: str
    chat_history: dict | None
    text_extraction: str
    requirement_generation: str
    scenario_generation: str
    test_case_generation: str
    test_script_generation: str
    email: str

    class Config:
        from_attributes = True


@router.post("/", response_model=UsecaseResponse)
def create_usecase(payload: UsecaseCreate, db: Session = Depends(get_db)):
    record = UsecaseMetadata(
        user_id=payload.user_id,
        usecase_name=payload.usecase_name,
        email=payload.email,
        chat_history=[],
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.patch("/{usecase_id}", response_model=UsecaseResponse)
def update_usecase(usecase_id: uuid.UUID, payload: UsecaseUpdate, db: Session = Depends(get_db)):
    record = db.query(UsecaseMetadata).filter(UsecaseMetadata.usecase_id == usecase_id, UsecaseMetadata.is_deleted == False).first()
    if not record:
        raise HTTPException(status_code=404, detail="Usecase not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(record, field, value)
    db.commit()
    db.refresh(record)
    return record


@router.get("/{usecase_id}/statuses")
def get_usecase_statuses(usecase_id: uuid.UUID, db: Session = Depends(get_db)):
    record = db.query(UsecaseMetadata).filter(UsecaseMetadata.usecase_id == usecase_id, UsecaseMetadata.is_deleted == False).first()
    if not record:
        raise HTTPException(status_code=404, detail="Usecase not found")
    return {
        "text_extraction": record.text_extraction,
        "requirement_generation": record.requirement_generation,
        "scenario_generation": record.scenario_generation,
        "test_case_generation": record.test_case_generation,
        "test_script_generation": record.test_script_generation,
    }


class ChatMessage(BaseModel):
    role: str
    content: str


@router.get("/{usecase_id}/chat")
def get_chat_history(usecase_id: uuid.UUID, db: Session = Depends(get_db)):
    record = db.query(UsecaseMetadata).filter(UsecaseMetadata.usecase_id == usecase_id, UsecaseMetadata.is_deleted == False).first()
    if not record:
        raise HTTPException(status_code=404, detail="Usecase not found")
    return record.chat_history or []


@router.post("/{usecase_id}/chat")
def append_chat_message(usecase_id: uuid.UUID, payload: ChatMessage, db: Session = Depends(get_db)):
    record = db.query(UsecaseMetadata).filter(UsecaseMetadata.usecase_id == usecase_id, UsecaseMetadata.is_deleted == False).first()
    if not record:
        raise HTTPException(status_code=404, detail="Usecase not found")
    history = record.chat_history or []
    history.append(payload.model_dump())
    record.chat_history = history
    db.commit()
    return {"status": "ok", "messages": history}


