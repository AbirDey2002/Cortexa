from fastapi import FastAPI, Response, BackgroundTasks, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json
import uvicorn
import uuid
import time
from datetime import datetime
import asyncio
import os
import logging
from typing import AsyncIterator, Dict, List, Optional
from services.llm.text2text_conversational.asset_invoker import invoke_asset_with_proper_timeout

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="test chat server")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
            logger.info(f"Received response from asset_invoker: {response_text[:100]}...")
            
            # Parse the response
            assistant_text = _parse_agent_output(response_text)
            
            # Store the full response for streaming
            streaming_responses[usecase_id] = assistant_text
            
            # Add system response to chat history
            system_entry = {"system": assistant_text, "timestamp": _utc_now_iso()}
            chat_storage[usecase_id].insert(0, system_entry)
            
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
    usecase_id = "c51a2175-31c9-43ec-a35f-55c5e1656b36"  # Default usecase ID
    
    # Return chat history if it exists, otherwise return default
    if usecase_id in chat_storage and chat_storage[usecase_id]:
        logger.info(f"Returning chat history for usecase_id={usecase_id}")
        return Response(content=json.dumps(chat_storage[usecase_id]), media_type="application/json")
    else:
        # Default chat history
        logger.info(f"Creating default chat history for usecase_id={usecase_id}")
        chat_history = [
            {
                "system": "Hello! How can I assist you today?",
                "timestamp": "2025-09-23T20:16:41.396211Z"
            },
            {
                "user": "hii",
                "timestamp": "2025-09-23T20:15:18.426919Z"
            }
        ]
        # Store it for persistence
        chat_storage[usecase_id] = chat_history
        return Response(content=json.dumps(chat_history), media_type="application/json")

@app.get("/test/chat/{usecase_id}")
def get_chat_by_id(usecase_id: str):
    # Return chat history if it exists, otherwise return empty array
    if usecase_id in chat_storage and chat_storage[usecase_id]:
        logger.info(f"Returning chat history for usecase_id={usecase_id}")
        return Response(content=json.dumps(chat_storage[usecase_id]), media_type="application/json")
    else:
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
    # Return the latest message for the usecase
    if usecase_id in chat_storage and chat_storage[usecase_id]:
        # Get the first message (latest) that is from the system
        for message in chat_storage[usecase_id]:
            if "system" in message:
                return Response(
                    content=json.dumps({"message": message["system"]}),
                    media_type="application/json"
                )
    
    # Return empty if no system message found
    return Response(content=json.dumps({"message": ""}), media_type="application/json")

@app.post("/test/chat")
async def test_post_chat(message: ChatMessage, background_tasks: BackgroundTasks):
    usecase_id = "c51a2175-31c9-43ec-a35f-55c5e1656b36"  # Default usecase ID
    
    # Extract the message from the request body
    user_message = message.content
    logger.info(f"Received message: {user_message}")
    
    # Initialize chat history if it doesn't exist
    if usecase_id not in chat_storage:
        chat_storage[usecase_id] = []
    
    # Add user message to chat history
    user_entry = {"user": user_message, "timestamp": _utc_now_iso()}
    chat_storage[usecase_id].insert(0, user_entry)
    
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
    # Get current status if it exists
    status = chat_storage.get(f"{usecase_id}_status", "Completed")
    logger.info(f"Status for usecase_id={usecase_id}: {status}")
    
    return Response(
        content=json.dumps({"status": status}),
        media_type="application/json"
    )

@app.get("/test/usecases")
def test_usecases():
    usecases = [
        {
            "usecase_id": "c51a2175-31c9-43ec-a35f-55c5e1656b36",
            "user_id": "52588196-f538-42bf-adb8-df885ab0120c",
            "usecase_name": "Hii Test Chat",
            "status": chat_storage.get("c51a2175-31c9-43ec-a35f-55c5e1656b36_status", "Completed"),
            "updated_at": "2025-09-23T20:15:18.426919Z",
            "created_at": "2025-09-23T20:15:18.426919Z",
        }
    ]
    return Response(content=json.dumps(usecases), media_type="application/json")

if __name__ == "__main__":
    uvicorn.run(
        "test_server:app",
        host="127.0.0.1",
        port=8001,
        reload=False,
        log_level="info",
    )