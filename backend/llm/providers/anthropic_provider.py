from __future__ import annotations

"""Anthropic provider shim backed by LiteLLM.

Delegates to :func:`litellm.acompletion` with the ``anthropic/`` model prefix.
Supports native tool use and structured output via Anthropic's tool-call API.

Example::

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

import logging
from collections.abc import AsyncIterator
from typing import Any

import litellm

from backend.llm.base import LLMChunk, LLMMessage, LLMProviderError, LLMResponse, LLMToolCall

logger = logging.getLogger(__name__)


class AnthropicProvider:
    """LiteLLM-backed shim for the Anthropic Messages API.

    Args:
        config: Provider configuration dict.  Relevant keys:

            - ``"model"`` — Anthropic model ID (e.g. ``"claude-opus-4-7"``).
            - ``"api_key"`` — Anthropic API key.
            - ``"extra_config"`` — reserved; currently unused.
    """

    provider_id = "anthropic"
    supports_structured_output = True
    supports_tool_use = True

    def __init__(self, config: dict[str, Any]) -> None:
        self._model = f"anthropic/{config['model']}"
        self._api_key: str | None = config.get("api_key")
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
        """Assemble the keyword arguments for :func:`litellm.acompletion`."""
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": [m.model_dump() for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
        }
        if self._api_key:
            kwargs["api_key"] = self._api_key
        if tools:
            kwargs["tools"] = tools
        # Anthropic structured output: pass json_schema as a tool with
        # tool_choice={"type": "tool"} to force JSON output.
        if json_schema and not tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": "structured_output",
                        "description": "Return structured JSON output.",
                        "parameters": json_schema,
                    },
                }
            ]
            kwargs["tool_choice"] = {"type": "function", "function": {"name": "structured_output"}}
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
        """Send *messages* to Anthropic and return the full response.

        Args:
            messages: Ordered conversation turns.
            tools: Optional OpenAI-format tool definitions.
            max_tokens: Maximum completion tokens.
            temperature: Sampling temperature (0 = deterministic).
            json_schema: JSON Schema dict; when set, forces structured output
                via Anthropic's tool-call mechanism.

        Returns:
            :class:`~backend.llm.base.LLMResponse` with text, token counts,
            and estimated cost.

        Raises:
            LLMProviderError: On any LiteLLM / Anthropic API error.
        """
        kwargs = self._build_kwargs(messages, tools, max_tokens, temperature, json_schema, False)
        try:
            response = await litellm.acompletion(**kwargs)
        except Exception as exc:
            raise LLMProviderError(f"Anthropic API error: {exc}") from exc

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
        """Stream *messages* to Anthropic and yield incremental chunks.

        Args:
            messages: Ordered conversation turns.
            tools: Optional tool definitions.
            max_tokens: Maximum completion tokens.
            temperature: Sampling temperature.

        Yields:
            :class:`~backend.llm.base.LLMChunk` deltas; the final chunk has
            :attr:`~backend.llm.base.LLMChunk.finish_reason` set.

        Raises:
            LLMProviderError: On any LiteLLM / Anthropic API error.
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
            raise LLMProviderError(f"Anthropic streaming error: {exc}") from exc
