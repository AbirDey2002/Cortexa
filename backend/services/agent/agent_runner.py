import logging
import os
import json
import warnings
import asyncio
import time
from datetime import datetime
from typing import Any, Dict, List, Tuple, Optional, Callable
from uuid import UUID
try:
    from langchain_core.tools import tool as lc_tool
except ImportError:
    # Fallback for environments/editors that don't resolve langchain_core
    from langchain.tools import tool as lc_tool
from sqlalchemy import text

from db.session import get_db_context
from models.usecase.usecase import UsecaseMetadata
from models.file_processing.ocr_records import OCROutputs, OCRInfo
from models.file_processing.file_metadata import FileMetadata
from models.generator.requirement import Requirement
from services.llm.gemini_conversational.history_manager import manage_chat_history_for_usecase
from core.env_config import get_env_variable
from core.config import AgentLogConfigs
import importlib

logger = logging.getLogger(__name__)

# Suppress Pydantic warning about typing.NotRequired from third-party libs
warnings.filterwarnings(
    "ignore",
    message=r"typing\.NotRequired is not a Python type.*",
    category=UserWarning,
    module="pydantic\._internal\._generate_schema",
)


def _color(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m"


# Trace collector for structured traces (no raw chain-of-thought)
class TraceCollector:
    def __init__(self) -> None:
        self.data: Dict[str, Any] = {
            "engine": None,  # "deepagents" | "fallback"
            "messages": {"assistant_final": None},
            "tool_calls": [],
            "planning": {"todos": [], "subagents": [], "filesystem_ops": []},
        }

    def set_engine(self, engine: str) -> None:
        self.data["engine"] = engine

    def set_assistant_final(self, text: str) -> None:
        self.data["messages"]["assistant_final"] = text

    def add_planning_artifact(self, kind: str, payload: Any) -> None:
        bucket = self.data.get("planning", {})
        if kind not in bucket:
            bucket[kind] = []
        bucket[kind].append(payload)
        self.data["planning"] = bucket

    def start_tool(self, name: str, args_preview: str) -> Dict[str, Any]:
        entry = {
            "name": name,
            "args_preview": args_preview,
            "started_at": datetime.utcnow().isoformat() + "Z",
            "finished_at": None,
            "duration_ms": None,
            "ok": None,
            "error": None,
            "result_preview": None,
            "chars_read": None,
        }
        self.data["tool_calls"].append(entry)
        return entry

    def finish_tool(
        self,
        entry: Dict[str, Any],
        ok: bool,
        *,
        result_preview: Optional[str] = None,
        error: Optional[str] = None,
        duration_ms: Optional[int] = None,
        chars_read: Optional[int] = None,
    ) -> None:
        entry["finished_at"] = datetime.utcnow().isoformat() + "Z"
        entry["ok"] = ok
        entry["error"] = error
        entry["result_preview"] = result_preview
        entry["duration_ms"] = duration_ms
        entry["chars_read"] = chars_read

    def dump(self) -> Dict[str, Any]:
        return self.data


# --- Conversation context helpers ---
def _extract_assistant_text(raw: Any) -> str:
    try:
        # If value is a list of chunk objects, concatenate their 'text' fields
        if isinstance(raw, list):
            try:
                texts: List[str] = []
                for ch in raw:
                    if isinstance(ch, dict) and "text" in ch:
                        val = ch.get("text")
                        if isinstance(val, str) and val:
                            texts.append(val)
                joined = "\n".join(texts).strip()
                if joined:
                    return joined[:4000]
            except Exception:
                pass
        s = raw if isinstance(raw, str) else str(raw)
        s = s.strip()
        # Try code-fenced JSON first
        try:
            import re as _re
            m = _re.search(r"```json\s*([\s\S]*?)\s*```", s, _re.IGNORECASE)
            if m:
                s_try = m.group(1)
            else:
                s_try = s
            import json as _json
            data = _json.loads(s_try)
            if isinstance(data, dict):
                if "user_answer" in data:
                    return str(data.get("user_answer") or "")[:4000]
                if "system_event" in data:
                    # UI orchestration event; do not feed to model context
                    return ""
                # Fallback: collapse dict
                return _json.dumps(data)[:2000]
        except Exception:
            pass
        # Try to extract from stringified list-of-chunks like: [{'type':'text','text':'...'}, ...]
        try:
            import re as _re2
            texts: List[str] = []
            for m in _re2.finditer(r"(?:'text'|\"text\")\s*:\s*(?:'([^']*)'|\"([^\"]*)\")", s):
                val = m.group(1) or m.group(2) or ""
                if val:
                    texts.append(val)
            if texts:
                joined = "\n\n".join(texts).strip()
                if joined:
                    return joined[:4000]
        except Exception:
            pass
        # Not JSON, return trimmed text
        return s[:4000]
    except Exception:
        return ""


def _build_agent_messages(usecase_id: Any, user_message: str) -> List[Dict[str, str]]:
    messages: List[Dict[str, str]] = []
    try:
        with get_db_context() as db:
            rec = db.query(UsecaseMetadata).filter(
                UsecaseMetadata.usecase_id == usecase_id,
                UsecaseMetadata.is_deleted == False,
            ).first()
            if not rec:
                return [{"role": "user", "content": user_message}]
            history = rec.chat_history or []
            chat_summary = getattr(rec, "chat_summary", None)
            # Determine if a summary marker exists; messages are stored newest-first
            marker_idx = None
            for i, entry in enumerate(history):
                if isinstance(entry, dict) and entry.get("marker", "").startswith("___SUMMARY_CUTOFF_"):
                    marker_idx = i
                    break
            # Add summary preface if available
            if chat_summary:
                preface = (
                    "Conversation up to the summary marker has been summarized below; do not rely on earlier messages.\n\n"
                    "=== CONVERSATION SUMMARY ===\n" + str(chat_summary)
                )
                messages.append({"role": "system", "content": preface})
            # Choose portion of history to include (after marker if present)
            if marker_idx is not None:
                recent_portion = history[:marker_idx]
            else:
                recent_portion = history
            # Convert to chronological order
            chronological = list(reversed(recent_portion))
            current_user_message_found = False
            for entry in chronological:
                if isinstance(entry, dict) and "user" in entry:
                    content = str(entry.get("user") or "")[:4000]
                    # Check if this is the current user message (most recent one)
                    if not current_user_message_found and content.strip() == user_message.strip():
                        current_user_message_found = True
                    # Include file information if present
                    files = entry.get("files", [])
                    if files:
                        file_names = [f.get("name", "unknown") for f in files if isinstance(f, dict)]
                        if file_names:
                            content += f"\n\n[Files uploaded: {', '.join(file_names)}]"
                    if content:
                        messages.append({"role": "user", "content": content})
                elif isinstance(entry, dict) and "modal" in entry:
                    # Convert [modal] marker to system message for agent context
                    # NO TEXT DATA in marker, only file_id reference
                    modal_data = entry.get("modal", {})
                    file_name = modal_data.get("file_name", "the document")
                    system_msg = f"PDF content for '{file_name}' has been displayed to the user above in the chat. The user can see the extracted OCR text from this document. You can reference this displayed content in your responses."
                    messages.append({"role": "system", "content": system_msg})
                elif isinstance(entry, dict) and "system" in entry:
                    text = _extract_assistant_text(entry.get("system"))
                    if text:
                        messages.append({"role": "assistant", "content": text})
    except Exception:
        pass
    # Append current user message only if it wasn't found in history
    if not current_user_message_found:
        messages.append({"role": "user", "content": user_message})
    return messages


def _normalize_assistant_output(raw: Any) -> str:
    try:
        if isinstance(raw, list):
            # Join chunk texts
            parts: List[str] = []
            for ch in raw:
                if isinstance(ch, dict) and "text" in ch:
                    val = ch.get("text")
                    if isinstance(val, str) and val:
                        parts.append(val)
            joined = "\n".join(parts).strip()
            if joined:
                return joined
            return str(raw)
        s = raw if isinstance(raw, str) else str(raw)
        s = s.strip()
        # Extract JSON user_answer
        try:
            import re as _re
            m = _re.search(r"```json\s*([\s\S]*?)\s*```", s, _re.IGNORECASE)
            s_try = m.group(1) if m else s
            import json as _json
            data = _json.loads(s_try)
            if isinstance(data, dict) and "user_answer" in data:
                return str(data.get("user_answer") or "")
        except Exception:
            pass
        # Extract from stringified chunk list
        try:
            import re as _re2
            texts: List[str] = []
            for mm in _re2.finditer(r"(?:'text'|\"text\")\s*:\s*(?:'([^']*)'|\"([^\"]*)\")", s):
                val = mm.group(1) or mm.group(2) or ""
                if val:
                    texts.append(val)
            if texts:
                return "\n\n".join(texts).strip()
        except Exception:
            pass
        return s
    except Exception:
        return str(raw)


def _log_agent_input(msgs: List[Dict[str, str]], *, label: str, usecase_id: Any) -> None:
    try:
        total = len(msgs)
        chars = sum(len(m.get("content", "")) for m in msgs)
        words = sum(len(m.get("content", "").split()) for m in msgs)
        header = f"\n\n=== AGENT INPUT [{label}] usecase={usecase_id} ===\nmessages={total} words={words} chars={chars}\n"
        # Preview first and last 3
        preview_lines: List[str] = []
        head = msgs[:3]
        tail = msgs[-3:] if total > 3 else []
        def fmt(m: Dict[str, str]) -> str:
            role = m.get("role", "?")
            content = m.get("content", "")
            snippet = content[:200].replace("\n", " ")
            return f"- {role}: len={len(content)} | {snippet}"
        if head:
            preview_lines.append("-- first --")
            for m in head:
                preview_lines.append(fmt(m))
        if tail:
            preview_lines.append("-- last --")
            for m in tail:
                preview_lines.append(fmt(m))
        block = header + "\n".join(preview_lines) + "\n=== END AGENT INPUT ===\n\n"
        logger.info(_color(block, "31"))
    except Exception as e:
        logger.warning(_color(f"[LOG-AGENT-INPUT] failed: {e}", "33"))


# Tool implementations (thin wrappers)
def tool_get_usecase_status(usecase_id) -> Dict[str, Any]:
    with get_db_context() as db:
        rec = db.query(UsecaseMetadata).filter(
            UsecaseMetadata.usecase_id == usecase_id,
            UsecaseMetadata.is_deleted == False,
        ).first()
        if not rec:
            return {"error": "usecase_not_found"}
        return {
            "text_extraction": rec.text_extraction,
            "requirement_generation": rec.requirement_generation,
            "scenario_generation": rec.scenario_generation,
            "test_case_generation": rec.test_case_generation,
            "requirement_generation_confirmed": getattr(rec, "requirement_generation_confirmed", False),
        }


def tool_check_text_extraction_status(file_id: str = None, usecase_id: UUID = None) -> Dict[str, Any]:
    """Check text extraction status. If file_id provided, check that file. If usecase_id provided, check all files in usecase."""
    with get_db_context() as db:
        if file_id:
            try:
                file_uuid = UUID(file_id) if isinstance(file_id, str) else file_id
            except (ValueError, TypeError):
                return {"error": "invalid_file_id", "message": f"Invalid file_id format: {file_id}"}
            
            # Check specific file
            file_metadata = db.query(FileMetadata).filter(FileMetadata.file_id == file_uuid).first()
            if not file_metadata:
                return {"error": "file_not_found", "message": f"File with id {file_id} not found"}
            
            usecase = db.query(UsecaseMetadata).filter(
                UsecaseMetadata.usecase_id == file_metadata.usecase_id,
                UsecaseMetadata.is_deleted == False,
            ).first()
            
            if not usecase:
                return {"error": "usecase_not_found"}
            
            ocr_info = db.query(OCRInfo).filter(OCRInfo.file_id == file_uuid).first()
            text_extraction_status = usecase.text_extraction or "Not Started"
            
            return {
                "file_id": str(file_uuid),
                "file_name": file_metadata.file_name,
                "text_extraction": text_extraction_status,
                "total_pages": ocr_info.total_pages if ocr_info else 0,
                "completed_pages": ocr_info.completed_pages if ocr_info else 0,
            }
        elif usecase_id:
            # Check all files in usecase
            usecase = db.query(UsecaseMetadata).filter(
                UsecaseMetadata.usecase_id == usecase_id,
                UsecaseMetadata.is_deleted == False,
            ).first()
            
            if not usecase:
                return {"error": "usecase_not_found"}
            
            text_extraction_status = usecase.text_extraction or "Not Started"
            
            files = db.query(FileMetadata).filter(FileMetadata.usecase_id == usecase_id).all()
            file_statuses = []
            for file_meta in files:
                ocr_info = db.query(OCRInfo).filter(OCRInfo.file_id == file_meta.file_id).first()
                file_statuses.append({
                    "file_id": str(file_meta.file_id),
                    "file_name": file_meta.file_name,
                    "total_pages": ocr_info.total_pages if ocr_info else 0,
                    "completed_pages": ocr_info.completed_pages if ocr_info else 0,
                })
            
            return {
                "usecase_id": str(usecase_id),
                "text_extraction": text_extraction_status,
                "files": file_statuses,
            }
        else:
            return {"error": "missing_parameter", "message": "Either file_id or usecase_id must be provided"}


def tool_get_documents_markdown(usecase_id) -> Dict[str, Any]:
    with get_db_context() as db:
        outputs = db.query(OCROutputs).join(UsecaseMetadata, UsecaseMetadata.usecase_id == usecase_id).all()
        # Minimal composition: collect all page_text for usecase's files
        # Prefer page 1 semantics already enforced elsewhere
        q = db.execute(
            text(
                """
                SELECT f.file_id, f.file_name, o.page_number, o.page_text
                FROM file_metadata f
                JOIN ocr_outputs o ON o.file_id = f.file_id
                WHERE f.usecase_id = :uid AND o.is_deleted = false
                ORDER BY f.created_at ASC, o.page_number ASC
                """
            ),
            {"uid": usecase_id},
        ).fetchall()
        files_map: Dict[str, Dict[str, Any]] = {}
        for row in q:
            fid = str(row.file_id)
            if fid not in files_map:
                files_map[fid] = {"file_id": fid, "file_name": row.file_name, "markdown": ""}
            files_map[fid]["markdown"] += (row.page_text or "") + "\n"
        files = list(files_map.values())
        combined = "\n".join([f"## {f['file_name']}\n\n{f['markdown'].strip()}\n" for f in files]).strip()
        logger.info(_color(f"[DOC-READ] files={len(files)} combined_chars={len(combined)}", "34"))
        return {"files": files, "combined_markdown": combined}


def tool_start_requirement_generation(usecase_id) -> Dict[str, Any]:
    # Side-effect free: only indicate whether confirmation is required or already in progress/completed
    try:
        with get_db_context() as db:
            rec = db.query(UsecaseMetadata).filter(
                UsecaseMetadata.usecase_id == usecase_id,
                UsecaseMetadata.is_deleted == False,
            ).first()
            if not rec:
                return {"error": "usecase_not_found"}
            
            text_extraction = rec.text_extraction or "Not Started"
            requirement_generation = rec.requirement_generation or "Not Started"
            confirmed = getattr(rec, "requirement_generation_confirmed", False)
            
            logger.info(_color(
                f"[REQ-GEN] start requested for usecase={usecase_id} text_extraction={text_extraction} "
                f"requirement_generation={requirement_generation} confirmed={confirmed}",
                "34"
            ))
            
            # Gate 1: Text extraction must be complete
            if text_extraction != "Completed":
                return {
                    "error": "precondition_not_met",
                    "message": f"Text extraction is '{text_extraction}'. Wait for document processing to complete.",
                    "text_extraction": text_extraction,
                    "requirement_generation": requirement_generation
                }
            
            # Gate 2: Check requirement generation status
            if requirement_generation == "In Progress":
                return {
                    "status": "in_progress",
                    "message": "Requirement generation is already running. You'll be notified when complete."
                }
            
            if requirement_generation == "Completed":
                return {
                    "status": "already_completed",
                    "message": "Requirements already generated. You can view or query them now."
                }
            
            if requirement_generation == "Failed" and confirmed:
                return {
                    "status": "retry_allowed",
                    "message": "Previous generation failed. I can retry if you'd like."
                }
            
            # Gate 3: Must be Not Started and not confirmed yet
            if requirement_generation == "Not Started" and not confirmed:
                return {
                    "status": "confirmation_required",
                    "message": "Ready to start requirement generation. Awaiting user confirmation."
                }
            
            return {"error": "unexpected_state", "requirement_generation": requirement_generation, "confirmed": confirmed}
    except Exception as e:
        logger.exception(_color(f"[REQ-GEN] tool error: {e}", "31"))
        return {"error": "internal_error"}


def tool_get_requirements(usecase_id) -> Dict[str, Any]:
    with get_db_context() as db:
        uc = db.query(UsecaseMetadata).filter(
            UsecaseMetadata.usecase_id == usecase_id,
            UsecaseMetadata.is_deleted == False,
        ).first()
        if not uc:
            return {"error": "usecase_not_found"}
        
        req_gen_status = uc.requirement_generation or "Not Started"
        
        if req_gen_status != "Completed":
            return {
                "error": "requirements_not_ready",
                "requirement_generation": req_gen_status,
                "message": f"Requirements are '{req_gen_status}'. "
                          f"{'Generate them first.' if req_gen_status == 'Not Started' else 'Please wait for generation to complete.'}"
            }
        
        reqs = db.query(Requirement).filter(
            Requirement.usecase_id == usecase_id,
            Requirement.is_deleted == False,
        ).all()
        payload = [r.requirement_text for r in reqs]
        logger.info(_color(f"[REQ-READ] count={len(payload)}", "34"))
        return {
            "requirements": payload,
            "count": len(payload),
            "message": f"Fetched {len(payload)} requirements for analysis."
        }


def tool_show_extracted_text(file_id: str = None, file_name: str = None, usecase_id: UUID = None) -> Dict[str, Any]:
    """Create [modal] placeholder in chat_history. Only call when user asks to see PDF.
    
    If file_id is not provided, uses file_name to match, or falls back to most recent file.
    Priority: file_id > file_name match > most recent file
    """
    with get_db_context() as db:
        # Verify usecase exists
        usecase = db.query(UsecaseMetadata).filter(
            UsecaseMetadata.usecase_id == usecase_id,
            UsecaseMetadata.is_deleted == False,
        ).first()
        
        if not usecase:
            return {"error": "usecase_not_found"}
        
        # Check if text extraction is completed
        text_extraction_status = usecase.text_extraction or "Not Started"
        if text_extraction_status != "Completed":
            return {
                "error": "text_extraction_not_complete",
                "message": f"Text extraction is '{text_extraction_status}'. Please wait for OCR to complete.",
                "text_extraction": text_extraction_status
            }
        
        file_metadata = None
        file_uuid = None
        
        # Priority 1: Use file_id if provided and valid
        if file_id:
            try:
                file_uuid = UUID(file_id) if isinstance(file_id, str) else file_id
                file_metadata = db.query(FileMetadata).filter(
                    FileMetadata.file_id == file_uuid
                ).first()
                
                if file_metadata and file_metadata.usecase_id == usecase_id and not file_metadata.is_deleted:
                    # Valid file_id found
                    pass
                else:
                    file_metadata = None
                    file_uuid = None
            except (ValueError, TypeError):
                # Invalid file_id format, will try file_name or fallback
                file_metadata = None
                file_uuid = None
        
        # Priority 2: Use file_name to match if file_id not available
        if not file_metadata and file_name:
            # Try exact match first (case-insensitive)
            file_metadata = db.query(FileMetadata).join(
                OCRInfo, FileMetadata.file_id == OCRInfo.file_id
            ).filter(
                FileMetadata.usecase_id == usecase_id,
                FileMetadata.is_deleted == False,
                FileMetadata.file_name.ilike(file_name)
            ).order_by(FileMetadata.created_at.desc()).first()
            
            # If no exact match, try partial match
            if not file_metadata:
                file_metadata = db.query(FileMetadata).join(
                    OCRInfo, FileMetadata.file_id == OCRInfo.file_id
                ).filter(
                    FileMetadata.usecase_id == usecase_id,
                    FileMetadata.is_deleted == False,
                    FileMetadata.file_name.ilike(f"%{file_name}%")
                ).order_by(FileMetadata.created_at.desc()).first()
            
            if file_metadata:
                file_uuid = file_metadata.file_id
        
        # Priority 3: Fallback to most recent file
        if not file_metadata:
            # Find most recent file with OCR info in this usecase (order by created_at DESC)
            file_metadata = db.query(FileMetadata).join(
                OCRInfo, FileMetadata.file_id == OCRInfo.file_id
            ).filter(
                FileMetadata.usecase_id == usecase_id,
                FileMetadata.is_deleted == False
            ).order_by(FileMetadata.created_at.desc()).first()
            
            if not file_metadata:
                return {
                    "error": "no_files_found",
                    "message": "No files with completed extraction found in this usecase."
                }
            file_uuid = file_metadata.file_id
        
        # Verify OCR info exists
        ocr_info = db.query(OCRInfo).filter(OCRInfo.file_id == file_uuid).first()
        if not ocr_info:
            return {"error": "ocr_info_not_found", "message": f"OCR information not found for file {file_metadata.file_name if file_metadata else 'unknown'}"}
        
        # Get current chat history
        chat_history = usecase.chat_history or []
        
        # Find the user message we just added (should be first or near the beginning)
        user_message = None
        user_index = -1
        for i, entry in enumerate(chat_history):
            if isinstance(entry, dict) and "user" in entry:
                user_message = entry
                user_index = i
                break
        
        if not user_message or user_index < 0:
            # If no user message found, append to end
            from datetime import datetime, timezone
            modal_timestamp = datetime.now(timezone.utc).isoformat()
        else:
            # Parse user message timestamp and add 1 second
            try:
                from datetime import datetime, timezone
                user_timestamp_str = user_message.get("timestamp", "")
                if user_timestamp_str:
                    user_timestamp = datetime.fromisoformat(user_timestamp_str.replace('Z', '+00:00'))
                    modal_timestamp = datetime.fromtimestamp(user_timestamp.timestamp() + 1, tz=timezone.utc).isoformat()
                else:
                    modal_timestamp = datetime.now(timezone.utc).isoformat()
            except Exception as e:
                logger.warning(_color(f"[SHOW-EXTRACTED-TEXT] Error parsing timestamp: {e}", "33"))
                from datetime import datetime, timezone
                modal_timestamp = datetime.now(timezone.utc).isoformat()
        
        # Create [modal] marker - NO TEXT DATA, only file_id reference
        # Include top-level timestamp for proper sorting in chat history
        modal_marker = {
            "modal": {
                "file_id": str(file_uuid),
                "file_name": file_metadata.file_name,
                "timestamp": modal_timestamp
            },
            "timestamp": modal_timestamp
        }
        
        # Insert marker right after user message (or at beginning if no user message)
        if user_index >= 0:
            updated_history = (
                chat_history[:user_index + 1] + 
                [modal_marker] + 
                chat_history[user_index + 1:]
            )
        else:
            updated_history = [modal_marker] + chat_history
        
        # Update chat history
        usecase.chat_history = updated_history
        db.commit()
        
        logger.info(_color(
            f"[SHOW-EXTRACTED-TEXT] Created modal marker for file_id={file_id} file_name={file_metadata.file_name}",
            "34"
        ))
        
        return {
            "status": "success",
            "message": f"PDF content for '{file_metadata.file_name}' will be displayed above.",
            "file_id": str(file_uuid),
            "file_name": file_metadata.file_name
        }


def tool_read_extracted_text(file_id: str) -> Dict[str, Any]:
    """Read full OCR text from database. Returns complete, non-truncated text for agent analysis."""
    try:
        file_uuid = UUID(file_id) if isinstance(file_id, str) else file_id
    except (ValueError, TypeError):
        return {"error": "invalid_file_id", "message": f"Invalid file_id format: {file_id}"}
    
    with get_db_context() as db:
        # Get file metadata
        file_metadata = db.query(FileMetadata).filter(
            FileMetadata.file_id == file_uuid
        ).first()
        
        if not file_metadata:
            logger.warning(_color(f"[READ-EXTRACTED-TEXT] file not found: {file_id}", "31"))
            return {"error": "file_not_found", "message": f"File with id {file_id} not found"}
        
        # Check if text extraction is completed for the usecase
        usecase = db.query(UsecaseMetadata).filter(
            UsecaseMetadata.usecase_id == file_metadata.usecase_id,
            UsecaseMetadata.is_deleted == False,
        ).first()
        
        if not usecase:
            return {"error": "usecase_not_found"}
        
        text_extraction_status = usecase.text_extraction or "Not Started"
        if text_extraction_status != "Completed":
            return {
                "error": "text_extraction_not_complete",
                "message": f"Text extraction is '{text_extraction_status}'. Please wait for OCR to complete.",
                "text_extraction": text_extraction_status
            }
        
        # Get OCR info first (prefer pages_json)
        ocr_info = db.query(OCRInfo).filter(OCRInfo.file_id == file_uuid).first()
        
        if ocr_info and ocr_info.pages_json:
            # Use pages_json if available
            pages_json = ocr_info.pages_json if isinstance(ocr_info.pages_json, dict) else {}
            pages = []
            for page_num_str, page_markdown in sorted(pages_json.items(), key=lambda x: int(x[0])):
                pages.append({
                    "page_number": int(page_num_str),
                    "markdown": page_markdown or "",
                    "is_completed": True
                })
        else:
            # Fallback to OCROutputs
            ocr_outputs = db.query(OCROutputs).filter(
                OCROutputs.file_id == file_uuid
            ).order_by(OCROutputs.page_number.asc()).all()
            
            pages = []
            for output in ocr_outputs:
                pages.append({
                    "page_number": output.page_number,
                    "markdown": output.page_text or "",
                    "is_completed": output.is_completed or False
                })
        
        # Build combined markdown (full text, no truncation)
        combined_markdown = "\n\n".join([
            f"## Page {p['page_number']}\n\n{p['markdown']}"
            for p in pages
        ])
        
        total_chars = len(combined_markdown)
        logger.info(_color(
            f"[READ-EXTRACTED-TEXT] file_id={file_id} file_name={file_metadata.file_name} "
            f"total_pages={len(pages)} total_chars={total_chars}",
            "34"
        ))
        
        # Return FULL text - no truncation for agent
        return {
            "file_id": str(file_uuid),
            "file_name": file_metadata.file_name,
            "total_pages": len(pages),
            "pages": pages,
            "combined_markdown": combined_markdown,
            "total_chars": total_chars,
            "message": f"Retrieved full OCR text from '{file_metadata.file_name}' ({len(pages)} pages, {total_chars} characters)."
        }


def build_tools(usecase_id, tracer: TraceCollector) -> List[Any]:
    """Build LangChain tool objects bound to a specific usecase_id with async wrappers and tracing."""

    @lc_tool
    async def get_usecase_status() -> Dict[str, Any]:
        """Get the current pipeline statuses (text_extraction, requirement_generation, scenario_generation, test_case_generation) for this chat's usecase."""
        name = "get_usecase_status"
        entry = tracer.start_tool(name, args_preview="{}")
        start = time.time()
        logger.info(_color(f"[TOOL-START {name}] usecase_id={usecase_id}", "34"))
        try:
            result = await asyncio.to_thread(tool_get_usecase_status, usecase_id)
            duration_ms = int((time.time() - start) * 1000)
            tracer.finish_tool(entry, True, result_preview=str({k: result.get(k) for k in ["text_extraction", "requirement_generation", "scenario_generation", "test_case_generation"]}), duration_ms=duration_ms)
            try:
                import json as _json
                out = _json.dumps(result, ensure_ascii=False)[:5000]
                if len(_json.dumps(result, ensure_ascii=False)) > 5000:
                    out += "... [TRUNCATED]"
                logger.info(_color(f"[TOOL-OUTPUT {name}] {out}", "34"))
            except Exception:
                pass
            logger.info(_color(f"[TOOL-END {name}] duration={duration_ms}ms", "34"))
            return result
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            tracer.finish_tool(entry, False, error=str(e), duration_ms=duration_ms)
            logger.exception(_color(f"[TOOL-ERROR {name}] {e}", "34"))
            raise

    @lc_tool
    async def get_documents_markdown() -> Dict[str, Any]:
        """Retrieve all extracted documents' Markdown (per-file and combined) for this usecase. Use to read/understand document contents (OCR results)."""
        name = "get_documents_markdown"
        entry = tracer.start_tool(name, args_preview="{}")
        start = time.time()
        logger.info(_color(f"[TOOL-START {name}] usecase_id={usecase_id}", "34"))
        try:
            result = await asyncio.to_thread(tool_get_documents_markdown, usecase_id)
            combined = result.get("combined_markdown", "")
            duration_ms = int((time.time() - start) * 1000)
            tracer.finish_tool(entry, True, result_preview=f"files={len(result.get('files', []))}", duration_ms=duration_ms, chars_read=len(combined))
            # Log full output (pretty JSON) before return with truncation
            try:
                import json as _json
                out = _json.dumps(result, ensure_ascii=False)[:5000]
                if len(_json.dumps(result, ensure_ascii=False)) > 5000:
                    out += "... [TRUNCATED]"
                logger.info(_color(f"[TOOL-OUTPUT {name}] {out}", "34"))
            except Exception:
                pass
            logger.info(_color(f"[TOOL-END {name}] duration={duration_ms}ms chars_read={len(combined)}", "34"))
            return result
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            tracer.finish_tool(entry, False, error=str(e), duration_ms=duration_ms)
            logger.exception(_color(f"[TOOL-ERROR {name}] {e}", "34"))
            raise

    @lc_tool
    async def start_requirement_generation() -> Dict[str, Any]:
        """
        Request requirement generation. ONLY call this when:
        - text_extraction is Completed
        - requirement_generation is Not Started
        - User explicitly requests it
        This should be your FINAL action. Do not call other tools after this.
        Returns: {'status': 'confirmation_required'} if conditions met, or error/status info otherwise.
        """
        name = "start_requirement_generation"
        entry = tracer.start_tool(name, args_preview="{}")
        start = time.time()
        logger.info(_color(f"[TOOL-START {name}] usecase_id={usecase_id}", "34"))
        try:
            result = await asyncio.to_thread(tool_start_requirement_generation, usecase_id)
            duration_ms = int((time.time() - start) * 1000)
            tracer.finish_tool(entry, True, result_preview=str(result), duration_ms=duration_ms)
            try:
                import json as _json
                out = _json.dumps(result, ensure_ascii=False)[:5000]
                if len(_json.dumps(result, ensure_ascii=False)) > 5000:
                    out += "... [TRUNCATED]"
                logger.info(_color(f"[TOOL-OUTPUT {name}] {out}", "34"))
            except Exception:
                pass
            logger.info(_color(f"[TOOL-END {name}] duration={duration_ms}ms", "34"))
            return result
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            tracer.finish_tool(entry, False, error=str(e), duration_ms=duration_ms)
            logger.exception(_color(f"[TOOL-ERROR {name}] {e}", "34"))
            raise

    @lc_tool
    async def get_requirements() -> Dict[str, Any]:
        """
        Fetch generated requirements for analysis. ONLY call when requirement_generation is Completed.
        Returns requirements as ephemeral context (do NOT include raw JSON in your response).
        If not ready, returns error with current status.
        """
        name = "get_requirements"
        entry = tracer.start_tool(name, args_preview="{}")
        start = time.time()
        logger.info(_color(f"[TOOL-START {name}] usecase_id={usecase_id}", "34"))
        try:
            result = await asyncio.to_thread(tool_get_requirements, usecase_id)
            count = len(result.get("requirements", []))
            duration_ms = int((time.time() - start) * 1000)
            tracer.finish_tool(entry, True, result_preview=f"count={count}", duration_ms=duration_ms)
            try:
                import json as _json
                out = _json.dumps(result, ensure_ascii=False)[:5000]
                if len(_json.dumps(result, ensure_ascii=False)) > 5000:
                    out += "... [TRUNCATED]"
                logger.info(_color(f"[TOOL-OUTPUT {name}] {out}", "34"))
            except Exception:
                pass
            logger.info(_color(f"[TOOL-END {name}] duration={duration_ms}ms count={count}", "34"))
            return result
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            tracer.finish_tool(entry, False, error=str(e), duration_ms=duration_ms)
            logger.exception(_color(f"[TOOL-ERROR {name}] {e}", "34"))
            raise

    @lc_tool
    async def check_text_extraction_status(file_id: str = None) -> Dict[str, Any]:
        """
        Check text extraction status. If file_id provided, check that file. If not provided, check all files in usecase.
        Call this tool to verify extraction status after file upload.
        Returns: extraction status (Not Started, In Progress, Completed, Failed), file_id, file_name, page counts.
        """
        name = "check_text_extraction_status"
        entry = tracer.start_tool(name, args_preview=f'{{"file_id": "{file_id if file_id else "usecase"}"}}')
        start = time.time()
        logger.info(_color(f"[TOOL-START {name}] file_id={file_id} usecase_id={usecase_id}", "34"))
        try:
            result = await asyncio.to_thread(tool_check_text_extraction_status, file_id, usecase_id)
            duration_ms = int((time.time() - start) * 1000)
            tracer.finish_tool(entry, True, result_preview=str(result.get("text_extraction", "unknown")), duration_ms=duration_ms)
            try:
                import json as _json
                out = _json.dumps(result, ensure_ascii=False)[:5000]
                if len(_json.dumps(result, ensure_ascii=False)) > 5000:
                    out += "... [TRUNCATED]"
                logger.info(_color(f"[TOOL-OUTPUT {name}] {out}", "34"))
            except Exception:
                pass
            logger.info(_color(f"[TOOL-END {name}] duration={duration_ms}ms", "34"))
            return result
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            tracer.finish_tool(entry, False, error=str(e), duration_ms=duration_ms)
            logger.exception(_color(f"[TOOL-ERROR {name}] {e}", "34"))
            raise

    @lc_tool
    async def show_extracted_text(file_id: str = None, file_name: str = None) -> Dict[str, Any]:
        """
        Create [modal] placeholder in chat_history to display PDF content to user.
        ONLY call when user explicitly requests to see/view/display PDF content.
        User phrases: "show me the PDF", "display the document", "what's in the file", "open the PDF", "show the extracted text", "look into this document", "show this document", "show again", "show me the [document name]".
        Conditions: text_extraction must be "Completed", user must explicitly ask to see content.
        You can call this tool multiple times if the user requests to see content again (e.g., "show again", "show me the document again").
        The tool will always create a modal marker when called, allowing users to re-display content.
        If file_id is not provided, the tool will try to match by file_name (extracted from user text or attached files), or use the most recent file.
        After calling, respond: "I've retrieved the PDF content. The document will be displayed above for you to review."
        Do NOT include the actual text content in your response.
        """
        name = "show_extracted_text"
        
        # Extract file names from most recent user message if file_name not provided
        extracted_file_name = file_name
        if not extracted_file_name:
            try:
                with get_db_context() as db:
                    usecase = db.query(UsecaseMetadata).filter(
                        UsecaseMetadata.usecase_id == usecase_id,
                        UsecaseMetadata.is_deleted == False,
                    ).first()
                    if usecase and usecase.chat_history:
                        # Get all available files in the usecase for matching
                        available_files = db.query(FileMetadata).join(
                            OCRInfo, FileMetadata.file_id == OCRInfo.file_id
                        ).filter(
                            FileMetadata.usecase_id == usecase_id,
                            FileMetadata.is_deleted == False
                        ).all()
                        available_file_names = [f.file_name for f in available_files] if available_files else []
                        
                        # Find most recent user message
                        for entry in usecase.chat_history:
                            if isinstance(entry, dict) and "user" in entry:
                                # Priority 1: Check attached files
                                files = entry.get("files", [])
                                if files and len(files) > 0:
                                    # Use the first file name from the most recent message
                                    first_file = files[0] if isinstance(files[0], dict) else {}
                                    extracted_file_name = first_file.get("name", "")
                                    if extracted_file_name:
                                        break
                                
                                # Priority 2: Extract file name from user's text message
                                if not extracted_file_name:
                                    user_text = str(entry.get("user", ""))
                                    user_text_lower = user_text.lower()
                                    import re
                                    
                                    # Improved patterns to extract file names from user text
                                    # These patterns capture the file name/keywords before common suffixes
                                    patterns = [
                                        # "display the contents of Magic Submission document" -> "Magic Submission"
                                        r"(?:display|show|open|view)\s+(?:me\s+)?(?:the\s+)?(?:contents?\s+of\s+)?(?:the\s+)?['\"]?([^'\"]+?)(?:\s+document|\s+file|\s+pdf|please|$)",
                                        # "show Magic Submission" -> "Magic Submission"
                                        r"(?:show|display|open)\s+(?:me\s+)?(?:the\s+)?['\"]?([^'\"]+?)(?:\s+again|please|$)",
                                        # "the Magic Submission document" -> "Magic Submission"
                                        r"the\s+['\"]?([^'\"]+?)(?:\s+document|\s+file|\s+pdf)",
                                        # "look into Magic Submission" -> "Magic Submission"
                                        r"look\s+(?:into|at)\s+(?:this\s+)?(?:the\s+)?['\"]?([^'\"]+?)(?:\s+document|\s+file|\s+pdf|$)",
                                    ]
                                    
                                    potential_names = []
                                    for pattern in patterns:
                                        matches = re.finditer(pattern, user_text_lower, re.IGNORECASE)
                                        for match in matches:
                                            potential_name = match.group(1).strip()
                                            # Remove common words that might be captured
                                            potential_name = re.sub(r'\b(?:the|a|an|this|that|document|file|pdf)\b', '', potential_name, flags=re.IGNORECASE).strip()
                                            if potential_name and len(potential_name) > 2:  # At least 3 characters
                                                potential_names.append(potential_name)
                                    
                                    # Try to match extracted names against available files
                                    for potential_name in potential_names:
                                        # First try exact match (case-insensitive)
                                        for file_name in available_file_names:
                                            if file_name.lower() == potential_name.lower():
                                                extracted_file_name = file_name
                                                logger.info(_color(f"[SHOW-EXTRACTED-TEXT] Exact match: '{potential_name}' -> '{extracted_file_name}'", "34"))
                                                break
                                        
                                        if extracted_file_name:
                                            break
                                        
                                        # Then try partial match - check if potential_name words are in file_name
                                        potential_words = [w.strip() for w in re.split(r'[\s\-_]+', potential_name) if len(w.strip()) > 2]
                                        if potential_words:
                                            best_match = None
                                            best_match_score = 0
                                            
                                            for file_name in available_file_names:
                                                file_name_lower = file_name.lower()
                                                # Count how many words from potential_name are in file_name
                                                match_count = sum(1 for word in potential_words if word.lower() in file_name_lower)
                                                match_score = match_count / len(potential_words) if potential_words else 0
                                                
                                                # Also check if potential_name is a significant substring
                                                if potential_name.lower() in file_name_lower:
                                                    match_score += 0.5
                                                
                                                if match_score > best_match_score and match_score >= 0.5:  # At least 50% match
                                                    best_match_score = match_score
                                                    best_match = file_name
                                            
                                            if best_match:
                                                extracted_file_name = best_match
                                                logger.info(_color(f"[SHOW-EXTRACTED-TEXT] Partial match: '{potential_name}' -> '{extracted_file_name}' (score: {best_match_score:.2f})", "34"))
                                                break
                                    
                                    if not extracted_file_name and potential_names:
                                        logger.info(_color(f"[SHOW-EXTRACTED-TEXT] Could not match extracted names {potential_names} against available files {available_file_names}", "33"))
                                
                                # Break after processing the most recent user message
                                break
            except Exception as e:
                logger.warning(_color(f"[SHOW-EXTRACTED-TEXT] Error extracting file name from history: {e}", "33"))
        
        entry = tracer.start_tool(name, args_preview=f'{{"file_id": "{file_id if file_id else "auto"}", "file_name": "{extracted_file_name if extracted_file_name else "none"}"}}')
        start = time.time()
        logger.info(_color(f"[TOOL-START {name}] file_id={file_id} file_name={extracted_file_name} usecase_id={usecase_id}", "34"))
        try:
            result = await asyncio.to_thread(tool_show_extracted_text, file_id, extracted_file_name, usecase_id)
            file_name_str = result.get("file_name", "N/A")
            duration_ms = int((time.time() - start) * 1000)
            tracer.finish_tool(entry, True, result_preview=f"file_id={file_id} file_name={file_name_str} status={result.get('status', 'unknown')}", duration_ms=duration_ms)
            try:
                import json as _json
                out = _json.dumps(result, ensure_ascii=False)[:5000]
                if len(_json.dumps(result, ensure_ascii=False)) > 5000:
                    out += "... [TRUNCATED]"
                logger.info(_color(f"[TOOL-OUTPUT {name}] {out}", "34"))
            except Exception:
                pass
            logger.info(_color(f"[TOOL-END {name}] duration={duration_ms}ms", "34"))
            return result
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            tracer.finish_tool(entry, False, error=str(e), duration_ms=duration_ms)
            logger.exception(_color(f"[TOOL-ERROR {name}] {e}", "34"))
            raise

    @lc_tool
    async def read_extracted_text(file_id: str) -> Dict[str, Any]:
        """
        Read full OCR text from database for agent analysis.
        Call when user asks questions about document content and you need to read the OCR text to answer.
        Use when user asks: "what does the document say about X?", "summarize the document", "what are the key points?"
        Conditions: text_extraction must be "Completed", user must be asking about document content.
        Returns full, non-truncated text for your analysis.
        Use this text to answer user's question, but do NOT include the full text in your response.
        """
        name = "read_extracted_text"
        entry = tracer.start_tool(name, args_preview=f'{{"file_id": "{file_id}"}}')
        start = time.time()
        logger.info(_color(f"[TOOL-START {name}] file_id={file_id} usecase_id={usecase_id}", "34"))
        try:
            result = await asyncio.to_thread(tool_read_extracted_text, file_id)
            total_chars = result.get("total_chars", 0)
            pages_count = result.get("total_pages", 0)
            file_name_str = result.get("file_name", "N/A")
            duration_ms = int((time.time() - start) * 1000)
            # Log truncated version for performance, but return full to agent
            tracer.finish_tool(entry, True, result_preview=f"file_id={file_id} file_name={file_name_str} pages={pages_count} chars={total_chars}", duration_ms=duration_ms, chars_read=total_chars)
            try:
                import json as _json
                # Log truncated version
                out = _json.dumps(result, ensure_ascii=False)[:5000]
                if len(_json.dumps(result, ensure_ascii=False)) > 5000:
                    out += "... [TRUNCATED IN LOG]"
                logger.info(_color(f"[TOOL-OUTPUT {name}] {out}", "34"))
                logger.info(_color(f"[TOOL-OUTPUT {name}] NOTE: Logs truncated for performance, but agent receives FULL text ({total_chars} chars)", "33"))
            except Exception:
                pass
            logger.info(_color(f"[TOOL-END {name}] duration={duration_ms}ms pages={pages_count} chars={total_chars}", "34"))
            # Return FULL result - no truncation for agent
            return result
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            tracer.finish_tool(entry, False, error=str(e), duration_ms=duration_ms)
            logger.exception(_color(f"[TOOL-ERROR {name}] {e}", "34"))
            raise

    return [
        get_usecase_status,
        get_documents_markdown,
        start_requirement_generation,
        get_requirements,
        check_text_extraction_status,
        show_extracted_text,
        read_extracted_text,
    ]


def run_agent_turn(usecase_id, user_message: str) -> Tuple[str, Dict[str, Any]]:
    """
    Run a single agent turn. If deepagents is available, use it for planning/traces; otherwise fallback to a simple rule-based flow.
    Returns: (assistant_text, traces)
    """
    tracer = TraceCollector()
    tools = build_tools(usecase_id, tracer)

    try:
        # Provide a concrete LangChain Gemini model instance to DeepAgents
        from core.env_config import get_env_variable
        GEMINI_API_KEY = get_env_variable("GEMINI_API_KEY", "")
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI  # type: ignore
            lc_model = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=GEMINI_API_KEY)
            model_label = "langchain_google_genai.ChatGoogleGenerativeAI"
        except Exception:
            # Very last resort: fall back to model string with provider prefix
            from langchain.chat_models import init_chat_model  # type: ignore
            lc_model = init_chat_model(model="google-genai:gemini-2.5-flash", api_key=GEMINI_API_KEY)
            model_label = "init_chat_model(google-genai:gemini-2.5-flash)"

        from deepagents import create_deep_agent  # type: ignore

        logger.info(_color(f"[AGENT-INIT] deepagents using model={model_label}", "34"))

        # Build and possibly summarize chat history if extremely long (>200k words)
        try:
            with get_db_context() as _db:
                rec = _db.query(UsecaseMetadata).filter(
                    UsecaseMetadata.usecase_id == usecase_id,
                    UsecaseMetadata.is_deleted == False,
                ).first()
                if rec:
                    hist = rec.chat_history or []
                    # Estimate words across user/system texts ignoring structured traces
                    def _entry_text(e: Any) -> str:
                        if isinstance(e, dict):
                            if "user" in e:
                                return str(e.get("user") or "")
                            if "system" in e:
                                return _extract_assistant_text(e.get("system"))
                        return ""
                    total_words = 0
                    for e in hist:
                        t = _entry_text(e)
                        if t:
                            total_words += len(t.split())
                    if total_words > 200000:
                        GEMINI_API_KEY = get_env_variable("GEMINI_API_KEY", "")
                        try:
                            import asyncio as _asyncio
                            context, updated_history, updated_summary, summarized = _asyncio.run(
                                manage_chat_history_for_usecase(
                                    usecase_id=usecase_id,
                                    chat_history=hist,
                                    chat_summary=getattr(rec, "chat_summary", None),
                                    user_query=user_message,
                                    api_key=GEMINI_API_KEY,
                                    db=_db,
                                    model_name="gemini-2.5-flash",
                                )
                            )
                            # Values persisted inside manager; nothing else needed here
                            logger.info(_color(f"[HISTORY] Summarized due to size words={total_words}", "34"))
                        except Exception as _e:
                            logger.warning(_color(f"[HISTORY] summarization failed: {_e}", "33"))
        except Exception:
            pass

        # Prefer file-based prompt if provided to ease multiline editing
        sys_prompt_file = get_env_variable("AGENT_SYSTEM_PROMPT_FILE", "").strip()
        system_prompt_value = None
        if sys_prompt_file:
            try:
                import os as _os
                if _os.path.exists(sys_prompt_file):
                    with open(sys_prompt_file, "r", encoding="utf-8") as f:
                        system_prompt_value = f.read()
            except Exception:
                system_prompt_value = None
        if not system_prompt_value:
            # Try module-based system prompt
            try:
                mod_path = get_env_variable("AGENT_SYSTEM_PROMPT_MODULE", "").strip()
                if mod_path:
                    mod = importlib.import_module(mod_path)
                    # Use module docstring or exported variable named 'prompt'
                    val = getattr(mod, "prompt", None)
                    if val is None:
                        val = getattr(mod, "__doc__", "") or ""
                    system_prompt_value = str(val or "")
            except Exception:
                system_prompt_value = None
        if not system_prompt_value:
            system_prompt_value = get_env_variable("AGENT_SYSTEM_PROMPT", "")
        if AgentLogConfigs.LOG_AGENT_SYSTEM_PROMPT:
            try:
                sp = system_prompt_value or ""
                if len(sp) > AgentLogConfigs.LOG_AGENT_SYSTEM_PROMPT_MAX_LENGTH:
                    sp = sp[:AgentLogConfigs.LOG_AGENT_SYSTEM_PROMPT_MAX_LENGTH] + "... [TRUNCATED]"
                logger.info("\033[33m[AGENT SYSTEM PROMPT]\n%s\033[0m", sp)
            except Exception:
                pass

        agent = create_deep_agent(
            tools=tools,
            model=lc_model,
            system_prompt=system_prompt_value,
        )

        async def _run() -> str:
            tracer.set_engine("deepagents")
            final_text: str = ""
            try:
                built_msgs = _build_agent_messages(usecase_id, user_message)
                _log_agent_input(built_msgs, label="astream:values", usecase_id=usecase_id)
                async for chunk in agent.astream(
                    {"messages": built_msgs},
                    stream_mode="values",
                ):
                    if isinstance(chunk, dict) and "messages" in chunk:
                        msgs = chunk["messages"]
                        if isinstance(msgs, list) and msgs:
                            last = msgs[-1]
                            content = None
                            if isinstance(last, dict):
                                content = last.get("content")
                            else:
                                content = getattr(last, "content", None)
                            if content:
                                final_text = str(content)
                # Removed second updates stream to avoid duplicate tool executions and logs
            except Exception as e:
                # If streaming fails, fall back to single invoke
                built_msgs3 = _build_agent_messages(usecase_id, user_message)
                _log_agent_input(built_msgs3, label="invoke", usecase_id=usecase_id)
                result = agent.invoke({"messages": built_msgs3})
                if isinstance(result, dict) and "messages" in result:
                    msgs = result.get("messages")
                    if isinstance(msgs, list) and msgs:
                        last = msgs[-1]
                        if isinstance(last, dict):
                            final_text = str(last.get("content", ""))
                        else:
                            final_text = str(getattr(last, "content", last))
                else:
                    final_text = str(result)
            if AgentLogConfigs.LOG_AGENT_RAW_OUTPUT:
                try:
                    txt = final_text or ""
                    if len(txt) > AgentLogConfigs.LOG_AGENT_RAW_OUTPUT_MAX_LENGTH:
                        txt = txt[:AgentLogConfigs.LOG_AGENT_RAW_OUTPUT_MAX_LENGTH] + "... [TRUNCATED]"
                    logger.info("\033[33m[AGENT RAW OUTPUT]\n%s\033[0m", txt)
                except Exception:
                    pass
            final_text_norm = _normalize_assistant_output(final_text)
            tracer.set_assistant_final(final_text_norm)
            logger.info(_color(f"[AGENT]\n\n{final_text_norm}\n", "32"))
            return final_text_norm

        assistant_text = asyncio.run(_run())
        # Post-run: if agent invoked start_requirement_generation, emit UI confirmation event
        try:
            tool_called = any(
                (tc.get("name") == "start_requirement_generation") for tc in tracer.data.get("tool_calls", [])
            )
        except Exception:
            tool_called = False
        
        if tool_called:
            logger.info(_color(f"[REQ-GEN-MODAL] Tool was called; checking if confirmation event needed", "35"))
            try:
                with get_db_context() as db:
                    rec = db.query(UsecaseMetadata).filter(
                        UsecaseMetadata.usecase_id == usecase_id,
                        UsecaseMetadata.is_deleted == False,
                    ).first()
                    if rec:
                        confirmed = getattr(rec, "requirement_generation_confirmed", False)
                        status_rg = rec.requirement_generation or "Not Started"
                        text_ext = rec.text_extraction or "Not Started"
                        
                        logger.info(_color(
                            f"[REQ-GEN-MODAL] Status check: text_extraction={text_ext}, "
                            f"requirement_generation={status_rg}, confirmed={confirmed}",
                            "35"
                        ))
                        
                        # Only emit if conditions are right
                        if text_ext == "Completed" and not confirmed and status_rg == "Not Started":
                            logger.info(_color(f"[REQ-GEN-MODAL] Emitting confirmation_required event", "35"))
                            assistant_text = json.dumps({
                                "system_event": "requirement_generation_confirmation_required",
                                "usecase_id": str(usecase_id),
                            })
                        elif status_rg == "In Progress":
                            logger.info(_color(f"[REQ-GEN-MODAL] Generation in progress; emitting in_progress event", "35"))
                            assistant_text = json.dumps({
                                "system_event": "requirement_generation_in_progress",
                                "usecase_id": str(usecase_id),
                            })
                        else:
                            logger.info(_color(
                                f"[REQ-GEN-MODAL] Conditions not met for event emission; keeping agent response",
                                "35"
                            ))
            except Exception as e:
                logger.warning(_color(f"[REQ-GEN-MODAL] Event emission failed: {e}", "33"))
        return assistant_text, tracer.dump()
    except Exception as e:
        logger.warning(_color(f"[AGENT-FALLBACK] deepagents unavailable or failed: {e}", "34"))
        tracer.set_engine("fallback")
        # Fallback: minimal rule-based (ReAct-like) selection with traced tool calls
        # 1) Check status (traced)
        name = "get_usecase_status"
        entry = tracer.start_tool(name, args_preview="{}")
        t0 = time.time()
        logger.info(_color(f"[TOOL-START {name}] usecase_id={usecase_id}", "34"))
        try:
            status = tool_get_usecase_status(usecase_id)
            tracer.finish_tool(entry, True, result_preview=str({k: status.get(k) for k in ["text_extraction", "requirement_generation", "scenario_generation", "test_case_generation"]}), duration_ms=int((time.time()-t0)*1000))
            try:
                import json as _json
                out = _json.dumps(status, ensure_ascii=False)[:5000]
                if len(_json.dumps(status, ensure_ascii=False)) > 5000:
                    out += "... [TRUNCATED]"
                logger.info(_color(f"[TOOL-OUTPUT {name}] {out}", "34"))
            except Exception:
                pass
            logger.info(_color(f"[TOOL-END {name}]", "34"))
        except Exception as ex:
            tracer.finish_tool(entry, False, error=str(ex), duration_ms=int((time.time()-t0)*1000))
            logger.exception(_color(f"[TOOL-ERROR {name}] {ex}", "34"))
        text = user_message.lower()
        # Log what the fallback will consider as input (no history in fallback)
        try:
            _log_agent_input([{ "role": "user", "content": user_message }], label="fallback", usecase_id=usecase_id)
        except Exception:
            pass
        assistant_text = ""
        # Determine intent
        wants_reqs = any(k in text for k in ["generate requirements", "extract requirements", "create requirements", "requirements list", "preconditions of requirements", "read requirements"])
        wants_doc_read = any(
            k in text for k in [
                "read the pdf",
                "read the document",
                "read the documents",
                "look into this document",
                "summarize",
                "summarise",
                "summarize the file",
                "summarize the pdf",
                "extract key points",
                "what does this attachment",
                "get details from the uploaded",
                "analyze the document",
                "analyze documents",
            ]
        )
        if wants_reqs:
            # Gate by consent and current status
            req_status = status.get("requirement_generation") if isinstance(status, dict) else None
            consent = status.get("requirement_generation_confirmed") if isinstance(status, dict) else False
            if req_status == "In Progress":
                assistant_text = json.dumps({"system_event": "requirement_generation_in_progress", "usecase_id": str(usecase_id)})
            elif not consent and req_status in (None, "Not Started", "Failed"):
                assistant_text = json.dumps({"system_event": "requirement_generation_confirmation_required", "usecase_id": str(usecase_id)})
            else:
                assistant_text = "Requirements request acknowledged."
        elif wants_doc_read:
            name = "get_documents_markdown"
            entry = tracer.start_tool(name, args_preview="{}")
            t0 = time.time()
            logger.info(_color(f"[TOOL-START {name}] usecase_id={usecase_id}", "34"))
            try:
                docs = tool_get_documents_markdown(usecase_id)
                combined = docs.get("combined_markdown", "")
                tracer.finish_tool(entry, True, result_preview=f"files={len(docs.get('files', []))}", duration_ms=int((time.time()-t0)*1000), chars_read=len(combined))
                try:
                    import json as _json
                    out = _json.dumps(docs, ensure_ascii=False)[:5000]
                    if len(_json.dumps(docs, ensure_ascii=False)) > 5000:
                        out += "... [TRUNCATED]"
                    logger.info(_color(f"[TOOL-OUTPUT {name}] {out}", "34"))
                except Exception:
                    pass
                logger.info(_color(f"[TOOL-END {name}] chars_read={len(combined)}", "34"))
            except Exception as ex:
                tracer.finish_tool(entry, False, error=str(ex), duration_ms=int((time.time()-t0)*1000))
                logger.exception(_color(f"[TOOL-ERROR {name}] {ex}", "34"))
            assistant_text = "Documents read. Ask a related query."
        else:
            assistant_text = "I can help with testing, OCR, and requirements. How can I assist you?"
        tracer.set_assistant_final(assistant_text)
        logger.info(_color(f"[AGENT] {assistant_text}", "32"))
        return assistant_text, tracer.dump()


