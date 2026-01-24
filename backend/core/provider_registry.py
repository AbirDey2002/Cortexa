"""
Provider registry for LLM providers and their models.
Defines supported providers, their models, and configuration.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum


class ProviderType(str, Enum):
    """Supported LLM provider types."""
    OPENAI = "openai"
    GEMINI = "gemini"
    CLAUDE = "claude"
    GROK = "grok"
    HUGGINGFACE = "huggingface"
    DEEPSEEK = "deepseek"


@dataclass
class ModelInfo:
    """Information about an LLM model."""
    id: str
    name: str
    description: str = ""
    context_window: int = 0
    is_default: bool = False


@dataclass
class ProviderInfo:
    """Information about an LLM provider."""
    id: str
    name: str
    description: str
    models: List[ModelInfo] = field(default_factory=list)
    env_key_name: str = ""  # Environment variable name for system key
    api_base_url: Optional[str] = None
    requires_base_url: bool = False


# Provider Registry - Static configuration of all supported providers (Updated Jan 2026)
PROVIDER_REGISTRY: Dict[str, ProviderInfo] = {
    ProviderType.OPENAI: ProviderInfo(
        id=ProviderType.OPENAI,
        name="OpenAI",
        description="GPT models from OpenAI",
        env_key_name="OPENAI_API_KEY",
        models=[
            # GPT-5 Series (Latest - Jan 2026)
            ModelInfo(id="gpt-5.2", name="GPT-5.2", description="Best for coding and agentic tasks", context_window=128000, is_default=True),
            ModelInfo(id="gpt-5.1", name="GPT-5.1", description="Balanced performance and cost", context_window=128000),
            ModelInfo(id="gpt-5", name="GPT-5", description="August 2025 flagship", context_window=128000),
            ModelInfo(id="gpt-5-mini", name="GPT-5 Mini", description="Fast and cost-efficient", context_window=128000),
            ModelInfo(id="gpt-5-nano", name="GPT-5 Nano", description="Fastest for simple tasks", context_window=128000),
            # GPT-4o Series (Stable)
            ModelInfo(id="gpt-4o", name="GPT-4o", description="GPT-4 Omni multimodal", context_window=128000),
            ModelInfo(id="gpt-4o-mini", name="GPT-4o Mini", description="Smaller, faster GPT-4o", context_window=128000),
            # O-Series Reasoning Models
            ModelInfo(id="o3", name="OpenAI o3", description="Advanced reasoning model", context_window=200000),
            ModelInfo(id="o3-mini", name="OpenAI o3 Mini", description="Cost-efficient reasoning", context_window=200000),
            ModelInfo(id="o4-mini", name="OpenAI o4 Mini", description="Fast reasoning for math/code", context_window=200000),
            ModelInfo(id="o1", name="OpenAI o1", description="Original reasoning model", context_window=128000),
            ModelInfo(id="o1-mini", name="OpenAI o1 Mini", description="Efficient reasoning", context_window=128000),
        ]
    ),
    ProviderType.GEMINI: ProviderInfo(
        id=ProviderType.GEMINI,
        name="Google Gemini",
        description="Gemini models from Google",
        env_key_name="GEMINI_API_KEY",
        models=[
            # Gemini 2.5 Series (GA - Recommended)
            ModelInfo(id="gemini-2.5-flash", name="Gemini 2.5 Flash", description="Balanced intelligence and latency", context_window=1000000, is_default=True),
            ModelInfo(id="gemini-2.5-pro", name="Gemini 2.5 Pro", description="Advanced reasoning, 1M context", context_window=1000000),
            ModelInfo(id="gemini-2.5-flash-lite", name="Gemini 2.5 Flash Lite", description="Ultra-fast and cost-efficient", context_window=1000000),
            # Gemini 2.0 Series (GA - Stable)
            ModelInfo(id="gemini-2.0-flash", name="Gemini 2.0 Flash", description="Multimodal with tool use", context_window=1000000),
            ModelInfo(id="gemini-2.0-flash-lite", name="Gemini 2.0 Flash Lite", description="Simple high-frequency tasks", context_window=1000000),
            # Gemini 3 Series (Preview - May not be available in all regions)
            ModelInfo(id="gemini-3-flash-preview", name="Gemini 3 Flash (Preview)", description="Pro-level intelligence at Flash speed", context_window=1000000),
            ModelInfo(id="gemini-3-pro-preview", name="Gemini 3 Pro (Preview)", description="Complex agentic workflows", context_window=1000000),
        ]
    ),
    ProviderType.CLAUDE: ProviderInfo(
        id=ProviderType.CLAUDE,
        name="Anthropic Claude",
        description="Claude models from Anthropic",
        env_key_name="ANTHROPIC_API_KEY",
        models=[
            # Claude 4.5 Series (Latest - Jan 2026)
            ModelInfo(id="claude-opus-4-5-20251101", name="Claude Opus 4.5", description="Most intelligent, complex tasks", context_window=200000, is_default=True),
            ModelInfo(id="claude-sonnet-4-5-20250929", name="Claude Sonnet 4.5", description="Best for coding and agents", context_window=200000),
            ModelInfo(id="claude-haiku-4-5-20251001", name="Claude Haiku 4.5", description="Fastest and most cost-effective", context_window=200000),
            # Claude 4 Series (Stable)
            ModelInfo(id="claude-opus-4-1-20250805", name="Claude Opus 4.1", description="Enhanced agentic tasks", context_window=200000),
            ModelInfo(id="claude-sonnet-4-20250514", name="Claude Sonnet 4", description="Fast and context-aware", context_window=200000),
            ModelInfo(id="claude-opus-4-20250514", name="Claude Opus 4", description="Powerful reasoning", context_window=200000),
            # Claude 3.7 Sonnet (Hybrid reasoning)
            ModelInfo(id="claude-3-7-sonnet-latest", name="Claude 3.7 Sonnet", description="Hybrid reasoning model", context_window=200000),
            # Claude 3.5 Series (Legacy)
            ModelInfo(id="claude-3-5-sonnet-20241022", name="Claude 3.5 Sonnet", description="Balanced performance", context_window=200000),
            ModelInfo(id="claude-3-5-haiku-20241022", name="Claude 3.5 Haiku", description="Fast and affordable", context_window=200000),
        ]
    ),
    ProviderType.GROK: ProviderInfo(
        id=ProviderType.GROK,
        name="xAI Grok",
        description="Grok models from xAI",
        env_key_name="XAI_API_KEY",
        api_base_url="https://api.x.ai/v1",
        models=[
            # Grok-4 Series (Latest - Jan 2026)
            ModelInfo(id="grok-4", name="Grok-4", description="Latest flagship, 256K context", context_window=256000, is_default=True),
            ModelInfo(id="grok-4-fast-reasoning", name="Grok-4 Fast Reasoning", description="2M context, for reasoning", context_window=2000000),
            ModelInfo(id="grok-4-fast-non-reasoning", name="Grok-4 Fast", description="High-throughput tasks", context_window=2000000),
            # Grok-3 Series (Stable)
            ModelInfo(id="grok-3", name="Grok-3", description="Enterprise-grade reasoning", context_window=128000),
            ModelInfo(id="grok-3-mini", name="Grok-3 Mini", description="Cost-efficient completions", context_window=128000),
            # Specialized
            ModelInfo(id="grok-code-fast-1", name="Grok Code Fast", description="Specialized for coding", context_window=128000),
            ModelInfo(id="grok-2-image-1212", name="Grok-2 Image", description="Text-to-image generation", context_window=8000),
        ]
    ),
    ProviderType.HUGGINGFACE: ProviderInfo(
        id=ProviderType.HUGGINGFACE,
        name="HuggingFace",
        description="Models via HuggingFace Inference API",
        env_key_name="HUGGINGFACE_API_KEY",
        requires_base_url=True,
        models=[
            # Llama 3.1 Series
            ModelInfo(id="meta-llama/Llama-3.1-405B-Instruct", name="Llama 3.1 405B", description="Largest Llama model", context_window=128000, is_default=True),
            ModelInfo(id="meta-llama/Llama-3.1-70B-Instruct", name="Llama 3.1 70B", description="Meta's Llama 3.1", context_window=128000),
            ModelInfo(id="meta-llama/Llama-3.1-8B-Instruct", name="Llama 3.1 8B", description="Efficient Llama", context_window=128000),
            # Mixtral
            ModelInfo(id="mistralai/Mixtral-8x22B-Instruct-v0.1", name="Mixtral 8x22B", description="Large MoE model", context_window=65536),
            ModelInfo(id="mistralai/Mixtral-8x7B-Instruct-v0.1", name="Mixtral 8x7B", description="Mistral's MoE", context_window=32000),
            # Qwen
            ModelInfo(id="Qwen/Qwen2.5-72B-Instruct", name="Qwen 2.5 72B", description="Alibaba's latest", context_window=128000),
        ]
    ),
    ProviderType.DEEPSEEK: ProviderInfo(
        id=ProviderType.DEEPSEEK,
        name="DeepSeek",
        description="DeepSeek AI models",
        env_key_name="DEEPSEEK_API_KEY",
        api_base_url="https://api.deepseek.com/v1",
        models=[
            # V3 Series (Latest)
            ModelInfo(id="deepseek-chat", name="DeepSeek Chat (V3.2)", description="General conversations", context_window=128000, is_default=True),
            ModelInfo(id="deepseek-reasoner", name="DeepSeek Reasoner", description="Chain-of-thought reasoning", context_window=128000),
            # Specialized
            ModelInfo(id="deepseek-coder", name="DeepSeek Coder", description="Code-focused model", context_window=64000),
        ]
    ),
}


def get_provider(provider_id: str) -> Optional[ProviderInfo]:
    """Get provider info by ID."""
    return PROVIDER_REGISTRY.get(provider_id)


def get_all_providers() -> List[ProviderInfo]:
    """Get all registered providers."""
    return list(PROVIDER_REGISTRY.values())


def get_provider_models(provider_id: str) -> List[ModelInfo]:
    """Get all models for a provider."""
    provider = get_provider(provider_id)
    return provider.models if provider else []


def get_default_model(provider_id: str) -> Optional[ModelInfo]:
    """Get the default model for a provider."""
    models = get_provider_models(provider_id)
    for model in models:
        if model.is_default:
            return model
    return models[0] if models else None


def get_model(provider_id: str, model_id: str) -> Optional[ModelInfo]:
    """Get a specific model from a provider."""
    models = get_provider_models(provider_id)
    for model in models:
        if model.id == model_id:
            return model
    return None


def is_valid_provider(provider_id: str) -> bool:
    """Check if a provider ID is valid."""
    return provider_id in PROVIDER_REGISTRY


def is_valid_model(provider_id: str, model_id: str) -> bool:
    """Check if a model ID is valid for a provider."""
    return get_model(provider_id, model_id) is not None


def get_provider_env_key_name(provider_id: str) -> Optional[str]:
    """Get the environment variable name for a provider's system key."""
    provider = get_provider(provider_id)
    return provider.env_key_name if provider else None
