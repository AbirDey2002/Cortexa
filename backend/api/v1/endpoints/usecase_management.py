from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
import uuid
import logging
from datetime import datetime, timezone
import os
import asyncio

from deps import get_db
from db.session import get_db_context
from models.usecase.usecase import UsecaseMetadata
from models.user.user import User
from services.llm.text2text_conversational.asset_invoker import (
    invoke_asset_with_proper_timeout,
)

# Hardcoded email for authentication
DEFAULT_EMAIL = "abir.dey@intellectdesign.com"


router = APIRouter()

# Create a separate router for frontend-specific endpoints
frontend_router = APIRouter()


@frontend_router.get("/{usecase_id}/chat")
def get_chat_history_frontend(usecase_id: uuid.UUID, db: Session = Depends(get_db)):
    """Frontend-specific endpoint to get chat history without ORM issues."""
    try:
        # Use raw SQL to avoid ORM issues
        from sqlalchemy import text
        query = text("""
            SELECT chat_history
            FROM usecase_metadata
            WHERE usecase_id = :usecase_id AND is_deleted = false
        """)
        
        result = db.execute(query, {"usecase_id": usecase_id}).fetchone()
        if not result:
            return []
            
        return result[0] or []
    except Exception as e:
        logging.error(f"Error in get_chat_history_frontend: {e}")
        return []


@frontend_router.get("/{usecase_id}/statuses")
def get_usecase_statuses_frontend(usecase_id: uuid.UUID, db: Session = Depends(get_db)):
    """Frontend-specific endpoint to get usecase statuses without ORM issues."""
    try:
        # Use raw SQL to avoid ORM issues
        from sqlalchemy import text
        query = text("""
            SELECT 
                text_extraction,
                requirement_generation,
                scenario_generation,
                test_case_generation,
                test_script_generation,
                status
            FROM usecase_metadata
            WHERE usecase_id = :usecase_id AND is_deleted = false
        """)
        
        result = db.execute(query, {"usecase_id": usecase_id}).fetchone()
        if not result:
            return {
                "text_extraction": "Not Started",
                "requirement_generation": "Not Started",
                "scenario_generation": "Not Started",
                "test_case_generation": "Not Started",
                "test_script_generation": "Not Started",
                "status": "Completed",
            }
            
        return {
            "text_extraction": result.text_extraction,
            "requirement_generation": result.requirement_generation,
            "scenario_generation": result.scenario_generation,
            "test_case_generation": result.test_case_generation,
            "test_script_generation": result.test_script_generation,
            "status": result.status,
        }
    except Exception as e:
        logging.error(f"Error in get_usecase_statuses_frontend: {e}")
        return {
            "text_extraction": "Not Started",
            "requirement_generation": "Not Started",
            "scenario_generation": "Not Started",
            "test_case_generation": "Not Started",
            "test_script_generation": "Not Started",
            "status": "Completed",
        }


class UsecaseCreate(BaseModel):
    user_id: uuid.UUID
    usecase_name: str = "New Chat"
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
    chat_history: list[dict] | None
    text_extraction: str
    requirement_generation: str
    scenario_generation: str
    test_case_generation: str
    test_script_generation: str
    email: str
    status: str

    class Config:
        from_attributes = True


@router.post("/", response_model=UsecaseResponse)
def create_usecase(payload: UsecaseCreate, db: Session = Depends(get_db)):
    # Get or create user with hardcoded email
    user = db.query(User).filter(User.email == DEFAULT_EMAIL).first()
    if not user:
        # Create a new user if not exists
        user = User(
            email=DEFAULT_EMAIL,
            name="Abir Dey",
            password="password"  # In a real app, this would be hashed
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    
    record = UsecaseMetadata(
        user_id=user.id,
        usecase_name=payload.usecase_name,
        email=DEFAULT_EMAIL,
        chat_history=[],
        status="Completed",
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
    try:
        # Use raw SQL to avoid ORM issues
        from sqlalchemy import text
        query = text("""
            SELECT 
                text_extraction,
                requirement_generation,
                scenario_generation,
                test_case_generation,
                test_script_generation,
                status
            FROM usecase_metadata
            WHERE usecase_id = :usecase_id AND is_deleted = false
        """)
        
        result = db.execute(query, {"usecase_id": usecase_id}).fetchone()
        if not result:
            return {
                "text_extraction": "Not Started",
                "requirement_generation": "Not Started",
                "scenario_generation": "Not Started",
                "test_case_generation": "Not Started",
                "test_script_generation": "Not Started",
                "status": "Completed",
            }
            
        return {
            "text_extraction": result.text_extraction,
            "requirement_generation": result.requirement_generation,
            "scenario_generation": result.scenario_generation,
            "test_case_generation": result.test_case_generation,
            "test_script_generation": result.test_script_generation,
            "status": result.status,
        }
    except Exception as e:
        logging.error(f"Error in get_usecase_statuses: {e}")
        return {
            "text_extraction": "Not Started",
            "requirement_generation": "Not Started",
            "scenario_generation": "Not Started",
            "test_case_generation": "Not Started",
            "test_script_generation": "Not Started",
            "status": "Completed",
        }


class ChatMessage(BaseModel):
    role: str
    content: str


@router.get("/{usecase_id}/chat")
def get_chat_history(usecase_id: uuid.UUID, db: Session = Depends(get_db)):
    try:
        # Use raw SQL to avoid ORM issues
        from sqlalchemy import text
        query = text("""
            SELECT chat_history
            FROM usecase_metadata
            WHERE usecase_id = :usecase_id AND is_deleted = false
        """)
        
        result = db.execute(query, {"usecase_id": usecase_id}).fetchone()
        if not result:
            return []
            
        return result[0] or []
    except Exception as e:
        logging.error(f"Error in get_chat_history: {e}")
        return []


def _parse_agent_output(raw_output: str) -> str:
    """Extract user_answer string from PF agent output which may be wrapped in ```json fences."""
    try:
        import json, re
        text = raw_output.strip()
        # remove code fences if present
        fence_match = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
        if fence_match:
            text = fence_match.group(1)
        data = json.loads(text)
        if isinstance(data, dict) and "user_answer" in data:
            return str(data["user_answer"])[:10000]
    except Exception:
        pass
    return raw_output


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_chat_inference_sync(usecase_id: uuid.UUID, user_message: str, timeout_seconds: int = 300):
    logger = logging.getLogger(__name__)
    logger.info("Starting chat inference for usecase_id=%s", usecase_id)
    with get_db_context() as db:
        record = db.query(UsecaseMetadata).filter(UsecaseMetadata.usecase_id == usecase_id, UsecaseMetadata.is_deleted == False).first()
        if not record:
            logger.error("Usecase not found for inference: %s", usecase_id)
            return
        try:
            asset_id = os.getenv("PF_CONVERSATION_ASSET_ID", "5df1fa69-6218-4482-a92b-bc1c2c168e3e")
            response_text, cost, tokens = invoke_asset_with_proper_timeout(asset_id_param=asset_id, query=user_message, timeout_seconds=timeout_seconds)
            assistant_text = _parse_agent_output(response_text)
            history = record.chat_history or []
            system_entry = {"system": assistant_text, "timestamp": _utc_now_iso()}
            history = [system_entry] + history
            record.chat_history = history
            record.status = "Completed"
            logger.info("Completed chat inference for usecase_id=%s", usecase_id)
        except Exception as e:
            logger.exception("Chat inference failed for usecase_id=%s: %s", usecase_id, e)
            history = record.chat_history or []
            err_entry = {"system": f"Error: {e}", "timestamp": _utc_now_iso()}
            record.chat_history = [err_entry] + history
            record.status = "Completed"


@router.post("/{usecase_id}/chat")
async def append_chat_message(usecase_id: uuid.UUID, payload: ChatMessage, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    record = db.query(UsecaseMetadata).filter(UsecaseMetadata.usecase_id == usecase_id, UsecaseMetadata.is_deleted == False).first()
    if not record:
        raise HTTPException(status_code=404, detail="Usecase not found")
    # Prepend user message, set status to In Progress
    history = record.chat_history or []
    user_entry = {"user": payload.content, "timestamp": _utc_now_iso()}
    history = [user_entry] + history
    record.chat_history = history
    record.status = "In Progress"
    db.commit()
    # Fire background inference
    background_tasks.add_task(_run_chat_inference_sync, usecase_id, payload.content)
    return {"status": "accepted", "usecase_id": str(usecase_id)}


@frontend_router.get("/list")
def list_usecases_simple(db: Session = Depends(get_db)):
    """A simplified endpoint that returns only basic usecase data without relationships."""
    try:
        # Get user by hardcoded email
        user = db.query(User).filter(User.email == DEFAULT_EMAIL).first()
        if not user:
            # Create a default user
            user = User(
                email=DEFAULT_EMAIL,
                name="Abir Dey",
                password="password"  # In a real app, this would be hashed
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            return []
        
        # Use raw SQL query to avoid ORM issues
        from sqlalchemy import text
        query = text("""
            SELECT 
                usecase_id, 
                user_id, 
                usecase_name, 
                status, 
                updated_at, 
                created_at 
            FROM 
                usecase_metadata 
            WHERE 
                is_deleted = false 
                AND user_id = :user_id
            ORDER BY updated_at DESC
        """)
        
        result = db.execute(query, {"user_id": user.id}).fetchall()
        
        # Process results
        return [
            {
                "usecase_id": str(r.usecase_id),
                "user_id": str(r.user_id),
                "usecase_name": r.usecase_name,
                "status": r.status,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in result
        ]
    except Exception as e:
        logging.error(f"Error in list_usecases: {e}")
        return []


@router.get("/")
def list_usecases(db: Session = Depends(get_db)):
    """Original endpoint that now delegates to the simple endpoint."""
    return list_usecases_simple(db=db)


@router.get("/{usecase_id}", response_model=UsecaseResponse)
def get_usecase(usecase_id: uuid.UUID, db: Session = Depends(get_db)):
    record = db.query(UsecaseMetadata).filter(UsecaseMetadata.usecase_id == usecase_id, UsecaseMetadata.is_deleted == False).first()
    if not record:
        raise HTTPException(status_code=404, detail="Usecase not found")
    return record


