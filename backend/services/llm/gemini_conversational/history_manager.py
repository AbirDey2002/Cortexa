"""
Comprehensive chat history management system for Cortexa.

This module provides the main orchestration for managing chat histories, including:
- Token counting and limit checking
- Automatic summarization when limits are exceeded
- Context preparation for LLM queries
- Database integration for chat summaries
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
import uuid

from .token_counter import (
    count_tokens_in_chat_history,
    count_tokens_in_summary,
    should_summarize_history,
    find_summarization_cutoff_point,
    get_token_usage_info
)
from .chat_summarizer import (
    summarize_chat_history,
    update_chat_history_with_summary,
    get_context_for_llm,
    find_existing_summary_marker
)

logger = logging.getLogger(__name__)


class ChatHistoryManager:
    """
    Main class for managing chat history with token limits and summarization.
    """
    
    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash"):
        """
        Initialize the chat history manager.
        
        Args:
            api_key (str): Gemini API key for summarization
            model_name (str): Gemini model name to use
        """
        self.api_key = api_key
        self.model_name = model_name
        
    
    async def process_chat_history(
        self,
        usecase_id: uuid.UUID,
        chat_history: List[Dict[str, Any]],
        chat_summary: Optional[str],
        db: Session
    ) -> Tuple[List[Dict[str, Any]], Optional[str], bool]:
        """
        Process chat history, performing summarization if needed.
        
        Args:
            usecase_id (UUID): Usecase identifier
            chat_history (List[Dict]): Current chat history (newest first)
            chat_summary (str): Existing summary (if any)
            db (Session): Database session
            
        Returns:
            Tuple[List[Dict], Optional[str], bool]: 
                - Updated chat history
                - Updated chat summary
                - Whether summarization was performed
        """
        try:
            # Get token usage information
            token_info = get_token_usage_info(chat_history, chat_summary, self.model_name)
            
            logger.info(f"Chat history analysis for usecase {usecase_id}: {token_info}")
            
            # Check if summarization is needed
            if token_info["should_summarize"] and len(chat_history) > 5:
                logger.info(f"Summarization needed for usecase {usecase_id}")
                
                # Perform summarization
                updated_history, updated_summary = await self._perform_summarization(
                    chat_history, chat_summary
                )
                
                # Update database
                await self._update_database(usecase_id, updated_history, updated_summary, db)
                
                return updated_history, updated_summary, True
            
            else:
                logger.info(f"No summarization needed for usecase {usecase_id}")
                return chat_history, chat_summary, False
                
        except Exception as e:
            logger.error(f"Error processing chat history for usecase {usecase_id}: {e}")
            # Return original data on error
            return chat_history, chat_summary, False
    
    
    async def _perform_summarization(
        self,
        chat_history: List[Dict[str, Any]],
        existing_summary: Optional[str]
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Perform the actual summarization process.
        
        Args:
            chat_history (List[Dict]): Current chat history
            existing_summary (str): Existing summary
            
        Returns:
            Tuple[List[Dict], str]: Updated history and new summary
        """
        # Find optimal cutoff point
        cutoff_index = find_summarization_cutoff_point(chat_history)
        
        if cutoff_index == 0:
            logger.warning("No suitable cutoff point found for summarization")
            return chat_history, existing_summary or ""
        
        # Extract messages to summarize
        from .chat_summarizer import extract_messages_for_summarization
        messages_to_summarize = extract_messages_for_summarization(chat_history, cutoff_index)
        
        # If we have an existing summary, include it in the context
        if existing_summary:
            # We need to summarize both the existing summary and new messages
            # For now, we'll create a comprehensive summary including both
            summary_context = f"Previous summary:\n{existing_summary}\n\nNew messages to integrate:"
            messages_to_summarize.insert(0, {
                "system": summary_context,
                "timestamp": "summary_context"
            })
        
        # Generate new summary
        new_summary = await summarize_chat_history(
            messages_to_summarize,
            self.model_name,
            self.api_key
        )
        
        # Update chat history with marker
        updated_history = update_chat_history_with_summary(
            chat_history, new_summary, cutoff_index
        )
        
        return updated_history, new_summary
    
    
    async def _update_database(
        self,
        usecase_id: uuid.UUID,
        updated_history: List[Dict[str, Any]],
        updated_summary: str,
        db: Session
    ) -> None:
        """
        Update the database with new history and summary.
        
        Args:
            usecase_id (UUID): Usecase identifier
            updated_history (List[Dict]): Updated chat history
            updated_summary (str): Updated summary
            db (Session): Database session
        """
        try:
            from models.usecase.usecase import UsecaseMetadata
            
            # Find the usecase record
            record = db.query(UsecaseMetadata).filter(
                UsecaseMetadata.usecase_id == usecase_id,
                UsecaseMetadata.is_deleted == False
            ).first()
            
            if record:
                record.chat_history = updated_history
                record.chat_summary = updated_summary
                db.commit()
                
                logger.info(f"Updated database for usecase {usecase_id} with summarized history")
            else:
                logger.error(f"Usecase {usecase_id} not found in database")
                
        except Exception as e:
            logger.error(f"Error updating database for usecase {usecase_id}: {e}")
            db.rollback()
            raise
    
    
    def prepare_context_for_llm(
        self,
        chat_history: List[Dict[str, Any]],
        chat_summary: Optional[str],
        user_query: str
    ) -> str:
        """
        Prepare the complete context for LLM including summary and recent history.
        
        Args:
            chat_history (List[Dict]): Recent chat history
            chat_summary (str): Chat summary (if any)
            user_query (str): Current user query
            
        Returns:
            str: Formatted context for LLM
        """
        # Prune non-essential fields from chat history for LLM context while preserving storage
        pruned_history = prune_chat_history_for_context(chat_history)
        # Get the context from summary and recent pruned history
        context = get_context_for_llm(pruned_history, chat_summary)
        
        # Add the current query
        if context:
            full_context = f"{context}\n\n=== CURRENT QUERY ===\nUser: {user_query}"
        else:
            full_context = f"User: {user_query}"
        
        return full_context
    
    
    def get_history_statistics(
        self,
        chat_history: List[Dict[str, Any]],
        chat_summary: Optional[str]
    ) -> Dict[str, Any]:
        """
        Get comprehensive statistics about the chat history.
        
        Args:
            chat_history (List[Dict]): Chat history
            chat_summary (str): Chat summary
            
        Returns:
            Dict: Statistics and information
        """
        token_info = get_token_usage_info(chat_history, chat_summary, self.model_name)
        
        # Add additional statistics
        marker_index = find_existing_summary_marker(chat_history)
        
        stats = {
            **token_info,
            "total_messages": len(chat_history),
            "has_summary": bool(chat_summary),
            "summary_length": len(chat_summary) if chat_summary else 0,
            "has_summary_marker": marker_index is not None,
            "recent_messages_count": marker_index if marker_index is not None else len(chat_history)
        }
        
        return stats


def prune_chat_history_for_context(chat_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return a compact history for LLM context only.

    Rules:
    - Keep user messages as plain text strings.
    - For assistant/system entries, extract readable text/markdown only; drop traces, tool metadata, signatures, files.
    - Preserve chronological order and timestamps if needed by downstream functions.
    """
    pruned: List[Dict[str, Any]] = []
    for entry in chat_history or []:
        # Pass through timestamp if present
        timestamp = entry.get("timestamp")
        if "user" in entry:
            value = str(entry.get("user", ""))
            pruned.append({"user": value, **({"timestamp": timestamp} if timestamp else {})})
            continue
        if "system" in entry:
            system_value = entry.get("system")
            # Attempt to extract main text from structured chunk arrays if present as a string
            text_out = _extract_text_like(system_value)
            pruned.append({"system": text_out, **({"timestamp": timestamp} if timestamp else {})})
            continue
        # Fallback: ignore unknown shapes
    return pruned


def _extract_text_like(value: Any) -> str:
    """Best-effort extraction of text content from various stored formats.

    Handles plain strings and stringified arrays of chunks like:
    "[{'type': 'text', 'text': '...'}, ...]" by extracting 'text' fields.
    """
    try:
        if isinstance(value, str):
            s = value.strip()
            # Fast path: looks like a JSON/py array of chunks
            if s.startswith("[") and ("'text'" in s or '"text"' in s):
                import re
                texts = re.findall(r"(?:'text'|\"text\")\s*:\s*(?:'([^']*)'|\"([^\"]*)\")", s)
                joined = "\n\n".join([t[0] or t[1] for t in texts if (t[0] or t[1])])
                return joined if joined else s
            return s
        return str(value)
    except Exception:
        return str(value)


# Utility functions for easy access
async def manage_chat_history_for_usecase(
    usecase_id: uuid.UUID,
    chat_history: List[Dict[str, Any]],
    chat_summary: Optional[str],
    user_query: str,
    api_key: str,
    db: Session,
    model_name: str = "gemini-2.5-flash"
) -> Tuple[str, List[Dict[str, Any]], Optional[str], bool]:
    """
    High-level function to manage chat history for a usecase.
    
    Args:
        usecase_id (UUID): Usecase identifier
        chat_history (List[Dict]): Current chat history
        chat_summary (str): Current summary
        user_query (str): User's current query
        api_key (str): Gemini API key
        db (Session): Database session
        model_name (str): Gemini model name
        
    Returns:
        Tuple[str, List[Dict], Optional[str], bool]: 
            - Context for LLM
            - Updated chat history
            - Updated summary
            - Whether summarization occurred
    """
    manager = ChatHistoryManager(api_key, model_name)
    
    # Process history (perform summarization if needed)
    updated_history, updated_summary, summarized = await manager.process_chat_history(
        usecase_id, chat_history, chat_summary, db
    )
    
    # Prepare context for LLM
    context = manager.prepare_context_for_llm(updated_history, updated_summary, user_query)
    
    return context, updated_history, updated_summary, summarized


if __name__ == "__main__":
    # Test the history manager
    import asyncio
    
    async def test_manager():
        # Create test data
        test_history = [
            {"user": f"Test message {i}", "timestamp": f"2025-01-08T10:{i:02d}:00Z"}
            for i in range(10)
        ]
        
        manager = ChatHistoryManager("test_key")
        stats = manager.get_history_statistics(test_history, None)
        
        print("History Statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
    
    asyncio.run(test_manager())
