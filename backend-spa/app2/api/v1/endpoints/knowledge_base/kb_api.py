"""
Knowledge Base Data Retrieval API

API endpoints for retrieving data from PurpleFabric Knowledge Base.
"""

import logging
import os
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

# Configure logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("KBRetrieval")

# Request/Response Models
class KBSearchRequest(BaseModel):
    """Request model for knowledge base search"""
    search_query: str = Field(..., description="The search query to execute")
    kb_id: str = Field(..., description="Knowledge Base ID to search in")
    top_k: int = Field(default=10, ge=1, le=100, description="Number of top results to return (1-100)")
    metadata: Dict[str, List[str]] = Field(default={}, description="Dictionary of metadata filters")
    tags: List[str] = Field(default=[], description="List of tags to filter by")

class KBSearchResponse(BaseModel):
    """Response model for knowledge base search"""
    success: bool
    data: str
    total_chunks: int
    message: Optional[str] = None

# Create router
router = APIRouter()

def retriever(
    search_query: str,
    kb_id: str,
    top_k: int,
    metadata: Dict[str, List[str]],
    tags: List[str]
) -> str:
    """
    Retrieve data from Knowledge Base
    
    Args:
        search_query: The search query to execute
        kb_id: Knowledge Base ID to search in
        top_k: Number of top results to return
        metadata: Dictionary of metadata filters (format: {"key": ["value1", "value2"]})
        tags: List of tags to filter by (format: ["tag1", "tag2"])
        
    Returns:
        str: Formatted string with all retrieved chunks in format "chunk 1: {...}, chunk 2: {...}"
    """
    
    # Authentication credentials
    APIKEY = os.getenv("PF_API_KEY", "")
    BASE_URL = "https://api.intellectseecstag.com"
    USER_ID = os.getenv("PF_USERNAME", "")
    PASSWORD = os.getenv("PF_PASSWORD", "")
    TENANT_ID = "idxpigtb"
    WORKSPACE_ID = "d9fd8387-579b-4919-ae9d-df8f256b147b"
    
    try:
        # Import PurpleFabric modules here to handle import errors gracefully
        try:
            from purplefabric import Session
            from purplefabric.core.exceptions import (
                ValidationError,
                ResourceNotFoundError,
                UnauthorizedError,
                PurpleFabricBaseError
            )
        except ImportError as e:
            return f"Error: PurpleFabric module not installed. {str(e)}"
        
        # Initialize session and KB client
        session = Session(
            apikey=APIKEY,
            base_url=BASE_URL,
            user_id=USER_ID,
            password=PASSWORD,
            tenant_id=TENANT_ID,
            headers={"x-platform-workspaceid": WORKSPACE_ID}
        )
        
        kb = session.client('kb')
        
        # Perform RAG search
        response = kb.rag_search(
            kb_id=kb_id,
            query=search_query,
            topk=top_k,
            min_similarity=0.3,
            metadata=metadata,
            tags=tags
        )
        
        # Format chunks
        chunks = response.data.get('chunks', [])
        
        if not chunks:
            return "No chunks found for the given query and filters."
        
        formatted_chunks = ""
        for i, chunk in enumerate(chunks, 1):
            chunk_data = {
                "similarity": chunk.get('similarity', 0),
                "text": chunk.get('text', ''),
                "document_name": chunk.get('document_name', 'Unknown'),
                "chunk_id": chunk.get('chunk_id', 'Unknown'),
                "metadata": chunk.get('metadata', {}),
                "tags": chunk.get('tags', [])
            }
            
            formatted_chunks += f"chunk {i}: {chunk_data}"
            if i < len(chunks):
                formatted_chunks += ",\n\n"
        
        return formatted_chunks
        
    except Exception as e:
        logger.error(f"Error in knowledge base retrieval: {str(e)}")
        return f"Error: {str(e)}"

@router.post("/search", response_model=KBSearchResponse)
async def search_knowledge_base(request: KBSearchRequest):
    """
    Search Knowledge Base using RAG (Retrieval-Augmented Generation)
    
    Retrieve relevant chunks from the PurpleFabric Knowledge Base based on the search query,
    with optional filtering by metadata and tags.
    
    Args:
        request: KBSearchRequest containing search parameters
        
    Returns:
        KBSearchResponse with formatted chunk data
    """
    
    try:
        # Validate inputs
        if not request.search_query.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Search query cannot be empty"
            )
        
        if not request.kb_id.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Knowledge Base ID cannot be empty"
            )
        
        # Perform the search
        result = retriever(
            search_query=request.search_query,
            kb_id=request.kb_id,
            top_k=request.top_k,
            metadata=request.metadata,
            tags=request.tags
        )
        
        # Check if result indicates an error
        if result.startswith("Error:"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result
            )
        
        # Count chunks in response
        chunk_count = result.count("chunk ") if result != "No chunks found for the given query and filters." else 0
        
        return KBSearchResponse(
            success=True,
            data=result,
            total_chunks=chunk_count,
            message="Search completed successfully" if chunk_count > 0 else "No results found"
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Unexpected error in search endpoint: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )

@router.get("/test")
async def test_knowledge_base():
    """
    Test endpoint to verify knowledge base functionality with example data
    """
    
    # Example request
    test_request = KBSearchRequest(
        search_query="top figures during the renaissance period",
        kb_id="fb611e8e-448a-4a0e-af50-0f3b9e8d128f",
        top_k=3,  # Smaller number for test
        metadata={"subject": ["history"]},
        tags=[]
    )
    
    try:
        # Use the same search function
        result = retriever(
            search_query=test_request.search_query,
            kb_id=test_request.kb_id,
            top_k=test_request.top_k,
            metadata=test_request.metadata,
            tags=test_request.tags
        )
        
        chunk_count = result.count("chunk ") if result != "No chunks found for the given query and filters." else 0
        
        return {
            "message": "Knowledge Base test completed",
            "test_query": test_request.search_query,
            "kb_id": test_request.kb_id,
            "total_chunks": chunk_count,
            "result_preview": result[:500] + "..." if len(result) > 500 else result,
            "success": not result.startswith("Error:")
        }
        
    except Exception as e:
        return {
            "message": "Knowledge Base test failed",
            "error": str(e),
            "success": False
        }

@router.get("/health")
async def kb_health_check():
    """Health check endpoint for knowledge base service"""
    return {
        "service": "Knowledge Base API",
        "status": "healthy",
        "version": "1.0.0",
        "endpoints": [
            "/search - Main search endpoint",
            "/test - Test endpoint with example data",
            "/health - This health check"
        ]
    } 