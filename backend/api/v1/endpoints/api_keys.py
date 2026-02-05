"""
API endpoints for managing user API keys (BYOK).
"""
import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from deps import get_db, get_current_user
from models.user.user import User
from models.user.api_key import UserAPIKey
from core.encryption import encrypt_api_key, get_key_display_suffix
from core.provider_registry import (
    get_all_providers,
    get_provider,
    get_provider_models,
    is_valid_provider,
    ProviderType,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ============== Pydantic Models ==============

class APIKeyCreate(BaseModel):
    """Request model for creating a new API key."""
    provider: str = Field(..., description="Provider ID (openai, gemini, claude, etc.)")
    api_key: str = Field(..., min_length=1, description="The API key to store")
    label: Optional[str] = Field(None, max_length=100, description="Optional label for the key")


class APIKeyUpdate(BaseModel):
    """Request model for updating an API key."""
    label: Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None


class APIKeyResponse(BaseModel):
    """Response model for an API key (without the actual key)."""
    id: UUID
    provider: str
    provider_name: str
    label: Optional[str]
    display_suffix: str
    is_active: bool
    created_at: str
    last_used_at: Optional[str]

    class Config:
        from_attributes = True


class ProviderResponse(BaseModel):
    """Response model for a provider."""
    id: str
    name: str
    description: str
    has_user_key: bool = False
    has_system_key: bool = False


class ModelResponse(BaseModel):
    """Response model for a model."""
    id: str
    name: str
    description: str
    context_window: int
    is_default: bool


class AvailableProvidersResponse(BaseModel):
    """Response with all providers and their availability."""
    providers: List[ProviderResponse]


class AvailableModelsResponse(BaseModel):
    """Response with models for a specific provider."""
    provider_id: str
    provider_name: str
    models: List[ModelResponse]


# ============== Helper Functions ==============

# Helper deleted


# ============== API Endpoints ==============

@router.post("/", response_model=APIKeyResponse, status_code=status.HTTP_201_CREATED)
async def add_api_key(
    key_data: APIKeyCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Add a new API key for a provider.
    If an active key already exists for this provider, it will be deactivated.
    """
    # Validate provider
    if not is_valid_provider(key_data.provider):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid provider: {key_data.provider}. Valid providers: {[p.value for p in ProviderType]}"
        )
    
    provider_info = get_provider(key_data.provider)
    
    # Deactivate any existing active keys for this provider
    existing_keys = db.query(UserAPIKey).filter(
        UserAPIKey.user_id == user.id,
        UserAPIKey.provider == key_data.provider,
        UserAPIKey.is_active == True,
        UserAPIKey.is_deleted == False
    ).all()
    
    for existing_key in existing_keys:
        existing_key.is_active = False
        logger.info(f"Deactivated existing key {existing_key.id} for provider {key_data.provider}")
    
    # Encrypt and store the new key
    encrypted = encrypt_api_key(key_data.api_key)
    display_suffix = get_key_display_suffix(key_data.api_key)
    
    new_key = UserAPIKey(
        user_id=user.id,
        provider=key_data.provider,
        label=key_data.label or f"{provider_info.name} Key",
        encrypted_key=encrypted,
        display_suffix=display_suffix,
        is_active=True
    )
    
    db.add(new_key)
    db.commit()
    db.refresh(new_key)
    
    logger.info(f"Created new API key for user {user.id}, provider {key_data.provider}")
    
    return APIKeyResponse(
        id=new_key.id,
        provider=new_key.provider,
        provider_name=provider_info.name,
        label=new_key.label,
        display_suffix=new_key.display_suffix,
        is_active=new_key.is_active,
        created_at=new_key.created_at.isoformat(),
        last_used_at=new_key.last_used_at.isoformat() if new_key.last_used_at else None
    )


@router.get("/", response_model=List[APIKeyResponse])
async def list_api_keys(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all API keys for the current user."""
    keys = db.query(UserAPIKey).filter(
        UserAPIKey.user_id == user.id,
        UserAPIKey.is_deleted == False
    ).order_by(UserAPIKey.created_at.desc()).all()
    
    result = []
    for key in keys:
        provider_info = get_provider(key.provider)
        provider_name = provider_info.name if provider_info else key.provider
        
        result.append(APIKeyResponse(
            id=key.id,
            provider=key.provider,
            provider_name=provider_name,
            label=key.label,
            display_suffix=key.display_suffix or "****",
            is_active=key.is_active,
            created_at=key.created_at.isoformat(),
            last_used_at=key.last_used_at.isoformat() if key.last_used_at else None
        ))
    
    return result


@router.patch("/{key_id}", response_model=APIKeyResponse)
async def update_api_key(
    key_id: UUID,
    update_data: APIKeyUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an API key's label or active status."""
    key = db.query(UserAPIKey).filter(
        UserAPIKey.id == key_id,
        UserAPIKey.user_id == user.id,
        UserAPIKey.is_deleted == False
    ).first()
    
    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    if update_data.label is not None:
        key.label = update_data.label
    
    if update_data.is_active is not None:
        key.is_active = update_data.is_active
    
    db.commit()
    db.refresh(key)
    
    provider_info = get_provider(key.provider)
    
    return APIKeyResponse(
        id=key.id,
        provider=key.provider,
        provider_name=provider_info.name if provider_info else key.provider,
        label=key.label,
        display_suffix=key.display_suffix or "****",
        is_active=key.is_active,
        created_at=key.created_at.isoformat(),
        last_used_at=key.last_used_at.isoformat() if key.last_used_at else None
    )


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    key_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Soft delete an API key."""
    key = db.query(UserAPIKey).filter(
        UserAPIKey.id == key_id,
        UserAPIKey.user_id == user.id,
        UserAPIKey.is_deleted == False
    ).first()
    
    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    key.is_deleted = True
    key.is_active = False
    db.commit()
    
    logger.info(f"Deleted API key {key_id} for user {user.id}")


@router.get("/providers", response_model=AvailableProvidersResponse)
async def list_providers(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all available LLM providers with their availability status.
    Shows whether the user has configured an API key.
    """
    # Get user's active keys by provider
    user_keys = db.query(UserAPIKey.provider).filter(
        UserAPIKey.user_id == user.id,
        UserAPIKey.is_active == True,
        UserAPIKey.is_deleted == False
    ).all()
    user_providers = {k.provider for k in user_keys}
    
    providers = []
    for provider in get_all_providers():
        providers.append(ProviderResponse(
            id=provider.id,
            name=provider.name,
            description=provider.description,
            has_user_key=provider.id in user_providers,
            has_system_key=False  # No longer using system keys
        ))
    
    return AvailableProvidersResponse(providers=providers)


@router.get("/providers/{provider_id}/models", response_model=AvailableModelsResponse)
async def list_provider_models(
    provider_id: str,
    user: User = Depends(get_current_user)
):
    """List all models available for a specific provider."""
    if not is_valid_provider(provider_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid provider: {provider_id}"
        )
    
    provider_info = get_provider(provider_id)
    models = get_provider_models(provider_id)
    
    return AvailableModelsResponse(
        provider_id=provider_id,
        provider_name=provider_info.name,
        models=[
            ModelResponse(
                id=m.id,
                name=m.name,
                description=m.description,
                context_window=m.context_window,
                is_default=m.is_default
            )
            for m in models
        ]
    )


class AllModelsResponse(BaseModel):
    """Response with all models available to the user."""
    models: List[dict]


@router.get("/available-models", response_model=AllModelsResponse)
async def list_all_available_models(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all models available to the user across all providers.
    Only includes models from providers where user has a key or system key exists.
    """
    try:
        from core.model_registry import get_all_models_for_user
        
        models = get_all_models_for_user(user.id, db)
        return AllModelsResponse(models=models)
    except Exception as e:
        logger.error(f"Failed to get available models for user {user.id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch available models: {str(e)}"
        )

