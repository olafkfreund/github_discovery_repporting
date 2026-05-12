from __future__ import annotations

"""OpenAI-compatible provider shim for self-hosted endpoints (vLLM, Ollama, LM Studio).

Delegates to :func:`litellm.acompletion` with the ``openai/`` model prefix and
an ``api_base`` override pointing at the local or private endpoint.

This provider does **not** support native structured output because self-hosted
models vary widely in their JSON-constrained decoding support.  Callers should
embed the JSON Schema in the system prompt when structured output is required.

Example::

    from backend.llm.factory import get_llm_provider

    # vLLM running on localhost
    provider = get_llm_provider({
        "provider": "openai_compatible",
        "model": "mistralai/Mistral-7B-Instruct-v0.3",
        "api_key": "no-key",
        "endpoint_url": "http://localhost:8000/v1",
        "extra_config": None,
    })
"""

import logging
from collections.abc import AsyncIterator
from typing import Any

import litellm

from backend.llm.base import LLMChunk, LLMMessage, LLMProviderError, LLMResponse

logger = logging.getLogger(__name__)


class OpenAICompatProvider:
    """LiteLLM-backed shim for any OpenAI-compatible inference endpoint.

    Targets vLLM, Ollama, LM Studio, and similar self-hosted servers that
    expose the OpenAI Chat Completions API shape.

    Args:
        config: Provider configuration dict.  Relevant keys:

            - ``"model"`` — Model ID as served by the endpoint.
            - ``"api_key"`` — API key (use ``"no-key"`` or similar when the
              server does not require authentication).
            - ``"endpoint_url"`` — Base URL of the OpenAI-compatible server
              (e.g. ``"http://localhost:8000/v1"`` for vLLM).
            - ``"extra_config"`` — reserved; currently unused.
    """

    provider_id = "openai_compatible"
    supports_structured_output = False
    supports_tool_use = True

    def __init__(self, config: dict[str, Any]) -> None:
        self._model = f"openai/{config['model']}"
        self._api_key: str | None = config.get("api_key")
        self._api_base: str | None = config.get("endpoint_url")
        self._extra: dict[str, Any] = config.get("extra_config") or {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_kwargs(
        self,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]] | None,
        max_tokens: int,
        temperature: float,
        stream: bool,
    ) -> dict[str, Any]:
        """Assemble keyword arguments for :func:`litellm.acompletion`."""
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": [m.model_dump() for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
        }
        if self._api_key:
            kwargs["api_key"] = self._api_key
        if self._api_base:
            kwargs["api_base"] = self._api_base
        if tools:
            kwargs["tools"] = tools
        return kwargs

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 8192,
        temperature: float = 0.0,
        json_schema: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """Send *messages* to the OpenAI-compatible endpoint and return the response.

        Args:
            messages: Ordered conversation turns.
            tools: Optional OpenAI-format tool definitions.
            max_tokens: Maximum completion tokens.
            temperature: Sampling temperature (0 = deterministic).
            json_schema: Ignored; this provider does not support native
                structured output.  Embed the schema in the system prompt.

        Returns:
            :class:`~backend.llm.base.LLMResponse` with text and token counts.

        Raises:
            LLMProviderError: On any LiteLLM / server error.
        """
        kwargs = self._build_kwargs(messages, tools, max_tokens, temperature, False)
        try:
            response = await litellm.acompletion(**kwargs)
        except Exception as exc:
            raise LLMProviderError(f"OpenAI-compatible API error: {exc}") from exc

        choice = response.choices[0]
        text = choice.message.content or ""
        usage = response.usage or {}
        try:
            cost = litellm.completion_cost(response)
        except Exception:
            cost = 0.0

        return LLMResponse(
            text=text,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            cost_usd=cost,
            finish_reason=choice.finish_reason,
        )

    async def stream_chat(
        self,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 8192,
        temperature: float = 0.0,
    ) -> AsyncIterator[LLMChunk]:
        """Stream *messages* to the OpenAI-compatible endpoint and yield chunks.

        Args:
            messages: Ordered conversation turns.
            tools: Optional tool definitions.
            max_tokens: Maximum completion tokens.
            temperature: Sampling temperature.

        Yields:
            :class:`~backend.llm.base.LLMChunk` deltas.

        Raises:
            LLMProviderError: On any LiteLLM / server error.
        """
        kwargs = self._build_kwargs(messages, tools, max_tokens, temperature, True)
        try:
            stream = await litellm.acompletion(**kwargs)
            async for chunk in stream:
                delta = chunk.choices[0].delta
                yield LLMChunk(
                    text_delta=delta.content or "",
                    finish_reason=chunk.choices[0].finish_reason,
                )
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError(f"OpenAI-compatible streaming error: {exc}") from exc
