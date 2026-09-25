"""Provider package.

Registering the built-in OpenAI-compatible provider (configuration-driven;
inactive unless QRESOLVE_AI_PROVIDER + its env vars are set).
"""
from backend.providers.base import (
    AIProvider,
    ProviderError,
    ProviderResponse,
    ProviderTimeout,
    ProviderUnavailable,
)
from backend.providers.openai_compat import OpenAICompatibleProvider
from backend.providers.registry import (
    get_provider,
    register_provider,
    registered_providers,
    unregister_provider,
)

register_provider(OpenAICompatibleProvider.name, OpenAICompatibleProvider.from_env)

__all__ = [
    "AIProvider",
    "ProviderError",
    "ProviderResponse",
    "ProviderTimeout",
    "ProviderUnavailable",
    "OpenAICompatibleProvider",
    "get_provider",
    "register_provider",
    "registered_providers",
    "unregister_provider",
]
