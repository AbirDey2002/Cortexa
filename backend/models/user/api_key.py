"""
UserAPIKey model for storing encrypted user API keys for LLM providers.
"""
import uuid
from sqlalchemy import (
    Column,
    ForeignKey,
    DateTime,
    String,
    Text,
    Boolean,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as pgUUID
from sqlalchemy.orm import relationship

from models.base import Base


class UserAPIKey(Base):
    """
    Stores encrypted API keys for LLM providers.
    Each user can have multiple keys for different providers.
    """
    __tablename__ = "user_api_keys"

    id = Column(pgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        pgUUID(as_uuid=True), 
        ForeignKey("users.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    
    # Provider identifier (openai, gemini, claude, grok, huggingface, deepseek)
    provider = Column(String(50), nullable=False, index=True)
    
    # User-friendly label for the key
    label = Column(String(100), nullable=True)
    
    # Fernet-encrypted API key (base64 encoded)
    encrypted_key = Column(Text, nullable=False)
    
    # Last 4 chars of key for display (e.g., "...a1b2")
    display_suffix = Column(String(10), nullable=True)
    
    # Whether this key is currently active
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    
    # Soft delete
    is_deleted = Column(Boolean, default=False, nullable=False)
    
    # Relationship
    user = relationship("User", back_populates="api_keys")

    def __repr__(self):
        return f"<UserAPIKey(id='{self.id}', provider='{self.provider}', user_id='{self.user_id}')>"
