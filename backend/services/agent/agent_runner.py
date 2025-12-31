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
from models.generator.scenario import Scenario
from models.generator.test_case import TestCase
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


def tool_start_scenario_generation(usecase_id: UUID) -> Dict[str, Any]:
    """Check if scenario generation can be started.
    Returns status indicating if confirmation is needed or generation state.
    """
    try:
        with get_db_context() as db:
            rec = db.query(UsecaseMetadata).filter(
                UsecaseMetadata.usecase_id == usecase_id,
                UsecaseMetadata.is_deleted == False,
            ).first()
            if not rec:
                return {"error": "usecase_not_found"}
            
            requirement_generation = rec.requirement_generation or "Not Started"
            scenario_generation = rec.scenario_generation or "Not Started"
            
            logger.info(_color(
                f"[SCENARIO-GEN] start requested for usecase={usecase_id} "
                f"requirement_generation={requirement_generation} scenario_generation={scenario_generation}",
                "34"
            ))
            
            # Gate 1: Requirement generation must be completed
            if requirement_generation == "Not Started":
                return {
                    "error": "precondition_not_met",
                    "message": "Requirements must be generated first before generating scenarios. Would you like me to start requirement generation?",
                    "requirement_generation": requirement_generation,
                    "scenario_generation": scenario_generation
                }
            
            if requirement_generation == "In Progress":
                return {
                    "error": "precondition_not_met",
                    "message": "Requirements are currently being generated. Please wait for requirement generation to complete, then you can generate scenarios.",
                    "requirement_generation": requirement_generation,
                    "scenario_generation": scenario_generation
                }
            
            if requirement_generation != "Completed":
                return {
                    "error": "precondition_not_met",
                    "message": f"Requirement generation status is '{requirement_generation}'. Requirements must be completed before generating scenarios.",
                    "requirement_generation": requirement_generation,
                    "scenario_generation": scenario_generation
                }
            
            # Gate 2: Check scenario generation status
            if scenario_generation == "In Progress":
                return {
                    "status": "in_progress",
                    "message": "Scenario generation is already running. You'll be notified when complete."
                }
            
            if scenario_generation == "Completed":
                return {
                    "status": "already_completed",
                    "message": "Scenarios already generated. You can view or query them now."
                }
            
            if scenario_generation == "Failed":
                return {
                    "status": "retry_allowed",
                    "message": "Previous scenario generation failed. I can retry if you'd like."
                }
            
            # Gate 3: Must be Not Started
            if scenario_generation == "Not Started":
                return {
                    "status": "confirmation_required",
                    "message": "Ready to start scenario generation. Awaiting user confirmation."
                }
            
            return {"error": "unexpected_state", "scenario_generation": scenario_generation}
    except Exception as e:
        logger.exception(_color(f"[SCENARIO-GEN] tool error: {e}", "31"))
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


def tool_show_requirements(usecase_id: UUID) -> Dict[str, Any]:
    """Create [modal] placeholder in chat_history for requirements display.
    Only call when user asks to see/show requirements.
    Similar to tool_show_extracted_text but for requirements.
    """
    with get_db_context() as db:
        # Verify usecase exists
        usecase = db.query(UsecaseMetadata).filter(
            UsecaseMetadata.usecase_id == usecase_id,
            UsecaseMetadata.is_deleted == False,
        ).first()
        
        if not usecase:
            return {"error": "usecase_not_found"}
        
        # Check requirement_generation status (allow "In Progress" or "Completed")
        req_gen_status = usecase.requirement_generation or "Not Started"
        if req_gen_status not in ("In Progress", "Completed"):
            return {
                "error": "requirements_not_ready",
                "message": f"Requirement generation is '{req_gen_status}'. {'Please wait for generation to start.' if req_gen_status == 'Not Started' else 'Please wait for generation to complete or retry if failed.'}",
                "requirement_generation": req_gen_status
            }
        
        # Get current chat history
        chat_history = usecase.chat_history or []
        
        # Remove any existing requirements markers (keep scenarios and PDF markers)
        # This ensures only the latest requirements marker exists, but scenarios remain independent
        requirements_markers_before = [e for e in chat_history if isinstance(e, dict) and e.get("modal", {}).get("type") == "requirements"]
        scenarios_markers_before = [e for e in chat_history if isinstance(e, dict) and e.get("modal", {}).get("type") == "scenarios"]
        
        filtered_history = [
            entry for entry in chat_history
            if not (isinstance(entry, dict) and entry.get("modal", {}).get("type") == "requirements")
        ]
        
        requirements_markers_after = [e for e in filtered_history if isinstance(e, dict) and e.get("modal", {}).get("type") == "requirements"]
        scenarios_markers_after = [e for e in filtered_history if isinstance(e, dict) and e.get("modal", {}).get("type") == "scenarios"]
        
        logger.info(_color(
            f"[SHOW-REQUIREMENTS] Removed old requirements markers. "
            f"History before: {len(chat_history)} entries, after: {len(filtered_history)} entries | "
            f"Requirements markers: {len(requirements_markers_before)} -> {len(requirements_markers_after)} (should be 0) | "
            f"Scenarios markers: {len(scenarios_markers_before)} -> {len(scenarios_markers_after)} (should be preserved)",
            "35"
        ))
        
        if len(scenarios_markers_before) > 0 and len(scenarios_markers_after) == 0:
            logger.error(_color(
                f"[SHOW-REQUIREMENTS-ERROR] Scenarios markers were accidentally removed! "
                f"Before: {len(scenarios_markers_before)}, After: {len(scenarios_markers_after)}",
                "31"
            ))
        
        # Find the user message we just added (should be first or near the beginning)
        user_message = None
        user_index = -1
        for i, entry in enumerate(filtered_history):
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
                logger.warning(_color(f"[SHOW-REQUIREMENTS] Error parsing timestamp: {e}", "33"))
                from datetime import datetime, timezone
                modal_timestamp = datetime.now(timezone.utc).isoformat()
        
        # Create [modal] marker - NO TEXT DATA, only usecase_id reference
        # Include top-level timestamp for proper sorting in chat history
        modal_marker = {
            "modal": {
                "type": "requirements",
                "usecase_id": str(usecase_id),
                "timestamp": modal_timestamp
            },
            "timestamp": modal_timestamp
        }
        
        # Insert marker right after user message (or at beginning if no user message)
        if user_index >= 0:
            updated_history = (
                filtered_history[:user_index + 1] + 
                [modal_marker] + 
                filtered_history[user_index + 1:]
            )
        else:
            updated_history = [modal_marker] + filtered_history
        
        # Update chat history
        usecase.chat_history = updated_history
        db.commit()
        
        # Verify the marker was saved
        db.refresh(usecase)
        saved_history = usecase.chat_history or []
        requirement_markers_saved = [e for e in saved_history if isinstance(e, dict) and e.get("modal", {}).get("type") == "requirements"]
        scenario_markers_saved = [e for e in saved_history if isinstance(e, dict) and e.get("modal", {}).get("type") == "scenarios"]
        
        logger.info(_color(
            f"[SHOW-REQUIREMENTS] Created modal marker for usecase_id={usecase_id} | "
            f"Total history entries: {len(saved_history)} | "
            f"Requirement markers found: {len(requirement_markers_saved)} | "
            f"Scenario markers found: {len(scenario_markers_saved)} | "
            f"Marker: {modal_marker}",
            "34"
        ))
        
        if len(requirement_markers_saved) == 0:
            logger.error(_color(
                f"[SHOW-REQUIREMENTS-ERROR] Modal marker was NOT saved to chat_history! "
                f"usecase_id={usecase_id}",
                "31"
            ))
        
        if len(scenario_markers_saved) == 0 and len(scenarios_markers_before) > 0:
            logger.error(_color(
                f"[SHOW-REQUIREMENTS-ERROR] Scenarios markers were lost after save! "
                f"Before filtering: {len(scenarios_markers_before)}, After save: {len(scenario_markers_saved)}",
                "31"
            ))
        
        return {
            "status": "success",
            "message": f"Requirements will be displayed above for you to review.",
            "usecase_id": str(usecase_id)
        }


def tool_show_scenarios(usecase_id: UUID) -> Dict[str, Any]:
    """Create [modal] placeholder in chat_history for scenarios display.
    Only call when user asks to see/show scenarios.
    Similar to tool_show_requirements but for scenarios.
    """
    logger.info(_color(f"[SHOW-SCENARIOS] Function called for usecase_id={usecase_id}", "36"))
    with get_db_context() as db:
        # Verify usecase exists
        usecase = db.query(UsecaseMetadata).filter(
            UsecaseMetadata.usecase_id == usecase_id,
            UsecaseMetadata.is_deleted == False,
        ).first()
        
        if not usecase:
            return {"error": "usecase_not_found"}
        
        # Check scenario_generation status (allow "In Progress" or "Completed")
        scenario_gen_status = usecase.scenario_generation or "Not Started"
        if scenario_gen_status not in ("In Progress", "Completed"):
            return {
                "error": "scenarios_not_ready",
                "message": f"Scenario generation is '{scenario_gen_status}'. {'Please wait for generation to start.' if scenario_gen_status == 'Not Started' else 'Please wait for generation to complete or retry if failed.'}",
                "scenario_generation": scenario_gen_status
            }
        
        # Get current chat history
        chat_history = usecase.chat_history or []
        
        # Remove any existing scenarios markers (keep requirements and PDF markers)
        # This ensures only the latest scenarios marker exists, but requirements remain independent
        requirements_markers_before = [e for e in chat_history if isinstance(e, dict) and e.get("modal", {}).get("type") == "requirements"]
        scenarios_markers_before = [e for e in chat_history if isinstance(e, dict) and e.get("modal", {}).get("type") == "scenarios"]
        
        filtered_history = [
            entry for entry in chat_history
            if not (isinstance(entry, dict) and entry.get("modal", {}).get("type") == "scenarios")
        ]
        
        requirements_markers_after = [e for e in filtered_history if isinstance(e, dict) and e.get("modal", {}).get("type") == "requirements"]
        scenarios_markers_after = [e for e in filtered_history if isinstance(e, dict) and e.get("modal", {}).get("type") == "scenarios"]
        
        logger.info(_color(
            f"[SHOW-SCENARIOS] Removed old scenarios markers. "
            f"History before: {len(chat_history)} entries, after: {len(filtered_history)} entries | "
            f"Requirements markers: {len(requirements_markers_before)} -> {len(requirements_markers_after)} (should be preserved) | "
            f"Scenarios markers: {len(scenarios_markers_before)} -> {len(scenarios_markers_after)} (should be 0)",
            "35"
        ))
        
        if len(requirements_markers_before) > 0 and len(requirements_markers_after) == 0:
            logger.error(_color(
                f"[SHOW-SCENARIOS-ERROR] Requirements markers were accidentally removed! "
                f"Before: {len(requirements_markers_before)}, After: {len(requirements_markers_after)}",
                "31"
            ))
        
        # Find the user message we just added (should be first or near the beginning)
        user_message = None
        user_index = -1
        for i, entry in enumerate(filtered_history):
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
                logger.warning(_color(f"[SHOW-SCENARIOS] Error parsing timestamp: {e}", "33"))
                from datetime import datetime, timezone
                modal_timestamp = datetime.now(timezone.utc).isoformat()
        
        # Create [modal] marker - NO TEXT DATA, only usecase_id reference
        # Include top-level timestamp for proper sorting in chat history
        modal_marker = {
            "modal": {
                "type": "scenarios",
                "usecase_id": str(usecase_id),
                "timestamp": modal_timestamp
            },
            "timestamp": modal_timestamp
        }
        
        # Verify requirements markers are still in filtered_history before inserting
        requirements_in_filtered = [e for e in filtered_history if isinstance(e, dict) and e.get("modal", {}).get("type") == "requirements"]
        if len(requirements_markers_before) > 0 and len(requirements_in_filtered) == 0:
            logger.error(_color(
                f"[SHOW-SCENARIOS-ERROR] Requirements markers missing from filtered_history! "
                f"Before: {len(requirements_markers_before)}, In filtered: {len(requirements_in_filtered)}",
                "31"
            ))
        
        # Insert marker right after user message (or at beginning if no user message)
        if user_index >= 0:
            updated_history = (
                filtered_history[:user_index + 1] + 
                [modal_marker] + 
                filtered_history[user_index + 1:]
            )
        else:
            updated_history = [modal_marker] + filtered_history
        
        # Verify requirements markers are in updated_history before saving
        requirements_in_updated = [e for e in updated_history if isinstance(e, dict) and e.get("modal", {}).get("type") == "requirements"]
        if len(requirements_markers_before) > 0 and len(requirements_in_updated) == 0:
            logger.error(_color(
                f"[SHOW-SCENARIOS-ERROR] Requirements markers missing from updated_history! "
                f"Before: {len(requirements_markers_before)}, In updated: {len(requirements_in_updated)}",
                "31"
            ))
        
        # Update chat history
        usecase.chat_history = updated_history
        db.commit()
        
        # Verify the marker was saved
        db.refresh(usecase)
        saved_history = usecase.chat_history or []
        scenario_markers = [e for e in saved_history if isinstance(e, dict) and e.get("modal", {}).get("type") == "scenarios"]
        requirement_markers = [e for e in saved_history if isinstance(e, dict) and e.get("modal", {}).get("type") == "requirements"]
        
        logger.info(_color(
            f"[SHOW-SCENARIOS] Created modal marker for usecase_id={usecase_id} | "
            f"Total history entries: {len(saved_history)} | "
            f"Scenario markers found: {len(scenario_markers)} | "
            f"Requirement markers found: {len(requirement_markers)} | "
            f"Marker: {modal_marker}",
            "34"
        ))
        
        if len(scenario_markers) == 0:
            logger.error(_color(
                f"[SHOW-SCENARIOS-ERROR] Modal marker was NOT saved to chat_history! "
                f"usecase_id={usecase_id}",
                "31"
            ))
        
        if len(requirement_markers) == 0 and len(requirements_markers_before) > 0:
            logger.error(_color(
                f"[SHOW-SCENARIOS-ERROR] Requirements markers were lost after save! "
                f"Before filtering: {len(requirements_markers_before)}, After save: {len(requirement_markers)} | "
                f"In filtered_history: {len(requirements_in_filtered)}, In updated_history: {len(requirements_in_updated)}",
                "31"
            ))
        
        return {
            "status": "success",
            "message": f"Scenarios will be displayed above for you to review.",
            "usecase_id": str(usecase_id)
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


def tool_read_requirement(usecase_id: UUID, display_id: int) -> Dict[str, Any]:
    """Read full requirement content from database by display_id. Returns complete, non-truncated text for agent analysis."""
    try:
        with get_db_context() as db:
            # Verify usecase exists
            usecase = db.query(UsecaseMetadata).filter(
                UsecaseMetadata.usecase_id == usecase_id,
                UsecaseMetadata.is_deleted == False,
            ).first()
            
            if not usecase:
                logger.warning(_color(f"[READ-REQUIREMENT] usecase not found: {usecase_id}", "31"))
                return {"error": "usecase_not_found", "message": f"Usecase with id {usecase_id} not found"}
            
            # Check requirement_generation status
            req_gen_status = usecase.requirement_generation or "Not Started"
            if req_gen_status not in ("In Progress", "Completed"):
                return {
                    "error": "requirements_not_ready",
                    "message": f"Requirement generation is '{req_gen_status}'. Requirements are not available yet.",
                    "requirement_generation": req_gen_status
                }
            
            # Find requirement by display_id
            requirement = db.query(Requirement).filter(
                Requirement.usecase_id == usecase_id,
                Requirement.display_id == display_id,
                Requirement.is_deleted == False,
            ).first()
            
            if not requirement:
                logger.warning(_color(f"[READ-REQUIREMENT] requirement not found: usecase_id={usecase_id} display_id={display_id}", "31"))
                return {
                    "error": "requirement_not_found", 
                    "message": f"Requirement with display_id {display_id} not found for this usecase"
                }
            
            # Get requirement_text JSON
            req_text = requirement.requirement_text or {}
            
            # Format as readable text (similar to OCR combined_markdown format)
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
            logger.info(_color(
                f"[READ-REQUIREMENT] usecase_id={usecase_id} display_id={display_id} "
                f"requirement_id={requirement.id} total_chars={total_chars}",
                "34"
            ))
            
            # Return FULL text - no truncation for agent
            return {
                "usecase_id": str(usecase_id),
                "display_id": display_id,
                "requirement_id": str(requirement.id),
                "requirement_name": name,
                "requirement_text": formatted_text,
                "requirement_json": req_text,  # Also include raw JSON for reference
                "total_chars": total_chars,
                "message": f"Retrieved requirement REQ-{display_id}: {name} ({total_chars} characters)."
            }
    except Exception as e:
        logger.error(_color(f"[READ-REQUIREMENT] error: {e}", "31"), exc_info=True)
        return {"error": "internal_error", "message": str(e)}


def tool_read_scenario(usecase_id: UUID, display_id: int) -> Dict[str, Any]:
    """Read full scenario content from database by display_id. Returns complete, non-truncated text for agent analysis."""
    try:
        with get_db_context() as db:
            # Verify usecase exists
            usecase = db.query(UsecaseMetadata).filter(
                UsecaseMetadata.usecase_id == usecase_id,
                UsecaseMetadata.is_deleted == False,
            ).first()
            
            if not usecase:
                logger.warning(_color(f"[READ-SCENARIO] usecase not found: {usecase_id}", "31"))
                return {"error": "usecase_not_found", "message": f"Usecase with id {usecase_id} not found"}
            
            # Check scenario_generation status
            scenario_gen_status = usecase.scenario_generation or "Not Started"
            if scenario_gen_status not in ("In Progress", "Completed"):
                return {
                    "error": "scenarios_not_ready",
                    "message": f"Scenario generation is '{scenario_gen_status}'. Scenarios are not available yet.",
                    "scenario_generation": scenario_gen_status
                }
            
            # Find scenario by display_id (via Requirement join to filter by usecase_id)
            scenario = db.query(Scenario).join(Requirement).filter(
                Requirement.usecase_id == usecase_id,
                Scenario.display_id == display_id,
                Scenario.is_deleted == False,
                Requirement.is_deleted == False,
            ).first()
            
            if not scenario:
                logger.warning(_color(f"[READ-SCENARIO] scenario not found: usecase_id={usecase_id} display_id={display_id}", "31"))
                return {
                    "error": "scenario_not_found", 
                    "message": f"Scenario with display_id {display_id} not found for this usecase"
                }
            
            # Get scenario_text JSON
            scen_text = scenario.scenario_text or {}
            
            # Format as readable text (similar to OCR combined_markdown format)
            formatted_text_parts = []
            
            # Add scenario name
            name = scen_text.get("ScenarioName", "")
            if name:
                formatted_text_parts.append(f"## Scenario: {name}\n")
            
            # Add description
            description = scen_text.get("ScenarioDescription", "")
            if description:
                formatted_text_parts.append(f"### Description\n{description}\n")
            
            # Add scenario ID
            scenario_id = scen_text.get("ScenarioID", "")
            if scenario_id:
                formatted_text_parts.append(f"### Scenario ID\n{scenario_id}\n")
            
            # Add flows
            flows = scen_text.get("Flows", [])
            if flows:
                formatted_text_parts.append("### Flows\n")
                for idx, flow in enumerate(flows, start=1):
                    formatted_text_parts.append(f"#### Flow {idx}\n")
                    
                    flow_type = flow.get("Type", "")
                    if flow_type:
                        formatted_text_parts.append(f"**Type**: {flow_type}\n")
                    
                    flow_description = flow.get("Description", "")
                    if flow_description:
                        formatted_text_parts.append(f"**Description**: {flow_description}\n")
                    
                    flow_coverage = flow.get("Coverage", "")
                    if flow_coverage:
                        formatted_text_parts.append(f"**Coverage**: {flow_coverage}\n")
                    
                    flow_expected_results = flow.get("ExpectedResults", "")
                    if flow_expected_results:
                        formatted_text_parts.append(f"**Expected Results**: {flow_expected_results}\n")
                    
                    formatted_text_parts.append("\n")
            
            # Combine all parts
            formatted_text = "\n".join(formatted_text_parts)
            
            total_chars = len(formatted_text)
            logger.info(_color(
                f"[READ-SCENARIO] usecase_id={usecase_id} display_id={display_id} "
                f"scenario_id={scenario.id} total_chars={total_chars}",
                "34"
            ))
            
            # Return FULL text - no truncation for agent
            return {
                "usecase_id": str(usecase_id),
                "display_id": display_id,
                "scenario_id": str(scenario.id),
                "scenario_name": name,
                "scenario_text": formatted_text,
                "scenario_json": scen_text,  # Also include raw JSON for reference
                "total_chars": total_chars,
                "message": f"Retrieved scenario TS-{display_id}: {name} ({total_chars} characters)."
            }
    except Exception as e:
        logger.error(_color(f"[READ-SCENARIO] error: {e}", "31"), exc_info=True)
        return {"error": "internal_error", "message": str(e)}


def tool_start_testcase_generation(usecase_id: UUID) -> Dict[str, Any]:
    """Check if test case generation can be started.
    Returns status indicating if confirmation is needed or generation state.
    """
    try:
        with get_db_context() as db:
            rec = db.query(UsecaseMetadata).filter(
                UsecaseMetadata.usecase_id == usecase_id,
                UsecaseMetadata.is_deleted == False,
            ).first()
            if not rec:
                return {"error": "usecase_not_found"}
            
            scenario_generation = rec.scenario_generation or "Not Started"
            test_case_generation = rec.test_case_generation or "Not Started"
            
            logger.info(_color(
                f"[TESTCASE-GEN] start requested for usecase={usecase_id} "
                f"scenario_generation={scenario_generation} test_case_generation={test_case_generation}",
                "34"
            ))
            
            # Gate 1: Scenario generation must be completed
            if scenario_generation == "Not Started":
                return {
                    "error": "precondition_not_met",
                    "message": "Scenarios must be generated first before generating test cases. Would you like me to start scenario generation?",
                    "scenario_generation": scenario_generation,
                    "test_case_generation": test_case_generation
                }
            
            if scenario_generation == "In Progress":
                return {
                    "error": "precondition_not_met",
                    "message": "Scenarios are currently being generated. Please wait for scenario generation to complete, then you can generate test cases.",
                    "scenario_generation": scenario_generation,
                    "test_case_generation": test_case_generation
                }
            
            if scenario_generation != "Completed":
                return {
                    "error": "precondition_not_met",
                    "message": f"Scenario generation status is '{scenario_generation}'. Scenarios must be completed before generating test cases.",
                    "scenario_generation": scenario_generation,
                    "test_case_generation": test_case_generation
                }
            
            # Gate 2: Check test case generation status
            if test_case_generation == "In Progress":
                return {
                    "status": "in_progress",
                    "message": "Test case generation is already running. You'll be notified when complete."
                }
            
            if test_case_generation == "Completed":
                return {
                    "status": "already_completed",
                    "message": "Test cases already generated. You can view or query them now."
                }
            
            if test_case_generation == "Failed":
                return {
                    "status": "retry_allowed",
                    "message": "Previous test case generation failed. I can retry if you'd like."
                }
            
            # Gate 3: Must be Not Started
            if test_case_generation == "Not Started":
                return {
                    "status": "confirmation_required",
                    "message": "Ready to start test case generation. Awaiting user confirmation."
                }
            
            return {"error": "unexpected_state", "test_case_generation": test_case_generation}
    except Exception as e:
        logger.exception(_color(f"[TESTCASE-GEN] tool error: {e}", "31"))
        return {"error": "internal_error"}


def tool_show_testcases(usecase_id: UUID) -> Dict[str, Any]:
    """Create [modal] placeholder in chat_history for test cases display.
    Only call when user asks to see/show test cases.
    Similar to tool_show_scenarios but for test cases.
    """
    logger.info(_color(f"[SHOW-TESTCASES] Function called for usecase_id={usecase_id}", "36"))
    with get_db_context() as db:
        # Verify usecase exists
        usecase = db.query(UsecaseMetadata).filter(
            UsecaseMetadata.usecase_id == usecase_id,
            UsecaseMetadata.is_deleted == False,
        ).first()
        
        if not usecase:
            return {"error": "usecase_not_found"}
        
        # Check test_case_generation status (allow "In Progress" or "Completed")
        test_case_gen_status = usecase.test_case_generation or "Not Started"
        if test_case_gen_status not in ("In Progress", "Completed"):
            return {
                "error": "testcases_not_ready",
                "message": f"Test case generation is '{test_case_gen_status}'. {'Please wait for generation to start.' if test_case_gen_status == 'Not Started' else 'Please wait for generation to complete or retry if failed.'}",
                "test_case_generation": test_case_gen_status
            }
        
        # Get current chat history
        chat_history = usecase.chat_history or []
        
        # Remove any existing testcases markers (keep requirements, scenarios, and PDF markers)
        testcases_markers_before = [e for e in chat_history if isinstance(e, dict) and e.get("modal", {}).get("type") == "testcases"]
        
        filtered_history = [
            entry
            for entry in chat_history
            if not (isinstance(entry, dict) and entry.get("modal", {}).get("type") == "testcases")
        ]
        
        # Find the user message we just added (should be first or near the beginning)
        user_message = None
        user_index = -1
        for i, entry in enumerate(filtered_history):
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
                logger.warning(_color(f"[SHOW-TESTCASES] Error parsing timestamp: {e}", "33"))
                from datetime import datetime, timezone
                modal_timestamp = datetime.now(timezone.utc).isoformat()
        
        # Create [modal] marker - NO TEXT DATA, only usecase_id reference
        # Include top-level timestamp for proper sorting in chat history
        modal_marker = {
            "modal": {
                "type": "testcases",
                "usecase_id": str(usecase_id),
                "timestamp": modal_timestamp
            },
            "timestamp": modal_timestamp
        }
        
        # Insert marker right after user message (or at beginning if no user message)
        if user_index >= 0:
            updated_history = (
                filtered_history[:user_index + 1] + 
                [modal_marker] + 
                filtered_history[user_index + 1:]
            )
        else:
            updated_history = [modal_marker] + filtered_history
        
        # Update chat history
        usecase.chat_history = updated_history
        db.commit()
        
        # Verify marker was saved
        db.refresh(usecase)
        saved_history = usecase.chat_history or []
        testcase_markers = [e for e in saved_history if isinstance(e, dict) and e.get("modal", {}).get("type") == "testcases"]
        
        logger.info(_color(
            f"[SHOW-TESTCASES] Created modal marker for usecase_id={usecase_id} | "
            f"Total history entries: {len(saved_history)} | "
            f"Testcase markers found: {len(testcase_markers)} | "
            f"Marker: {modal_marker}",
            "34"
        ))
        
        if len(testcase_markers) == 0:
            logger.error(_color(
                f"[SHOW-TESTCASES-ERROR] Modal marker was NOT saved to chat_history! "
                f"usecase_id={usecase_id}",
                "31"
            ))
        
        return {
            "status": "success",
            "message": f"Test cases will be displayed above for you to review.",
            "usecase_id": str(usecase_id)
        }


def tool_read_testcase(usecase_id: UUID, display_id: int) -> Dict[str, Any]:
    """Read a specific test case by display_id for agent analysis.
    Returns formatted test case text.
    """
    try:
        with get_db_context() as db:
            # Verify usecase exists
            usecase = db.query(UsecaseMetadata).filter(
                UsecaseMetadata.usecase_id == usecase_id,
                UsecaseMetadata.is_deleted == False,
            ).first()
            
            if not usecase:
                return {"error": "usecase_not_found"}
            
            # Check test_case_generation status
            test_case_gen_status = usecase.test_case_generation or "Not Started"
            if test_case_gen_status not in ("In Progress", "Completed"):
                return {
                    "error": "testcases_not_ready",
                    "message": f"Test case generation is '{test_case_gen_status}'. Test cases are not available yet.",
                    "test_case_generation": test_case_gen_status
                }
            
            # Query all test cases for usecase, ordered by created_at
            from models.generator.test_case import TestCase
            all_test_cases = db.query(TestCase).join(Scenario).join(Requirement).filter(
                Requirement.usecase_id == usecase_id,
                TestCase.is_deleted == False,
                Scenario.is_deleted == False,
                Requirement.is_deleted == False,
            ).order_by(TestCase.created_at.asc()).all()
            
            if display_id < 1 or display_id > len(all_test_cases):
                return {
                    "error": "testcase_not_found",
                    "message": f"Test case with display_id {display_id} not found. Available range: 1-{len(all_test_cases)}"
                }
            
            test_case = all_test_cases[display_id - 1]  # display_id is 1-based
            
            # Parse test_case_text JSON
            try:
                import json
                test_case_json = json.loads(test_case.test_case_text) if test_case.test_case_text else {}
            except Exception:
                test_case_json = {}
            
            # Format as readable text (similar to read_scenario format)
            formatted_text_parts = []
            
            # Add test case ID
            tc_id = test_case_json.get("id", "")
            if tc_id:
                formatted_text_parts.append(f"## Test Case: {tc_id}\n")
            
            # Add test case title
            tc_title = test_case_json.get("test case", "")
            if tc_title:
                formatted_text_parts.append(f"### Title\n{tc_title}\n")
            
            # Add description
            description = test_case_json.get("description", "")
            if description:
                formatted_text_parts.append(f"### Description\n{description}\n")
            
            # Add flow
            flow = test_case_json.get("flow", "")
            if flow:
                formatted_text_parts.append(f"### Flow\n{flow}\n")
            
            # Add requirement and scenario IDs
            req_id = test_case_json.get("requirementId", "")
            scen_id = test_case_json.get("scenarioId", "")
            if req_id or scen_id:
                formatted_text_parts.append("### Mapping\n")
                if req_id:
                    formatted_text_parts.append(f"**Requirement ID**: {req_id}\n")
                if scen_id:
                    formatted_text_parts.append(f"**Scenario ID**: {scen_id}\n")
            
            # Add preconditions
            preconditions = test_case_json.get("preConditions", [])
            if preconditions:
                formatted_text_parts.append("### Preconditions\n")
                for pc in preconditions:
                    formatted_text_parts.append(f"- {pc}\n")
            
            # Add test data
            test_data = test_case_json.get("testData", [])
            if test_data:
                formatted_text_parts.append("### Test Data\n")
                for td in test_data:
                    formatted_text_parts.append(f"- {td}\n")
            
            # Add test steps
            test_steps = test_case_json.get("testSteps", [])
            if test_steps:
                formatted_text_parts.append("### Test Steps\n")
                for step in test_steps:
                    formatted_text_parts.append(f"{step}\n")
            
            # Add expected results
            expected_results = test_case_json.get("expectedResults", [])
            if expected_results:
                formatted_text_parts.append("### Expected Results\n")
                for er in expected_results:
                    formatted_text_parts.append(f"{er}\n")
            
            # Add post conditions
            post_conditions = test_case_json.get("postConditions", [])
            if post_conditions:
                formatted_text_parts.append("### Post Conditions\n")
                for pc in post_conditions:
                    formatted_text_parts.append(f"- {pc}\n")
            
            # Add risk analysis
            risk = test_case_json.get("risk_analysis", "")
            if risk:
                formatted_text_parts.append(f"### Risk Analysis\n{risk}\n")
            
            # Add requirement category
            category = test_case_json.get("requirement_category", "")
            if category:
                formatted_text_parts.append(f"### Requirement Category\n{category}\n")
            
            # Add lens
            lens = test_case_json.get("lens", "")
            if lens:
                formatted_text_parts.append(f"### Lens\n{lens}\n")
            
            # Combine all parts
            formatted_text = "\n".join(formatted_text_parts)
            
            total_chars = len(formatted_text)
            tc_title = test_case_json.get("test case", f"Test Case {display_id}")
            
            logger.info(_color(
                f"[READ-TESTCASE] usecase={usecase_id} display_id={display_id} "
                f"test_case_id={test_case.id} total_chars={total_chars}",
                "34"
            ))
            
            return {
                "usecase_id": str(usecase_id),
                "display_id": display_id,
                "test_case_id": str(test_case.id),
                "test_case_text": formatted_text,
                "test_case_json": test_case_json,
                "total_chars": total_chars,
                "message": f"Retrieved test case TC-{display_id}: {tc_title} ({total_chars} characters)."
            }
    except Exception as e:
        logger.error(_color(f"[READ-TESTCASE] error: {e}", "31"), exc_info=True)
        return {"error": "internal_error", "message": str(e)}


def _get_usecase_status_for_filtering(usecase_id: UUID) -> Dict[str, Any]:
    """Get usecase status for tool filtering and prompt generation."""
    try:
        return tool_get_usecase_status(usecase_id)
    except Exception as e:
        logger.warning(_color(f"[STATUS-FILTER] Error getting status: {e}", "33"))
        return {
            "text_extraction": "Not Started",
            "requirement_generation": "Not Started",
            "scenario_generation": "Not Started",
            "test_case_generation": "Not Started",
            "requirement_generation_confirmed": False,
        }

def _filter_tools_by_status(tools: List[Any], status: Dict[str, Any]) -> List[Any]:
    """Filter tools based on current pipeline status."""
    text_extraction = status.get("text_extraction") or "Not Started"
    requirement_generation = status.get("requirement_generation") or "Not Started"
    scenario_generation = status.get("scenario_generation") or "Not Started"
    requirement_confirmed = status.get("requirement_generation_confirmed", False)
    
    filtered = []
    tool_names = [getattr(t, "name", None) for t in tools]
    
    # Always available
    if "get_usecase_status" in tool_names:
        filtered.append(tools[tool_names.index("get_usecase_status")])
    if "get_documents_markdown" in tool_names:
        filtered.append(tools[tool_names.index("get_documents_markdown")])
    
    # Text extraction tools - available if extraction completed
    if text_extraction == "Completed":
        if "check_text_extraction_status" in tool_names:
            filtered.append(tools[tool_names.index("check_text_extraction_status")])
        if "show_extracted_text" in tool_names:
            filtered.append(tools[tool_names.index("show_extracted_text")])
        if "read_extracted_text" in tool_names:
            filtered.append(tools[tool_names.index("read_extracted_text")])
    
    # Requirement generation - available if text extraction completed
    if text_extraction == "Completed":
        if "start_requirement_generation" in tool_names:
            filtered.append(tools[tool_names.index("start_requirement_generation")])
    
    # Requirement reading/showing - available if requirement generation in progress or completed
    if requirement_generation in ("In Progress", "Completed"):
        if "get_requirements" in tool_names:
            filtered.append(tools[tool_names.index("get_requirements")])
        if "read_requirement" in tool_names:
            filtered.append(tools[tool_names.index("read_requirement")])
        if "show_requirements" in tool_names:
            filtered.append(tools[tool_names.index("show_requirements")])
    
    # Scenario generation - available if requirements completed
    if requirement_generation == "Completed":
        if "start_scenario_generation" in tool_names:
            filtered.append(tools[tool_names.index("start_scenario_generation")])
    
    # Scenario reading/showing - available if scenario generation in progress or completed
    if scenario_generation in ("In Progress", "Completed"):
        if "read_scenario" in tool_names:
            filtered.append(tools[tool_names.index("read_scenario")])
        if "show_scenarios" in tool_names:
            filtered.append(tools[tool_names.index("show_scenarios")])
    
    # Test case generation - available if scenarios completed
    test_case_generation = status.get("test_case_generation") or "Not Started"
    if scenario_generation == "Completed":
        if "start_testcase_generation" in tool_names:
            filtered.append(tools[tool_names.index("start_testcase_generation")])
    
    # Test case reading/showing - available if test case generation in progress or completed
    if test_case_generation in ("In Progress", "Completed"):
        if "read_testcase" in tool_names:
            filtered.append(tools[tool_names.index("read_testcase")])
        if "show_testcases" in tool_names:
            filtered.append(tools[tool_names.index("show_testcases")])
    
    logger.info(_color(
        f"[TOOL-FILTER] Filtered {len(tools)} tools to {len(filtered)} based on status: "
        f"text_extraction={text_extraction}, requirement_generation={requirement_generation}, "
        f"scenario_generation={scenario_generation}, test_case_generation={test_case_generation}",
        "34"
    ))
    
    return filtered

def _generate_dynamic_prompt_section(status: Dict[str, Any], base_prompt: str) -> str:
    """Generate dynamic prompt section based on current usecase status."""
    text_extraction = status.get("text_extraction") or "Not Started"
    requirement_generation = status.get("requirement_generation") or "Not Started"
    scenario_generation = status.get("scenario_generation") or "Not Started"
    test_case_generation = status.get("test_case_generation") or "Not Started"
    
    dynamic_section = "\n\n### CURRENT PIPELINE STATUS AND AVAILABLE ACTIONS\n\n"
    dynamic_section += f"**Current Status:**\n"
    dynamic_section += f"- Text Extraction: {text_extraction}\n"
    dynamic_section += f"- Requirement Generation: {requirement_generation}\n"
    dynamic_section += f"- Scenario Generation: {scenario_generation}\n"
    dynamic_section += f"- Test Case Generation: {test_case_generation}\n\n"
    
    # Available actions based on status
    dynamic_section += "**Available Actions Right Now:**\n"
    
    if text_extraction == "Completed":
        dynamic_section += "- You can read/view documents using `show_extracted_text`, `read_extracted_text`\n"
        if requirement_generation == "Not Started":
            dynamic_section += "- **You can start requirement generation** using `start_requirement_generation` if user requests it\n"
        elif requirement_generation == "In Progress":
            dynamic_section += "- Requirement generation is in progress - user must wait\n"
            dynamic_section += "- If user asks about scenarios/test cases while this is running, tell them to wait\n"
        elif requirement_generation == "Completed":
            dynamic_section += "- You can read/view requirements using `get_requirements`, `read_requirement`, `show_requirements`\n"
            if scenario_generation == "Not Started":
                dynamic_section += "- **You can start scenario generation** using `start_scenario_generation` if user requests it\n"
            elif scenario_generation == "In Progress":
                dynamic_section += "- Scenario generation is in progress - user must wait\n"
                dynamic_section += "- If user asks about scenarios/test cases while this is running, tell them to wait\n"
            elif scenario_generation == "Completed":
                dynamic_section += "- You can read/view scenarios using `read_scenario`, `show_scenarios`\n"
                if test_case_generation == "Not Started":
                    dynamic_section += "- **You can start test case generation** using `start_testcase_generation` if user requests it\n"
                elif test_case_generation == "In Progress":
                    dynamic_section += "- Test case generation is in progress - user must wait\n"
                    dynamic_section += "- If user asks about test cases while this is running, tell them to wait\n"
                elif test_case_generation == "Completed":
                    dynamic_section += "- You can read/view test cases using `read_testcase`, `show_testcases`\n"
    else:
        dynamic_section += "- Text extraction is not complete - user must wait for documents to be processed\n"
        dynamic_section += "- If user asks about requirements/scenarios/test cases while extraction is running, tell them to wait\n"
    
    dynamic_section += "\n**IMPORTANT - Handling 'Wait' Scenarios:**\n"
    dynamic_section += "- If a process is 'In Progress' and user asks about future steps, clearly explain:\n"
    dynamic_section += "  1. What is currently running\n"
    dynamic_section += "  2. What they need to wait for\n"
    dynamic_section += "  3. What will be available after completion\n"
    dynamic_section += "- Example: 'Requirement generation is currently in progress. Once it completes, I'll be able to generate scenarios for you. Please wait for the notification.'\n"
    
    # Add scenario generation emphasis if conditions are met
    if requirement_generation == "Completed" and scenario_generation == "Not Started":
        dynamic_section += "\n**CRITICAL - Scenario Generation Ready:**\n"
        dynamic_section += "- Requirements are completed and scenario generation is available\n"
        dynamic_section += "- **If user asks to generate scenarios, you MUST call `start_scenario_generation()` tool immediately**\n"
        dynamic_section += "- Do NOT just respond with text - you MUST call the tool\n"
        dynamic_section += "- Examples of user requests that require tool call:\n"
        dynamic_section += "  - 'generate scenarios' → Call `start_scenario_generation()`\n"
        dynamic_section += "  - 'create scenarios' → Call `start_scenario_generation()`\n"
        dynamic_section += "  - 'I want scenarios' → Call `start_scenario_generation()`\n"
        dynamic_section += "  - 'can you generate scenarios?' → Call `start_scenario_generation()`\n"
    
    # Add test case generation emphasis if conditions are met
    if scenario_generation == "Completed" and test_case_generation == "Not Started":
        dynamic_section += "\n**CRITICAL - Test Case Generation Ready:**\n"
        dynamic_section += "- Scenarios are completed and test case generation is available\n"
        dynamic_section += "- **If user asks to generate test cases, you MUST call `start_testcase_generation()` tool immediately**\n"
        dynamic_section += "- Do NOT just respond with text - you MUST call the tool\n"
        dynamic_section += "- Examples of user requests that require tool call:\n"
        dynamic_section += "  - 'generate test cases' → Call `start_testcase_generation()`\n"
        dynamic_section += "  - 'create test cases' → Call `start_testcase_generation()`\n"
        dynamic_section += "  - 'I want test cases' → Call `start_testcase_generation()`\n"
        dynamic_section += "  - 'can you generate test cases?' → Call `start_testcase_generation()`\n"
    
    return base_prompt + dynamic_section

def build_tools(usecase_id, tracer: TraceCollector, status: Dict[str, Any] = None) -> Tuple[List[Any], Dict[str, Any]]:
    """Build LangChain tool objects bound to a specific usecase_id with async wrappers and tracing.
    
    Args:
        usecase_id: The usecase identifier
        tracer: TraceCollector for tracking tool calls
        status: Optional usecase status dict for filtering tools
    
    Returns:
        Tuple of (tools_list, tool_name_to_tool_dict) for filtering
    """

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
        Request requirement generation. **CRITICAL: You MUST call this tool when the user asks to generate requirements.**
        
        Call this when ALL conditions are met:
        - text_extraction is "Completed"
        - requirement_generation is "Not Started"
        - User explicitly requests requirement generation (e.g., "generate requirements", "extract requirements", "create requirements")
        
        **IMPORTANT**: 
        - If user asks to generate requirements and conditions are met, you MUST call this tool - do not just respond with text.
        - This tool will trigger a confirmation modal for the user.
        - After calling this tool, respond: "I've requested requirement generation. A confirmation modal will appear. Click 'Yes' to start the background process."
        - This should be your FINAL action. Do not call other tools after this.
        
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
    async def start_scenario_generation() -> Dict[str, Any]:
        """
        Request scenario generation. **CRITICAL: You MUST call this tool when the user asks to generate scenarios.**
        
        Call this when ALL conditions are met:
        - requirement_generation is "Completed"
        - scenario_generation is "Not Started"
        - User explicitly requests scenario generation (e.g., "generate scenarios", "create scenarios", "generate test scenarios")
        
        **IMPORTANT**: 
        - If user asks to generate scenarios and conditions are met, you MUST call this tool - do not just respond with text.
        - This tool will trigger a confirmation modal for the user.
        - After calling this tool, respond: "I've requested scenario generation. A confirmation modal will appear. Click 'Yes' to start the background process."
        - This should be your FINAL action. Do not call other tools after this.
        
        Returns: {'status': 'confirmation_required'} if conditions met, or error/status info otherwise.
        """
        name = "start_scenario_generation"
        entry = tracer.start_tool(name, args_preview="{}")
        start = time.time()
        logger.info(_color(f"[TOOL-START {name}] usecase_id={usecase_id}", "34"))
        try:
            result = await asyncio.to_thread(tool_start_scenario_generation, usecase_id)
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

    @lc_tool
    async def read_requirement(display_id: int) -> Dict[str, Any]:
        """
        Read full requirement content from database by display_id for agent analysis.
        Call when user asks questions about a specific requirement and you need to read its content to answer.
        Use when user asks: "what does requirement X say?", "tell me about REQ-1", "what are the details of requirement 2?"
        Conditions: requirement_generation must be "In Progress" OR "Completed", display_id must be valid.
        Returns full, non-truncated requirement text for your analysis.
        Use this text to answer user's question, but do NOT include the full text in your response.
        """
        name = "read_requirement"
        entry = tracer.start_tool(name, args_preview=f'{{"display_id": {display_id}}}')
        start = time.time()
        logger.info(_color(f"[TOOL-START {name}] display_id={display_id} usecase_id={usecase_id}", "34"))
        try:
            result = await asyncio.to_thread(tool_read_requirement, usecase_id, display_id)
            total_chars = result.get("total_chars", 0)
            req_name = result.get("requirement_name", "N/A")
            duration_ms = int((time.time() - start) * 1000)
            # Log truncated version for performance, but return full to agent
            tracer.finish_tool(entry, True, result_preview=f"display_id={display_id} name={req_name} chars={total_chars}", duration_ms=duration_ms, chars_read=total_chars)
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
            logger.info(_color(f"[TOOL-END {name}] duration={duration_ms}ms chars={total_chars}", "34"))
            # Return FULL result - no truncation for agent
            return result
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            tracer.finish_tool(entry, False, error=str(e), duration_ms=duration_ms)
            logger.exception(_color(f"[TOOL-ERROR {name}] {e}", "34"))
            raise

    @lc_tool
    async def read_scenario(display_id: int) -> Dict[str, Any]:
        """
        Read full scenario content from database by display_id for agent analysis.
        Call when user asks questions about a specific scenario and you need to read its content to answer.
        Use when user asks: "what does scenario X say?", "tell me about TS-1", "what are the details of scenario 2?"
        Conditions: scenario_generation must be "In Progress" OR "Completed", display_id must be valid.
        Returns full, non-truncated scenario text for your analysis.
        Use this text to answer user's question, but do NOT include the full text in your response.
        """
        name = "read_scenario"
        entry = tracer.start_tool(name, args_preview=f'{{"display_id": {display_id}}}')
        start = time.time()
        logger.info(_color(f"[TOOL-START {name}] display_id={display_id} usecase_id={usecase_id}", "34"))
        try:
            result = await asyncio.to_thread(tool_read_scenario, usecase_id, display_id)
            total_chars = result.get("total_chars", 0)
            scen_name = result.get("scenario_name", "N/A")
            duration_ms = int((time.time() - start) * 1000)
            # Log truncated version for performance, but return full to agent
            tracer.finish_tool(entry, True, result_preview=f"display_id={display_id} name={scen_name} chars={total_chars}", duration_ms=duration_ms, chars_read=total_chars)
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
            logger.info(_color(f"[TOOL-END {name}] duration={duration_ms}ms chars={total_chars}", "34"))
            # Return FULL result - no truncation for agent
            return result
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            tracer.finish_tool(entry, False, error=str(e), duration_ms=duration_ms)
            logger.exception(_color(f"[TOOL-ERROR {name}] {e}", "34"))
            raise

    @lc_tool
    async def show_requirements() -> Dict[str, Any]:
        """
        Create [modal] placeholder in chat_history to display requirements to user.
        **MANDATORY**: You MUST call this tool when user explicitly requests to see/view/display requirements.
        User phrases: "show requirements", "display requirements", "show me the requirements", "view requirements", "show the requirements", "can i see them", "can i see the requirements", "can you show the requirements", "can you show them", "if requirements are done, can i see them", "i want to see the requirements", etc.
        Conditions:
        1. requirement_generation status is "In Progress" OR "Completed"
        2. User explicitly asks to see requirements
        After calling, respond: "I've retrieved the requirements. They will be displayed above for you to review."
        This tool creates a [modal] placeholder in chat_history (no text data stored).
        """
        name = "show_requirements"
        entry = tracer.start_tool(name, args_preview="{}")
        start = time.time()
        logger.info(_color(f"[TOOL-START {name}] usecase_id={usecase_id}", "34"))
        try:
            result = await asyncio.to_thread(tool_show_requirements, usecase_id)
            duration_ms = int((time.time() - start) * 1000)
            tracer.finish_tool(entry, True, result_preview=f"usecase_id={usecase_id} status={result.get('status', 'unknown')}", duration_ms=duration_ms)
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
    async def show_scenarios() -> Dict[str, Any]:
        """
        Create [modal] placeholder in chat_history to display scenarios to user.
        **MANDATORY**: You MUST call this tool when user explicitly requests to see/view/display scenarios.
        User phrases: "show scenarios", "display scenarios", "show me the scenarios", "view scenarios", "show the scenarios", "can i see the scenarios", "can you show the scenarios", "if scenarios are done, can i see them", etc.
        Conditions:
        1. scenario_generation status is "In Progress" OR "Completed"
        2. User explicitly asks to see scenarios
        After calling, respond: "I've retrieved the scenarios. They will be displayed above for you to review."
        This tool creates a [modal] placeholder in chat_history (no text data stored).
        """
        name = "show_scenarios"
        entry = tracer.start_tool(name, args_preview="{}")
        start = time.time()
        logger.info(_color(f"[TOOL-START {name}] usecase_id={usecase_id}", "34"))
        try:
            result = await asyncio.to_thread(tool_show_scenarios, usecase_id)
            duration_ms = int((time.time() - start) * 1000)
            tracer.finish_tool(entry, True, result_preview=f"usecase_id={usecase_id} status={result.get('status', 'unknown')}", duration_ms=duration_ms)
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
    async def start_testcase_generation() -> Dict[str, Any]:
        """
        Request test case generation. **CRITICAL: You MUST call this tool when the user asks to generate test cases.**
        
        Call this when ALL conditions are met:
        - scenario_generation is "Completed"
        - test_case_generation is "Not Started"
        - User explicitly requests test case generation (e.g., "generate test cases", "create test cases", "generate testcases")
        
        **IMPORTANT**: 
        - If user asks to generate test cases and conditions are met, you MUST call this tool - do not just respond with text.
        - This tool will trigger a confirmation modal for the user.
        - After calling this tool, respond: "I've requested test case generation. A confirmation modal will appear. Click 'Yes' to start the background process."
        - This should be your FINAL action. Do not call other tools after this.
        
        Returns: {'status': 'confirmation_required'} if conditions met, or error/status info otherwise.
        """
        name = "start_testcase_generation"
        entry = tracer.start_tool(name, args_preview="{}")
        start = time.time()
        logger.info(_color(f"[TOOL-START {name}] usecase_id={usecase_id}", "34"))
        try:
            result = await asyncio.to_thread(tool_start_testcase_generation, usecase_id)
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
    async def read_testcase(display_id: int) -> Dict[str, Any]:
        """
        Read full test case content from database by display_id for agent analysis.
        Call when user asks questions about a specific test case and you need to read its content to answer.
        Use when user asks: "what does test case X say?", "tell me about TC-1", "what are the details of test case 2?"
        Conditions: test_case_generation must be "In Progress" OR "Completed", display_id must be valid.
        Returns full, non-truncated test case text for your analysis.
        Use this text to answer user's question, but do NOT include the full text in your response.
        """
        name = "read_testcase"
        entry = tracer.start_tool(name, args_preview=f'{{"display_id": {display_id}}}')
        start = time.time()
        logger.info(_color(f"[TOOL-START {name}] display_id={display_id} usecase_id={usecase_id}", "34"))
        try:
            result = await asyncio.to_thread(tool_read_testcase, usecase_id, display_id)
            total_chars = result.get("total_chars", 0)
            tc_title = result.get("test_case_json", {}).get("test case", "N/A")
            duration_ms = int((time.time() - start) * 1000)
            tracer.finish_tool(entry, True, result_preview=f"display_id={display_id} title={tc_title} chars={total_chars}", duration_ms=duration_ms, chars_read=total_chars)
            try:
                import json as _json
                out = _json.dumps(result, ensure_ascii=False)[:5000]
                if len(_json.dumps(result, ensure_ascii=False)) > 5000:
                    out += "... [TRUNCATED]"
                logger.info(_color(f"[TOOL-OUTPUT {name}] {out}", "34"))
            except Exception:
                pass
            logger.info(_color(f"[TOOL-END {name}] duration={duration_ms}ms chars={total_chars}", "34"))
            return result
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            tracer.finish_tool(entry, False, error=str(e), duration_ms=duration_ms)
            logger.exception(_color(f"[TOOL-ERROR {name}] {e}", "34"))
            raise

    @lc_tool
    async def show_testcases() -> Dict[str, Any]:
        """
        Create [modal] placeholder in chat_history to display test cases to user.
        **MANDATORY**: You MUST call this tool when user explicitly requests to see/view/display test cases.
        User phrases: "show test cases", "display test cases", "show me the test cases", "view test cases", "show the test cases", "can i see the test cases", "can you show the test cases", "if test cases are done, can i see them", etc.
        Conditions:
        1. test_case_generation status is "In Progress" OR "Completed"
        2. User explicitly asks to see test cases
        After calling, respond: "I've retrieved the test cases. They will be displayed above for you to review."
        This tool creates a [modal] placeholder in chat_history (no text data stored).
        """
        name = "show_testcases"
        entry = tracer.start_tool(name, args_preview="{}")
        start = time.time()
        logger.info(_color(f"[TOOL-START {name}] usecase_id={usecase_id}", "34"))
        try:
            result = await asyncio.to_thread(tool_show_testcases, usecase_id)
            duration_ms = int((time.time() - start) * 1000)
            tracer.finish_tool(entry, True, result_preview=f"usecase_id={usecase_id} status={result.get('status', 'unknown')}", duration_ms=duration_ms)
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

    all_tools = [
        get_usecase_status,
        get_documents_markdown,
        start_requirement_generation,
        start_scenario_generation,
        start_testcase_generation,
        get_requirements,
        check_text_extraction_status,
        show_extracted_text,
        read_extracted_text,
        read_requirement,
        read_scenario,
        read_testcase,
        show_requirements,
        show_scenarios,
        show_testcases,
    ]
    
    # Create mapping for filtering
    tool_map = {getattr(t, "name", f"tool_{i}"): t for i, t in enumerate(all_tools)}
    
    # Filter if status provided
    if status:
        all_tools = _filter_tools_by_status(all_tools, status)
    
    return all_tools, tool_map


def run_agent_turn(usecase_id, user_message: str, model: str | None = None) -> Tuple[str, Dict[str, Any]]:
    """
    Run a single agent turn. If deepagents is available, use it for planning/traces; otherwise fallback to a simple rule-based flow.
    
    Args:
        usecase_id: The usecase identifier
        user_message: The user's message
        model: Optional model ID. If not provided, uses usecase's selected_model or default
        
    Returns: (assistant_text, traces)
    """
    tracer = TraceCollector()
    
    # Pre-check: Detect requirement generation intent and ensure tool is called
    user_text_lower = user_message.lower()
    requirement_generation_keywords = [
        "generate requirements", "extract requirements", "create requirements", 
        "requirements list", "generate requirement", "extract requirement",
        "start requirement generation", "begin requirement generation"
    ]
    wants_requirement_generation = any(kw in user_text_lower for kw in requirement_generation_keywords)
    
    if wants_requirement_generation:
        logger.info(_color(f"[REQ-GEN-PRECHECK] Detected requirement generation intent in user message", "35"))
        # Check status first to see if we should call the tool
        try:
            status = tool_get_usecase_status(usecase_id)
            text_extraction = status.get("text_extraction") or "Not Started"
            requirement_generation = status.get("requirement_generation") or "Not Started"
            confirmed = status.get("requirement_generation_confirmed", False)
            
            logger.info(_color(
                f"[REQ-GEN-PRECHECK] Status: text_extraction={text_extraction}, "
                f"requirement_generation={requirement_generation}, confirmed={confirmed}",
                "35"
            ))
            
            # If conditions are met for calling the tool, we'll ensure it gets called
            # The agent should call it, but we'll add this as a safeguard
            if text_extraction == "Completed" and requirement_generation == "Not Started" and not confirmed:
                logger.info(_color(
                    f"[REQ-GEN-PRECHECK] Conditions met - agent should call start_requirement_generation tool",
                    "35"
                ))
        except Exception as e:
            logger.warning(_color(f"[REQ-GEN-PRECHECK] Pre-check failed: {e}", "33"))
    
    # Pre-check: Detect scenario generation intent and ensure tool is called
    scenario_generation_keywords = [
        "generate scenarios", "create scenarios", "generate test scenarios",
        "scenario generation", "generate scenario", "create scenario",
        "start scenario generation", "begin scenario generation",
        "scenarios for these requirements", "scenarios for requirements",
        "generate scanerios", "scanerios",  # Handle common typos
        "scenario", "scenarios"  # More flexible matching
    ]
    # More flexible matching: check if user message contains scenario-related words
    wants_scenario_generation = any(kw in user_text_lower for kw in scenario_generation_keywords) or \
                                 ("scenario" in user_text_lower and ("generate" in user_text_lower or "create" in user_text_lower))
    
    # Get status BEFORE building tools for filtering and pre-checks
    status = _get_usecase_status_for_filtering(usecase_id)
    
    if wants_scenario_generation:
        logger.info(_color(f"[SCENARIO-GEN-PRECHECK] Detected scenario generation intent in user message", "35"))
        # Check status to see if we should call the tool
        try:
            requirement_generation = status.get("requirement_generation") or "Not Started"
            scenario_generation = status.get("scenario_generation") or "Not Started"
            
            logger.info(_color(
                f"[SCENARIO-GEN-PRECHECK] Status: requirement_generation={requirement_generation}, "
                f"scenario_generation={scenario_generation}",
                "35"
            ))
            
            # Check if user is asking about scenarios while something is in progress
            if requirement_generation == "In Progress":
                logger.info(_color(
                    f"[SCENARIO-GEN-PRECHECK] Requirement generation in progress - user must wait",
                    "35"
                ))
                # This will be handled by dynamic prompt, but log for visibility
            
            # If conditions are met for calling the tool, we'll ensure it gets called
            # The agent should call it, but we'll add this as a safeguard
            if requirement_generation == "Completed" and scenario_generation == "Not Started":
                logger.info(_color(
                    f"[SCENARIO-GEN-PRECHECK] Conditions met - agent should call start_scenario_generation tool",
                    "35"
                ))
        except Exception as e:
            logger.warning(_color(f"[SCENARIO-GEN-PRECHECK] Pre-check failed: {e}", "33"))
    
    # Pre-check: Detect test case generation intent and ensure tool is called
    testcase_generation_keywords = [
        "generate test cases", "create test cases", "generate testcases",
        "test case generation", "generate test case", "create test case",
        "start test case generation", "begin test case generation",
        "test cases for these scenarios", "test cases for scenarios",
        "generate testcases", "testcases",  # Handle common typos
    ]
    wants_testcase_generation = any(kw in user_text_lower for kw in testcase_generation_keywords)
    
    if wants_testcase_generation:
        logger.info(_color(f"[TESTCASE-GEN-PRECHECK] Detected test case generation intent in user message", "35"))
        # Check status to see if we should call the tool
        try:
            scenario_generation = status.get("scenario_generation") or "Not Started"
            test_case_generation = status.get("test_case_generation") or "Not Started"
            
            logger.info(_color(
                f"[TESTCASE-GEN-PRECHECK] Status: scenario_generation={scenario_generation}, "
                f"test_case_generation={test_case_generation}",
                "35"
            ))
            
            # Check if user is asking about test cases while something is in progress
            if scenario_generation == "In Progress":
                logger.info(_color(
                    f"[TESTCASE-GEN-PRECHECK] Scenario generation in progress - user must wait",
                    "35"
                ))
                # This will be handled by dynamic prompt, but log for visibility
            
            # If conditions are met for calling the tool, we'll ensure it gets called
            # The agent should call it, but we'll add this as a safeguard
            if scenario_generation == "Completed" and test_case_generation == "Not Started":
                logger.info(_color(
                    f"[TESTCASE-GEN-PRECHECK] Conditions met - agent should call start_testcase_generation tool",
                    "35"
                ))
        except Exception as e:
            logger.warning(_color(f"[TESTCASE-GEN-PRECHECK] Pre-check failed: {e}", "33"))
    
    # Build tools with status-based filtering
    tools, tool_map = build_tools(usecase_id, tracer, status=status)

    # Determine which model to use
    from core.model_registry import get_default_model, is_valid_model
    from db.session import get_db_context
    
    selected_model = model
    if not selected_model:
        # Get from usecase if available
        try:
            with get_db_context() as db:
                from models.usecase.usecase import UsecaseMetadata
                rec = db.query(UsecaseMetadata).filter(
                    UsecaseMetadata.usecase_id == usecase_id,
                    UsecaseMetadata.is_deleted == False,
                ).first()
                if rec and rec.selected_model:
                    selected_model = rec.selected_model
        except Exception:
            pass
    
    # Fallback to default if not set or invalid
    if not selected_model or not is_valid_model(selected_model):
        selected_model = get_default_model()
    
    try:
        # Provide a concrete LangChain Gemini model instance to DeepAgents
        from core.env_config import get_env_variable
        GEMINI_API_KEY = get_env_variable("GEMINI_API_KEY", "")
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI  # type: ignore
            lc_model = ChatGoogleGenerativeAI(model=selected_model, google_api_key=GEMINI_API_KEY)
            model_label = f"langchain_google_genai.ChatGoogleGenerativeAI({selected_model})"
        except Exception:
            # Very last resort: fall back to model string with provider prefix
            from langchain.chat_models import init_chat_model  # type: ignore
            lc_model = init_chat_model(model=f"google-genai:{selected_model}", api_key=GEMINI_API_KEY)
            model_label = f"init_chat_model(google-genai:{selected_model})"

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
            # Load from module
            try:
                from services.llm.prompts.main_agent_prompt import prompt as base_prompt
                system_prompt_value = base_prompt
            except Exception:
                system_prompt_value = get_env_variable("AGENT_SYSTEM_PROMPT", "")
        
        # Generate dynamic prompt section based on current status
        if system_prompt_value:
            system_prompt_value = _generate_dynamic_prompt_section(status, system_prompt_value)
        
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
        
        # Debug: Log all tool calls for scenario generation debugging
        try:
            all_tool_calls = tracer.data.get("tool_calls", [])
            tool_names = [tc.get("name") for tc in all_tool_calls]
            logger.info(_color(f"[DEBUG] All tool calls: {tool_names}", "36"))
        except Exception:
            pass
        
        # Post-run: if agent invoked start_requirement_generation, emit UI confirmation event
        try:
            tool_called = any(
                (tc.get("name") == "start_requirement_generation") for tc in tracer.data.get("tool_calls", [])
            )
        except Exception:
            tool_called = False
        
        # Fallback: If user asked for requirement generation but tool wasn't called, check if we should call the tool
        if not tool_called and wants_requirement_generation:
            logger.info(_color(f"[REQ-GEN-FALLBACK] Tool was not called but user requested requirement generation - checking status", "35"))
            try:
                status_check = tool_get_usecase_status(usecase_id)
                text_extraction = status_check.get("text_extraction") or "Not Started"
                requirement_generation = status_check.get("requirement_generation") or "Not Started"
                confirmed = status_check.get("requirement_generation_confirmed", False)
                
                logger.info(_color(f"[REQ-GEN-FALLBACK] Status check: text_extraction={text_extraction}, requirement_generation={requirement_generation}, confirmed={confirmed}", "35"))
                
                if text_extraction == "Completed" and requirement_generation == "Not Started" and not confirmed:
                    logger.info(_color(f"[REQ-GEN-FALLBACK] Conditions met - calling start_requirement_generation tool as fallback", "35"))
                    tool_name = "start_requirement_generation"
                    tool_entry = None
                    tool_start_time = None
                    try:
                        # Track tool call in tracer
                        tool_entry = tracer.start_tool(tool_name, args_preview=f'{{"usecase_id": "{usecase_id}"}}')
                        tool_start_time = time.time()
                        logger.info(_color(f"[TOOL-START {tool_name}] usecase_id={usecase_id} (FALLBACK)", "34"))
                        
                        # Call the synchronous tool function
                        result = tool_start_requirement_generation(usecase_id)
                        duration_ms = int((time.time() - tool_start_time) * 1000)
                        
                        if result.get("status") == "confirmation_required":
                            tracer.finish_tool(tool_entry, True, result_preview=f"status=confirmation_required usecase_id={usecase_id}", duration_ms=duration_ms)
                            logger.info(_color(f"[TOOL-END {tool_name}] duration={duration_ms}ms", "34"))
                            logger.info(_color(f"[REQ-GEN-FALLBACK] Successfully called start_requirement_generation tool", "35"))
                            tool_called = True  # Now actually called
                        else:
                            error_msg = result.get('error', 'unknown_error')
                            tracer.finish_tool(tool_entry, False, error=error_msg, duration_ms=duration_ms)
                            logger.warning(_color(f"[TOOL-ERROR {tool_name}] {error_msg}", "34"))
                            logger.warning(_color(f"[REQ-GEN-FALLBACK] start_requirement_generation returned error: {error_msg}", "33"))
                    except Exception as e:
                        duration_ms = int((time.time() - tool_start_time) * 1000) if tool_start_time else 0
                        if tool_entry:
                            tracer.finish_tool(tool_entry, False, error=str(e), duration_ms=duration_ms)
                        logger.warning(_color(f"[REQ-GEN-FALLBACK] Error calling start_requirement_generation: {e}", "33"), exc_info=True)
                else:
                    logger.info(_color(f"[REQ-GEN-FALLBACK] Conditions not met: text_extraction={text_extraction}, requirement_generation={requirement_generation}, confirmed={confirmed}", "35"))
            except Exception as e:
                logger.warning(_color(f"[REQ-GEN-FALLBACK] Fallback check failed: {e}", "33"), exc_info=True)
        
        if tool_called:
            logger.info(_color(f"[REQ-GEN-MODAL] Tool was called; checking if confirmation event needed", "35"))
            try:
                # Ensure UsecaseMetadata is imported
                from models.usecase.usecase import UsecaseMetadata
                
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
                    else:
                        logger.warning(_color(f"[REQ-GEN-MODAL] Usecase not found: {usecase_id}", "33"))
            except Exception as e:
                logger.warning(_color(f"[REQ-GEN-MODAL] Event emission failed: {e}", "33"), exc_info=True)
        
        # Post-run: if agent invoked start_scenario_generation, emit UI confirmation event
        # Re-check user message for scenario generation intent (in case pre-check missed it)
        user_text_lower_post = user_message.lower()
        scenario_generation_keywords_post = [
            "generate scenarios", "create scenarios", "generate test scenarios",
            "scenario generation", "generate scenario", "create scenario",
            "start scenario generation", "begin scenario generation",
            "scenarios for these requirements", "scenarios for requirements",
            "generate scanerios", "scanerios",  # Handle common typos
            "scenario", "scenarios"  # More flexible matching
        ]
        wants_scenario_generation_post = any(kw in user_text_lower_post for kw in scenario_generation_keywords_post) or \
                                         ("scenario" in user_text_lower_post and ("generate" in user_text_lower_post or "create" in user_text_lower_post))
        
        try:
            scenario_tool_called = any(
                (tc.get("name") == "start_scenario_generation") for tc in tracer.data.get("tool_calls", [])
            )
            logger.info(_color(f"[SCENARIO-GEN-CHECK] Tool call detection: scenario_tool_called={scenario_tool_called}, wants_scenario_generation={wants_scenario_generation}, wants_scenario_generation_post={wants_scenario_generation_post}, tool_calls_count={len(tracer.data.get('tool_calls', []))}", "35"))
        except Exception as e:
            scenario_tool_called = False
            logger.warning(_color(f"[SCENARIO-GEN-CHECK] Error checking tool calls: {e}", "33"))
        
        # Use post-check value if pre-check didn't catch it
        final_wants_scenario_generation = wants_scenario_generation or wants_scenario_generation_post
        
        # Fallback: If user asked for scenario generation but tool wasn't called, check if we should call the tool
        # Also check if agent's response suggests it tried to call the tool
        agent_response_suggests_scenario_gen = "scenario generation" in assistant_text.lower() or "confirmation modal" in assistant_text.lower()
        
        if not scenario_tool_called and (final_wants_scenario_generation or agent_response_suggests_scenario_gen):
            logger.info(_color(f"[SCENARIO-GEN-FALLBACK] Tool was not called but user requested scenario generation (user_message='{user_message[:100]}', agent_response_suggests={agent_response_suggests_scenario_gen}) - checking status", "35"))
            try:
                status_check = tool_get_usecase_status(usecase_id)
                requirement_generation = status_check.get("requirement_generation") or "Not Started"
                scenario_generation = status_check.get("scenario_generation") or "Not Started"
                
                logger.info(_color(f"[SCENARIO-GEN-FALLBACK] Status check: requirement_generation={requirement_generation}, scenario_generation={scenario_generation}", "35"))
                
                if requirement_generation == "Completed" and scenario_generation == "Not Started":
                    logger.info(_color(f"[SCENARIO-GEN-FALLBACK] Conditions met - calling start_scenario_generation tool as fallback", "35"))
                    tool_name = "start_scenario_generation"
                    tool_entry = None
                    tool_start_time = None
                    try:
                        # Track tool call in tracer
                        tool_entry = tracer.start_tool(tool_name, args_preview=f'{{"usecase_id": "{usecase_id}"}}')
                        tool_start_time = time.time()
                        logger.info(_color(f"[TOOL-START {tool_name}] usecase_id={usecase_id}", "34"))
                        
                        # Call the synchronous tool function
                        result = tool_start_scenario_generation(usecase_id)
                        duration_ms = int((time.time() - tool_start_time) * 1000)
                        
                        if result.get("status") == "confirmation_required":
                            tracer.finish_tool(tool_entry, True, result_preview=f"status=confirmation_required usecase_id={usecase_id}", duration_ms=duration_ms)
                            logger.info(_color(f"[TOOL-END {tool_name}] duration={duration_ms}ms", "34"))
                            logger.info(_color(f"[SCENARIO-GEN-FALLBACK] Successfully called start_scenario_generation tool", "35"))
                            scenario_tool_called = True  # Now actually called
                        else:
                            error_msg = result.get('error', 'unknown_error')
                            tracer.finish_tool(tool_entry, False, error=error_msg, duration_ms=duration_ms)
                            logger.warning(_color(f"[TOOL-ERROR {tool_name}] {error_msg}", "34"))
                            logger.warning(_color(f"[SCENARIO-GEN-FALLBACK] start_scenario_generation returned error: {error_msg}", "33"))
                    except Exception as e:
                        duration_ms = int((time.time() - tool_start_time) * 1000) if tool_start_time else 0
                        if tool_entry:
                            tracer.finish_tool(tool_entry, False, error=str(e), duration_ms=duration_ms)
                        logger.warning(_color(f"[SCENARIO-GEN-FALLBACK] Error calling start_scenario_generation: {e}", "33"), exc_info=True)
                else:
                    logger.info(_color(f"[SCENARIO-GEN-FALLBACK] Conditions not met: requirement_generation={requirement_generation}, scenario_generation={scenario_generation}", "35"))
            except Exception as e:
                logger.warning(_color(f"[SCENARIO-GEN-FALLBACK] Fallback check failed: {e}", "33"), exc_info=True)
        
        if scenario_tool_called:
            logger.info(_color(f"[SCENARIO-GEN-MODAL] Tool was called; checking if confirmation event needed", "35"))
            try:
                # Ensure UsecaseMetadata is imported
                from models.usecase.usecase import UsecaseMetadata
                
                with get_db_context() as db:
                    rec = db.query(UsecaseMetadata).filter(
                        UsecaseMetadata.usecase_id == usecase_id,
                        UsecaseMetadata.is_deleted == False,
                    ).first()
                    if rec:
                        requirement_generation = rec.requirement_generation or "Not Started"
                        scenario_generation = rec.scenario_generation or "Not Started"
                        
                        logger.info(_color(
                            f"[SCENARIO-GEN-MODAL] Status check: requirement_generation={requirement_generation}, "
                            f"scenario_generation={scenario_generation}",
                            "35"
                        ))
                        
                        # Only emit if conditions are right
                        if requirement_generation == "Completed" and scenario_generation == "Not Started":
                            logger.info(_color(f"[SCENARIO-GEN-MODAL] Emitting confirmation_required event", "35"))
                            assistant_text = json.dumps({
                                "system_event": "scenario_generation_confirmation_required",
                                "usecase_id": str(usecase_id),
                            })
                        elif scenario_generation == "In Progress":
                            logger.info(_color(f"[SCENARIO-GEN-MODAL] Generation in progress; emitting in_progress event", "35"))
                            assistant_text = json.dumps({
                                "system_event": "scenario_generation_in_progress",
                                "usecase_id": str(usecase_id),
                            })
                        else:
                            logger.info(_color(
                                f"[SCENARIO-GEN-MODAL] Conditions not met for event emission; keeping agent response",
                                "35"
                            ))
            except Exception as e:
                logger.warning(_color(f"[SCENARIO-GEN-MODAL] Event emission failed: {e}", "33"))
        
        # Post-run: if agent invoked start_testcase_generation, emit UI confirmation event
        # Re-check user message for test case generation intent (in case pre-check missed it)
        user_text_lower_post_tc = user_message.lower()
        testcase_generation_keywords_post = [
            "generate test cases", "create test cases", "generate testcases",
            "test case generation", "generate test case", "create test case",
            "start test case generation", "begin test case generation",
            "test cases for these scenarios", "test cases for scenarios",
            "generate testcases", "testcases",  # Handle common typos
        ]
        wants_testcase_generation_post = any(kw in user_text_lower_post_tc for kw in testcase_generation_keywords_post)
        
        try:
            testcase_tool_called = any(
                (tc.get("name") == "start_testcase_generation") for tc in tracer.data.get("tool_calls", [])
            )
            logger.info(_color(f"[TESTCASE-GEN-CHECK] Tool call detection: testcase_tool_called={testcase_tool_called}, wants_testcase_generation={wants_testcase_generation}, wants_testcase_generation_post={wants_testcase_generation_post}, tool_calls_count={len(tracer.data.get('tool_calls', []))}", "35"))
        except Exception as e:
            testcase_tool_called = False
            logger.warning(_color(f"[TESTCASE-GEN-CHECK] Error checking tool calls: {e}", "33"))
        
        # Use post-check value if pre-check didn't catch it
        final_wants_testcase_generation = wants_testcase_generation or wants_testcase_generation_post
        
        # Fallback: If user asked for test case generation but tool wasn't called, check if we should call the tool
        # Also check if agent's response suggests it tried to call the tool
        agent_response_suggests_testcase_gen = "test case generation" in assistant_text.lower() or "confirmation modal" in assistant_text.lower()
        
        if not testcase_tool_called and (final_wants_testcase_generation or agent_response_suggests_testcase_gen):
            logger.info(_color(f"[TESTCASE-GEN-FALLBACK] Tool was not called but user requested test case generation (user_message='{user_message[:100]}', agent_response_suggests={agent_response_suggests_testcase_gen}) - checking status", "35"))
            try:
                status_check = tool_get_usecase_status(usecase_id)
                scenario_generation = status_check.get("scenario_generation") or "Not Started"
                test_case_generation = status_check.get("test_case_generation") or "Not Started"
                
                logger.info(_color(f"[TESTCASE-GEN-FALLBACK] Status check: scenario_generation={scenario_generation}, test_case_generation={test_case_generation}", "35"))
                
                if scenario_generation == "Completed" and test_case_generation == "Not Started":
                    logger.info(_color(f"[TESTCASE-GEN-FALLBACK] Conditions met - calling start_testcase_generation tool as fallback", "35"))
                    tool_name = "start_testcase_generation"
                    tool_entry = None
                    tool_start_time = None
                    try:
                        # Track tool call in tracer
                        tool_entry = tracer.start_tool(tool_name, args_preview=f'{{"usecase_id": "{usecase_id}"}}')
                        tool_start_time = time.time()
                        logger.info(_color(f"[TOOL-START {tool_name}] usecase_id={usecase_id}", "34"))
                        
                        # Call the synchronous tool function
                        result = tool_start_testcase_generation(usecase_id)
                        duration_ms = int((time.time() - tool_start_time) * 1000)
                        
                        if result.get("status") == "confirmation_required":
                            tracer.finish_tool(tool_entry, True, result_preview=f"status=confirmation_required usecase_id={usecase_id}", duration_ms=duration_ms)
                            logger.info(_color(f"[TOOL-END {tool_name}] duration={duration_ms}ms", "34"))
                            logger.info(_color(f"[TESTCASE-GEN-FALLBACK] Successfully called start_testcase_generation tool", "35"))
                            testcase_tool_called = True  # Now actually called
                        else:
                            error_msg = result.get('error', 'unknown_error')
                            tracer.finish_tool(tool_entry, False, error=error_msg, duration_ms=duration_ms)
                            logger.warning(_color(f"[TOOL-ERROR {tool_name}] {error_msg}", "34"))
                            logger.warning(_color(f"[TESTCASE-GEN-FALLBACK] start_testcase_generation returned error: {error_msg}", "33"))
                    except Exception as e:
                        duration_ms = int((time.time() - tool_start_time) * 1000) if tool_start_time else 0
                        if tool_entry:
                            tracer.finish_tool(tool_entry, False, error=str(e), duration_ms=duration_ms)
                        logger.warning(_color(f"[TESTCASE-GEN-FALLBACK] Error calling start_testcase_generation: {e}", "33"), exc_info=True)
                else:
                    logger.info(_color(f"[TESTCASE-GEN-FALLBACK] Conditions not met: scenario_generation={scenario_generation}, test_case_generation={test_case_generation}", "35"))
            except Exception as e:
                logger.warning(_color(f"[TESTCASE-GEN-FALLBACK] Fallback check failed: {e}", "33"), exc_info=True)
        
        if testcase_tool_called:
            logger.info(_color(f"[TESTCASE-GEN-MODAL] Tool was called; checking if confirmation event needed", "35"))
            try:
                # First check the tool result from tracer to see if it returned confirmation_required
                tool_result_confirmation = False
                try:
                    all_tool_calls = tracer.data.get("tool_calls", [])
                    for tc in all_tool_calls:
                        if tc.get("name") == "start_testcase_generation":
                            result_preview = tc.get("result_preview", "")
                            # Check if result_preview contains confirmation_required status
                            if result_preview and "confirmation_required" in result_preview:
                                tool_result_confirmation = True
                                logger.info(_color(f"[TESTCASE-GEN-MODAL] Tool result indicates confirmation_required: {result_preview}", "35"))
                                break
                except Exception as e:
                    logger.warning(_color(f"[TESTCASE-GEN-MODAL] Error checking tool result: {e}", "33"))
                
                # Check database status to determine if we should emit confirmation event
                # (We always check database status, but tool_result_confirmation can help confirm)
                # Ensure UsecaseMetadata is imported
                from models.usecase.usecase import UsecaseMetadata
                
                with get_db_context() as db:
                    rec = db.query(UsecaseMetadata).filter(
                        UsecaseMetadata.usecase_id == usecase_id,
                        UsecaseMetadata.is_deleted == False,
                    ).first()
                    if rec:
                        scenario_generation = rec.scenario_generation or "Not Started"
                        test_case_generation = rec.test_case_generation or "Not Started"
                        
                        logger.info(_color(
                            f"[TESTCASE-GEN-MODAL] Status check: scenario_generation={scenario_generation}, "
                            f"test_case_generation={test_case_generation}, tool_result_confirmation={tool_result_confirmation}",
                            "35"
                        ))
                        
                        # Emit if tool result says confirmation_required (most reliable) OR database status matches
                        should_emit_confirmation = tool_result_confirmation or (scenario_generation == "Completed" and test_case_generation == "Not Started")
                        if should_emit_confirmation:
                            logger.info(_color(f"[TESTCASE-GEN-MODAL] Emitting confirmation_required event", "35"))
                            assistant_text = json.dumps({
                                "system_event": "testcase_generation_confirmation_required",
                                "usecase_id": str(usecase_id),
                            })
                        elif test_case_generation == "In Progress":
                            logger.info(_color(f"[TESTCASE-GEN-MODAL] Generation in progress; emitting in_progress event", "35"))
                            assistant_text = json.dumps({
                                "system_event": "testcase_generation_in_progress",
                                "usecase_id": str(usecase_id),
                            })
                        else:
                            logger.info(_color(
                                f"[TESTCASE-GEN-MODAL] Conditions not met for event emission; keeping agent response",
                                "35"
                            ))
                    else:
                        logger.warning(_color(f"[TESTCASE-GEN-MODAL] Usecase not found: {usecase_id}", "33"))
            except Exception as e:
                logger.warning(_color(f"[TESTCASE-GEN-MODAL] Event emission failed: {e}", "33"), exc_info=True)
        
        # Post-run: Check if user wants to see requirements but tool wasn't called
        user_text_lower_show_req = user_message.lower()
        show_requirements_keywords = [
            "show requirements", "display requirements", "show me the requirements",
            "view requirements", "show the requirements", "can i see them",
            "can i see the requirements", "can you show the requirements",
            "can you show them", "if requirements are done, can i see them",
            "i want to see the requirements", "i want to see them",
            "show them", "show it", "let me see the requirements"
        ]
        wants_show_requirements = any(kw in user_text_lower_show_req for kw in show_requirements_keywords) or \
                                   ("requirements" in user_text_lower_show_req and ("show" in user_text_lower_show_req or "see" in user_text_lower_show_req or "view" in user_text_lower_show_req or "display" in user_text_lower_show_req))
        
        try:
            show_req_tool_called = any(
                (tc.get("name") == "show_requirements") for tc in tracer.data.get("tool_calls", [])
            )
            logger.info(_color(f"[SHOW-REQ-CHECK] Tool call detection: show_req_tool_called={show_req_tool_called}, wants_show_requirements={wants_show_requirements}, tool_calls_count={len(tracer.data.get('tool_calls', []))}", "35"))
        except Exception as e:
            show_req_tool_called = False
            logger.warning(_color(f"[SHOW-REQ-CHECK] Error checking tool calls: {e}", "33"))
        
        # Fallback: If user asked to see requirements but tool wasn't called, check if we should call it
        # Also check if agent's response suggests it tried to show requirements
        agent_response_suggests_show_req = "retrieved the requirements" in assistant_text.lower() or "requirements" in assistant_text.lower() and ("display" in assistant_text.lower() or "shown" in assistant_text.lower() or "above" in assistant_text.lower())
        
        if not show_req_tool_called and (wants_show_requirements or agent_response_suggests_show_req):
            logger.info(_color(f"[SHOW-REQ-FALLBACK] Tool was not called but user requested to see requirements (user_message='{user_message[:100]}', agent_response_suggests={agent_response_suggests_show_req}) - checking status", "35"))
            try:
                status = tool_get_usecase_status(usecase_id)
                requirement_generation = status.get("requirement_generation") or "Not Started"
                
                logger.info(_color(f"[SHOW-REQ-FALLBACK] Status check: requirement_generation={requirement_generation}", "35"))
                
                if requirement_generation in ("In Progress", "Completed"):
                    logger.info(_color(f"[SHOW-REQ-FALLBACK] Conditions met - calling show_requirements tool as fallback", "35"))
                    tool_name = "show_requirements"
                    tool_entry = None
                    tool_start_time = None
                    try:
                        # Track tool call in tracer
                        tool_entry = tracer.start_tool(tool_name, args_preview=f'{{"usecase_id": "{usecase_id}"}}')
                        tool_start_time = time.time()
                        logger.info(_color(f"[TOOL-START {tool_name}] usecase_id={usecase_id}", "34"))
                        
                        result = tool_show_requirements(usecase_id)
                        duration_ms = int((time.time() - tool_start_time) * 1000)
                        
                        if result.get("status") == "success":
                            tracer.finish_tool(tool_entry, True, result_preview=f"status=success usecase_id={usecase_id}", duration_ms=duration_ms)
                            logger.info(_color(f"[TOOL-END {tool_name}] duration={duration_ms}ms", "34"))
                            logger.info(_color(f"[SHOW-REQ-FALLBACK] Successfully called show_requirements tool", "35"))
                            # Update assistant_text to indicate requirements were retrieved
                            assistant_text = "I've retrieved the requirements. They will be displayed above for you to review."
                        else:
                            error_msg = result.get('error', 'unknown_error')
                            tracer.finish_tool(tool_entry, False, error=error_msg, duration_ms=duration_ms)
                            logger.warning(_color(f"[TOOL-ERROR {tool_name}] {error_msg}", "34"))
                            logger.warning(_color(f"[SHOW-REQ-FALLBACK] show_requirements returned error: {error_msg}", "33"))
                    except Exception as e:
                        duration_ms = int((time.time() - tool_start_time) * 1000) if tool_start_time else 0
                        if tool_entry:
                            tracer.finish_tool(tool_entry, False, error=str(e), duration_ms=duration_ms)
                        logger.warning(_color(f"[TOOL-ERROR {tool_name}] {e}", "34"))
                        logger.warning(_color(f"[SHOW-REQ-FALLBACK] Error calling show_requirements: {e}", "33"), exc_info=True)
                else:
                    logger.info(_color(f"[SHOW-REQ-FALLBACK] Conditions not met: requirement_generation={requirement_generation}", "35"))
            except Exception as e:
                logger.warning(_color(f"[SHOW-REQ-FALLBACK] Fallback check failed: {e}", "33"), exc_info=True)
        
        # Post-run: Check if user wants to see scenarios but tool wasn't called
        user_text_lower_show_scen = user_message.lower()
        show_scenarios_keywords = [
            "show scenarios", "display scenarios", "show me the scenarios",
            "view scenarios", "show the scenarios", "can i see the scenarios",
            "can you show the scenarios", "can you show them",
            "if scenarios are done, can i see them", "if scenarios are done, can you show them",
            "i want to see the scenarios", "i want to see them",
            "show them", "show it", "let me see the scenarios"
        ]
        wants_show_scenarios = any(kw in user_text_lower_show_scen for kw in show_scenarios_keywords) or \
                               ("scenarios" in user_text_lower_show_scen and ("show" in user_text_lower_show_scen or "see" in user_text_lower_show_scen or "view" in user_text_lower_show_scen or "display" in user_text_lower_show_scen))
        
        try:
            show_scen_tool_called = any(
                (tc.get("name") == "show_scenarios") for tc in tracer.data.get("tool_calls", [])
            )
            logger.info(_color(f"[SHOW-SCEN-CHECK] Tool call detection: show_scen_tool_called={show_scen_tool_called}, wants_show_scenarios={wants_show_scenarios}, tool_calls_count={len(tracer.data.get('tool_calls', []))}", "35"))
        except Exception as e:
            show_scen_tool_called = False
            logger.warning(_color(f"[SHOW-SCEN-CHECK] Error checking tool calls: {e}", "33"))
        
        # Fallback: If user asked to see scenarios but tool wasn't called, check if we should call it
        # Also check if agent's response suggests it tried to show scenarios
        agent_response_suggests_show_scen = "retrieved the scenarios" in assistant_text.lower() or "scenarios" in assistant_text.lower() and ("display" in assistant_text.lower() or "shown" in assistant_text.lower() or "above" in assistant_text.lower())
        
        if not show_scen_tool_called and (wants_show_scenarios or agent_response_suggests_show_scen):
            logger.info(_color(f"[SHOW-SCEN-FALLBACK] Tool was not called but user requested to see scenarios (user_message='{user_message[:100]}', agent_response_suggests={agent_response_suggests_show_scen}) - checking status", "35"))
            try:
                status = tool_get_usecase_status(usecase_id)
                scenario_generation = status.get("scenario_generation") or "Not Started"
                
                logger.info(_color(f"[SHOW-SCEN-FALLBACK] Status check: scenario_generation={scenario_generation}", "35"))
                
                if scenario_generation in ("In Progress", "Completed"):
                    logger.info(_color(f"[SHOW-SCEN-FALLBACK] Conditions met - calling show_scenarios tool as fallback", "35"))
                    tool_name = "show_scenarios"
                    tool_entry = None
                    tool_start_time = None
                    try:
                        # Track tool call in tracer
                        tool_entry = tracer.start_tool(tool_name, args_preview=f'{{"usecase_id": "{usecase_id}"}}')
                        tool_start_time = time.time()
                        logger.info(_color(f"[TOOL-START {tool_name}] usecase_id={usecase_id}", "34"))
                        
                        result = tool_show_scenarios(usecase_id)
                        duration_ms = int((time.time() - tool_start_time) * 1000)
                        
                        if result.get("status") == "success":
                            tracer.finish_tool(tool_entry, True, result_preview=f"status=success usecase_id={usecase_id}", duration_ms=duration_ms)
                            logger.info(_color(f"[TOOL-END {tool_name}] duration={duration_ms}ms", "34"))
                            logger.info(_color(f"[SHOW-SCEN-FALLBACK] Successfully called show_scenarios tool", "35"))
                            # Update assistant_text to indicate scenarios were retrieved
                            assistant_text = "I've retrieved the scenarios. They will be displayed above for you to review."
                        else:
                            error_msg = result.get('error', 'unknown_error')
                            tracer.finish_tool(tool_entry, False, error=error_msg, duration_ms=duration_ms)
                            logger.warning(_color(f"[TOOL-ERROR {tool_name}] {error_msg}", "34"))
                            logger.warning(_color(f"[SHOW-SCEN-FALLBACK] show_scenarios returned error: {error_msg}", "33"))
                    except Exception as e:
                        duration_ms = int((time.time() - tool_start_time) * 1000) if tool_start_time else 0
                        if tool_entry:
                            tracer.finish_tool(tool_entry, False, error=str(e), duration_ms=duration_ms)
                        logger.warning(_color(f"[TOOL-ERROR {tool_name}] {e}", "34"))
                        logger.warning(_color(f"[SHOW-SCEN-FALLBACK] Error calling show_scenarios: {e}", "33"), exc_info=True)
                else:
                    logger.info(_color(f"[SHOW-SCEN-FALLBACK] Conditions not met: scenario_generation={scenario_generation}", "35"))
            except Exception as e:
                logger.warning(_color(f"[SHOW-SCEN-FALLBACK] Fallback check failed: {e}", "33"), exc_info=True)
        
        # Post-run: Check if user wants to see test cases but tool wasn't called
        user_text_lower_show_tc = user_message.lower()
        show_testcases_keywords = [
            "show test cases", "display test cases", "show me the test cases",
            "view test cases", "show the test cases", "can i see the test cases",
            "can you show the test cases", "can you show them",
            "if test cases are done, can i see them", "if test cases are done, can you show them",
            "i want to see the test cases", "i want to see them",
            "show them", "show it", "let me see the test cases"
        ]
        wants_show_testcases = any(kw in user_text_lower_show_tc for kw in show_testcases_keywords) or \
                               (("test case" in user_text_lower_show_tc or "testcase" in user_text_lower_show_tc) and ("show" in user_text_lower_show_tc or "see" in user_text_lower_show_tc or "view" in user_text_lower_show_tc or "display" in user_text_lower_show_tc))
        
        try:
            show_tc_tool_called = any(
                (tc.get("name") == "show_testcases") for tc in tracer.data.get("tool_calls", [])
            )
            logger.info(_color(f"[SHOW-TC-CHECK] Tool call detection: show_tc_tool_called={show_tc_tool_called}, wants_show_testcases={wants_show_testcases}, tool_calls_count={len(tracer.data.get('tool_calls', []))}", "35"))
        except Exception as e:
            show_tc_tool_called = False
            logger.warning(_color(f"[SHOW-TC-CHECK] Error checking tool calls: {e}", "33"))
        
        # Fallback: If user asked to see test cases but tool wasn't called, check if we should call it
        # Also check if agent's response suggests it tried to show test cases
        agent_response_suggests_show_tc = "retrieved the test cases" in assistant_text.lower() or ("test case" in assistant_text.lower() or "testcase" in assistant_text.lower()) and ("display" in assistant_text.lower() or "shown" in assistant_text.lower() or "above" in assistant_text.lower())
        
        if not show_tc_tool_called and (wants_show_testcases or agent_response_suggests_show_tc):
            logger.info(_color(f"[SHOW-TC-FALLBACK] Tool was not called but user requested to see test cases (user_message='{user_message[:100]}', agent_response_suggests={agent_response_suggests_show_tc}) - checking status", "35"))
            try:
                status = tool_get_usecase_status(usecase_id)
                test_case_generation = status.get("test_case_generation") or "Not Started"
                
                logger.info(_color(f"[SHOW-TC-FALLBACK] Status check: test_case_generation={test_case_generation}", "35"))
                
                if test_case_generation in ("In Progress", "Completed"):
                    logger.info(_color(f"[SHOW-TC-FALLBACK] Conditions met - calling show_testcases tool as fallback", "35"))
                    tool_name = "show_testcases"
                    tool_entry = None
                    tool_start_time = None
                    try:
                        # Track tool call in tracer
                        tool_entry = tracer.start_tool(tool_name, args_preview=f'{{"usecase_id": "{usecase_id}"}}')
                        tool_start_time = time.time()
                        logger.info(_color(f"[TOOL-START {tool_name}] usecase_id={usecase_id}", "34"))
                        
                        result = tool_show_testcases(usecase_id)
                        duration_ms = int((time.time() - tool_start_time) * 1000)
                        
                        if result.get("status") == "success":
                            tracer.finish_tool(tool_entry, True, result_preview=f"status=success usecase_id={usecase_id}", duration_ms=duration_ms)
                            logger.info(_color(f"[TOOL-END {tool_name}] duration={duration_ms}ms", "34"))
                            logger.info(_color(f"[SHOW-TC-FALLBACK] Successfully called show_testcases tool", "35"))
                            # Update assistant_text to indicate test cases were retrieved
                            assistant_text = "I've retrieved the test cases. They will be displayed above for you to review."
                        else:
                            error_msg = result.get('error', 'unknown_error')
                            tracer.finish_tool(tool_entry, False, error=error_msg, duration_ms=duration_ms)
                            logger.warning(_color(f"[TOOL-ERROR {tool_name}] {error_msg}", "34"))
                            logger.warning(_color(f"[SHOW-TC-FALLBACK] show_testcases returned error: {error_msg}", "33"))
                    except Exception as e:
                        duration_ms = int((time.time() - tool_start_time) * 1000) if tool_start_time else 0
                        if tool_entry:
                            tracer.finish_tool(tool_entry, False, error=str(e), duration_ms=duration_ms)
                        logger.warning(_color(f"[TOOL-ERROR {tool_name}] {e}", "34"))
                        logger.warning(_color(f"[SHOW-TC-FALLBACK] Error calling show_testcases: {e}", "33"), exc_info=True)
                else:
                    logger.info(_color(f"[SHOW-TC-FALLBACK] Conditions not met: test_case_generation={test_case_generation}", "35"))
            except Exception as e:
                logger.warning(_color(f"[SHOW-TC-FALLBACK] Fallback check failed: {e}", "33"), exc_info=True)
        
        # Final debug: Log all tool calls before returning (should include fallback tools)
        try:
            final_tool_calls = tracer.data.get("tool_calls", [])
            final_tool_names = [tc.get("name") for tc in final_tool_calls]
            logger.info(_color(f"[DEBUG-FINAL] All tool calls before return: {final_tool_names} (count={len(final_tool_calls)})", "36"))
        except Exception:
            pass
        
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


