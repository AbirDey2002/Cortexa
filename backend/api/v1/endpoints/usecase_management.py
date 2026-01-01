from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
import uuid
import logging
from datetime import datetime, timezone
import os
import asyncio
import hashlib

from deps import get_db
from db.session import get_db_context
from models.usecase.usecase import UsecaseMetadata
from models.user.user import User
from core.model_registry import is_valid_model, get_default_model
from core.auth import verify_token
from typing import Dict, Any
from services.llm.gemini_conversational.gemini_invoker import (
    invoke_gemini_chat_with_history_management,
)
from services.llm.gemini_conversational.json_output_parser import parse_llm_response

# Hardcoded email for authentication
DEFAULT_EMAIL = "abir.dey@intellectdesign.com"
# Security: Use environment variable for default password, with secure fallback
DEFAULT_PASSWORD = os.getenv("DEFAULT_USER_PASSWORD", "ChangeMe123!Please")

def hash_password(password: str) -> str:
    """Securely hash a password using SHA-256. In production, use bcrypt or similar."""
    return hashlib.sha256(password.encode()).hexdigest()


router = APIRouter()

# Create a separate router for frontend-specific endpoints
frontend_router = APIRouter()


class UpdateModelRequest(BaseModel):
    model: str


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
    selected_model: str | None = None

    class Config:
        from_attributes = True


@router.post("/", response_model=UsecaseResponse)
def create_usecase(
    payload: UsecaseCreate,
    token_payload: Dict[str, Any] = Depends(verify_token),
    db: Session = Depends(get_db)
):
    # Get or create user with hardcoded email
    user = db.query(User).filter(User.email == DEFAULT_EMAIL).first()
    if not user:
        # Create a new user if not exists
        user = User(
            email=DEFAULT_EMAIL,
            name="Abir Dey",
            password=hash_password(DEFAULT_PASSWORD)  # Now properly hashed
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
def update_usecase(
    usecase_id: uuid.UUID,
    payload: UsecaseUpdate,
    token_payload: Dict[str, Any] = Depends(verify_token),
    db: Session = Depends(get_db)
):
    record = db.query(UsecaseMetadata).filter(UsecaseMetadata.usecase_id == usecase_id, UsecaseMetadata.is_deleted == False).first()
    if not record:
        raise HTTPException(status_code=404, detail="Usecase not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(record, field, value)
    db.commit()
    db.refresh(record)
    return record


@router.get("/{usecase_id}/statuses")
def get_usecase_statuses(
    usecase_id: uuid.UUID,
    token_payload: Dict[str, Any] = Depends(verify_token),
    db: Session = Depends(get_db)
):
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
    files: list[dict] | None = None  # Optional file information


@router.get("/{usecase_id}/chat")
def get_chat_history(
    usecase_id: uuid.UUID,
    token_payload: Dict[str, Any] = Depends(verify_token),
    db: Session = Depends(get_db)
):
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
    """Extract user_answer string from agent output (robust JSON-first parsing)."""
    try:
        user_answer, tool_call, parsing_success = parse_llm_response(raw_output)
        return str(user_answer)[:10000]
    except Exception:
        try:
            import json, re
            text = raw_output.strip()
            fence_match = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
            if fence_match:
                text = fence_match.group(1)
            data = json.loads(text)
            if isinstance(data, dict) and "user_answer" in data:
                return str(data["user_answer"])[:10000]
        except Exception:
            pass
        return raw_output


def _check_for_tool_call(raw_output: str) -> tuple[bool, str, dict]:
    """
    Check if the agent output contains a tool call.
    
    Returns:
        tuple: (is_tool_call, tool_type, parsed_data)
    """
    try:
        import json, re
        text = raw_output.strip()
        # remove code fences if present
        fence_match = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
        if fence_match:
            text = fence_match.group(1)
        data = json.loads(text)
        if isinstance(data, dict) and "tool_call" in data:
            tool_type = data["tool_call"]
            return True, tool_type, data
    except Exception:
        pass
    return False, "", {}


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
            # Use Gemini as default with history management
            chat_history = record.chat_history or []
            chat_summary = getattr(record, "chat_summary", None)

            import asyncio
            response_text, cost, tokens, updated_history, updated_summary, summarized = asyncio.run(
                invoke_gemini_chat_with_history_management(
                    usecase_id=usecase_id,
                    query=user_message,
                    chat_history=chat_history,
                    chat_summary=chat_summary,
                    db=db,
                    timeout_seconds=timeout_seconds,
                )
            )

            # Parse and persist
            assistant_text = _parse_agent_output(response_text)
            system_entry = {"system": assistant_text, "timestamp": _utc_now_iso()}
            
            # Prepend response to updated history from Gemini manager if available
            history = updated_history if updated_history is not None else (record.chat_history or [])
            history = [system_entry] + history
            record.chat_history = history
            # Persist summary if updated
            if updated_summary is not None:
                record.chat_summary = updated_summary
            record.status = "Completed"
            logger.info("Completed chat inference for usecase_id=%s", usecase_id)
        except Exception as e:
            logger.exception("Chat inference failed for usecase_id=%s: %s", usecase_id, e)
            history = record.chat_history or []
            err_entry = {"system": f"Error: {e}", "timestamp": _utc_now_iso()}
            record.chat_history = [err_entry] + history
            record.status = "Completed"


@router.post("/{usecase_id}/chat")
async def append_chat_message(
    usecase_id: uuid.UUID,
    payload: ChatMessage,
    background_tasks: BackgroundTasks,
    token_payload: Dict[str, Any] = Depends(verify_token),
    db: Session = Depends(get_db)
):
    record = db.query(UsecaseMetadata).filter(UsecaseMetadata.usecase_id == usecase_id, UsecaseMetadata.is_deleted == False).first()
    if not record:
        raise HTTPException(status_code=404, detail="Usecase not found")
    # Prepend user message, set status to In Progress
    history = record.chat_history or []
    user_entry = {"user": payload.content, "timestamp": _utc_now_iso()}
    
    # Add file information if provided
    if payload.files:
        user_entry["files"] = payload.files
        
    history = [user_entry] + history
    record.chat_history = history
    record.status = "In Progress"
    db.commit()
    # Fire background inference
    background_tasks.add_task(_run_chat_inference_sync, usecase_id, payload.content)
    return {"status": "accepted", "usecase_id": str(usecase_id)}


@frontend_router.get("/list")
def list_usecases_simple(
    token_payload: Dict[str, Any] = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """A simplified endpoint that returns only basic usecase data without relationships."""
    try:
        # Get user by hardcoded email
        user = db.query(User).filter(User.email == DEFAULT_EMAIL).first()
        if not user:
            # Create a default user
            user = User(
                email=DEFAULT_EMAIL,
                name="Abir Dey",
                password=hash_password(DEFAULT_PASSWORD)  # Now properly hashed
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
def list_usecases(
    token_payload: Dict[str, Any] = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Original endpoint that now delegates to the simple endpoint."""
    return list_usecases_simple(db=db)


@router.get("/{usecase_id}", response_model=UsecaseResponse)
def get_usecase(
    usecase_id: uuid.UUID,
    token_payload: Dict[str, Any] = Depends(verify_token),
    db: Session = Depends(get_db)
):
    record = db.query(UsecaseMetadata).filter(UsecaseMetadata.usecase_id == usecase_id, UsecaseMetadata.is_deleted == False).first()
    if not record:
        raise HTTPException(status_code=404, detail="Usecase not found")
    return record


@frontend_router.post("/{usecase_id}/model")
def update_usecase_model_frontend(
    usecase_id: uuid.UUID,
    payload: UpdateModelRequest,
    token_payload: Dict[str, Any] = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """
    Update the selected model for a usecase (frontend endpoint).
    
    Args:
        usecase_id: The usecase identifier
        payload: Request body containing model ID
        
    Returns:
        Success message with updated model
    """
    # Validate model
    if not is_valid_model(payload.model):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid model '{payload.model}'. Use /api/v1/models to see available models."
        )
    
    # Get usecase
    record = db.query(UsecaseMetadata).filter(
        UsecaseMetadata.usecase_id == usecase_id,
        UsecaseMetadata.is_deleted == False
    ).first()
    
    if not record:
        raise HTTPException(status_code=404, detail="Usecase not found")
    
    # Update model
    record.selected_model = payload.model
    db.commit()
    
    return {
        "usecase_id": str(usecase_id),
        "selected_model": payload.model,
        "message": "Model updated successfully"
    }

