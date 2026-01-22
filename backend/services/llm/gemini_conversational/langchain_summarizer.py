"""
LangChain-based chat summarization service.

This module provides functionality to summarize chat histories using LangChain's
load_summarize_chain with Gemini models.
"""

import logging
from typing import List, Dict, Any
from langchain.chains.summarize import load_summarize_chain
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

logger = logging.getLogger(__name__)


def format_messages_for_langchain(messages: List[Dict[str, Any]]) -> str:
    """
    Format chat messages into a single text string for LangChain summarization.
    
    Args:
        messages (List[Dict]): Messages to format (should be oldest first)
        
    Returns:
        str: Formatted conversation text
    """
    formatted_lines = []
    
    for entry in messages:
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


async def summarize_with_langchain(
    messages: List[Dict[str, Any]],
    api_key: str,
    model_name: str = "gemini-2.5-flash"
) -> str:
    """
    Summarize chat messages using LangChain's load_summarize_chain.
    
    Args:
        messages (List[Dict]): Messages to summarize (oldest first)
        api_key (str): Gemini API key
        model_name (str): Gemini model name to use
        
    Returns:
        str: Summary of the chat history
        
    Raises:
        Exception: If summarization fails
    """
    logger.info(f"Starting LangChain summarization: {len(messages)} messages, model={model_name}")
    
    if not api_key:
        logger.error("API key is required for LangChain summarization")
        raise ValueError("API key is required for LangChain summarization")
    
    if not messages:
        logger.warning("No messages provided for summarization, returning empty string")
        return ""
    
    try:
        # Import here to avoid dependency issues if not installed
        logger.debug("Importing ChatGoogleGenerativeAI from langchain_google_genai")
        from langchain_google_genai import ChatGoogleGenerativeAI
        
        # Initialize the LLM
        logger.debug(f"Initializing ChatGoogleGenerativeAI with model={model_name}, temperature=0.3")
        llm = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=api_key,
            temperature=0.3  # Lower temperature for more consistent summaries
        )
        
        # Format messages into text
        logger.debug("Formatting messages for LangChain summarization")
        conversation_text = format_messages_for_langchain(messages)
        conversation_length = len(conversation_text)
        logger.info(f"Formatted conversation text: {conversation_length} characters")
        
        # Create Document objects for LangChain
        # If the text is long, split it into chunks
        logger.debug("Creating RecursiveCharacterTextSplitter (chunk_size=10000, chunk_overlap=500)")
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=10000,  # Split into chunks of 10k characters
            chunk_overlap=500,  # Overlap of 500 characters for context
            length_function=len
        )
        
        # Split the conversation into documents
        logger.debug("Splitting conversation into documents")
        texts = text_splitter.split_text(conversation_text)
        docs = [Document(page_content=text) for text in texts]
        logger.info(f"Split conversation into {len(docs)} document(s)")
        
        # Load the summarization chain
        # Use "stuff" chain type for shorter texts, "map_reduce" for longer ones
        chain_type = "stuff" if len(docs) == 1 else "map_reduce"
        logger.info(f"Using chain_type='{chain_type}' for summarization (1 doc: stuff, >1 doc: map_reduce)")
        
        logger.debug("Loading summarization chain")
        chain = load_summarize_chain(
            llm=llm,
            chain_type=chain_type,
            verbose=False
        )
        
        # Run the chain
        logger.info("Invoking LangChain summarization chain")
        result = chain.invoke(docs)
        logger.debug(f"Chain invocation completed, result type: {type(result)}")
        
        # Extract summary from result
        if isinstance(result, dict):
            summary = result.get("output_text", "")
            logger.debug(f"Extracted summary from dict result, length: {len(summary)} characters")
        else:
            summary = str(result)
            logger.debug(f"Converted result to string, length: {len(summary)} characters")
        
        if summary:
            summary_length = len(summary.strip())
            logger.info(f"Successfully summarized {len(messages)} messages using LangChain. Summary length: {summary_length} characters")
            return summary.strip()
        else:
            logger.error("No summary generated from LangChain - result was empty")
            raise Exception("No summary generated from LangChain")
            
    except ImportError as e:
        logger.error(f"LangChain Google GenAI not installed: {e}", exc_info=True)
        raise ImportError(
            "langchain-google-genai package is required. "
            "Install it with: pip install langchain-google-genai"
        )
    except Exception as e:
        logger.error(f"Error summarizing chat history with LangChain: {e}", exc_info=True)
        raise

