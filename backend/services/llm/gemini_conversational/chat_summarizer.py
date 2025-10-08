"""
Chat summarization service for managing long conversation histories.

This service provides functionality to summarize chat histories when they exceed
token limits, using a specialized Gemini model with a summarization prompt.
"""

import json
import logging
from typing import List, Dict, Any, Optional, Tuple
import google.generativeai as genai
from datetime import datetime, timezone

from .token_counter import (
    count_tokens_in_chat_history,
    should_summarize_history,
    find_summarization_cutoff_point
)

logger = logging.getLogger(__name__)

# Specialized summarization prompt for chat histories
CHAT_SUMMARIZER_PROMPT = """You are a specialized chat history summarizer for Cortexa, a testing-aware AI assistant. Your task is to create concise, comprehensive summaries of conversation histories while preserving all important context and information.

**SUMMARIZATION GUIDELINES:**
1. Preserve all technical details, requirements, and test-related information
2. Maintain the chronological flow of the conversation
3. Keep track of user preferences, constraints, and ongoing projects
4. Preserve any decisions made, conclusions reached, or problems solved
5. Include relevant context about files discussed, tools mentioned, or workflows established
6. Maintain the testing focus - preserve all QA, testing strategies, and technical specifications

**OUTPUT FORMAT:**
Provide a structured summary in plain text (not JSON) with these sections:
- **Context**: Brief overview of the conversation topic and purpose
- **Key Points**: Main discussion points, decisions, and technical details
- **Testing Focus**: Any testing-related discussions, strategies, or requirements
- **Files & Tools**: Mentioned files, tools, or technical resources
- **Ongoing Items**: Unresolved questions, next steps, or continued work
- **User Preferences**: Any expressed preferences, constraints, or requirements

Keep the summary detailed enough to maintain full context while being more concise than the original conversation."""

SUMMARY_MARKER_PREFIX = "___SUMMARY_CUTOFF_"


def create_summary_marker(cutoff_index: int, timestamp: str = None) -> Dict[str, Any]:
    """
    Create a marker in chat history to indicate where summarization was cut off.
    
    Args:
        cutoff_index (int): Index in original chat history where summary was cut
        timestamp (str): Optional timestamp for the marker
        
    Returns:
        Dict: Marker entry for chat history
    """
    if not timestamp:
        timestamp = datetime.now(timezone.utc).isoformat()
    
    return {
        "marker": f"{SUMMARY_MARKER_PREFIX}{cutoff_index}",
        "type": "summary_cutoff",
        "cutoff_index": cutoff_index,
        "timestamp": timestamp,
        "note": "Chat history before this point has been summarized"
    }


def find_existing_summary_marker(chat_history: List[Dict[str, Any]]) -> Optional[int]:
    """
    Find existing summary marker in chat history.
    
    Args:
        chat_history (List[Dict]): Chat history to search
        
    Returns:
        Optional[int]: Index of the marker, or None if not found
    """
    for i, entry in enumerate(chat_history):
        if isinstance(entry, dict) and "marker" in entry:
            if entry["marker"].startswith(SUMMARY_MARKER_PREFIX):
                return i
    return None


def extract_messages_for_summarization(
    chat_history: List[Dict[str, Any]], 
    cutoff_index: int
) -> List[Dict[str, Any]]:
    """
    Extract messages that need to be summarized (before cutoff point).
    
    Args:
        chat_history (List[Dict]): Complete chat history (newest first)
        cutoff_index (int): Index where to cut off for summarization
        
    Returns:
        List[Dict]: Messages to be summarized (oldest first for chronological order)
    """
    # Since chat_history is newest first, we take from cutoff_index onwards
    # and reverse to get chronological order (oldest first)
    messages_to_summarize = chat_history[cutoff_index:]
    return list(reversed(messages_to_summarize))


def format_chat_for_summarization(chat_messages: List[Dict[str, Any]]) -> str:
    """
    Format chat messages for the summarization prompt.
    
    Args:
        chat_messages (List[Dict]): Messages to format (should be oldest first)
        
    Returns:
        str: Formatted conversation for summarization
    """
    formatted_lines = []
    
    for entry in chat_messages:
        timestamp = entry.get("timestamp", "")
        
        if "user" in entry:
            formatted_lines.append(f"[{timestamp}] User: {entry['user']}")
            
            # Include file information if present
            if "files" in entry and entry["files"]:
                files_info = ", ".join([f["name"] for f in entry["files"] if "name" in f])
                formatted_lines.append(f"    📎 Files: {files_info}")
                
        elif "system" in entry:
            formatted_lines.append(f"[{timestamp}] Cortexa: {entry['system']}")
            
        elif "assistant" in entry:
            formatted_lines.append(f"[{timestamp}] Assistant: {entry['assistant']}")
    
    return "\n".join(formatted_lines)


async def summarize_chat_history(
    chat_messages: List[Dict[str, Any]],
    model_name: str = "gemini-2.5-flash",
    api_key: str = None
) -> str:
    """
    Summarize a list of chat messages using Gemini model.
    
    Args:
        chat_messages (List[Dict]): Messages to summarize (oldest first)
        model_name (str): Gemini model to use for summarization
        api_key (str): Gemini API key
        
    Returns:
        str: Summary of the chat history
        
    Raises:
        Exception: If summarization fails
    """
    if not api_key:
        raise ValueError("API key is required for chat summarization")
    
    if not chat_messages:
        return ""
    
    try:
        # Configure Gemini
        genai.configure(api_key=api_key)
        
        # Initialize summarization model
        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=CHAT_SUMMARIZER_PROMPT
        )
        
        # Format the conversation
        formatted_conversation = format_chat_for_summarization(chat_messages)
        
        # Create summarization prompt
        prompt = f"""Please summarize the following conversation history:

{formatted_conversation}

Provide a comprehensive summary following the guidelines in your system prompt."""
        
        # Generate summary
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,  # Lower temperature for more consistent summaries
                max_output_tokens=2048,
                top_p=0.8,
                top_k=40
            )
        )
        
        if response.text:
            logger.info(f"Successfully summarized {len(chat_messages)} messages")
            return response.text.strip()
        else:
            raise Exception("No summary generated from Gemini")
            
    except Exception as e:
        logger.error(f"Error summarizing chat history: {e}")
        raise


def update_chat_history_with_summary(
    chat_history: List[Dict[str, Any]],
    summary: str,
    cutoff_index: int
) -> List[Dict[str, Any]]:
    """
    Update chat history by removing summarized messages and adding summary marker.
    
    Args:
        chat_history (List[Dict]): Original chat history (newest first)
        summary (str): Generated summary
        cutoff_index (int): Index where summarization was cut off
        
    Returns:
        List[Dict]: Updated chat history with summary marker
    """
    # Keep only the recent messages (before cutoff_index)
    updated_history = chat_history[:cutoff_index]
    
    # Add summary marker
    marker = create_summary_marker(cutoff_index)
    updated_history.append(marker)
    
    logger.info(f"Updated chat history: kept {len(updated_history)} recent messages, "
                f"summarized {cutoff_index} older messages")
    
    return updated_history


def get_context_for_llm(
    chat_history: List[Dict[str, Any]],
    chat_summary: str = None
) -> str:
    """
    Prepare context for LLM including summary and recent history.
    
    Args:
        chat_history (List[Dict]): Recent chat history (newest first)
        chat_summary (str): Existing summary
        
    Returns:
        str: Formatted context for LLM
    """
    context_parts = []
    
    # Add summary if available
    if chat_summary:
        context_parts.append("=== CONVERSATION SUMMARY ===")
        context_parts.append(chat_summary)
        context_parts.append("")
    
    # Add recent chat history (reverse to get chronological order)
    if chat_history:
        # Find if there's a summary marker
        marker_index = find_existing_summary_marker(chat_history)
        
        # Get messages after the marker (or all if no marker)
        recent_messages = chat_history[:marker_index] if marker_index is not None else chat_history
        
        if recent_messages:
            context_parts.append("=== RECENT CONVERSATION ===")
            formatted_recent = format_chat_for_summarization(list(reversed(recent_messages)))
            context_parts.append(formatted_recent)
    
    return "\n".join(context_parts)


if __name__ == "__main__":
    # Test the summarization utilities
    test_history = [
        {"user": "I need help with API testing", "timestamp": "2025-01-08T10:00:00Z"},
        {"system": "I'd be happy to help with API testing. What specific API are you working with?", "timestamp": "2025-01-08T10:00:05Z"},
        {"user": "It's a REST API for user management", "timestamp": "2025-01-08T10:01:00Z"},
        {"system": "Great! For REST API testing, we should cover CRUD operations. Let's start with the GET endpoint.", "timestamp": "2025-01-08T10:01:05Z"},
    ]
    
    # Test formatting
    formatted = format_chat_for_summarization(test_history)
    print("Formatted conversation:")
    print(formatted)
    
    # Test marker creation
    marker = create_summary_marker(2)
    print("\nSummary marker:")
    print(json.dumps(marker, indent=2))
