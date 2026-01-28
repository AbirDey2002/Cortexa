"""
Helper module for resolving LLM API keys in the agent system.
Provides a simple interface to the BYOK key resolution system.
"""
import logging
from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from core.env_config import get_env_variable
from core.provider_registry import ProviderType

logger = logging.getLogger(__name__)


def resolve_gemini_key(user_id: Optional[UUID], db: Optional[Session] = None) -> str:
    """
    Resolve the Gemini API key for a user (BYOK only - no system fallback).
    
    Priority:
    1. User's BYOK key (if available and active)
    
    Args:
        user_id: The user's UUID (None for system-level operations)
        db: Optional database session. If not provided, returns empty string.
        
    Returns:
        The API key to use, or empty string if none available.
    """
    # If we have a user_id and db session, try BYOK resolution
    if user_id and db:
        try:
            from services.llm.key_resolver import KeyResolver
            resolver = KeyResolver(db)
            key, source = resolver.resolve_key(user_id, ProviderType.GEMINI)
            if key:
                logger.info(f"Using {source} API key for Gemini (user={user_id})")
                return key
        except Exception as e:
            logger.warning(f"BYOK key resolution failed: {e}")
    
    # No system fallback - BYOK only
    logger.warning("No Gemini API key available. User must provide their own key (BYOK).")
    return ""


def resolve_provider_key(
    provider: str,
    user_id: Optional[UUID] = None,
    db: Optional[Session] = None
) -> Tuple[str, str]:
    """
    Resolve API key for any supported provider.
    
    Args:
        provider: Provider ID (openai, gemini, claude, etc.)
        user_id: Optional user UUID for BYOK resolution
        db: Optional database session
        
    Returns:
        Tuple of (api_key, source) where source is 'user', 'system', or 'none'
    """
    # Try BYOK resolution first
    if user_id and db:
        try:
            from services.llm.key_resolver import KeyResolver
            resolver = KeyResolver(db)
            key, source = resolver.resolve_key(user_id, provider)
            if key:
                return (key, source)
        except Exception as e:
            logger.warning(f"BYOK resolution failed for {provider}: {e}")
    
    # Fallback to system key
    from core.provider_registry import get_provider_env_key_name
    env_key_name = get_provider_env_key_name(provider)
    if env_key_name:
        system_key = get_env_variable(env_key_name, "")
        if system_key:
            return (system_key, "system")
    
    return ("", "none")
