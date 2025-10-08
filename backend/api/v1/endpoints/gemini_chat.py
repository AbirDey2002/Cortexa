from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
import uuid
import logging
from datetime import datetime, timezone
import os
import hashlib

from deps import get_db
from db.session import get_db_context
from models.usecase.usecase import UsecaseMetadata
from models.user.user import User
from services.llm.gemini_conversational.gemini_invoker import (
    invoke_gemini_chat_with_timeout,
    invoke_gemini_chat_with_history_management,
    get_chat_history_statistics,
    check_summarization_needed
)
from services.llm.gemini_conversational.json_output_parser import parse_llm_response, create_enhanced_cortexa_prompt
from services.llm.gemini_conversational.history_manager import manage_chat_history_for_usecase
import google.generativeai as genai
from core.env_config import get_env_variable

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


class ChatMessage(BaseModel):
    role: str
    content: str
    files: list[dict] | None = None  # Optional file information


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

# In-memory streaming buffers for Gemini
gemini_streaming_responses: dict[str, str] = {}
gemini_response_chunks: dict[str, list[str]] = {}

GEMINI_API_KEY = get_env_variable("GEMINI_API_KEY", "")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

async def _generate_gemini_streaming_response(usecase_id: str, response_text: str):
    # Clear any previous chunks
    gemini_response_chunks[usecase_id] = []
    # Stream by words (UI compatibility with PF test stream)
    words = response_text.split()
    for i, word in enumerate(words):
        chunk = word + (" " if i < len(words) - 1 else "")
        if usecase_id in gemini_response_chunks:
            gemini_response_chunks[usecase_id].append(chunk)
        yield chunk

def _parse_gemini_output(raw_output: str) -> str:
    """Extract user_answer string from Gemini agent output using robust parsing."""
    try:
        user_answer, tool_call, parsing_success = parse_llm_response(raw_output)
        
        if not parsing_success:
            logger.warning(f"Used fallback parsing for Gemini output: {raw_output[:100]}...")
        
        return user_answer[:10000]  # Limit response length
        
    except Exception as e:
        logger.error(f"Error parsing Gemini output: {e}")
        # Fallback to original logic if LangChain parsing fails
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
        return raw_output[:10000]  # Return raw output as fallback


def _check_for_tool_call_gemini(raw_output: str) -> tuple[bool, str, dict]:
    """
    Check if the Gemini agent output contains a tool call.
    
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


def _run_gemini_chat_inference_sync(usecase_id: uuid.UUID, user_message: str, timeout_seconds: int = 300):
    """
    Enhanced Gemini chat inference with automatic history management and summarization.
    """
    logger = logging.getLogger(__name__)
    
    try:
        with get_db_context() as db:
            record = db.query(UsecaseMetadata).filter(
                UsecaseMetadata.usecase_id == usecase_id, 
                UsecaseMetadata.is_deleted == False
            ).first()
            
            if not record:
                logger.error(f"Usecase {usecase_id} not found")
                return
            
            logger.info(f"Starting enhanced Gemini chat inference for usecase_id={usecase_id}")
            
            # Get current chat history and summary
            chat_history = record.chat_history or []
            chat_summary = record.chat_summary
            
            logger.info(f"Current state - History messages: {len(chat_history)}, "
                       f"Has summary: {bool(chat_summary)}")
            
            # Use enhanced Gemini chat with history management (streaming)
            import asyncio
            try:
                # Prepare context and possibly summarize
                context, updated_history, updated_summary, summarized = asyncio.run(
                    manage_chat_history_for_usecase(
                        usecase_id=usecase_id,
                        chat_history=chat_history,
                        chat_summary=chat_summary,
                        user_query=user_message,
                        api_key=GEMINI_API_KEY,
                        db=db,
                        model_name="gemini-2.5-flash"
                    )
                )

                # Initialize model for streaming
                model = genai.GenerativeModel(
                    model_name="gemini-2.5-flash",
                    system_instruction=create_enhanced_cortexa_prompt()
                )

                # Log context sizes
                logger.info(
                    "Gemini streaming input (history msgs=%d, context chars=%d)",
                    len(updated_history or []), len(context)
                )

                # Start streaming
                assistant_text = ""
                gemini_streaming_responses[str(usecase_id)] = ""
                try:
                    stream = model.generate_content(context, stream=True)
                    for chunk in stream:
                        if hasattr(chunk, "text") and chunk.text:
                            assistant_text += chunk.text
                            gemini_streaming_responses[str(usecase_id)] = assistant_text
                except Exception:
                    # Fallback to non-streaming if streaming fails
                    resp = model.generate_content(context)
                    assistant_text = resp.text or ""
                    gemini_streaming_responses[str(usecase_id)] = assistant_text

                # Add system response to the updated chat history
                system_entry = {"system": assistant_text, "timestamp": _utc_now_iso()}
                updated_history = [system_entry] + (updated_history or [])

                # Update the record with new history and summary
                record.chat_history = updated_history
                record.chat_summary = updated_summary

                db.commit()

                logger.info(
                    "Database updated for usecase_id=%s. History messages: %d, Summary length: %d",
                    usecase_id,
                    len(updated_history),
                    len(updated_summary) if updated_summary else 0,
                )

            except Exception as e:
                logger.exception(f"Enhanced Gemini API call failed for usecase_id={usecase_id}: {e}")
                history = record.chat_history or []
                err_entry = {"system": f"Error: {e}", "timestamp": _utc_now_iso()}
                record.chat_history = [err_entry] + history
                db.commit()

            record.status = "Completed"
            logger.info("Completed enhanced Gemini chat inference for usecase_id=%s", usecase_id)
        
    except Exception as e:
        logger.exception("Enhanced Gemini chat inference failed for usecase_id=%s: %s", usecase_id, e)
        with get_db_context() as db:
            record = db.query(UsecaseMetadata).filter(
                UsecaseMetadata.usecase_id == usecase_id, 
                UsecaseMetadata.is_deleted == False
            ).first()
            if record:
                history = record.chat_history or []
                err_entry = {"system": f"Error: {e}", "timestamp": _utc_now_iso()}
                record.chat_history = [err_entry] + history
                record.status = "Completed"
                db.commit()


@router.post("/{usecase_id}/gemini-chat")
async def append_gemini_chat_message(usecase_id: uuid.UUID, payload: ChatMessage, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    New endpoint for Gemini-powered chat conversations.
    This runs alongside the existing PF-powered chat endpoint.
    """
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
    
    # Fire background inference with Gemini
    background_tasks.add_task(_run_gemini_chat_inference_sync, usecase_id, payload.content)
    return {"status": "accepted", "usecase_id": str(usecase_id), "provider": "gemini"}


@router.get("/{usecase_id}/gemini-chat")
def get_gemini_chat_history(usecase_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get chat history for Gemini conversations (same as regular chat history)."""
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
        logging.error(f"Error in get_gemini_chat_history: {e}")
        return []


@frontend_router.get("/{usecase_id}/gemini-chat")
def get_gemini_chat_history_frontend(usecase_id: uuid.UUID, db: Session = Depends(get_db)):
    """Frontend-specific endpoint to get Gemini chat history without ORM issues."""
    return get_gemini_chat_history(usecase_id, db)


@router.get("/{usecase_id}/gemini-chat/stream")
async def stream_gemini_chat(usecase_id: uuid.UUID):
    """Stream the latest Gemini response as it is generated."""
    uid = str(usecase_id)
    # If no response yet, stream empty generator until available
    text = gemini_streaming_responses.get(uid, "")
    return StreamingResponse(_generate_gemini_streaming_response(uid, text), media_type="text/plain")


# Health check endpoint for Gemini service
@router.get("/gemini/health")
def gemini_health_check():
    """Check if Gemini service is properly configured."""
    from core.env_config import get_env_variable
    
    gemini_api_key = get_env_variable("GEMINI_API_KEY", "")
    
    if not gemini_api_key:
        return {
            "status": "error",
            "message": "GEMINI_API_KEY not configured",
            "configured": False
        }
    
    # Mask the API key for security
    masked_key = gemini_api_key[:8] + "..." + gemini_api_key[-4:] if len(gemini_api_key) > 12 else "configured"
    
    return {
        "status": "ok",
        "message": "Gemini service configured",
        "configured": True,
        "api_key": masked_key
    }


# New endpoints for history management monitoring
@router.get("/{usecase_id}/gemini-chat/statistics")
def get_chat_statistics(usecase_id: uuid.UUID, db: Session = Depends(get_db)):
    """Get detailed statistics about chat history and token usage."""
    try:
        record = db.query(UsecaseMetadata).filter(
            UsecaseMetadata.usecase_id == usecase_id, 
            UsecaseMetadata.is_deleted == False
        ).first()
        
        if not record:
            raise HTTPException(status_code=404, detail="Usecase not found")
        
        chat_history = record.chat_history or []
        chat_summary = record.chat_summary
        
        stats = get_chat_history_statistics(chat_history, chat_summary)
        
        return {
            "usecase_id": str(usecase_id),
            "statistics": stats,
            "timestamp": _utc_now_iso()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error getting chat statistics for usecase {usecase_id}: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving statistics")


@router.get("/{usecase_id}/gemini-chat/summarization-status")
def get_summarization_status(usecase_id: uuid.UUID, db: Session = Depends(get_db)):
    """Check if chat history needs summarization."""
    try:
        record = db.query(UsecaseMetadata).filter(
            UsecaseMetadata.usecase_id == usecase_id, 
            UsecaseMetadata.is_deleted == False
        ).first()
        
        if not record:
            raise HTTPException(status_code=404, detail="Usecase not found")
        
        chat_history = record.chat_history or []
        chat_summary = record.chat_summary
        
        status = check_summarization_needed(chat_history, chat_summary)
        
        return {
            "usecase_id": str(usecase_id),
            "summarization_status": status,
            "current_summary_length": len(chat_summary) if chat_summary else 0,
            "chat_messages_count": len(chat_history),
            "timestamp": _utc_now_iso()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error checking summarization status for usecase {usecase_id}: {e}")
        raise HTTPException(status_code=500, detail="Error checking summarization status")


@router.post("/{usecase_id}/gemini-chat/force-summarization")
async def force_summarization(usecase_id: uuid.UUID, db: Session = Depends(get_db)):
    """Force summarization of chat history (for testing/maintenance)."""
    try:
        record = db.query(UsecaseMetadata).filter(
            UsecaseMetadata.usecase_id == usecase_id, 
            UsecaseMetadata.is_deleted == False
        ).first()
        
        if not record:
            raise HTTPException(status_code=404, detail="Usecase not found")
        
        chat_history = record.chat_history or []
        chat_summary = record.chat_summary
        
        if len(chat_history) < 3:
            return {
                "message": "Not enough chat history to summarize",
                "usecase_id": str(usecase_id),
                "action": "none"
            }
        
        # Import the history manager
        from services.llm.gemini_conversational.history_manager import ChatHistoryManager
        from core.env_config import get_env_variable
        
        api_key = get_env_variable("GEMINI_API_KEY", "")
        if not api_key:
            raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured")
        
        manager = ChatHistoryManager(api_key)
        
        # Force process the history
        updated_history, updated_summary, summarized = await manager.process_chat_history(
            usecase_id, chat_history, chat_summary, db
        )
        
        return {
            "message": "Summarization completed" if summarized else "No summarization needed",
            "usecase_id": str(usecase_id),
            "summarization_performed": summarized,
            "original_messages": len(chat_history),
            "updated_messages": len(updated_history),
            "summary_length": len(updated_summary) if updated_summary else 0,
            "timestamp": _utc_now_iso()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error forcing summarization for usecase {usecase_id}: {e}")
        raise HTTPException(status_code=500, detail="Error performing summarization")
