from dotenv import load_dotenv
load_dotenv()  # Load environment variables before importing config classes

from fastapi import FastAPI, Response, BackgroundTasks, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from models.base import Base
from db.session import engine
from api.v1.api_router import api_router
import json
import uuid
import time
from datetime import datetime
import asyncio
import logging
from typing import AsyncIterator, Dict, List, Optional
from core.logging_config import setup_logging
import os
from pathlib import Path
from services.llm.text2text_conversational.asset_invoker import invoke_asset_with_proper_timeout

# Initialize database
Base.metadata.create_all(bind=engine)

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(title="cortexa backend")

# Include API router
app.include_router(api_router)

# Mount static files directory for serving uploaded files
uploads_dir = "uploads"
if not os.path.exists(uploads_dir):
    os.makedirs(uploads_dir)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")

# In-memory storage for chat history
chat_storage = {}

# In-memory streaming storage for ongoing responses
streaming_responses: Dict[str, List[str]] = {}

# In-memory storage for response chunks
response_chunks: Dict[str, List[str]] = {}

# Function to parse agent output
def _parse_agent_output(raw_output: str) -> str:
    """Extract user_answer string from PF agent output which may be wrapped in ```json fences."""
    try:
        import re
        text = raw_output.strip()
        # remove code fences if present
        fence_match = re.search(r"```json\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
        if fence_match:
            text = fence_match.group(1)
        data = json.loads(text)
        if isinstance(data, dict) and "user_answer" in data:
            return str(data["user_answer"])[:10000]
    except Exception as e:
        logger.error(f"Error parsing agent output: {e}")
    return raw_output

# Function to get current ISO timestamp
def _utc_now_iso() -> str:
    return datetime.now().isoformat() + "Z"

# Simulate streaming response generation
async def _generate_streaming_response(usecase_id: str, response_text: str) -> AsyncIterator[str]:
    # Clear any previous chunks
    response_chunks[usecase_id] = []
    
    # Split the response into words to simulate streaming
    words = response_text.split()
    
    # Stream the words with a small delay
    for i, word in enumerate(words):
        # Add a space after each word except the last one
        chunk = word + (" " if i < len(words) - 1 else "")
        
        # Store the chunk for potential reconnections
        if usecase_id in response_chunks:
            response_chunks[usecase_id].append(chunk)
        
        # Yield the chunk
        yield chunk
        
        # Simulate processing time
        await asyncio.sleep(0.05)

# Background task to process messages with LLM
def _run_chat_inference(usecase_id: str, user_message: str):
    try:
        # Initialize chat history if it doesn't exist
        if usecase_id not in chat_storage:
            chat_storage[usecase_id] = []
            
        # Set status to In Progress
        chat_storage[f"{usecase_id}_status"] = "In Progress"
        
        logger.info(f"Starting chat inference for usecase_id={usecase_id}")
        
        # Call asset_invoker
        asset_id = os.getenv("ASSET_ID", "5df1fa69-6218-4482-a92b-bc1c2c168e3e")
        logger.info(f"Calling asset_invoker for usecase {usecase_id} with message: {user_message}")
        
        try:
            response_text, cost, tokens = invoke_asset_with_proper_timeout(
                asset_id_param=asset_id, 
                query=user_message, 
                timeout_seconds=300
            )
            logger.info(f"Received response from asset_invoker: {response_text}...")
            
            # Parse the response
            assistant_text = _parse_agent_output(response_text)
            
            # Store the full response for streaming
            streaming_responses[usecase_id] = assistant_text
            
            # Add system response to chat history
            system_entry = {"system": assistant_text, "timestamp": _utc_now_iso()}
            chat_storage[usecase_id].insert(0, system_entry)
            
            # Update chat history and timestamp in the database
            try:
                from sqlalchemy import text
                from db.session import get_db_context
                
                with get_db_context() as db:
                    # First get current chat history
                    select_query = text("""
                        SELECT chat_history 
                        FROM usecase_metadata 
                        WHERE usecase_id = :usecase_id AND is_deleted = false
                    """)
                    
                    result = db.execute(select_query, {"usecase_id": usecase_id}).fetchone()
                    
                    # Initialize chat history or use existing
                    db_chat_history = result[0] if result and result[0] else []
                    
                    # Add new message to the beginning
                    db_chat_history.insert(0, system_entry)
                    
                    # Update in database - convert chat history to JSON string
                    import json
                    update_query = text("""
                        UPDATE usecase_metadata 
                        SET chat_history = :chat_history, updated_at = NOW(), status = 'Completed'
                        WHERE usecase_id = :usecase_id AND is_deleted = false
                    """)
                    
                    db.execute(update_query, {"usecase_id": usecase_id, "chat_history": json.dumps(db_chat_history)})
                    db.commit()
                    logger.info(f"Updated chat history and timestamp in database for usecase_id={usecase_id}")
            except Exception as e:
                logger.error(f"Error updating chat history and timestamp in database: {e}")
            
        except Exception as e:
            logger.error(f"Error in asset invocation: {e}")
            # Add error message to chat history
            error_entry = {"system": f"Error: {e}", "timestamp": _utc_now_iso()}
            chat_storage[usecase_id].insert(0, error_entry)
            streaming_responses[usecase_id] = f"Error: {e}"
        
        # Set status to Completed
        chat_storage[f"{usecase_id}_status"] = "Completed"
        logger.info(f"Completed chat inference for usecase_id={usecase_id}")
        
    except Exception as e:
        logger.error(f"Error in chat inference: {e}")
        # Add error message to chat history
        if usecase_id not in chat_storage:
            chat_storage[usecase_id] = []
        error_entry = {"system": f"Error: {e}", "timestamp": _utc_now_iso()}
        chat_storage[usecase_id].insert(0, error_entry)
        chat_storage[f"{usecase_id}_status"] = "Completed"
        streaming_responses[usecase_id] = f"Error: {e}"

class ChatMessage(BaseModel):
    role: str
    content: str

# Simple test endpoint for chat
@app.get("/test/chat")
def test_chat():
    # This endpoint is no longer used - all calls should specify a usecase_id
    logger.warning("Deprecated endpoint /test/chat called without usecase_id")
    return Response(content=json.dumps([]), media_type="application/json")

@app.get("/test/chat/{usecase_id}")
def get_chat_by_id(usecase_id: str):
    # First check in-memory storage
    if usecase_id in chat_storage and chat_storage[usecase_id]:
        logger.info(f"Returning chat history from memory for usecase_id={usecase_id}")
        return Response(content=json.dumps(chat_storage[usecase_id]), media_type="application/json")
    
    # If not in memory, check the database
    try:
        from sqlalchemy import text
        from db.session import get_db_context
        
        with get_db_context() as db:
            query = text("""
                SELECT chat_history 
                FROM usecase_metadata 
                WHERE usecase_id = :usecase_id AND is_deleted = false
            """)
            
            result = db.execute(query, {"usecase_id": usecase_id}).fetchone()
            
            if result and result[0]:
                logger.info(f"Returning chat history from database for usecase_id={usecase_id}")
                # Store in memory for future requests
                chat_storage[usecase_id] = result[0]
                return Response(content=json.dumps(result[0]), media_type="application/json")
    except Exception as e:
        logger.error(f"Error retrieving chat history from database: {e}")
    
    # If not found in memory or database, return empty array
    logger.info(f"No chat history found for usecase_id={usecase_id}")
    return Response(content=json.dumps([]), media_type="application/json")

@app.get("/test/chat/{usecase_id}/stream")
async def stream_chat(usecase_id: str):
    # Check if there's a response to stream
    if usecase_id not in streaming_responses:
        # Return empty response if no streaming response is available
        async def empty_stream():
            yield ""
        return StreamingResponse(empty_stream(), media_type="text/plain")
    
    # Get the full response
    full_response = streaming_responses[usecase_id]
    
    # Stream the response
    return StreamingResponse(
        _generate_streaming_response(usecase_id, full_response),
        media_type="text/plain"
    )

@app.get("/test/chat/{usecase_id}/latest")
def get_latest_message(usecase_id: str):
    # First check in-memory storage
    if usecase_id in chat_storage and chat_storage[usecase_id]:
        # Get the first message (latest) that is from the system
        for message in chat_storage[usecase_id]:
            if "system" in message:
                return Response(
                    content=json.dumps({"message": message["system"]}),
                    media_type="application/json"
                )
    
    # If not in memory, check the database
    try:
        from sqlalchemy import text
        from db.session import get_db_context
        
        with get_db_context() as db:
            query = text("""
                SELECT chat_history 
                FROM usecase_metadata 
                WHERE usecase_id = :usecase_id AND is_deleted = false
            """)
            
            result = db.execute(query, {"usecase_id": usecase_id}).fetchone()
            
            if result and result[0]:
                # Store in memory for future requests
                chat_storage[usecase_id] = result[0]
                
                # Find the latest system message
                for message in result[0]:
                    if "system" in message:
                        return Response(
                            content=json.dumps({"message": message["system"]}),
                            media_type="application/json"
                        )
    except Exception as e:
        logger.error(f"Error retrieving latest message from database: {e}")
    
    # Return empty if no system message found
    return Response(content=json.dumps({"message": ""}), media_type="application/json")

@app.post("/test/chat/{usecase_id}")
async def test_post_chat(usecase_id: str, message: ChatMessage, background_tasks: BackgroundTasks):
    # Use the usecase_id from the URL path
    
    # Extract the message from the request body
    user_message = message.content
    logger.info(f"Received message: {user_message}")
    
    # Initialize chat history if it doesn't exist
    if usecase_id not in chat_storage:
        chat_storage[usecase_id] = []
    
    # Add user message to chat history
    user_entry = {"user": user_message, "timestamp": _utc_now_iso()}
    chat_storage[usecase_id].insert(0, user_entry)
    
    # Update chat history in the database
    try:
        from sqlalchemy import text
        from db.session import get_db_context
        
        with get_db_context() as db:
            # First get current chat history
            select_query = text("""
                SELECT chat_history 
                FROM usecase_metadata 
                WHERE usecase_id = :usecase_id AND is_deleted = false
            """)
            
            result = db.execute(select_query, {"usecase_id": usecase_id}).fetchone()
            
            # Initialize chat history or use existing
            db_chat_history = result[0] if result and result[0] else []
            
            # Add new message to the beginning
            db_chat_history.insert(0, user_entry)
            
            # Update in database - convert chat history to JSON string
            import json
            update_query = text("""
                UPDATE usecase_metadata 
                SET chat_history = :chat_history, status = 'In Progress' 
                WHERE usecase_id = :usecase_id AND is_deleted = false
            """)
            
            db.execute(update_query, {"usecase_id": usecase_id, "chat_history": json.dumps(db_chat_history)})
            db.commit()
            logger.info(f"Updated chat history in database for usecase_id={usecase_id}")
    except Exception as e:
        logger.error(f"Error updating chat history in database: {e}")
    
    # Set status to In Progress
    chat_storage[f"{usecase_id}_status"] = "In Progress"
    
    # Run inference in background
    background_tasks.add_task(_run_chat_inference, usecase_id, user_message)
    
    response = {
        "status": "accepted",
        "usecase_id": usecase_id
    }
    return Response(content=json.dumps(response), media_type="application/json")

@app.get("/test/statuses")
def test_statuses():
    usecase_id = "c51a2175-31c9-43ec-a35f-55c5e1656b36"  # Default usecase ID
    
    # Get current status if it exists
    status = chat_storage.get(f"{usecase_id}_status", "Completed")
    logger.info(f"Status for usecase_id={usecase_id}: {status}")
    
    statuses = {
        "text_extraction": "Not Started",
        "requirement_generation": "Not Started",
        "scenario_generation": "Not Started",
        "test_case_generation": "Not Started",
        "test_script_generation": "Not Started",
        "status": status,
    }
    return Response(content=json.dumps(statuses), media_type="application/json")

@app.get("/test/statuses/{usecase_id}")
def get_usecase_status(usecase_id: str):
    # First check in-memory status
    status = chat_storage.get(f"{usecase_id}_status", None)
    
    # If not in memory, check the database
    if status is None:
        try:
            from sqlalchemy import text
            from db.session import get_db_context
            
            with get_db_context() as db:
                query = text("""
                    SELECT status 
                    FROM usecase_metadata 
                    WHERE usecase_id = :usecase_id AND is_deleted = false
                """)
                
                result = db.execute(query, {"usecase_id": usecase_id}).fetchone()
                
                if result and result[0]:
                    status = result[0]
                else:
                    status = "Completed"  # Default if not found
        except Exception as e:
            logger.error(f"Error retrieving status from database: {e}")
            status = "Completed"  # Default on error
    
    logger.info(f"Status for usecase_id={usecase_id}: {status}")
    
    # If status is completed, also return the latest message
    if status == "Completed":
        latest_message = None
        
        # Check in-memory storage first
        if usecase_id in chat_storage and chat_storage[usecase_id]:
            for message in chat_storage[usecase_id]:
                if "system" in message:
                    latest_message = message["system"]
                    break
        
        # If not found in memory, check database
        if latest_message is None:
            try:
                from sqlalchemy import text
                from db.session import get_db_context
                
                with get_db_context() as db:
                    query = text("""
                        SELECT chat_history 
                        FROM usecase_metadata 
                        WHERE usecase_id = :usecase_id AND is_deleted = false
                    """)
                    
                    result = db.execute(query, {"usecase_id": usecase_id}).fetchone()
                    
                    if result and result[0]:
                        chat_history = result[0]
                        # Store in memory for future requests
                        chat_storage[usecase_id] = chat_history
                        
                        # Find the latest system message
                        for message in chat_history:
                            if "system" in message:
                                latest_message = message["system"]
                                break
            except Exception as e:
                logger.error(f"Error retrieving latest message from database: {e}")
        
        if latest_message:
            return Response(
                content=json.dumps({
                    "status": status,
                    "latest_message": latest_message
                }),
                media_type="application/json"
            )
    
    return Response(
        content=json.dumps({"status": status}),
        media_type="application/json"
    )

@app.get("/test/usecases")
def test_usecases():
    try:
        # Connect to the database to get actual usecases
        from sqlalchemy import create_engine, text
        from db.session import get_db_context
        
        usecases = []
        with get_db_context() as db:
            # Get user by hardcoded email
            query = text("SELECT id FROM users WHERE email = :email")
            user_result = db.execute(query, {"email": "abir.dey@intellectdesign.com"}).fetchone()
            
            if user_result:
                user_id = user_result[0]
                
                # Get all usecases for this user
                query = text("""
                    SELECT 
                        usecase_id, 
                        user_id, 
                        usecase_name, 
                        status, 
                        updated_at, 
                        created_at 
                    FROM 
                        usecase_metadata 
                    WHERE 
                        is_deleted = false 
                        AND user_id = :user_id
                    ORDER BY updated_at DESC
                """)
                
                result = db.execute(query, {"user_id": user_id}).fetchall()
                
                # Process results
                usecases = [
                    {
                        "usecase_id": str(r.usecase_id),
                        "user_id": str(r.user_id),
                        "usecase_name": r.usecase_name,
                        "status": chat_storage.get(f"{r.usecase_id}_status", r.status),
                        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                        "created_at": r.created_at.isoformat() if r.created_at else None,
                    }
                    for r in result
                ]
        
        # If no usecases found, return a default one for testing
        if not usecases:
            usecases = [
                {
                    "usecase_id": "c51a2175-31c9-43ec-a35f-55c5e1656b36",
                    "user_id": "52588196-f538-42bf-adb8-df885ab0120c",
                    "usecase_name": "Default Test Chat",
                    "status": "Completed",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            ]
            
        return Response(content=json.dumps(usecases), media_type="application/json")
    except Exception as e:
        logger.error(f"Error in test_usecases: {e}")
        # Return a default usecase if there's an error
        usecases = [
            {
                "usecase_id": "c51a2175-31c9-43ec-a35f-55c5e1656b36",
                "user_id": "52588196-f538-42bf-adb8-df885ab0120c",
                "usecase_name": "Default Test Chat",
                "status": "Completed",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ]
        return Response(content=json.dumps(usecases), media_type="application/json")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if __name__ == "__main__":
    import uvicorn
    from core.config import HostingConfigs

    # Avoid infinite reload loops by excluding changing files like logs
    reload_enabled = os.getenv("RELOAD", "false").lower() == "true"
    reload_excludes = [
        "logs/*",
        "**/*.log",
        "**/__pycache__/**",
    ]

    uvicorn.run(
        "main:app",
        host=HostingConfigs.HOST,
        port=HostingConfigs.PORT,
        reload=reload_enabled,
        reload_excludes=reload_excludes,
    )