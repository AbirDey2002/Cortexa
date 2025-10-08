"""
Robust JSON output parsing for Gemini responses using LangChain.

This module provides utilities to ensure consistent JSON-only output from LLMs,
handling malformed responses and extra text that can cause parsing errors.
"""

import json
import re
import logging
from typing import Dict, Any, Optional, Tuple
from langchain_core.output_parsers import PydanticOutputParser, BaseOutputParser
from langchain_core.exceptions import OutputParserException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class CortexaResponse(BaseModel):
    """Structured response model for Cortexa agent."""
    user_answer: str = Field(description="The assistant's response to the user in plain text")
    tool_call: Optional[str] = Field(default=None, description="Name of tool to be called, or null if no tool needed")


class StrictJSONOutputParser(BaseOutputParser[Dict[str, Any]]):
    """
    Custom output parser that extracts JSON from potentially malformed LLM responses.
    
    This parser is designed to handle cases where the LLM outputs valid JSON
    but also includes additional text before or after the JSON object.
    """
    
    def parse(self, text: str) -> Dict[str, Any]:
        """
        Parse JSON from text, handling malformed responses.
        
        Args:
            text (str): Raw text from LLM that should contain JSON
            
        Returns:
            Dict[str, Any]: Parsed JSON object
            
        Raises:
            OutputParserException: If no valid JSON can be extracted
        """
        if not text or not text.strip():
            raise OutputParserException("Empty response from LLM")
        
        # Strategy 1: Try direct JSON parsing first
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass
        
        # Strategy 2: Extract JSON using regex patterns
        json_patterns = [
            # Look for JSON object at the start
            r'^\s*(\{[^}]*"user_answer"[^}]*\})',
            # Look for JSON object anywhere in text
            r'(\{[^}]*"user_answer"[^}]*\})',
            # Look for any valid JSON object
            r'(\{(?:[^{}]|{[^{}]*})*\})',
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, text, re.MULTILINE | re.DOTALL)
            for match in matches:
                try:
                    parsed = json.loads(match)
                    # Validate it has required structure
                    if isinstance(parsed, dict) and "user_answer" in parsed:
                        logger.info(f"Successfully extracted JSON using pattern: {pattern[:20]}...")
                        return parsed
                except json.JSONDecodeError:
                    continue
        
        # Strategy 3: Try to clean up and extract JSON manually
        cleaned_text = self._clean_text_for_json(text)
        try:
            return json.loads(cleaned_text)
        except json.JSONDecodeError:
            pass
        
        # Strategy 4: Create fallback JSON from text
        fallback_json = self._create_fallback_json(text)
        logger.warning(f"Used fallback JSON parsing for malformed response: {text[:100]}...")
        return fallback_json
    
    def _clean_text_for_json(self, text: str) -> str:
        """
        Clean text to extract potential JSON.
        
        Args:
            text (str): Raw text
            
        Returns:
            str: Cleaned text that might be valid JSON
        """
        # Remove common prefixes/suffixes
        text = text.strip()
        
        # Remove markdown code fences
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*$', '', text)
        
        # Find first { and last }
        first_brace = text.find('{')
        last_brace = text.rfind('}')
        
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            return text[first_brace:last_brace + 1]
        
        return text
    
    def _create_fallback_json(self, text: str) -> Dict[str, Any]:
        """
        Create a fallback JSON response when parsing fails.
        
        Args:
            text (str): Original text that couldn't be parsed
            
        Returns:
            Dict[str, Any]: Fallback JSON response
        """
        # Try to extract meaningful content
        content = text.strip()
        
        # Remove JSON-like characters if they exist
        content = re.sub(r'[{}",:]', ' ', content)
        content = re.sub(r'\s+', ' ', content).strip()
        
        # If content is too short, use original
        if len(content) < 10:
            content = text.strip()
        
        return {
            "user_answer": content if content else "I apologize, but I had trouble formatting my response properly. Could you please try again?",
            "tool_call": None
        }
    
    @property
    def _type(self) -> str:
        return "strict_json"


class CortexaOutputParser(PydanticOutputParser[CortexaResponse]):
    """
    Pydantic-based output parser for Cortexa responses.
    
    This ensures type safety and validation of the response structure.
    """
    
    def __init__(self):
        super().__init__(pydantic_object=CortexaResponse)
    
    def parse(self, text: str) -> CortexaResponse:
        """
        Parse text into a validated CortexaResponse object.
        
        Args:
            text (str): Raw text from LLM
            
        Returns:
            CortexaResponse: Validated response object
        """
        try:
            # First try the parent parser
            return super().parse(text)
        except OutputParserException:
            # Fall back to our strict JSON parser
            strict_parser = StrictJSONOutputParser()
            json_data = strict_parser.parse(text)
            
            # Convert to CortexaResponse
            return CortexaResponse(**json_data)


def create_enhanced_cortexa_prompt() -> str:
    """
    Create an enhanced system prompt that enforces strict JSON output.
    
    Returns:
        str: Enhanced system prompt
    """
    return """You are Cortexa, a helpful, testing-aware assistant. You converse naturally on any topic. When requests relate to application testing, you act as a test copilot: clarify goals, plan briefly, choose tools, execute, and present concise, actionable results.

**CRITICAL OUTPUT REQUIREMENTS**
- You MUST respond with ONLY a single, valid JSON object
- No text before the JSON object
- No text after the JSON object
- No markdown code fences
- No explanations outside the JSON
- No additional comments or questions

**REQUIRED JSON FORMAT**
{
  "user_answer": "your concise reply to the user in plain text",
  "tool_call": null
}

**TOOL CALLS**
- Set "tool_call" to null for normal responses
- Set "tool_call" to a string like "ocr" only when a specific tool is needed

**CONVERSATION MEMORY**
- You have access to full chat history
- Use it to resolve references and maintain continuity
- Keep responses concise but helpful

**EXAMPLES**
User: "Hello!"
Response: {"user_answer": "Hello! I'm Cortexa, your testing-aware assistant. How can I help you today?", "tool_call": null}

User: "Can you extract text from this image?"
Response: {"user_answer": "I'll help you extract text from the image.", "tool_call": "ocr"}

Remember: Output ONLY the JSON object, nothing else."""


def parse_llm_response(response_text: str) -> Tuple[str, Optional[str], bool]:
    """
    Parse LLM response using robust error handling.
    
    Args:
        response_text (str): Raw response from LLM
        
    Returns:
        Tuple[str, Optional[str], bool]: 
            - Parsed user_answer
            - Tool call (if any)
            - Whether parsing was successful
    """
    try:
        parser = CortexaOutputParser()
        parsed_response = parser.parse(response_text)
        
        return parsed_response.user_answer, parsed_response.tool_call, True
        
    except Exception as e:
        logger.error(f"Error parsing LLM response: {e}")
        logger.error(f"Original response: {response_text}")
        
        # Fallback parsing
        try:
            strict_parser = StrictJSONOutputParser()
            json_data = strict_parser.parse(response_text)
            return json_data.get("user_answer", response_text), json_data.get("tool_call"), False
            
        except Exception as fallback_error:
            logger.error(f"Fallback parsing also failed: {fallback_error}")
            return response_text, None, False


if __name__ == "__main__":
    # Test the parsers with various inputs
    test_cases = [
        '{"user_answer": "Hello!", "tool_call": null}',
        '{"user_answer": "I can help with that.", "tool_call": "ocr"}',
        '''{"user_answer": "Sure, I can help!", "tool_call": null}

Question: What about this other thing?''',
        '''Here's my response:
{"user_answer": "That's a great question!", "tool_call": null}

Let me know if you need more help.''',
        'Invalid JSON response that needs fallback handling'
    ]
    
    print("Testing JSON Output Parsers")
    print("=" * 50)
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\nTest Case {i}:")
        print(f"Input: {test_case[:50]}...")
        
        try:
            user_answer, tool_call, success = parse_llm_response(test_case)
            print(f"✅ Parsed successfully: {success}")
            print(f"User Answer: {user_answer[:50]}...")
            print(f"Tool Call: {tool_call}")
        except Exception as e:
            print(f"❌ Error: {e}")
