"""
Key resolver service for dynamically resolving API keys.
Prioritizes user-provided keys over system environment variables.
"""
import os
import logging
from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from models.user.api_key import UserAPIKey
from core.encryption import decrypt_api_key
from core.provider_registry import get_provider_env_key_name, is_valid_provider

logger = logging.getLogger(__name__)


class KeyResolver:
    """
    Resolves API keys for LLM providers.
    Priority: User key > System environment variable
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_user_key(self, user_id: UUID, provider: str) -> Optional[str]:
        """
        Get an active user-provided API key for a provider.
        
        Args:
            user_id: The user's UUID
            provider: Provider identifier (e.g., 'openai', 'gemini')
            
        Returns:
            Decrypted API key if found and active, None otherwise
        """
        if not is_valid_provider(provider):
            logger.warning(f"Invalid provider requested: {provider}")
            return None
        
        try:
            key_record = self.db.query(UserAPIKey).filter(
                UserAPIKey.user_id == user_id,
                UserAPIKey.provider == provider,
                UserAPIKey.is_active == True,
                UserAPIKey.is_deleted == False
            ).first()
            
            if key_record:
                decrypted = decrypt_api_key(key_record.encrypted_key)
                # Update last_used_at
                from sqlalchemy import func
                key_record.last_used_at = func.now()
                self.db.commit()
                return decrypted
            
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving user key for {provider}: {e}")
            return None
    
    def get_system_key(self, provider: str) -> Optional[str]:
        """
        Get the system-wide API key from environment variables.
        
        Args:
            provider: Provider identifier
            
        Returns:
            API key from environment if set, None otherwise
        """
        env_key_name = get_provider_env_key_name(provider)
        if not env_key_name:
            return None
        
        key = os.getenv(env_key_name, "")
        return key if key else None
    
    def resolve_key(self, user_id: UUID, provider: str) -> Tuple[Optional[str], str]:
        """
        Resolve the API key for a user and provider.
        Only returns user-provided keys - no system fallback.
        
        Args:
            user_id: The user's UUID
            provider: Provider identifier
            
        Returns:
            Tuple of (api_key, source) where source is 'user' or 'none'
        """
        # Only use user-provided keys (no system fallback)
        user_key = self.get_user_key(user_id, provider)
        if user_key:
            logger.info(f"Using user-provided key for {provider}")
            return (user_key, "user")
        
        logger.warning(f"No API key available for {provider} - user must configure their own key")
        return (None, "none")
    
    def has_key(self, user_id: UUID, provider: str) -> bool:
        """
        Check if any key (user or system) is available for a provider.
        """
        key, _ = self.resolve_key(user_id, provider)
        return key is not None
    
    def get_available_providers(self, user_id: UUID) -> list:
        """
        Get list of providers that have available keys (user or system).
        
        Args:
            user_id: The user's UUID
            
        Returns:
            List of provider IDs with available keys
        """
        from core.provider_registry import get_all_providers
        
        available = []
        for provider in get_all_providers():
            if self.has_key(user_id, provider.id):
                available.append(provider.id)
        
        return available


def get_key_resolver(db: Session) -> KeyResolver:
    """Factory function to create a KeyResolver instance."""
    return KeyResolver(db)
