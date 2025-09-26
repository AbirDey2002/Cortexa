"""
This file is the common module to invoke Conversation Asset of PF.

PF is a Gen AI framework used to get LLM responses.
"""

import requests as req
import time
import os
import sys
from typing import Tuple, Optional, Dict, Union

# Add the parent directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

# Import environment configuration
from core.env_config import get_pf_config

# Load configurable values from environment settings
pf_config = get_pf_config()

# API credentials
api_key = pf_config.get('API_KEY')
pf_username = pf_config.get('PF_USERNAME')
pf_password = pf_config.get('PF_PASSWORD')
asset_id = pf_config.get('ASSET_ID')

# Base URL from environment
pf_base_url = pf_config.get('PF_BASE_URL', 'https://api.intellectseecstag.com')

# API endpoints constructed from base URL
PF_ACCESS_TOKEN_URL = f"{pf_base_url}/accesstoken/idxpigtb"
PF_CREATE_CONVERSATION_URL = f"{pf_base_url}/magicplatform/v1/genai/conversation/create"
PF_ADD_MESSAGE_URL = f"{pf_base_url}/magicplatform/v1/genai/conversation/addmessage"
PF_GET_RESPONSE_BASE_URL = f"{pf_base_url}/magicplatform/v1/genai/conversation/response"


headers_QA = {
    'apikey': api_key,
    'username': pf_username,
    'password': pf_password
}

def get_access_token(headers):
    """
    Retrieve an access token using the provided headers.

    Args:
        headers (dict): The headers containing authentication details.

    Returns:
        str: The access token or an empty string if the token retrieval fails.
    """
    value = ""
    res = req.get(PF_ACCESS_TOKEN_URL, headers=headers)
    if res.status_code == 200:
        data = res.json()
        value = data['access_token']
    else:
        pass
    return value



def create_chat(asset_headers, payload):
    """
    Create a new chat conversation.

    Args:
        asset_headers (dict): The headers for the API request.
        payload (dict): The payload containing the conversation details.

    Returns:
        str: The conversation ID of the created chat.
    """
    response = req.post(
        PF_CREATE_CONVERSATION_URL,
        headers=asset_headers, json=payload)
    
    try:
        response_data = response.json()
        
        # Check if response contains the expected structure
        if 'conversation_details' in response_data and 'conversation_id' in response_data['conversation_details']:
            conversation_id = response_data['conversation_details']['conversation_id']
            return conversation_id
        else:
            # Handle different response structures
            # Try alternative structures that might exist
            if 'conversation_id' in response_data:
                conversation_id = response_data['conversation_id']
                return conversation_id
            elif 'id' in response_data:
                conversation_id = response_data['id']
                return conversation_id
            else:
                return None
                
    except Exception as e:
        return None


def asset_post(asset_headers, asset_payload):
    """
    Post a message to an existing chat conversation.

    Args:
        asset_headers (dict): The headers for the API request.
        asset_payload (dict): The payload containing the message details.

    Returns:
        str: The message ID of the posted message.
    """
    asset_post = req.post(
        PF_ADD_MESSAGE_URL,
        headers=asset_headers, json=asset_payload)
    
    try:
        response_data = asset_post.json()
        
        # Check if response contains the expected message_id
        if 'message_id' in response_data:
            message_id = response_data['message_id']
            return message_id
        else:
            # Try alternative structures
            if 'id' in response_data:
                message_id = response_data['id']
                return message_id
            else:
                return None
                
    except Exception as e:
        return None


def get_response(asset_headers, conversation_id, message_id):
    """
    Retrieve the response for a posted message in a chat conversation.

    Args:
        asset_headers (dict): The headers for the API request.
        conversation_id (str): The conversation ID.
        message_id (str): The message ID.

    Returns:
        tuple: A tuple containing the response text and the total cost of the response.
    """
    retry_count = 0
    
    while True:
        time.sleep(5)
        try:
            response = req.get(
                f"{PF_GET_RESPONSE_BASE_URL}/{conversation_id}/{message_id}",
                headers=asset_headers)
        except Exception as e:
            access_token = get_access_token(headers_QA)
            asset_headers = {
                'Content-Type': 'application/json',
                'apikey': api_key,
                'Authorization': 'Bearer ' + access_token,
            }
        try:
            response_ = response.json()
            if response_['error_code'] == "GenaiBaseException":
                raise Exception(response_['error_description'])
        except:
            pass

        try:  
            res = response.json()['message_content'][0]['response']
            cost = response.json()['message_content'][0]['metrics']['total_cost']
            tokens = response.json()['message_content'][0]['metrics']['total_tokens']

            return res, cost, tokens
            
        except Exception as e:            
            time.sleep(4)


def get_response_with_timeout(asset_headers, conversation_id, message_id, timeout_seconds=180):
    """
    Retrieve the response for a posted message in a chat conversation with timeout.

    Args:
        asset_headers (dict): The headers for the API request.
        conversation_id (str): The conversation ID.
        message_id (str): The message ID.
        timeout_seconds (int): Maximum time to wait for response in seconds.

    Returns:
        tuple: A tuple containing the response text and the total cost of the response.
        
    Raises:
        TimeoutError: If the response is not received within the timeout period.
    """
    start_time = time.time()
    retry_count = 0
    
    while True:
        # Check if timeout has been exceeded
        elapsed_time = time.time() - start_time
        if elapsed_time > timeout_seconds:
            raise TimeoutError(f"PF response timeout after {timeout_seconds} seconds")
        
        time.sleep(5)
        try:
            # Add timeout to the HTTP request itself
            response = req.get(
                f"{PF_GET_RESPONSE_BASE_URL}/{conversation_id}/{message_id}",
                headers=asset_headers,
                timeout=30)  # 30 second timeout for individual requests
        except req.exceptions.Timeout:
            continue
        except Exception as e:
            access_token = get_access_token(headers_QA)
            asset_headers = {
                'Content-Type': 'application/json',
                'apikey': api_key,
                'Authorization': 'Bearer ' + access_token,
            }
            continue
            
        try:
            response_ = response.json()
            if response_['error_code'] == "GenaiBaseException":
                raise Exception(response_['error_description'])
        except:
            pass

        try:  
            res = response.json()['message_content'][0]['response']
            cost = response.json()['message_content'][0]['metrics']['total_cost']
            tokens = response.json()['message_content'][0]['metrics']['total_tokens']
            return res, cost, tokens
            
        except Exception as e:            
            time.sleep(4)
    

def invoke_asset(asset_id_param=None, query=None) -> Tuple[str, float, int]:
    """
    Invoke a conversation asset with the given query and retrieve the response.

    Args:
        asset_id_param (str, optional): The asset ID to be invoked. Defaults to the one from environment settings.
        query (str or dict): The query to be sent to the asset. Can be a string or a dictionary 
                           with enhanced parameters like "additional user query" and "retrieved knowledge based details".

    Returns:
        tuple: A tuple containing the response text, cost, and tokens.
    """
    # Use provided asset_id or fall back to the one from environment settings
    used_asset_id = asset_id_param if asset_id_param else asset_id
    
    start_time = time.time()
    
    # Handle both string and dictionary query formats
    if isinstance(query, dict):
        # If query is a dictionary, extract the main query and log additional parameters
        main_query = query.get("query", "")
        
        # Use the main query for the actual API call
        query_to_send = main_query
    else:
        # If query is a string, use it directly
        query_to_send = query
    
    # Get fresh access token
    access_token = get_access_token(headers_QA)
    
    asset_headers = {
        'Content-Type': 'application/json',
        'apikey': api_key,
        'Authorization': 'Bearer ' + access_token,
    }

    # Create conversation
    create_payload = {"conversation_name": "spa_ea", "asset_version_id": used_asset_id, "mode": "EXPERIMENT"}
    conversation_id = create_chat(asset_headers, create_payload)
    
    if not conversation_id:
        return "Error: Failed to create conversation - check API credentials and endpoint", 0, 0

    # Invoke asset
    asset_payload = {"conversation_id": conversation_id, "query": query_to_send, "KB_Types": []}
    message_id = asset_post(asset_headers, asset_payload)
    
    if not message_id:
        return "Error: Failed to post message - check conversation ID and message format", 0, 0

    # Get response
    output = get_response(asset_headers, conversation_id, message_id)
    
    total_time = time.time() - start_time
    
    return output


def invoke_asset_with_proper_timeout(asset_id_param=None, query=None, timeout_seconds=300) -> Tuple[str, float, int]:
    """
    Invoke a conversation asset with the given query and retrieve the response with proper timeout handling.
    This version ensures that all operations respect the timeout limit.

    Args:
        asset_id_param (str, optional): The asset ID to be invoked. Defaults to the one from environment settings.
        query (str or dict): The query to be sent to the asset. Can be a string or a dictionary 
                           with enhanced parameters like "additional user query" and "retrieved knowledge based details".
        timeout_seconds (int): Maximum time for the entire operation in seconds.

    Returns:
        tuple: A tuple containing the response text, cost, and tokens.
        
    Raises:
        TimeoutError: If the operation exceeds the timeout limit.
    """
    # Use provided asset_id or fall back to the one from environment settings
    used_asset_id = asset_id_param if asset_id_param else asset_id
    
    start_time = time.time()
    
    # Handle both string and dictionary query formats
    if isinstance(query, dict):
        # If query is a dictionary, extract the main query and log additional parameters
        main_query = query.get("query", "")
        additional_user_query = query.get("additional user query", "")
        kb_details = query.get("retrieved knowledge based details", "")
        
        # Use the main query for the actual API call
        query_to_send = main_query + "\nAdditional User Instructions: " + additional_user_query + "\nRetrieved Knowledge Based Details: " + kb_details
    else:
        # If query is a string, use it directly
        query_to_send = query
    
    try:
        # Get fresh access token with timeout
        access_token = get_access_token(headers_QA)
        
        asset_headers = {
            'Content-Type': 'application/json',
            'apikey': api_key,
            'Authorization': 'Bearer ' + access_token,
        }

        # Create conversation with timeout check
        if time.time() - start_time > timeout_seconds:
            raise TimeoutError("Timeout exceeded before creating conversation")
            
        create_payload = {"conversation_name": "spa_ea", "asset_version_id": used_asset_id, "mode": "EXPERIMENT"}
        conversation_id = create_chat(asset_headers, create_payload)
        
        if not conversation_id:
            return "Error: Failed to create conversation - check API credentials and endpoint", 0, 0

        # Invoke asset with timeout check
        if time.time() - start_time > timeout_seconds:
            raise TimeoutError("Timeout exceeded before posting message")
            
        asset_payload = {"conversation_id": conversation_id, "query": query_to_send, "KB_Types": []}
        message_id = asset_post(asset_headers, asset_payload)
        
        if not message_id:
            return "Error: Failed to post message - check conversation ID and message format", 0, 0

        # Calculate remaining time for get_response
        elapsed_time = time.time() - start_time
        remaining_time = timeout_seconds - elapsed_time
        
        if remaining_time <= 0:
            raise TimeoutError("Timeout exceeded before getting response")
        
        # Get response with the remaining timeout
        output = get_response_with_timeout(asset_headers, conversation_id, message_id, remaining_time)
        
        total_time = time.time() - start_time
        
        return output
        
    except TimeoutError:
        total_time = time.time() - start_time
        raise
    except Exception as e:
        raise


if __name__ == "__main__":
    # Example usage when script is run directly
    test_asset_id = "5df1fa69-6218-4482-a92b-bc1c2c168e3e"
    test_query = "Hello! What can you help me with?"
    
    print("Invoking asset...")
    response, cost, tokens = invoke_asset(test_asset_id, test_query)
    print(f"\nResponse: {response}")
    print(f"Cost: {cost}")
    # print(f"Tokens: {tokens}")  # Disabled to prevent sensitive info exposure