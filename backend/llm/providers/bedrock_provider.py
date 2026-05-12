from __future__ import annotations

"""AWS Bedrock provider shim backed by LiteLLM.

Delegates to :func:`litellm.acompletion` with the ``bedrock/`` model prefix.
Credentials are supplied via ``extra_config`` keys or fall back to the standard
boto3 credential chain (env vars, ``~/.aws/credentials``, IAM role).

Bedrock does not support native structured output; callers should embed the
JSON Schema in the system prompt and use ``supports_structured_output=False``
to gate that behaviour.

Example::

    from backend.llm.factory import get_llm_provider

    provider = get_llm_provider({
        "provider": "bedrock",
        "model": "anthropic.claude-3-5-sonnet-20241022-v2:0",
        "api_key": None,
        "endpoint_url": None,
        "extra_config": {
            "aws_access_key_id": "AKIA...",
            "aws_secret_access_key": "...",
            "aws_region": "us-east-1",
        },
    })
"""

import logging
from collections.abc import AsyncIterator
from typing import Any

import litellm

from backend.llm.base import LLMChunk, LLMMessage, LLMProviderError, LLMResponse

logger = logging.getLogger(__name__)


class BedrockProvider:
    """LiteLLM-backed shim for AWS Bedrock.

    Args:
        config: Provider configuration dict.  Relevant ``extra_config`` keys:

            - ``"aws_access_key_id"`` — AWS access key (optional; falls back to
              boto3 credential chain).
            - ``"aws_secret_access_key"`` — AWS secret key.
            - ``"aws_session_token"`` — Optional session token for temporary
              credentials.
            - ``"aws_region"`` — AWS region (e.g. ``"us-east-1"``).
    """

    provider_id = "bedrock"
    supports_structured_output = False
    supports_tool_use = True

    def __init__(self, config: dict[str, Any]) -> None:
        self._model = f"bedrock/{config['model']}"
        extra: dict[str, Any] = config.get("extra_config") or {}
        self._aws_access_key_id: str | None = extra.get("aws_access_key_id")
        self._aws_secret_access_key: str | None = extra.get("aws_secret_access_key")
        self._aws_session_token: str | None = extra.get("aws_session_token")
        self._aws_region_name: str | None = extra.get("aws_region")

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
        if self._aws_access_key_id:
            kwargs["aws_access_key_id"] = self._aws_access_key_id
        if self._aws_secret_access_key:
            kwargs["aws_secret_access_key"] = self._aws_secret_access_key
        if self._aws_session_token:
            kwargs["aws_session_token"] = self._aws_session_token
        if self._aws_region_name:
            kwargs["aws_region_name"] = self._aws_region_name
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
        """Send *messages* to AWS Bedrock and return the full response.

        Args:
            messages: Ordered conversation turns.
            tools: Optional OpenAI-format tool definitions.
            max_tokens: Maximum completion tokens.
            temperature: Sampling temperature (0 = deterministic).
            json_schema: Ignored; Bedrock does not support native structured
                output.  Embed the schema in the system prompt instead.

        Returns:
            :class:`~backend.llm.base.LLMResponse` with text and token counts.

        Raises:
            LLMProviderError: On any LiteLLM / Bedrock error.
        """
        kwargs = self._build_kwargs(messages, tools, max_tokens, temperature, False)
        try:
            response = await litellm.acompletion(**kwargs)
        except Exception as exc:
            raise LLMProviderError(f"Bedrock API error: {exc}") from exc

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
        """Stream *messages* to AWS Bedrock and yield incremental chunks.

        Args:
            messages: Ordered conversation turns.
            tools: Optional tool definitions.
            max_tokens: Maximum completion tokens.
            temperature: Sampling temperature.

        Yields:
            :class:`~backend.llm.base.LLMChunk` deltas.

        Raises:
            LLMProviderError: On any LiteLLM / Bedrock error.
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
            raise LLMProviderError(f"Bedrock streaming error: {exc}") from exc
