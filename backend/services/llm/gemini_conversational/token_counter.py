"""
Token counting utilities for Gemini models.

This module provides utilities to count tokens in text content for Gemini models,
which is essential for managing context windows and determining when summarization is needed.
"""

import json
import logging
from typing import List, Dict, Any, Tuple
import google.generativeai as genai


logger = logging.getLogger(__name__)

# Token limits for different Gemini models
# Note: This is kept for backward compatibility. New code should use model_registry.
GEMINI_TOKEN_LIMITS = {
    "gemini-2.5-flash": 250_000,    # 250k token context window
    "gemini-2.5-pro": 250_000,      # 250k token context window  
    "gemini-2.0-flash": 250_000,    # 250k token context window
    "gemini-2.5-flash-lite": 250_000,  # 250k token context window
    "gemini-2.0-flash-live": 250_000,  # 250k token context window
}

# Conservative estimate for tokens per character (Gemini uses subword tokenization)
CHARS_PER_TOKEN_ESTIMATE = 4


def estimate_tokens_from_text(text: str) -> int:
    """
    Estimate token count from text using character-based approximation.
    
    This is a rough estimate as actual tokenization depends on the model's vocabulary.
    For more accurate counting, we would need the actual tokenizer.
    
    Args:
        text (str): Text to count tokens for
        
    Returns:
        int: Estimated token count
    """
    if not text:
        return 0
    
    # Conservative estimate: ~4 characters per token for most languages
    return len(text) // CHARS_PER_TOKEN_ESTIMATE


def count_tokens_in_chat_history(chat_history: List[Dict[str, Any]]) -> int:
    """
    Count estimated tokens in a chat history array.
    
    Args:
        chat_history (List[Dict]): List of chat messages
        
    Returns:
        int: Estimated total token count
    """
    if not chat_history:
        return 0
    
    total_tokens = 0
    
    for entry in chat_history:
        # Handle different message types
        if "user" in entry:
            total_tokens += estimate_tokens_from_text(str(entry["user"]))
        elif "system" in entry:
            total_tokens += estimate_tokens_from_text(str(entry["system"]))
        elif "assistant" in entry:
            total_tokens += estimate_tokens_from_text(str(entry["assistant"]))
        
        # Also count metadata like timestamps, file info
        if "files" in entry and entry["files"]:
            total_tokens += estimate_tokens_from_text(json.dumps(entry["files"]))
        
        if "timestamp" in entry:
            total_tokens += estimate_tokens_from_text(str(entry["timestamp"]))
    
    return total_tokens


def count_tokens_in_summary(summary: str) -> int:
    """
    Count estimated tokens in a chat summary.
    
    Args:
        summary (str): Summary text
        
    Returns:
        int: Estimated token count
    """
    return estimate_tokens_from_text(summary) if summary else 0


def get_token_limit_for_model(model_name: str) -> int:
    """
    Get token limit for a model. First checks model_registry, then falls back to local dict.
    """
    # Try to get from model registry first
    try:
        from core.model_registry import get_model_by_id
        model_info = get_model_by_id(model_name)
        if model_info:
            return model_info.token_limit
    except Exception:
        pass
    
    # Fallback to local dict
    # Remove "models/" prefix if present
    clean_model_name = model_name.replace("models/", "")
    
    # Default to 250k tokens if model not found
    return GEMINI_TOKEN_LIMITS.get(clean_model_name, 250_000)


def should_summarize_history(
    chat_history: List[Dict[str, Any]], 
    chat_summary: str = None,
    model_name: str = "gemini-2.5-flash",
    threshold_ratio: float = 0.8
) -> bool:
    """
    Determine if chat history should be summarized based on token count.
    
    Args:
        chat_history (List[Dict]): Current chat history
        chat_summary (str): Existing summary (if any)
        model_name (str): Name of the Gemini model being used
        threshold_ratio (float): Ratio of token limit to trigger summarization
        
    Returns:
        bool: True if history should be summarized
    """
    history_tokens = count_tokens_in_chat_history(chat_history)
    summary_tokens = count_tokens_in_summary(chat_summary)
    total_tokens = history_tokens + summary_tokens
    
    token_limit = get_token_limit_for_model(model_name)
    threshold = int(token_limit * threshold_ratio)
    
    logger.info(f"Token analysis: History={history_tokens}, Summary={summary_tokens}, "
                f"Total={total_tokens}, Limit={token_limit}, Threshold={threshold}")
    
    return total_tokens > threshold


def find_summarization_cutoff_point(
    chat_history: List[Dict[str, Any]], 
    keep_recent_ratio: float = 0.3
) -> int:
    """
    Find the optimal cutoff point for summarization, keeping recent messages.
    
    Args:
        chat_history (List[Dict]): Chat history (newest first)
        keep_recent_ratio (float): Ratio of recent messages to keep unsummarized
        
    Returns:
        int: Index in chat_history where to cut off for summarization
    """
    if not chat_history:
        return 0
    
    # Keep at least the most recent 30% of messages
    keep_count = max(1, int(len(chat_history) * keep_recent_ratio))
    
    # Don't summarize if there are very few messages
    if len(chat_history) <= 5:
        return 0
    
    return min(keep_count, len(chat_history) - 1)


def get_token_usage_info(
    chat_history: List[Dict[str, Any]], 
    chat_summary: str = None,
    model_name: str = "gemini-2.5-flash"
) -> Dict[str, Any]:
    """
    Get comprehensive token usage information.
    
    Args:
        chat_history (List[Dict]): Current chat history
        chat_summary (str): Existing summary
        model_name (str): Gemini model name
        
    Returns:
        Dict: Token usage statistics
    """
    history_tokens = count_tokens_in_chat_history(chat_history)
    summary_tokens = count_tokens_in_summary(chat_summary)
    total_tokens = history_tokens + summary_tokens
    token_limit = get_token_limit_for_model(model_name)
    
    return {
        "history_tokens": history_tokens,
        "summary_tokens": summary_tokens,
        "total_tokens": total_tokens,
        "token_limit": token_limit,
        "usage_percentage": (total_tokens / token_limit) * 100,
        "should_summarize": should_summarize_history(chat_history, chat_summary, model_name),
        "model_name": model_name
    }


if __name__ == "__main__":
    # Test the token counting utilities
    test_history = [
        {"user": "Hello, can you help me with testing?", "timestamp": "2025-01-08T00:00:00Z"},
        {"system": "Of course! I'd be happy to help you with testing. What specific area are you working on?", "timestamp": "2025-01-08T00:00:05Z"},
        {"user": "I need to test an API endpoint", "timestamp": "2025-01-08T00:01:00Z"},
        {"system": "Great! API testing is important. What type of API are you working with?", "timestamp": "2025-01-08T00:01:05Z"}
    ]
    
    info = get_token_usage_info(test_history)
    print("Token Usage Info:")
    for key, value in info.items():
        print(f"  {key}: {value}")
