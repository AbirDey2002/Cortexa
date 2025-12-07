"""
Model Management API Endpoints

Endpoints for managing and listing available models.
"""

from fastapi import APIRouter, HTTPException
from core.model_registry import get_all_models, is_valid_model, get_model_by_id

router = APIRouter()


@router.get("/models")
async def list_models():
    """
    Get list of all available models.
    
    Returns:
        List of model objects with id, name, and description
    """
    return {"models": get_all_models()}


@router.get("/models/{model_id}")
async def get_model(model_id: str):
    """
    Get information about a specific model.
    
    Args:
        model_id: The model identifier
        
    Returns:
        Model information
        
    Raises:
        404: If model not found
    """
    model = get_model_by_id(model_id)
    if not model:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")
    
    return {
        "id": model.id,
        "name": model.name,
        "description": model.description,
        "provider": model.provider,
        "token_limit": model.token_limit,
        "available": model.available
    }


