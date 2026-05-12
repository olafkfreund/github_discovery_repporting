from __future__ import annotations

"""Factory function for constructing :class:`~backend.llm.base.LLMProvider` instances.

The factory accepts a plain ``dict`` whose shape mirrors the future
``LLMConnection`` ORM row.  This decouples the provider logic from the
database layer so the shims can be tested without a live database.

Example::

    from backend.llm.factory import get_llm_provider

    provider = get_llm_provider({
        "provider": "openai",
        "model": "gpt-4o",
        "api_key": "sk-...",
        "endpoint_url": None,
        "extra_config": None,
    })
"""

from typing import Any

from backend.llm.base import LLMProvider
from backend.llm.providers.anthropic_provider import AnthropicProvider
from backend.llm.providers.azure_openai_provider import AzureOpenAIProvider
from backend.llm.providers.bedrock_provider import BedrockProvider
from backend.llm.providers.openai_compat_provider import OpenAICompatProvider
from backend.llm.providers.openai_provider import OpenAIProvider
from backend.llm.providers.vertex_provider import VertexProvider

# Map the provider identifier string to its concrete class.
_PROVIDER_MAP: dict[str, type[LLMProvider]] = {
    "anthropic": AnthropicProvider,  # type: ignore[type-abstract]
    "openai": OpenAIProvider,  # type: ignore[type-abstract]
    "bedrock": BedrockProvider,  # type: ignore[type-abstract]
    "azure_openai": AzureOpenAIProvider,  # type: ignore[type-abstract]
    "vertex": VertexProvider,  # type: ignore[type-abstract]
    "openai_compatible": OpenAICompatProvider,  # type: ignore[type-abstract]
}


def get_llm_provider(config: dict[str, Any]) -> LLMProvider:
    """Construct and return an :class:`~backend.llm.base.LLMProvider` from *config*.

    The config dict shape matches the future ``LLMConnection`` ORM row and is
    intentionally kept as a plain ``dict`` so this function can be called from
    tests and CLI tools without a database session.

    Args:
        config: Provider configuration mapping.  Required keys:

            - ``"provider"`` — one of ``"anthropic"``, ``"openai"``,
              ``"bedrock"``, ``"azure_openai"``, ``"vertex"``,
              ``"openai_compatible"``.
            - ``"model"`` — model identifier string (provider-specific format).
            - ``"api_key"`` — API key or ``None`` when credentials come from
              environment variables or IAM roles.
            - ``"endpoint_url"`` — base URL override, or ``None`` to use the
              provider default.
            - ``"extra_config"`` — provider-specific extras (e.g.
              ``{"aws_region": "us-east-1"}`` for Bedrock), or ``None``.

    Returns:
        A concrete :class:`~backend.llm.base.LLMProvider` instance ready for use.

    Raises:
        ValueError: If the ``"provider"`` value is not recognised.

    Example::

        provider = get_llm_provider({
            "provider": "bedrock",
            "model": "anthropic.claude-3-5-sonnet-20241022-v2:0",
            "api_key": None,
            "endpoint_url": None,
            "extra_config": {"aws_region": "eu-west-1"},
        })
    """
    provider_name: str = config.get("provider", "")
    cls = _PROVIDER_MAP.get(provider_name)
    if cls is None:
        valid = ", ".join(sorted(_PROVIDER_MAP))
        raise ValueError(f"Unknown LLM provider {provider_name!r}. Valid choices are: {valid}.")
    return cls(config)  # type: ignore[abstract, call-arg]
