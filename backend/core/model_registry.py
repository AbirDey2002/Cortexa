"""
Model Registry for Gemini Models

Centralized registry of all available Gemini models with their configurations.
"""

from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class ModelInfo:
    """Information about a model."""
    id: str  # e.g., "gemini-2.5-flash"
    name: str  # Display name, e.g., "Gemini 2.5 Flash"
    description: str
    provider: str = "google-generativeai"
    token_limit: int = 250_000
    available: bool = True


# Registry of all available models
AVAILABLE_MODELS: List[ModelInfo] = [
    ModelInfo(
        id="gemini-2.5-flash",
        name="Gemini 2.5 Flash",
        description="Fast and efficient model",
        token_limit=250_000
    ),
    ModelInfo(
        id="gemini-2.5-flash-lite",
        name="Gemini 2.5 Flash Lite",
        description="Lightweight version with higher rate limits",
        token_limit=250_000
    ),
    ModelInfo(
        id="gemini-2.5-pro",
        name="Gemini 2.5 Pro",
        description="Most capable model",
        token_limit=250_000
    ),
]


def get_model_by_id(model_id: str) -> Optional[ModelInfo]:
    """Get model info by ID."""
    return next((m for m in AVAILABLE_MODELS if m.id == model_id), None)


def get_all_models() -> List[Dict]:
    """Get all available models as dictionaries."""
    return [
        {
            "id": m.id,
            "name": m.name,
            "description": m.description
        }
        for m in AVAILABLE_MODELS
        if m.available
    ]


def is_valid_model(model_id: str) -> bool:
    """Check if a model ID is valid."""
    return get_model_by_id(model_id) is not None


def get_default_model() -> str:
    """Get the default model ID."""
    return "gemini-2.5-flash-lite"

