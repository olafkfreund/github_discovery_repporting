from __future__ import annotations

"""OpenAI provider shim backed by LiteLLM.

Delegates to :func:`litellm.acompletion` with the ``openai/`` model prefix.
Supports native structured output via ``response_format`` (``json_schema``
mode) and tool use.

Example::

    from backend.llm.factory import get_llm_provider

    provider = get_llm_provider({
        "provider": "openai",
        "model": "gpt-4o",
        "api_key": "sk-...",
        "endpoint_url": None,
        "extra_config": None,
    })
    response = await provider.chat(messages=[...])
"""

import logging
from collections.abc import AsyncIterator
from typing import Any

import litellm

from backend.llm.base import LLMChunk, LLMMessage, LLMProviderError, LLMResponse, LLMToolCall

logger = logging.getLogger(__name__)


class OpenAIProvider:
    """LiteLLM-backed shim for the OpenAI Chat Completions API.

    Args:
        config: Provider configuration dict.  Relevant keys:

            - ``"model"`` — OpenAI model ID (e.g. ``"gpt-4o"``).
            - ``"api_key"`` — OpenAI API key.
            - ``"endpoint_url"`` — Optional custom base URL (overrides the
              default ``https://api.openai.com/v1``).
            - ``"extra_config"`` — reserved; currently unused.
    """

    provider_id = "openai"
    supports_structured_output = True
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
        json_schema: dict[str, Any] | None,
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
        if json_schema and not tools:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "response", "schema": json_schema},
            }
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
        """Send *messages* to OpenAI and return the full response.

        Args:
            messages: Ordered conversation turns.
            tools: Optional OpenAI-format tool definitions.
            max_tokens: Maximum completion tokens.
            temperature: Sampling temperature (0 = deterministic).
            json_schema: JSON Schema dict; when set, uses OpenAI's
                ``response_format=json_schema`` for structured output.

        Returns:
            :class:`~backend.llm.base.LLMResponse` with text, token counts,
            and estimated cost.

        Raises:
            LLMProviderError: On any LiteLLM / OpenAI API error.
        """
        kwargs = self._build_kwargs(messages, tools, max_tokens, temperature, json_schema, False)
        try:
            response = await litellm.acompletion(**kwargs)
        except Exception as exc:
            raise LLMProviderError(f"OpenAI API error: {exc}") from exc

        choice = response.choices[0]
        message = choice.message
        text = message.content or ""

        tool_calls: list[LLMToolCall] = []
        if getattr(message, "tool_calls", None):
            for tc in message.tool_calls:
                import json

                tool_calls.append(
                    LLMToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=json.loads(tc.function.arguments),
                    )
                )

        usage = response.usage or {}
        try:
            cost = litellm.completion_cost(response)
        except Exception:
            cost = 0.0

        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
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
        """Stream *messages* to OpenAI and yield incremental chunks.

        Args:
            messages: Ordered conversation turns.
            tools: Optional tool definitions.
            max_tokens: Maximum completion tokens.
            temperature: Sampling temperature.

        Yields:
            :class:`~backend.llm.base.LLMChunk` deltas.

        Raises:
            LLMProviderError: On any LiteLLM / OpenAI API error.
        """
        kwargs = self._build_kwargs(messages, tools, max_tokens, temperature, None, True)
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
            raise LLMProviderError(f"OpenAI streaming error: {exc}") from exc
