from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
import uuid
import logging
from datetime import datetime, timezone, timedelta
import os
import hashlib
import json

from deps import get_db
from models.file_processing.file_metadata import FileMetadata
from models.file_processing.ocr_records import OCRInfo, OCROutputs
from services.file_processing.pdf_text_extractor import download_file_to_bytes, extract_pdf_text, to_markdown, extract_pdf_markdown
from core.config import OCRServiceConfigs
from db.session import get_db_context
from models.usecase.usecase import UsecaseMetadata
from models.user.user import User
from models.generator.requirement import Requirement
from services.llm.gemini_conversational.gemini_invoker import (
    invoke_gemini_chat_with_timeout,
    invoke_gemini_chat_with_history_management,
    get_chat_history_statistics,
    check_summarization_needed
)
from services.llm.gemini_conversational.json_output_parser import parse_llm_response, create_enhanced_cortexa_prompt
from services.llm.gemini_conversational.history_manager import manage_chat_history_for_usecase
from services.agent.agent_runner import run_agent_turn
import google.generativeai as genai
from core.env_config import get_env_variable
from core.model_registry import is_valid_model, get_default_model
from core.auth import verify_token
from typing import Dict, Any

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
    model: str | None = None  # Optional model selection


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

# In-memory streaming buffers for Gemini
gemini_streaming_responses: dict[str, str] = {}
gemini_response_chunks: dict[str, list[str]] = {}

GEMINI_API_KEY = get_env_variable("GEMINI_API_KEY", "")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


def _get_usecase_documents_markdown(db: Session, usecase_id: uuid.UUID) -> tuple[list[dict], str]:
    """Build list of files with markdown and a combined markdown string from DB (no HTTP)."""
    files = db.query(FileMetadata).filter(
        FileMetadata.usecase_id == usecase_id,
        FileMetadata.is_deleted == False,
    ).order_by(FileMetadata.created_at.asc()).all()
    result_files: list[dict] = []
    combined_parts: list[str] = []
    for f in files:
        outputs = db.query(OCROutputs).filter(
            OCROutputs.file_id == f.file_id,
            OCROutputs.is_deleted == False,
        ).order_by(OCROutputs.page_number.asc()).all()
        md = "\n".join([(o.page_text or "") for o in outputs])
        result_files.append({
            "file_id": str(f.file_id),
            "file_name": f.file_name,
            "markdown": md,
        })
        if md.strip():
            combined_parts.append(f"## {f.file_name}\n\n{md}\n")
    combined_markdown = "\n".join(combined_parts).strip()
    return result_files, combined_markdown

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


def _run_gemini_chat_inference_sync(usecase_id: uuid.UUID, user_message: str, model: str | None = None, timeout_seconds: int = 300):
    """
    Enhanced Gemini chat inference with automatic history management and summarization.
    
    Args:
        usecase_id: The usecase identifier
        user_message: The user's message
        model: Optional model ID. If not provided, uses usecase's selected_model or default
        timeout_seconds: Timeout for the operation
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
            
            # Determine which model to use: request model > usecase model > default
            selected_model = model or record.selected_model or get_default_model()
            
            # Validate model
            if not is_valid_model(selected_model):
                logger.warning(f"Invalid model '{selected_model}', falling back to default")
                selected_model = get_default_model()
            
            # Update usecase with selected model if provided in request
            if model and model != record.selected_model:
                record.selected_model = model
                db.commit()
                logger.info(f"Updated usecase {usecase_id} model to {model}")
            
            logger.info(f"Starting enhanced Gemini chat inference for usecase_id={usecase_id} with model={selected_model}")
            
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
                        model_name=selected_model
                    )
                )

                # Delegate to deep agent for orchestration
                assistant_text, traces = run_agent_turn(usecase_id, user_message, model=selected_model)
                gemini_streaming_responses[str(usecase_id)] = assistant_text
                
                # Debug: Log traces structure
                try:
                    tool_calls_count = len(traces.get("tool_calls", [])) if isinstance(traces, dict) else 0
                    tool_names = [tc.get("name", "unknown") for tc in traces.get("tool_calls", [])] if isinstance(traces, dict) else []
                    logger.info(f"[TRACES-DEBUG] Traces received: tool_calls_count={tool_calls_count}, tool_names={tool_names}")
                except Exception as e:
                    logger.warning(f"[TRACES-DEBUG] Error logging traces: {e}")

                # First pass logging
                try:
                    logger.info(
                        "Chatbot response chars for usecase_id=%s: %d",
                        str(usecase_id),
                        len(assistant_text or ""),
                    )
                    if OCRServiceConfigs.LOG_OCR_TEXT and assistant_text:
                        snippet = assistant_text.strip()
                        max_len = OCRServiceConfigs.OCR_TEXT_LOG_MAX_LENGTH
                        if len(snippet) > max_len:
                            snippet = snippet[:max_len] + "... [TRUNCATED]"
                        logger.info("Chatbot response (snippet):\n%s", snippet if snippet else "[EMPTY]")
                except Exception:
                    pass

                # All tool orchestration handled inside deep agent runner

                # PDF markers are now created during file upload, not here
                # This ensures correct ordering: User message → PDF marker → Agent response

                # Persist full record (system text + structured traces)
                system_entry = {"system": assistant_text, "timestamp": _utc_now_iso(), "traces": traces}
                
                # Re-read chat_history from DB to get any [modal] markers created by tools during execution
                db.refresh(record)
                current_db_history = record.chat_history or []
                
                # Collect ALL modal markers from current_db_history (both new and existing)
                # This ensures requirements and scenarios markers persist independently
                all_modal_markers = []
                user_timestamp = None
                for entry in current_db_history:
                    if isinstance(entry, dict) and "user" in entry:
                        user_timestamp = entry.get("timestamp")
                        break
                
                # Collect ALL modal markers (requirements, scenarios, testcases, PDF) - preserve all types independently
                for entry in current_db_history:
                    if isinstance(entry, dict) and "modal" in entry:
                        modal = entry.get("modal", {})
                        modal_type = modal.get("type")  # "requirements", "scenarios", "testcases", or None (for PDF)
                        modal_file_id = modal.get("file_id")  # For PDF markers
                        
                        # For requirements, scenarios, and testcases, always preserve the latest marker of each type
                        # For PDF markers, check if created during this turn
                        if modal_type in ("requirements", "scenarios", "testcases"):
                            # Always include requirements/scenarios/testcases markers (they're managed independently by tools)
                            all_modal_markers.append(entry)
                        elif modal_file_id:
                            # For PDF markers, check if created during this turn
                            modal_timestamp = entry.get("timestamp") or modal.get("timestamp", "")
                            if modal_timestamp and user_timestamp:
                                try:
                                    from datetime import datetime, timezone
                                    modal_time = datetime.fromisoformat(modal_timestamp.replace('Z', '+00:00'))
                                    user_time = datetime.fromisoformat(user_timestamp.replace('Z', '+00:00'))
                                    # PDF marker should be after user message (within reasonable time window of 30 seconds)
                                    if modal_time >= user_time and (modal_time - user_time).total_seconds() < 30:
                                        all_modal_markers.append(entry)
                                except:
                                    # If timestamp parsing fails, include the marker anyway if it's recent
                                    all_modal_markers.append(entry)
                            else:
                                # Include if no timestamps available (shouldn't happen, but be safe)
                                all_modal_markers.append(entry)
                
                # Build final history: agent response first, then modal markers, then rest
                # History is stored newest-first: [agent, modal, user, ...]
                final_history = [system_entry]
                final_history.extend(all_modal_markers)
                
                # Add the rest of updated_history (from history manager), excluding duplicates
                # updated_history already has the user message and older entries
                # Track all modal markers we've already added to avoid duplicates
                seen_modal_keys = set()
                for m in all_modal_markers:
                    if isinstance(m, dict) and "modal" in m:
                        modal = m.get("modal", {})
                        # For requirements/scenarios/testcases, track by type
                        if modal.get("type") in ("requirements", "scenarios", "testcases"):
                            seen_modal_keys.add(f"type:{modal.get('type')}")
                        # For PDF, track by file_id
                        elif modal.get("file_id"):
                            seen_modal_keys.add(f"file_id:{modal.get('file_id')}")
                
                for entry in updated_history or []:
                    # Skip if it's a modal marker we already added
                    if isinstance(entry, dict) and "modal" in entry:
                        modal = entry.get("modal", {})
                        modal_type = modal.get("type")
                        modal_file_id = modal.get("file_id")
                        
                        if modal_type in ("requirements", "scenarios", "testcases"):
                            if f"type:{modal_type}" in seen_modal_keys:
                                continue
                        elif modal_file_id:
                            if f"file_id:{modal_file_id}" in seen_modal_keys:
                                continue
                    final_history.append(entry)
                
                record.chat_history = final_history
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
async def append_gemini_chat_message(
    usecase_id: uuid.UUID,
    payload: ChatMessage,
    background_tasks: BackgroundTasks,
    token_payload: Dict[str, Any] = Depends(verify_token),
    db: Session = Depends(get_db)
):
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

    # Handle uploaded files: ensure FileMetadata rows and store extracted PDF text
    try:
        if payload.files:
            # Resolve user_id from usecase record
            user_id = record.user_id
            usecase_uuid = record.usecase_id

            resolved_files: list[FileMetadata] = []
            for f in payload.files:
                file_name = str(f.get("name") or "").strip()
                if not file_name:
                    continue
                # Try to find existing file metadata by usecase and name
                fm = db.query(FileMetadata).filter(
                    FileMetadata.usecase_id == usecase_uuid,
                    FileMetadata.file_name == file_name,
                    FileMetadata.is_deleted == False,
                ).first()
                if not fm:
                    # Construct local link fallback
                    file_link = f"/uploads/{file_name}"
                    fm = FileMetadata(
                        file_name=file_name,
                        file_link=file_link,
                        user_id=user_id,
                        usecase_id=usecase_uuid,
                    )
                    db.add(fm)
                    db.flush()  # get file_id
                resolved_files.append(fm)

            # For each resolved file, extract text and upsert OCR rows (idempotent)
            for fm in resolved_files:
                # Download/read file bytes
                bytes_data = download_file_to_bytes(fm.file_link)
                if not bytes_data:
                    logging.getLogger(__name__).warning(
                        "No bytes read for file_link=%s (file_name=%s)", fm.file_link, fm.file_name
                    )
                # Prefer robust markdown extractor
                md_text = extract_pdf_markdown(bytes_data)
                extractor_used = "pdfplumber"
                if not md_text:
                    text = extract_pdf_text(bytes_data)
                    md_text = to_markdown(text)
                    extractor_used = "fallback"
                # Ensure fenced code block formatting if text still lacks markdown cues
                if md_text and not any(sym in md_text for sym in ("# ", "- ", "1. ")):
                    # Wrap in a paragraph to make it explicit markdown content
                    md_text = md_text.replace("\n\n", "\n\n\n").strip()

                # Logging of extracted text (controlled by config to avoid sensitive exposure)
                logger = logging.getLogger(__name__)
                logger.info(
                    "Markdown extractor=%s, markdown chars for file '%s' (id=%s): %d",
                    extractor_used,
                    fm.file_name,
                    str(fm.file_id),
                    len(md_text or ""),
                )
                if OCRServiceConfigs.LOG_OCR_TEXT and md_text:
                    snippet = md_text.strip()
                    max_len = OCRServiceConfigs.OCR_TEXT_LOG_MAX_LENGTH
                    if len(snippet) > max_len:
                        snippet = snippet[:max_len] + "... [TRUNCATED]"
                    logger.info("Markdown PDF text (snippet):\n%s", snippet if snippet else "[EMPTY]")
                # Upsert OCRInfo (single row per file)
                info = db.query(OCRInfo).filter(OCRInfo.file_id == fm.file_id).first()
                if not info:
                    info = OCRInfo(
                        file_id=fm.file_id,
                        total_pages=1,
                        completed_pages=1,
                        error_pages=0,
                    )
                    db.add(info)
                else:
                    info.total_pages = 1
                    info.completed_pages = 1
                    info.error_pages = 0

                # Upsert OCROutputs for page 1
                output = db.query(OCROutputs).filter(
                    OCROutputs.file_id == fm.file_id,
                    OCROutputs.page_number == 1,
                ).first()
                if not output:
                    output = OCROutputs(
                        file_id=fm.file_id,
                        page_number=1,
                        page_text=md_text or "",
                        is_completed=True,
                    )
                    db.add(output)
                else:
                    output.page_text = md_text or ""
                    output.error_msg = None
                    output.is_completed = True

            db.commit()
    except Exception as e:
        # Do not fail chat append if file processing fails
        logging.getLogger(__name__).error(f"Error processing uploaded files for usecase {usecase_id}: {e}")
    
    # PDF markers are now created by Tool 2 (show_extracted_text) when agent calls it
    # No automatic marker creation here - markers only created when user explicitly asks to see PDF
    
    # Fire background inference with Gemini
    background_tasks.add_task(_run_gemini_chat_inference_sync, usecase_id, payload.content, payload.model)
    return {"status": "accepted", "usecase_id": str(usecase_id), "provider": "gemini"}


@router.get("/{usecase_id}/gemini-chat")
def get_gemini_chat_history(
    usecase_id: uuid.UUID,
    token_payload: Dict[str, Any] = Depends(verify_token),
    db: Session = Depends(get_db)
):
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
def get_gemini_chat_history_frontend(
    usecase_id: uuid.UUID,
    token_payload: Dict[str, Any] = Depends(verify_token),
    db: Session = Depends(get_db)
):
    """Frontend-specific endpoint to get Gemini chat history without ORM issues."""
    return get_gemini_chat_history(usecase_id, db)


@router.get("/{usecase_id}/gemini-chat/stream")
async def stream_gemini_chat(
    usecase_id: uuid.UUID,
    token_payload: Dict[str, Any] = Depends(verify_token)
):
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
def get_chat_statistics(
    usecase_id: uuid.UUID,
    token_payload: Dict[str, Any] = Depends(verify_token),
    db: Session = Depends(get_db)
):
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
def get_summarization_status(
    usecase_id: uuid.UUID,
    token_payload: Dict[str, Any] = Depends(verify_token),
    db: Session = Depends(get_db)
):
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
async def force_summarization(
    usecase_id: uuid.UUID,
    token_payload: Dict[str, Any] = Depends(verify_token),
    db: Session = Depends(get_db)
):
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
