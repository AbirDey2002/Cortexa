"""
Model Registry for LLM Models

Centralized registry integrating with provider_registry for multi-provider support.
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session


@dataclass
class ModelInfo:
    """Information about a model."""
    id: str  # e.g., "gemini-2.5-flash", "gpt-4o"
    name: str  # Display name, e.g., "Gemini 2.5 Flash"
    description: str
    provider: str = "gemini"  # Provider ID
    token_limit: int = 250_000
    available: bool = True


# Legacy Gemini models (kept for backward compatibility)
GEMINI_MODELS: List[ModelInfo] = [
    ModelInfo(
        id="gemini-2.5-flash",
        name="Gemini 2.5 Flash",
        description="Fast and efficient model",
        provider="gemini",
        token_limit=250_000
    ),
    ModelInfo(
        id="gemini-2.5-flash-lite",
        name="Gemini 2.5 Flash Lite",
        description="Lightweight version with higher rate limits",
        provider="gemini",
        token_limit=250_000
    ),
    ModelInfo(
        id="gemini-2.5-pro",
        name="Gemini 2.5 Pro",
        description="Most capable model",
        provider="gemini",
        token_limit=250_000
    ),
]


def get_model_by_id(model_id: str) -> Optional[ModelInfo]:
    """Get model info by ID from legacy Gemini registry."""
    return next((m for m in GEMINI_MODELS if m.id == model_id), None)


def get_all_models() -> List[Dict]:
    """Get all available Gemini models as dictionaries (legacy)."""
    return [
        {
            "id": m.id,
            "name": m.name,
            "description": m.description
        }
        for m in GEMINI_MODELS
        if m.available
    ]


def is_valid_model(model_id: str) -> bool:
    """
    Check if a model ID is valid.
    Now checks both legacy Gemini registry and multi-provider registry.
    """
    # Check legacy Gemini models
    if get_model_by_id(model_id) is not None:
        return True
    
    # Check multi-provider registry
    try:
        from core.provider_registry import PROVIDER_REGISTRY
        for provider in PROVIDER_REGISTRY.values():
            for model in provider.models:
                if model.id == model_id:
                    return True
    except Exception:
        pass
    
    return False


def get_default_model() -> str:
    """Get the default model ID."""
    return "gemini-2.5-flash-lite"


def get_all_models_for_user(user_id: UUID, db: Session) -> List[Dict]:
    """
    Get all models available to a user based on their configured BYOK keys.
    
    Returns models from all providers where the user has an active key,
    plus models from providers with system keys.
    """
    try:
        from services.llm.unified_invoker import get_available_models_for_user
        return get_available_models_for_user(user_id, db)
    except Exception:
        # Fallback to legacy Gemini models
        return get_all_models()


def get_provider_for_model(model_id: str) -> Optional[str]:
    """Determine which provider a model belongs to."""
    # Check legacy Gemini
    if get_model_by_id(model_id) is not None:
        return "gemini"
    
    # Check multi-provider registry
    try:
        from core.provider_registry import PROVIDER_REGISTRY
        for provider_id, provider in PROVIDER_REGISTRY.items():
            for model in provider.models:
                if model.id == model_id:
                    return provider_id
    except Exception:
        pass
    
    # Default to gemini for unknown models
    return "gemini"


