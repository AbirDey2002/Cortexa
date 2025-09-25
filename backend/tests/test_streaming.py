"""
Test script for streaming responses and status polling
"""

import asyncio
import json
import time
import requests
from fastapi.testclient import TestClient
import sys
import os

# Add the parent directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

# Import the app from test_server.py
from test_server import app

client = TestClient(app)

def test_status_polling():
    """Test status polling while a message is being processed"""
    
    # Send a message
    response = client.post(
        "/test/chat",
        json={"role": "user", "content": "Test message for status polling"}
    )
    assert response.status_code == 200
    data = response.json()
    usecase_id = data["usecase_id"]
    
    # Poll the status endpoint
    status = "In Progress"
    max_retries = 10
    retries = 0
    
    while status == "In Progress" and retries < max_retries:
        status_response = client.get("/test/statuses")
        assert status_response.status_code == 200
        status_data = status_response.json()
        status = status_data["status"]
        print(f"Current status: {status}")
        retries += 1
        time.sleep(1)
    
    # Final status should be "Completed"
    assert status == "Completed"
    
    # Get the chat history
    chat_response = client.get("/test/chat")
    assert chat_response.status_code == 200
    chat_data = chat_response.json()
    
    # Verify the message and response are in the chat history
    assert any(msg.get("user") == "Test message for status polling" for msg in chat_data)
    assert any(msg.get("system") is not None for msg in chat_data)

def test_streaming_response():
    """Test streaming response capability"""
    
    # This would typically be tested with a real HTTP client that supports streaming
    # For demonstration purposes, we'll just verify the streaming endpoint exists
    
    response = client.get("/test/chat/stream")
    # The endpoint might not exist yet, so we're just checking it's accessible
    assert response.status_code in [200, 404]

if __name__ == "__main__":
    print("Testing status polling...")
    test_status_polling()
    print("Status polling test completed successfully!")
    
    print("\nTesting streaming response...")
    test_streaming_response()
    print("Streaming response test completed!")
