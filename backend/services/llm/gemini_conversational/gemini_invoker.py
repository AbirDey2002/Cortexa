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

# Add the parent directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

# Import environment configuration
from core.env_config import get_env_variable

# Import history management modules
from .history_manager import manage_chat_history_for_usecase, ChatHistoryManager
from .token_counter import get_token_usage_info
from .json_output_parser import (
    parse_llm_response, 
    create_enhanced_cortexa_prompt,
    CortexaOutputParser,
    StrictJSONOutputParser
)

# Configure the Gemini API
GEMINI_API_KEY = get_env_variable("GEMINI_API_KEY", "")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# System prompt for Cortexa agent - using enhanced version with strict JSON requirements
CORTEXA_SYSTEM_PROMPT = create_enhanced_cortexa_prompt()

# Logger
logger = logging.getLogger(__name__)

def invoke_gemini_chat(query: str, chat_history: Optional[list] = None, timeout_seconds: int = 60) -> Tuple[str, float, int]:
    """
    Invoke Google Gemini 2.5 Flash for conversational AI.

    Args:
        query (str): The user's message/query
        chat_history (list, optional): List of previous chat messages
        timeout_seconds (int): Maximum time to wait for response

    Returns:
        tuple: A tuple containing (response_text, cost_estimate, tokens_estimate)
    """
    if not GEMINI_API_KEY:
        return "Error: GEMINI_API_KEY environment variable not set", 0.0, 0

    start_time = time.time()
    
    try:
        # Initialize the model
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=CORTEXA_SYSTEM_PROMPT
        )
        
        # Build conversation history for context
        conversation_context = []
        if chat_history:
            for entry in chat_history:
                if "user" in entry:
                    conversation_context.append(f"User: {entry['user']}")
                elif "system" in entry:
                    conversation_context.append(f"Assistant: {entry['system']}")
        
        # Add current query
        full_prompt = "\n".join(conversation_context + [f"User: {query}"])

        # Log inputs sent to the LLM (trimmed for readability)
        try:
            context_str = "\n".join(conversation_context)
            logger.info(
                "Gemini LLM input (history msgs=%d, context chars=%d, total prompt chars=%d):\nContext Preview:\n%s\nPrompt Preview:\n%s",
                len(chat_history or []),
                len(context_str),
                len(full_prompt),
                (context_str[:800] + ("..." if len(context_str) > 800 else "")),
                (full_prompt[:800] + ("..." if len(full_prompt) > 800 else "")),
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


# Enhanced functions with history management and summarization

async def invoke_gemini_chat_with_history_management(
    usecase_id: uuid.UUID,
    query: str,
    chat_history: List[Dict],
    chat_summary: Optional[str],
    db: Session,
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
            model_name="gemini-2.5-flash"
        )
        
        # Initialize the model
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
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
