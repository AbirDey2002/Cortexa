"""
Unified LLM Invoker for multi-provider support.
Provides a single interface to invoke LLMs from different providers using BYOK keys.
"""
import logging
from typing import Optional, Dict, Any, Tuple, List
from uuid import UUID
from enum import Enum

from sqlalchemy.orm import Session

from core.provider_registry import ProviderType, get_provider, get_default_model as get_default_provider_model
from services.llm.key_resolver import KeyResolver

logger = logging.getLogger(__name__)


class InvokerError(Exception):
    """Exception raised when LLM invocation fails."""
    pass


def _get_provider_from_model(model_id: str) -> str:
    """
    Determine provider from model ID.
    Returns provider string or raises InvokerError if unknown.
    """
    model_lower = model_id.lower()
    
    # Gemini models
    if "gemini" in model_lower:
        return ProviderType.GEMINI
    
    # OpenAI models
    if any(x in model_lower for x in ["gpt-4", "gpt-3.5", "gpt4", "o1", "o3"]):
        return ProviderType.OPENAI
    
    # Claude models
    if "claude" in model_lower:
        return ProviderType.CLAUDE
    
    # Grok models
    if "grok" in model_lower:
        return ProviderType.GROK
    
    # DeepSeek models
    if "deepseek" in model_lower:
        return ProviderType.DEEPSEEK
    
    # HuggingFace models (typically contain / for org/model)
    if "/" in model_id or any(x in model_lower for x in ["llama", "mixtral", "phi", "mistral"]):
        return ProviderType.HUGGINGFACE
    
    # Default to Gemini if unknown
    logger.warning(f"Unknown model provider for {model_id}, defaulting to Gemini")
    return ProviderType.GEMINI


def create_langchain_model(
    provider: str,
    model_id: str,
    api_key: str,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    **kwargs
) -> Any:
    """
    Create a LangChain chat model instance for the specified provider.
    
    Args:
        provider: Provider ID (openai, gemini, claude, etc.)
        model_id: Model identifier
        api_key: API key to use
        temperature: Sampling temperature
        max_tokens: Maximum output tokens
        
    Returns:
        LangChain BaseChatModel instance
    """
    try:
        if provider == ProviderType.GEMINI:
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                model=model_id,
                google_api_key=api_key,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
        
        elif provider == ProviderType.OPENAI:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=model_id,
                api_key=api_key,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
        
        elif provider == ProviderType.CLAUDE:
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model=model_id,
                api_key=api_key,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
        
        elif provider == ProviderType.GROK:
            # Grok uses OpenAI-compatible API
            from langchain_openai import ChatOpenAI
            provider_info = get_provider(ProviderType.GROK)
            return ChatOpenAI(
                model=model_id,
                api_key=api_key,
                base_url=provider_info.api_base_url if provider_info else "https://api.x.ai/v1",
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
        
        elif provider == ProviderType.DEEPSEEK:
            # DeepSeek uses OpenAI-compatible API
            from langchain_openai import ChatOpenAI
            provider_info = get_provider(ProviderType.DEEPSEEK)
            return ChatOpenAI(
                model=model_id,
                api_key=api_key,
                base_url=provider_info.api_base_url if provider_info else "https://api.deepseek.com/v1",
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
        
        elif provider == ProviderType.HUGGINGFACE:
            from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
            # HuggingFace requires endpoint setup
            endpoint = HuggingFaceEndpoint(
                repo_id=model_id,
                huggingfacehub_api_token=api_key,
                temperature=temperature,
                max_new_tokens=max_tokens,
                **kwargs
            )
            return ChatHuggingFace(llm=endpoint)
        
        else:
            raise InvokerError(f"Unsupported provider: {provider}")
            
    except ImportError as e:
        raise InvokerError(f"Missing LangChain package for {provider}: {e}")
    except Exception as e:
        raise InvokerError(f"Failed to create model for {provider}: {e}")


def get_chat_model_for_user(
    user_id: UUID,
    model_id: str,
    db: Session,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    **kwargs
) -> Tuple[Any, str, str]:
    """
    Get a LangChain chat model configured with the user's BYOK key or system key.
    
    Args:
        user_id: User's UUID
        model_id: Model identifier (e.g., "gpt-4o", "claude-3-sonnet")
        db: Database session
        temperature: Sampling temperature
        max_tokens: Maximum output tokens
        
    Returns:
        Tuple of (model_instance, provider, key_source)
        - model_instance: LangChain chat model
        - provider: Provider ID used
        - key_source: 'user' or 'system'
    """
    # Determine provider from model ID
    provider = _get_provider_from_model(model_id)
    
    # Resolve API key using BYOK system
    resolver = KeyResolver(db)
    api_key, key_source = resolver.resolve_key(user_id, provider)
    
    if not api_key:
        raise InvokerError(f"No API key available for {provider}. Configure one in Settings → API Keys.")
    
    logger.info(f"Creating {provider} model '{model_id}' with {key_source} key for user {user_id}")
    
    # Create the model
    model = create_langchain_model(
        provider=provider,
        model_id=model_id,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs
    )
    
    return (model, provider, key_source)


def invoke_chat(
    user_id: UUID,
    model_id: str,
    messages: List[Dict[str, str]],
    db: Session,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    **kwargs
) -> Tuple[str, str, str]:
    """
    Invoke a chat model with the given messages.
    
    Args:
        user_id: User's UUID
        model_id: Model identifier
        messages: List of message dicts with 'role' and 'content'
        db: Database session
        temperature: Sampling temperature
        max_tokens: Maximum output tokens
        
    Returns:
        Tuple of (response_text, provider, key_source)
    """
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
    
    model, provider, key_source = get_chat_model_for_user(
        user_id=user_id,
        model_id=model_id,
        db=db,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs
    )
    
    # Convert message dicts to LangChain messages
    lc_messages = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        
        if role == "system":
            lc_messages.append(SystemMessage(content=content))
        elif role == "assistant":
            lc_messages.append(AIMessage(content=content))
        else:  # user
            lc_messages.append(HumanMessage(content=content))
    
    # Invoke the model
    try:
        response = model.invoke(lc_messages)
        response_text = response.content if hasattr(response, 'content') else str(response)
        return (response_text, provider, key_source)
    except Exception as e:
        logger.error(f"LLM invocation failed: {e}")
        raise InvokerError(f"Failed to invoke {provider} model: {e}")


async def ainvoke_chat(
    user_id: UUID,
    model_id: str,
    messages: List[Dict[str, str]],
    db: Session,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    **kwargs
) -> Tuple[str, str, str]:
    """
    Async version of invoke_chat.
    """
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
    
    model, provider, key_source = get_chat_model_for_user(
        user_id=user_id,
        model_id=model_id,
        db=db,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs
    )
    
    # Convert message dicts to LangChain messages
    lc_messages = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        
        if role == "system":
            lc_messages.append(SystemMessage(content=content))
        elif role == "assistant":
            lc_messages.append(AIMessage(content=content))
        else:
            lc_messages.append(HumanMessage(content=content))
    
    # Invoke the model asynchronously
    try:
        response = await model.ainvoke(lc_messages)
        response_text = response.content if hasattr(response, 'content') else str(response)
        return (response_text, provider, key_source)
    except Exception as e:
        logger.error(f"Async LLM invocation failed: {e}")
        raise InvokerError(f"Failed to invoke {provider} model: {e}")


def get_available_models_for_user(user_id: UUID, db: Session) -> List[Dict[str, Any]]:
    """
    Get all models available to a user based on their configured keys.
    
    Returns list of dicts with provider, model info, and key source.
    """
    from core.provider_registry import get_all_providers, get_provider_models
    
    resolver = KeyResolver(db)
    available_models = []
    
    for provider in get_all_providers():
        api_key, key_source = resolver.resolve_key(user_id, provider.id)
        
        if api_key:
            models = get_provider_models(provider.id)
            for model in models:
                available_models.append({
                    "provider_id": provider.id,
                    "provider_name": provider.name,
                    "model_id": model.id,
                    "model_name": model.name,
                    "description": model.description,
                    "context_window": model.context_window,
                    "is_default": model.is_default,
                    "key_source": key_source
                })
    
    return available_models
