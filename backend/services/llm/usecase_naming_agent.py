"""
Usecase Naming Agent Service

This module provides functionality to automatically generate meaningful names for usecases
based on conversation context or document content.
"""

import logging
from typing import Optional, Tuple, List, Dict, Any
from uuid import UUID
import google.generativeai as genai
from sqlalchemy.orm import Session
from sqlalchemy import text

from core.env_config import get_env_variable
from .prompts.usecase_naming_prompt import (
    conversation_naming_prompt,
    document_naming_prompt
)

logger = logging.getLogger(__name__)

# Configuration
MAX_NAME_LENGTH = 200  # Maximum characters for usecase name (allows up to ~15 words)
NAMING_MODEL = "gemini-2.5-flash"  # Fast and cost-effective model for naming


def _is_first_message_exchange(chat_history: List[Dict[str, Any]]) -> bool:
    """
    Check if this is the first user message + first assistant response exchange.
    
    Args:
        chat_history (List[Dict]): Chat history (newest first)
        
    Returns:
        bool: True if exactly 1 user message and 1 system/assistant message
    """
    if not chat_history:
        return False
    
    user_count = 0
    system_count = 0
    
    for entry in chat_history:
        if isinstance(entry, dict):
            # Skip modal markers entirely
            if "modal" in entry:
                continue
            # Skip summary markers
            if "marker" in entry:
                continue
            
            # Count actual user messages
            if "user" in entry:
                user_count += 1
            # Count actual system/assistant messages
            elif "system" in entry:
                system_count += 1
    
    # First exchange = exactly 1 user message and 1 system message
    result = user_count == 1 and system_count == 1
    logger.debug(f"First message exchange check: user_count={user_count}, system_count={system_count}, result={result}")
    return result


def _extract_first_exchange(chat_history: List[Dict[str, Any]]) -> Tuple[str, str]:
    """
    Extract the first user query and first agent response from chat history.
    
    Args:
        chat_history (List[Dict]): Chat history (newest first)
        
    Returns:
        Tuple[str, str]: (user_query, agent_response)
    """
    user_query = ""
    agent_response = ""
    
    # Reverse to get chronological order (oldest first)
    chronological = list(reversed(chat_history))
    
    for entry in chronological:
        if not isinstance(entry, dict):
            continue
            
        # Skip modal markers and summary markers
        if "modal" in entry or "marker" in entry:
            continue
        
        if "user" in entry and not user_query:
            user_query = str(entry.get("user", "")).strip()
        elif "system" in entry and not agent_response:
            system_value = entry.get("system", "")
            # Extract text from system response
            if isinstance(system_value, str):
                agent_response = system_value.strip()
            elif isinstance(system_value, list):
                # Handle list of chunks
                texts = []
                for chunk in system_value:
                    if isinstance(chunk, dict) and "text" in chunk:
                        texts.append(str(chunk.get("text", "")))
                agent_response = "\n".join(texts).strip()
            else:
                agent_response = str(system_value).strip()
        
        # Stop once we have both
        if user_query and agent_response:
            break
    
    logger.debug(f"Extracted first exchange: user_query length={len(user_query)}, agent_response length={len(agent_response)}")
    return user_query, agent_response


def _get_all_extracted_text(usecase_id: UUID, db: Session) -> str:
    """
    Get all extracted text from all files in a usecase.
    
    Args:
        usecase_id (UUID): Usecase identifier
        db (Session): Database session
        
    Returns:
        str: Combined markdown text from all files
    """
    try:
        from models.file_processing.file_metadata import FileMetadata
        from models.file_processing.ocr_records import OCROutputs
        
        # Get all files for the usecase
        files = db.query(FileMetadata).filter(
            FileMetadata.usecase_id == usecase_id,
            FileMetadata.is_deleted == False
        ).order_by(FileMetadata.created_at.asc()).all()
        
        if not files:
            logger.warning(f"No files found for usecase {usecase_id}")
            return ""
        
        combined_parts = []
        
        for file_metadata in files:
            # Get OCR outputs for this file
            outputs = db.query(OCROutputs).filter(
                OCROutputs.file_id == file_metadata.file_id,
                OCROutputs.is_deleted == False
            ).order_by(OCROutputs.page_number.asc()).all()
            
            if outputs:
                # Combine page texts
                page_texts = [o.page_text or "" for o in outputs if o.page_text]
                file_text = "\n".join(page_texts).strip()
                
                if file_text:
                    combined_parts.append(f"## {file_metadata.file_name}\n\n{file_text}\n")
        
        combined_markdown = "\n".join(combined_parts).strip()
        logger.info(f"Retrieved {len(files)} files, combined text length: {len(combined_markdown)} characters")
        
        return combined_markdown
        
    except Exception as e:
        logger.error(f"Error getting extracted text for usecase {usecase_id}: {e}", exc_info=True)
        return ""


class UsecaseNamingAgent:
    """
    Agent for generating meaningful usecase names.
    """
    
    def __init__(self, api_key: str, model_name: str = NAMING_MODEL):
        """
        Initialize the naming agent.
        
        Args:
            api_key (str): Gemini API key
            model_name (str): Gemini model name to use
        """
        self.api_key = api_key
        self.model_name = model_name
        
        if not api_key:
            logger.warning("No API key provided for UsecaseNamingAgent")
    
    def generate_name_from_conversation(
        self, 
        user_query: str, 
        agent_response: str
    ) -> Optional[str]:
        """
        Generate a usecase name from the first user query and agent response.
        
        Args:
            user_query (str): First user message
            agent_response (str): First agent response
            
        Returns:
            Optional[str]: Generated name, or None if generation fails
        """
        if not self.api_key:
            logger.error("Cannot generate name: API key not configured")
            return None
        
        if not user_query or not agent_response:
            logger.warning("Cannot generate name: missing user query or agent response")
            return None
        
        try:
            # Configure Gemini
            genai.configure(api_key=self.api_key)
            
            # Initialize model with naming prompt
            model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=conversation_naming_prompt
            )
            
            # Create prompt with conversation context
            prompt = f"""User Query:
{user_query}

Agent Response:
{agent_response}

Based on the above conversation, generate a concise usecase name following the guidelines in your system prompt."""
            
            logger.info(f"Generating usecase name from conversation (user_query: {len(user_query)} chars, agent_response: {len(agent_response)} chars)")
            
            # Generate name with safety settings that allow more permissive responses
            try:
                response = model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.3,  # Lower temperature for more consistent names
                        max_output_tokens=50,  # Names should be short
                        top_p=0.8,
                        top_k=40
                    ),
                    safety_settings=[
                        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                    ]
                )
            except Exception as safety_error:
                logger.warning(f"Error with safety settings, trying without: {safety_error}")
                # Retry without custom safety settings
                response = model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.3,
                        max_output_tokens=50,
                        top_p=0.8,
                        top_k=40
                    )
                )
            
            # Check for blocked/filtered responses
            if response.candidates and len(response.candidates) > 0:
                candidate = response.candidates[0]
                finish_reason = candidate.finish_reason if hasattr(candidate, 'finish_reason') else None
                
                # finish_reason 2 = SAFETY (blocked), 3 = RECITATION (blocked), 4 = OTHER (blocked)
                if finish_reason in (2, 3, 4):
                    logger.warning(f"Gemini response blocked (finish_reason={finish_reason}) for conversation-based usecase naming. Trying fallback strategies.")
                    
                    # Fallback 1: Try to extract any available text from the response
                    if hasattr(candidate, 'content') and candidate.content:
                        parts = candidate.content.parts if hasattr(candidate.content, 'parts') else []
                        for part in parts:
                            if hasattr(part, 'text') and part.text:
                                name = part.text.strip()
                                name = name.strip('"\'')
                                if len(name) > MAX_NAME_LENGTH:
                                    name = name[:MAX_NAME_LENGTH].rsplit(' ', 1)[0]
                                logger.info(f"Extracted name from blocked response: '{name}'")
                                return name
                    
                    # Fallback 2: Try with a simpler prompt (just extract key words)
                    logger.info("Trying fallback with simplified prompt")
                    try:
                        # Extract key words from user query and agent response
                        simple_prompt = f"""User query: {user_query[:200]}
Agent response: {agent_response[:300]}

Generate a short name (2-5 words) for this conversation topic."""
                        
                        fallback_response = model.generate_content(
                            simple_prompt,
                            generation_config=genai.types.GenerationConfig(
                                temperature=0.5,
                                max_output_tokens=30
                            ),
                            safety_settings=[
                                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                            ]
                        )
                        
                        # Check if fallback response is also blocked
                        if fallback_response.candidates and len(fallback_response.candidates) > 0:
                            fallback_candidate = fallback_response.candidates[0]
                            fallback_finish_reason = fallback_candidate.finish_reason if hasattr(fallback_candidate, 'finish_reason') else None
                            if fallback_finish_reason in (2, 3, 4):
                                logger.warning(f"Fallback prompt also blocked (finish_reason={fallback_finish_reason})")
                                # Try to extract from parts
                                if hasattr(fallback_candidate, 'content') and fallback_candidate.content:
                                    parts = fallback_candidate.content.parts if hasattr(fallback_candidate.content, 'parts') else []
                                    for part in parts:
                                        if hasattr(part, 'text') and part.text:
                                            name = part.text.strip()
                                            name = name.strip('"\'')
                                            if len(name) > MAX_NAME_LENGTH:
                                                name = name[:MAX_NAME_LENGTH].rsplit(' ', 1)[0]
                                            logger.info(f"Extracted name from blocked fallback response: '{name}'")
                                            return name
                        else:
                            # Try to access text normally
                            try:
                                if fallback_response.text:
                                    name = fallback_response.text.strip()
                                    name = name.strip('"\'')
                                    if len(name) > MAX_NAME_LENGTH:
                                        name = name[:MAX_NAME_LENGTH].rsplit(' ', 1)[0]
                                    logger.info(f"Generated name from fallback prompt: '{name}'")
                                    return name
                            except ValueError:
                                # Response blocked, try to extract from parts
                                if fallback_response.candidates and len(fallback_response.candidates) > 0:
                                    fallback_candidate = fallback_response.candidates[0]
                                    if hasattr(fallback_candidate, 'content') and fallback_candidate.content:
                                        parts = fallback_candidate.content.parts if hasattr(fallback_candidate.content, 'parts') else []
                                        for part in parts:
                                            if hasattr(part, 'text') and part.text:
                                                name = part.text.strip()
                                                name = name.strip('"\'')
                                                if len(name) > MAX_NAME_LENGTH:
                                                    name = name[:MAX_NAME_LENGTH].rsplit(' ', 1)[0]
                                                logger.info(f"Extracted name from fallback response parts: '{name}'")
                                                return name
                    except Exception as fallback_error:
                        logger.warning(f"Fallback prompt also failed: {fallback_error}")
                    
                    # Fallback 3: Extract name heuristically from user query
                    logger.info("Trying heuristic extraction from user query")
                    try:
                        heuristic_name = self._extract_name_from_conversation_heuristic(user_query, agent_response)
                        if heuristic_name:
                            logger.info(f"Generated name using heuristic: '{heuristic_name}'")
                            return heuristic_name
                    except Exception as heuristic_error:
                        logger.warning(f"Heuristic extraction failed: {heuristic_error}")
                    
                    logger.error(f"All fallback strategies failed for blocked response (finish_reason={finish_reason})")
                    return None
            
            # Normal response handling
            try:
                if response.text:
                    name = response.text.strip()
                    # Remove quotes if present
                    name = name.strip('"\'')
                    # Truncate if too long
                    if len(name) > MAX_NAME_LENGTH:
                        name = name[:MAX_NAME_LENGTH].rsplit(' ', 1)[0]  # Truncate at word boundary
                    
                    logger.info(f"Generated usecase name from conversation: '{name}'")
                    return name
                else:
                    logger.error("No name generated from Gemini (empty response)")
                    return None
            except ValueError as ve:
                # Handle the case where response.text throws ValueError (blocked response)
                logger.warning(f"Could not access response.text: {ve}. Trying alternative extraction.")
                if response.candidates and len(response.candidates) > 0:
                    candidate = response.candidates[0]
                    if hasattr(candidate, 'content') and candidate.content:
                        parts = candidate.content.parts if hasattr(candidate.content, 'parts') else []
                        for part in parts:
                            if hasattr(part, 'text') and part.text:
                                name = part.text.strip()
                                name = name.strip('"\'')
                                if len(name) > MAX_NAME_LENGTH:
                                    name = name[:MAX_NAME_LENGTH].rsplit(' ', 1)[0]
                                logger.info(f"Extracted name from response parts: '{name}'")
                                return name
                logger.error(f"Could not extract name from response: {ve}")
                return None
                
        except Exception as e:
            logger.error(f"Error generating name from conversation: {e}", exc_info=True)
            return None
    
    def generate_name_from_document(self, document_text: str) -> Optional[str]:
        """
        Generate a usecase name from extracted document text.
        
        Args:
            document_text (str): Combined text from all documents
            
        Returns:
            Optional[str]: Generated name, or None if generation fails
        """
        if not self.api_key:
            logger.error("Cannot generate name: API key not configured")
            return None
        
        if not document_text or not document_text.strip():
            logger.warning("Cannot generate name: document text is empty")
            return None
        
        try:
            # Configure Gemini
            genai.configure(api_key=self.api_key)
            
            # Initialize model with naming prompt
            model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=document_naming_prompt
            )
            
            # Truncate document text if too long (to avoid token limits)
            # Use first 10000 characters for naming (increased to capture more context)
            truncated_text = document_text[:10000] if len(document_text) > 10000 else document_text
            
            # Create prompt with full document content
            prompt = f"""Here is the complete document content:

{truncated_text}

Please analyze the above document content and generate a concise, descriptive usecase name that best represents the document's main topic, subject, or purpose. Follow the naming guidelines provided in your system instructions."""
            
            logger.info(f"Generating usecase name from document (text length: {len(document_text)} chars, using: {len(truncated_text)} chars)")
            
            # Generate name with safety settings that allow more permissive responses
            try:
                response = model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.3,  # Lower temperature for more consistent names
                        max_output_tokens=50,  # Names should be short
                        top_p=0.8,
                        top_k=40
                    ),
                    safety_settings=[
                        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                    ]
                )
            except Exception as safety_error:
                logger.warning(f"Error with safety settings, trying without: {safety_error}")
                # Retry without custom safety settings
                response = model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.3,
                        max_output_tokens=50,
                        top_p=0.8,
                        top_k=40
                    )
                )
            
            # Check for blocked/filtered responses
            if response.candidates and len(response.candidates) > 0:
                candidate = response.candidates[0]
                finish_reason = candidate.finish_reason if hasattr(candidate, 'finish_reason') else None
                
                # finish_reason 2 = SAFETY (blocked), 3 = RECITATION (blocked), 4 = OTHER (blocked)
                if finish_reason in (2, 3, 4):
                    logger.warning(f"Gemini response blocked (finish_reason={finish_reason}) for document-based usecase naming. Trying fallback strategies.")
                    
                    # Fallback 1: Try to extract any available text from the response
                    if hasattr(candidate, 'content') and candidate.content:
                        parts = candidate.content.parts if hasattr(candidate.content, 'parts') else []
                        for part in parts:
                            if hasattr(part, 'text') and part.text:
                                name = part.text.strip()
                                name = name.strip('"\'')
                                if len(name) > MAX_NAME_LENGTH:
                                    name = name[:MAX_NAME_LENGTH].rsplit(' ', 1)[0]
                                logger.info(f"Extracted name from blocked response: '{name}'")
                                return name
                    
                    # Fallback 2: Try with a simpler prompt (just first 1000 chars)
                    logger.info("Trying fallback with simplified prompt (first 1000 chars)")
                    try:
                        simple_text = document_text[:1000] if len(document_text) > 1000 else document_text
                        simple_prompt = f"""Document excerpt:

{simple_text}

Generate a short name (3-8 words) for this document based on its content."""
                        
                        fallback_response = model.generate_content(
                            simple_prompt,
                            generation_config=genai.types.GenerationConfig(
                                temperature=0.5,
                                max_output_tokens=30
                            ),
                            safety_settings=[
                                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                            ]
                        )
                        
                        # Check if fallback response is also blocked
                        if fallback_response.candidates and len(fallback_response.candidates) > 0:
                            fallback_candidate = fallback_response.candidates[0]
                            fallback_finish_reason = fallback_candidate.finish_reason if hasattr(fallback_candidate, 'finish_reason') else None
                            if fallback_finish_reason in (2, 3, 4):
                                logger.warning(f"Fallback prompt also blocked (finish_reason={fallback_finish_reason})")
                                # Try to extract from parts
                                if hasattr(fallback_candidate, 'content') and fallback_candidate.content:
                                    parts = fallback_candidate.content.parts if hasattr(fallback_candidate.content, 'parts') else []
                                    for part in parts:
                                        if hasattr(part, 'text') and part.text:
                                            name = part.text.strip()
                                            name = name.strip('"\'')
                                            if len(name) > MAX_NAME_LENGTH:
                                                name = name[:MAX_NAME_LENGTH].rsplit(' ', 1)[0]
                                            logger.info(f"Extracted name from blocked fallback response: '{name}'")
                                            return name
                        else:
                            # Try to access text normally
                            try:
                                if fallback_response.text:
                                    name = fallback_response.text.strip()
                                    name = name.strip('"\'')
                                    if len(name) > MAX_NAME_LENGTH:
                                        name = name[:MAX_NAME_LENGTH].rsplit(' ', 1)[0]
                                    logger.info(f"Generated name from fallback prompt: '{name}'")
                                    return name
                            except ValueError:
                                # Response blocked, try to extract from parts
                                if fallback_response.candidates and len(fallback_response.candidates) > 0:
                                    fallback_candidate = fallback_response.candidates[0]
                                    if hasattr(fallback_candidate, 'content') and fallback_candidate.content:
                                        parts = fallback_candidate.content.parts if hasattr(fallback_candidate.content, 'parts') else []
                                        for part in parts:
                                            if hasattr(part, 'text') and part.text:
                                                name = part.text.strip()
                                                name = name.strip('"\'')
                                                if len(name) > MAX_NAME_LENGTH:
                                                    name = name[:MAX_NAME_LENGTH].rsplit(' ', 1)[0]
                                                logger.info(f"Extracted name from fallback response parts: '{name}'")
                                                return name
                    except Exception as fallback_error:
                        logger.warning(f"Fallback prompt also failed: {fallback_error}")
                    
                    # Fallback 3: Extract name from document text heuristically
                    logger.info("Trying heuristic extraction from document text")
                    try:
                        heuristic_name = self._extract_name_heuristic(document_text)
                        if heuristic_name:
                            logger.info(f"Generated name using heuristic: '{heuristic_name}'")
                            return heuristic_name
                    except Exception as heuristic_error:
                        logger.warning(f"Heuristic extraction failed: {heuristic_error}")
                    
                    logger.error(f"All fallback strategies failed for blocked response (finish_reason={finish_reason})")
                    return None
            
            # Normal response handling
            try:
                if response.text:
                    name = response.text.strip()
                    # Remove quotes if present
                    name = name.strip('"\'')
                    # Truncate if too long
                    if len(name) > MAX_NAME_LENGTH:
                        name = name[:MAX_NAME_LENGTH].rsplit(' ', 1)[0]  # Truncate at word boundary
                    
                    logger.info(f"Generated usecase name from document: '{name}'")
                    return name
                else:
                    logger.error("No name generated from Gemini (empty response)")
                    return None
            except ValueError as ve:
                # Handle the case where response.text throws ValueError (blocked response)
                logger.warning(f"Could not access response.text: {ve}. Trying alternative extraction.")
                if response.candidates and len(response.candidates) > 0:
                    candidate = response.candidates[0]
                    if hasattr(candidate, 'content') and candidate.content:
                        parts = candidate.content.parts if hasattr(candidate.content, 'parts') else []
                        for part in parts:
                            if hasattr(part, 'text') and part.text:
                                name = part.text.strip()
                                name = name.strip('"\'')
                                if len(name) > MAX_NAME_LENGTH:
                                    name = name[:MAX_NAME_LENGTH].rsplit(' ', 1)[0]
                                logger.info(f"Extracted name from response parts: '{name}'")
                                return name
                
                # Try heuristic fallback
                heuristic_name = self._extract_name_heuristic(document_text)
                if heuristic_name:
                    logger.info(f"Generated name using heuristic after ValueError: '{heuristic_name}'")
                    return heuristic_name
                
                logger.error(f"Could not extract name from response: {ve}")
                return None
                
        except Exception as e:
            logger.error(f"Error generating name from document: {e}", exc_info=True)
            # Last resort: try heuristic extraction
            try:
                heuristic_name = self._extract_name_heuristic(document_text)
                if heuristic_name:
                    logger.info(f"Generated name using heuristic after exception: '{heuristic_name}'")
                    return heuristic_name
            except:
                pass
            return None
    
    def _extract_name_heuristic(self, document_text: str) -> Optional[str]:
        """
        Extract a name heuristically from document text when Gemini blocks the response.
        
        Args:
            document_text (str): Document text
            
        Returns:
            Optional[str]: Extracted name or None
        """
        try:
            import re
            
            # Try to find title-like patterns (lines that look like titles)
            lines = document_text.split('\n')[:20]  # Check first 20 lines
            
            # Look for lines that are:
            # - Short (less than 100 chars)
            # - Title case or all caps
            # - Not empty
            # - Don't start with common prefixes
            for line in lines:
                line = line.strip()
                if not line or len(line) > 100:
                    continue
                
                # Skip common prefixes
                if line.lower().startswith(('table of', 'contents', 'page', 'chapter', 'section', 'abstract', 'introduction')):
                    continue
                
                # Check if it looks like a title (title case or all caps, short)
                words = line.split()
                if 2 <= len(words) <= 15:
                    # Check if it's mostly title case or all caps
                    title_case_count = sum(1 for w in words if w and (w[0].isupper() or w.isupper()))
                    if title_case_count >= len(words) * 0.7:  # At least 70% title case
                        # Clean up the name
                        name = ' '.join(words)
                        if len(name) > MAX_NAME_LENGTH:
                            name = name[:MAX_NAME_LENGTH].rsplit(' ', 1)[0]
                        return name
            
            # Fallback: Extract first meaningful sentence or phrase
            # Remove markdown headers
            text_clean = re.sub(r'^#+\s+', '', document_text, flags=re.MULTILINE)
            # Get first 200 chars
            first_part = text_clean[:200].strip()
            if first_part:
                # Extract first sentence or first 50 chars
                sentences = re.split(r'[.!?]\s+', first_part)
                if sentences:
                    first_sentence = sentences[0].strip()
                    if 10 <= len(first_sentence) <= 100:
                        words = first_sentence.split()[:10]  # Max 10 words
                        name = ' '.join(words)
                        if len(name) > MAX_NAME_LENGTH:
                            name = name[:MAX_NAME_LENGTH].rsplit(' ', 1)[0]
                        return name
            
            return None
        except Exception as e:
            logger.warning(f"Error in heuristic name extraction: {e}")
            return None
    
    def _extract_name_from_conversation_heuristic(self, user_query: str, agent_response: str) -> Optional[str]:
        """
        Extract a name heuristically from user query and agent response when Gemini blocks the response.
        
        Args:
            user_query (str): First user message
            agent_response (str): First agent response
            
        Returns:
            Optional[str]: Extracted name or None
        """
        try:
            import re
            
            # Strategy 1: Extract key words from user query
            # Remove common question words and stop words
            stop_words = {'what', 'how', 'why', 'when', 'where', 'who', 'can', 'could', 'would', 'should', 
                         'is', 'are', 'was', 'were', 'do', 'does', 'did', 'the', 'a', 'an', 'and', 'or', 'but',
                         'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them',
                         'help', 'please', 'want', 'need', 'like', 'tell', 'explain', 'show'}
            
            # Extract meaningful words from user query
            query_words = re.findall(r'\b\w+\b', user_query.lower())
            meaningful_words = [w for w in query_words if w not in stop_words and len(w) > 2]
            
            if meaningful_words:
                # Take first 3-5 meaningful words
                name_words = meaningful_words[:5]
                if 2 <= len(name_words) <= 15:
                    # Capitalize first letter of each word (title case)
                    name = ' '.join(word.capitalize() for word in name_words)
                    if len(name) > MAX_NAME_LENGTH:
                        name = name[:MAX_NAME_LENGTH].rsplit(' ', 1)[0]
                    logger.info(f"Extracted name from user query keywords: '{name}'")
                    return name
            
            # Strategy 2: Extract first sentence or phrase from user query
            # Remove question marks and exclamation marks
            query_clean = user_query.strip('?!.').strip()
            if query_clean:
                # Take first 10 words
                words = query_clean.split()[:10]
                if 2 <= len(words) <= 15:
                    # Capitalize appropriately
                    name = ' '.join(word.capitalize() if i == 0 or word.lower() not in stop_words else word.lower() 
                                   for i, word in enumerate(words))
                    if len(name) > MAX_NAME_LENGTH:
                        name = name[:MAX_NAME_LENGTH].rsplit(' ', 1)[0]
                    logger.info(f"Extracted name from user query sentence: '{name}'")
                    return name
            
            # Strategy 3: Extract key topic from agent response (first sentence)
            if agent_response:
                # Get first sentence of agent response
                first_sentence_match = re.match(r'^([^.!?]+)', agent_response.strip())
                if first_sentence_match:
                    first_sentence = first_sentence_match.group(1).strip()
                    # Extract key words (nouns and important verbs)
                    words = first_sentence.split()[:8]
                    if 2 <= len(words) <= 15:
                        name = ' '.join(word.capitalize() if i == 0 else word.lower() for i, word in enumerate(words))
                        if len(name) > MAX_NAME_LENGTH:
                            name = name[:MAX_NAME_LENGTH].rsplit(' ', 1)[0]
                        logger.info(f"Extracted name from agent response: '{name}'")
                        return name
            
            # Strategy 4: Combine user query and agent response keywords
            if meaningful_words:
                # Use just the first 3 words as a simple name
                name_words = meaningful_words[:3]
                name = ' '.join(word.capitalize() for word in name_words)
                if len(name) > MAX_NAME_LENGTH:
                    name = name[:MAX_NAME_LENGTH].rsplit(' ', 1)[0]
                logger.info(f"Extracted simple name from keywords: '{name}'")
                return name
            
            return None
        except Exception as e:
            logger.warning(f"Error in conversation heuristic name extraction: {e}")
            return None


def generate_and_update_usecase_name_from_conversation(
    usecase_id: UUID,
    user_query: str,
    agent_response: str,
    db: Session,
    api_key: str
) -> bool:
    """
    Generate usecase name from conversation and update database.
    
    Args:
        usecase_id (UUID): Usecase identifier
        user_query (str): First user message
        agent_response (str): First agent response
        db (Session): Database session
        api_key (str): Gemini API key
        
    Returns:
        bool: True if name was successfully updated, False otherwise
    """
    try:
        from models.usecase.usecase import UsecaseMetadata
        
        # Generate name
        naming_agent = UsecaseNamingAgent(api_key)
        new_name = naming_agent.generate_name_from_conversation(user_query, agent_response)
        
        if not new_name:
            logger.warning(f"Failed to generate name for usecase {usecase_id}")
            return False
        
        # Update database
        usecase = db.query(UsecaseMetadata).filter(
            UsecaseMetadata.usecase_id == usecase_id,
            UsecaseMetadata.is_deleted == False
        ).first()
        
        if not usecase:
            logger.error(f"Usecase {usecase_id} not found")
            return False
        
        # Only update if name is different and not a default "Chat X" name
        current_name = usecase.usecase_name or ""
        if new_name != current_name and not current_name.startswith("Chat "):
            usecase.usecase_name = new_name
            db.commit()
            logger.info(f"Updated usecase {usecase_id} name from '{current_name}' to '{new_name}'")
            return True
        elif current_name.startswith("Chat "):
            # Always update if current name is a default "Chat X" name
            usecase.usecase_name = new_name
            db.commit()
            logger.info(f"Updated usecase {usecase_id} name from default '{current_name}' to '{new_name}'")
            return True
        else:
            logger.info(f"Usecase {usecase_id} name unchanged: '{current_name}'")
            return False
            
    except Exception as e:
        logger.error(f"Error updating usecase name from conversation: {e}", exc_info=True)
        try:
            db.rollback()
        except:
            pass
        return False


def _run_conversation_naming_task(usecase_id: UUID, user_query: str, agent_response: str, api_key: str):
    """
    Background task wrapper for conversation-based naming (Stage 1).
    Creates its own database session.
    
    Args:
        usecase_id (UUID): Usecase identifier
        user_query (str): First user message
        agent_response (str): First agent response
        api_key (str): Gemini API key
    """
    try:
        from db.session import get_db_context
        
        with get_db_context() as db:
            generate_and_update_usecase_name_from_conversation(
                usecase_id=usecase_id,
                user_query=user_query,
                agent_response=agent_response,
                db=db,
                api_key=api_key
            )
    except Exception as e:
        logger.error(f"Error in background conversation naming task for usecase {usecase_id}: {e}", exc_info=True)


def _run_document_naming_task(usecase_id: UUID, api_key: str):
    """
    Background task wrapper for document-based naming (Stage 2).
    Creates its own database session.
    
    Args:
        usecase_id (UUID): Usecase identifier
        api_key (str): Gemini API key
    """
    try:
        from db.session import get_db_context
        
        with get_db_context() as db:
            generate_and_update_usecase_name_from_document(
                usecase_id=usecase_id,
                db=db,
                api_key=api_key
            )
    except Exception as e:
        logger.error(f"Error in background document naming task for usecase {usecase_id}: {e}", exc_info=True)


def generate_and_update_usecase_name_from_document(
    usecase_id: UUID,
    db: Session,
    api_key: str
) -> bool:
    """
    Generate usecase name from extracted documents and update database.
    
    Args:
        usecase_id (UUID): Usecase identifier
        db (Session): Database session
        api_key (str): Gemini API key
        
    Returns:
        bool: True if name was successfully updated, False otherwise
    """
    try:
        from models.usecase.usecase import UsecaseMetadata
        from models.file_processing.file_metadata import FileMetadata
        
        logger.info(f"Starting document-based naming for usecase {usecase_id}")
        
        # Get extracted text
        document_text = _get_all_extracted_text(usecase_id, db)
        
        if not document_text or not document_text.strip():
            logger.warning(f"No extracted text found for usecase {usecase_id}")
            # Try to use filename as fallback
            files = db.query(FileMetadata).filter(
                FileMetadata.usecase_id == usecase_id,
                FileMetadata.is_deleted == False
            ).order_by(FileMetadata.created_at.asc()).all()
            
            if files:
                # Use first filename (remove extension and clean up)
                import os
                filename = files[0].file_name
                name_without_ext = os.path.splitext(filename)[0]
                # Clean up filename (remove underscores, dashes, etc.)
                name_clean = name_without_ext.replace('_', ' ').replace('-', ' ').strip()
                if name_clean and len(name_clean) <= MAX_NAME_LENGTH:
                    usecase = db.query(UsecaseMetadata).filter(
                        UsecaseMetadata.usecase_id == usecase_id,
                        UsecaseMetadata.is_deleted == False
                    ).first()
                    if usecase:
                        current_name = usecase.usecase_name or ""
                        usecase.usecase_name = name_clean
                        db.commit()
                        logger.info(f"Updated usecase {usecase_id} name from '{current_name}' to '{name_clean}' (using filename fallback)")
                        return True
            return False
        
        logger.info(f"Retrieved document text for usecase {usecase_id}: {len(document_text)} characters")
        
        # Generate name
        naming_agent = UsecaseNamingAgent(api_key)
        new_name = naming_agent.generate_name_from_document(document_text)
        
        if not new_name:
            logger.warning(f"Failed to generate name from document for usecase {usecase_id}, trying filename fallback")
            # Fallback to filename
            files = db.query(FileMetadata).filter(
                FileMetadata.usecase_id == usecase_id,
                FileMetadata.is_deleted == False
            ).order_by(FileMetadata.created_at.asc()).all()
            
            if files:
                import os
                filename = files[0].file_name
                name_without_ext = os.path.splitext(filename)[0]
                name_clean = name_without_ext.replace('_', ' ').replace('-', ' ').strip()
                if name_clean and len(name_clean) <= MAX_NAME_LENGTH:
                    new_name = name_clean
                    logger.info(f"Using filename as fallback: '{new_name}'")
                else:
                    return False
            else:
                return False
        
        logger.info(f"Generated name for usecase {usecase_id}: '{new_name}'")
        
        # Update database
        usecase = db.query(UsecaseMetadata).filter(
            UsecaseMetadata.usecase_id == usecase_id,
            UsecaseMetadata.is_deleted == False
        ).first()
        
        if not usecase:
            logger.error(f"Usecase {usecase_id} not found")
            return False
        
        # Update name (document-based naming should always update)
        current_name = usecase.usecase_name or ""
        usecase.usecase_name = new_name
        db.commit()
        logger.info(f"Updated usecase {usecase_id} name from '{current_name}' to '{new_name}' (document-based)")
        return True
            
    except Exception as e:
        logger.error(f"Error updating usecase name from document: {e}", exc_info=True)
        try:
            db.rollback()
        except:
            pass
        return False

