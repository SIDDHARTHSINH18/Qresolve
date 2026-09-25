"""Provider registry.

The registry is empty until something registers a factory. get_provider()
returns None unless QRESOLVE_AI_PROVIDER names a registered provider AND
that provider's from_env() finds its configuration — so an unconfigured
system is fully functional with the heuristic fallback only.
"""
from __future__ import annotations

import os
from typing import Callable

from backend.providers.base import AIProvider, ProviderUnavailable

# factory: () -> AIProvider | None  (None = not configured)
_FACTORIES: dict[str, Callable[[], AIProvider | None]] = {}


def register_provider(name: str, factory: Callable[[], AIProvider | None]) -> None:
    _FACTORIES[name.lower()] = factory


def unregister_provider(name: str) -> None:
    _FACTORIES.pop(name.lower(), None)


def registered_providers() -> list[str]:
    return sorted(_FACTORIES)


def get_provider() -> AIProvider | None:
    """Build the configured provider, or None when no provider is configured.

    Raises ProviderUnavailable only when the user explicitly asked for a
    provider (env var set) that is not registered or not configurable.
    """
    requested = os.environ.get("QRESOLVE_AI_PROVIDER")
    if not requested:
        return None
    factory = _FACTORIES.get(requested.lower())
    if factory is None:
        raise ProviderUnavailable(
            f"QRESOLVE_AI_PROVIDER={requested!r} is not a registered provider "
            f"(available: {registered_providers()})"
        )
    provider = factory()
    if provider is None:
        raise ProviderUnavailable(
            f"Provider {requested!r} is registered but not configured "
            "(missing environment variables)"
        )
    return provider
