"""
This file is the module to invoke Google Gemini 2.5 Flash for conversational purposes.

Google Gemini 2.5 Flash is used to get LLM responses for conversational AI.
Enhanced with intelligent history management and summarization capabilities.
"""

import json
import os
import sys
import time
import uuid
from typing import Tuple, Optional, Dict, Union, List
from sqlalchemy.orm import Session

import google.generativeai as genai
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# Add the parent directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

# Import environment configuration
from core.env_config import get_env_variable

# Import history management modules
from .history_manager import manage_chat_history_for_usecase, ChatHistoryManager, prune_chat_history_for_context
from .token_counter import get_token_usage_info
from .json_output_parser import (
    parse_llm_response, 
    create_enhanced_cortexa_prompt,
    CortexaOutputParser,
    StrictJSONOutputParser
)

# Configure the Gemini API - fallback system key
GEMINI_API_KEY = get_env_variable("GEMINI_API_KEY", "")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# System prompt for Cortexa agent - using enhanced version with strict JSON requirements
CORTEXA_SYSTEM_PROMPT = create_enhanced_cortexa_prompt()

# Logger
logger = logging.getLogger(__name__)


def _get_effective_api_key(api_key: Optional[str] = None) -> str:
    """
    Get the effective API key to use.
    Priority: explicit api_key parameter > system env variable.
    """
    if api_key and api_key.strip():
        return api_key.strip()
    return GEMINI_API_KEY


def get_user_gemini_key(user_id) -> Optional[str]:
    """
    Get user's Gemini API key from database.
    
    Args:
        user_id: The user's UUID
        
    Returns:
        Decrypted API key if found and active, None otherwise
    """
    from uuid import UUID
    from db.session import get_db_context
    from services.llm.key_resolver import KeyResolver
    
    try:
        # Convert to UUID if string
        if isinstance(user_id, str):
            user_id = UUID(user_id)
        
        with get_db_context() as db:
            resolver = KeyResolver(db)
            key, source = resolver.resolve_key(user_id, "gemini")
            if key:
                logger.info(f"get_user_gemini_key: resolved key for user from {source}")
            return key
    except Exception as e:
        logger.error(f"get_user_gemini_key: error resolving key: {e}")
        return None

def invoke_gemini_chat(
    query: str,
    chat_history: Optional[list] = None,
    model_name: str = "gemini-2.5-flash",
    timeout_seconds: int = 60,
    api_key: Optional[str] = None
) -> Tuple[str, float, int]:
    """
    Invoke Google Gemini for conversational AI.

    Args:
        query (str): The user's message/query
        chat_history (list, optional): List of previous chat messages
        model_name (str): Model name to use (default: gemini-2.5-flash)
        timeout_seconds (int): Maximum time to wait for response
        api_key (str, optional): API key to use. If not provided, uses system key.

    Returns:
        tuple: A tuple containing (response_text, cost_estimate, tokens_estimate)
    """
    effective_key = _get_effective_api_key(api_key)
    if not effective_key:
        return "Error: No API key available (GEMINI_API_KEY not set and no user key provided)", 0.0, 0
    
    # Configure with the effective key
    genai.configure(api_key=effective_key)

    start_time = time.time()
    
    try:
        # Initialize the model
        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=CORTEXA_SYSTEM_PROMPT
        )
        
        # Build conversation history for context
        # Use pruned history for LLM context
        conversation_context = []
        if chat_history:
            pruned = prune_chat_history_for_context(chat_history)
            for entry in pruned:
                if "user" in entry:
                    conversation_context.append(f"User: {entry['user']}")
                elif "system" in entry:
                    conversation_context.append(f"Assistant: {entry['system']}")
        
        # Add current query
        full_prompt = "\n".join(conversation_context + [f"User: {query}"])

        # Log inputs sent to the LLM (full)
        try:
            context_str = "\n".join(conversation_context)
            logger.info(
                "Gemini LLM input (history msgs=%d, context chars=%d, total prompt chars=%d):\nContext:\n%s\nPrompt:\n%s",
                len(chat_history or []),
                len(context_str),
                len(full_prompt),
                context_str,
                full_prompt,
            )
        except Exception:
            pass
        
        # Generate response with timeout
        response = model.generate_content(
            full_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                max_output_tokens=2048,
                top_p=0.8,
                top_k=40
            )
        )
        
        # Extract response text
        response_text = response.text if response.text else "No response generated"
        # Write full response to disk
        try:
            base = _requirements_log_dir()
            ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
            out_path = os.path.join(base, f"{ts}-gemini_chat-out.txt")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(response_text)
            logger.info("invoke_gemini_chat: wrote full response to %s (chars=%d)", out_path, len(response_text))
        except Exception:
            pass
        
        # Estimate costs (Gemini pricing is typically very low)
        # These are rough estimates based on input/output tokens
        estimated_cost = 0.001  # Very rough estimate
        estimated_tokens = len(response_text.split()) * 1.3  # Rough token estimate
        
        total_time = time.time() - start_time
        
        # Use robust JSON parsing with LangChain
        try:
            user_answer, tool_call, parsing_success = parse_llm_response(response_text)
            
            # Create properly formatted JSON response
            formatted_response = json.dumps({
                "user_answer": user_answer,
                "tool_call": tool_call
            })
            
            if not parsing_success:
                logger.warning(f"Used fallback JSON parsing for response: {response_text[:100]}...")
            
            return formatted_response, estimated_cost, int(estimated_tokens)
            
        except Exception as parse_error:
            logger.error(f"Critical parsing error: {parse_error}")
            # Final fallback - return error in proper JSON format
            error_response = json.dumps({
                "user_answer": f"I apologize, but I encountered an error processing my response. Please try again.",
                "tool_call": None
            })
            return error_response, estimated_cost, int(estimated_tokens)
        
    except Exception as e:
        error_message = f"Error calling Gemini API: {str(e)}"
        # Return error in the expected JSON format
        error_response = json.dumps({
            "user_answer": error_message,
            "tool_call": None
        })
        return error_response, 0.0, 0


def invoke_gemini_chat_with_timeout(query: str, chat_history: Optional[list] = None, timeout_seconds: int = 300) -> Tuple[str, float, int]:
    """
    Invoke Google Gemini 2.5 Flash with proper timeout handling.

    Args:
        query (str): The user's message/query
        chat_history (list, optional): List of previous chat messages
        timeout_seconds (int): Maximum time for the entire operation

    Returns:
        tuple: A tuple containing (response_text, cost_estimate, tokens_estimate)
        
    Raises:
        TimeoutError: If the operation exceeds the timeout limit.
    """
    start_time = time.time()
    
    try:
        # Call the main function with timeout monitoring
        result = invoke_gemini_chat(query, chat_history, timeout_seconds)
        
        elapsed_time = time.time() - start_time
        if elapsed_time > timeout_seconds:
            raise TimeoutError(f"Gemini response timeout after {timeout_seconds} seconds")
        
        return result
        
    except TimeoutError:
        raise
    except Exception as e:
        error_message = f"Error in Gemini chat with timeout: {str(e)}"
        error_response = json.dumps({
            "user_answer": error_message,
            "tool_call": None
        })
        return error_response, 0.0, 0


def _requirements_log_dir() -> str:
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "logs", "requirements")
    os.makedirs(base, exist_ok=True)
    return base


def invoke_freeform_prompt(
    prompt: str,
    model_name: str = "gemini-2.5-flash",
    api_key: Optional[str] = None
) -> str:
    """Send a single freeform prompt to Gemini and return raw text.

    Logs full prompt/response to console and writes to backend/logs/requirements.
    
    Args:
        prompt (str): The prompt to send
        model_name (str): Model name to use (default: gemini-2.5-flash)
        api_key (str, optional): API key to use. If not provided, uses system key.
    """
    effective_key = _get_effective_api_key(api_key)
    if not effective_key:
        logger.error("invoke_freeform_prompt: No API key available")
        return ""
    
    genai.configure(api_key=effective_key)
    model = genai.GenerativeModel(model_name=model_name)
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
    log_dir = _requirements_log_dir()
    in_path = os.path.join(log_dir, f"{ts}-freeform-in.txt")
    out_path = os.path.join(log_dir, f"{ts}-freeform-out.txt")
    try:
        # Log to files and console
        try:
            with open(in_path, "w", encoding="utf-8") as f:
                f.write(prompt)
        except Exception:
            pass
        logger.info("invoke_freeform_prompt: prompt_chars=%d file=%s", len(prompt), in_path)
        resp = model.generate_content(prompt)
        text = resp.text or ""
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception:
            pass
        logger.info("invoke_freeform_prompt: response_chars=%d file=%s", len(text), out_path)
        return text
    except Exception as e:
        logger.error("invoke_freeform_prompt: error %s", e, exc_info=True)
        return ""


# Async wrappers
_EXECUTOR: Optional[ThreadPoolExecutor] = None


def _get_executor() -> ThreadPoolExecutor:
    global _EXECUTOR
    if _EXECUTOR is None:
        _EXECUTOR = ThreadPoolExecutor(max_workers=4)
    return _EXECUTOR


async def async_generate_content(model, prompt: str) -> str:
    loop = asyncio.get_running_loop()
    def _call():
        resp = model.generate_content(prompt)
        return resp.text if getattr(resp, "text", None) else ""
    return await loop.run_in_executor(_get_executor(), _call)


async def async_generate_stream(model, prompt: str):
    # Fallback: run sync stream in a thread and yield chunks via an async queue
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[str] = asyncio.Queue()

    def _producer():
        try:
            stream = model.generate_content(prompt, stream=True)
            for chunk in stream:
                if hasattr(chunk, "text") and chunk.text:
                    asyncio.run_coroutine_threadsafe(queue.put(chunk.text), loop)
        except Exception as e:
            logger.error("async_generate_stream error: %s", e, exc_info=True)
        finally:
            asyncio.run_coroutine_threadsafe(queue.put("__STREAM_END__"), loop)

    _get_executor().submit(_producer)
    while True:
        piece = await queue.get()
        if piece == "__STREAM_END__":
            break
        yield piece


# Enhanced functions with history management and summarization

async def invoke_gemini_chat_with_history_management(
    usecase_id: uuid.UUID,
    query: str,
    chat_history: List[Dict],
    chat_summary: Optional[str],
    db: Session,
    model_name: str = "gemini-2.5-flash",
    timeout_seconds: int = 300
) -> Tuple[str, float, int, List[Dict], Optional[str], bool]:
    """
    Enhanced Gemini chat with intelligent history management and summarization.
    
    This function automatically manages chat history, performs summarization when needed,
    and provides the full conversation context to the LLM.
    
    Args:
        usecase_id (UUID): Usecase identifier
        query (str): The user's message/query
        chat_history (List[Dict]): Current chat history (newest first)
        chat_summary (str): Current chat summary (if any)
        db (Session): Database session for persistence
        timeout_seconds (int): Maximum time for the entire operation
    
    Returns:
        Tuple containing:
        - response_text (str): LLM response
        - cost_estimate (float): Estimated cost
        - tokens_estimate (int): Estimated tokens used
        - updated_history (List[Dict]): Updated chat history
        - updated_summary (str): Updated chat summary
        - summarization_performed (bool): Whether summarization was performed
    """
    if not GEMINI_API_KEY:
        error_response = json.dumps({
            "user_answer": "Error: GEMINI_API_KEY environment variable not set",
            "tool_call": None
        })
        return error_response, 0.0, 0, chat_history, chat_summary, False

    start_time = time.time()
    
    try:
        # Manage chat history with automatic summarization
        context, updated_history, updated_summary, summarized = await manage_chat_history_for_usecase(
            usecase_id=usecase_id,
            chat_history=chat_history,
            chat_summary=chat_summary,
            user_query=query,
            api_key=GEMINI_API_KEY,
            db=db,
            model_name=model_name
        )
        
        # Initialize the model
        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=CORTEXA_SYSTEM_PROMPT
        )
        
        # Generate response using the prepared context
        response = model.generate_content(
            context,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                max_output_tokens=2048,
                top_p=0.8,
                top_k=40
            )
        )
        
        
        # Extract response text
        response_text = response.text if response.text else "No response generated"
        # Write full response to disk
        try:
            base = _requirements_log_dir()
            ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S-%f")
            out_path = os.path.join(base, f"{ts}-gemini_history-out.txt")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(response_text)
            logger.info("invoke_gemini_chat_with_history_management: wrote full response to %s (chars=%d)", out_path, len(response_text))
        except Exception:
            pass
        
        # Estimate costs
        estimated_cost = 0.001  # Very rough estimate
        estimated_tokens = len(response_text.split()) * 1.3
        
        # Use robust JSON parsing with LangChain
        try:
            user_answer, tool_call, parsing_success = parse_llm_response(response_text)
            
            # Create properly formatted JSON response
            formatted_response = json.dumps({
                "user_answer": user_answer,
                "tool_call": tool_call
            })
            
            if not parsing_success:
                logger.warning(f"Used fallback JSON parsing in history management: {response_text[:100]}...")
                
        except Exception as parse_error:
            logger.error(f"Critical parsing error in history management: {parse_error}")
            # Final fallback - return error in proper JSON format
            formatted_response = json.dumps({
                "user_answer": f"I apologize, but I encountered an error processing my response. Please try again.",
                "tool_call": None
            })
        
        # Check timeout
        elapsed_time = time.time() - start_time
        if elapsed_time > timeout_seconds:
            raise TimeoutError(f"Gemini response timeout after {timeout_seconds} seconds")
        
        return formatted_response, estimated_cost, int(estimated_tokens), updated_history, updated_summary, summarized
        
    except TimeoutError:
        error_response = json.dumps({
            "user_answer": f"Request timed out after {timeout_seconds} seconds",
            "tool_call": None
        })
        return error_response, 0.0, 0, chat_history, chat_summary, False
        
    except Exception as e:
        error_message = f"Error in enhanced Gemini chat: {str(e)}"
        error_response = json.dumps({
            "user_answer": error_message,
            "tool_call": None
        })
        return error_response, 0.0, 0, chat_history, chat_summary, False


def get_chat_history_statistics(
    chat_history: List[Dict],
    chat_summary: Optional[str] = None,
    model_name: str = "gemini-2.5-flash"
) -> Dict:
    """
    Get comprehensive statistics about chat history and token usage.
    
    Args:
        chat_history (List[Dict]): Chat history to analyze
        chat_summary (str): Chat summary (if any)
        model_name (str): Gemini model name
        
    Returns:
        Dict: Comprehensive statistics
    """
    if not GEMINI_API_KEY:
        return {"error": "GEMINI_API_KEY not configured"}
    
    try:
        manager = ChatHistoryManager(GEMINI_API_KEY, model_name)
        return manager.get_history_statistics(chat_history, chat_summary)
    except Exception as e:
        return {"error": f"Error getting statistics: {str(e)}"}


def check_summarization_needed(
    chat_history: List[Dict],
    chat_summary: Optional[str] = None,
    model_name: str = "gemini-2.5-flash"
) -> Dict:
    """
    Check if chat history needs summarization.
    
    Args:
        chat_history (List[Dict]): Chat history to check
        chat_summary (str): Existing summary
        model_name (str): Gemini model name
        
    Returns:
        Dict: Analysis results including whether summarization is needed
    """
    try:
        from .token_counter import should_summarize_history, get_token_usage_info
        
        needs_summary = should_summarize_history(chat_history, chat_summary, model_name)
        token_info = get_token_usage_info(chat_history, chat_summary, model_name)
        
        return {
            "needs_summarization": needs_summary,
            "token_info": token_info,
            "recommendation": "Summarization recommended" if needs_summary else "No action needed"
        }
        
    except Exception as e:
        return {"error": f"Error checking summarization: {str(e)}"}


if __name__ == "__main__":
    # Example usage when script is run directly
    test_query = "Hello! What can you help me with today?"
    
    print("Testing Gemini invoker...")
    try:
        # Test basic function
        response, cost, tokens = invoke_gemini_chat(test_query)
        print(f"\nBasic Response: {response}")
        print(f"Estimated Cost: ${cost}")
        print(f"Estimated Tokens: {tokens}")
        
        # Test statistics
        test_history = [
            {"user": "Test message 1", "timestamp": "2025-01-08T10:00:00Z"},
            {"system": "Test response 1", "timestamp": "2025-01-08T10:00:05Z"}
        ]
        
        stats = get_chat_history_statistics(test_history)
        print(f"\nHistory Statistics: {stats}")
        
    except Exception as e:
        print(f"Error: {e}")
