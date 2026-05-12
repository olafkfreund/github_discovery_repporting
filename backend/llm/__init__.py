from __future__ import annotations

"""LLM provider abstraction for BPS-tool.

This package provides a uniform :class:`~backend.llm.base.LLMProvider` Protocol
backed by LiteLLM so that any supported model (Anthropic, OpenAI, AWS Bedrock,
Azure OpenAI, Vertex AI, or any OpenAI-compatible endpoint) can be used for AI
analysis without changing call-site code.

Usage::

    from backend.llm.factory import get_llm_provider

    provider = get_llm_provider({
        "provider": "anthropic",
        "model": "claude-opus-4-7",
        "api_key": "sk-ant-...",
        "endpoint_url": None,
        "extra_config": None,
    })
    response = await provider.chat(messages=[...])
"""

from backend.llm.base import (
    LLMChunk,
    LLMMessage,
    LLMProvider,
    LLMProviderError,
    LLMResponse,
    LLMToolCall,
)
from backend.llm.factory import get_llm_provider

__all__ = [
    "LLMChunk",
    "LLMMessage",
    "LLMProvider",
    "LLMProviderError",
    "LLMResponse",
    "LLMToolCall",
    "get_llm_provider",
]
