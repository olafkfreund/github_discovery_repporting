from __future__ import annotations

"""Base types and Protocol definition for the LLM provider abstraction.

This module defines the shared data models and the :class:`LLMProvider` Protocol
that all concrete provider shims must satisfy.  Callers depend only on the types
defined here — never on a concrete implementation — so providers can be swapped
without touching business logic.

Example::

    from backend.llm.base import LLMMessage, LLMProvider

    async def run_prompt(provider: LLMProvider, text: str) -> str:
        messages = [LLMMessage(role="user", content=text)]
        response = await provider.chat(messages=messages)
        return response.text
"""

from collections.abc import AsyncIterator
from typing import Any, ClassVar, Literal

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class LLMMessage(BaseModel):
    """A single message in a conversation thread.

    Args:
        role: The speaker role.  ``"tool"`` is used for tool-result turns.
        content: The text body of the message.
    """

    role: Literal["system", "user", "assistant", "tool"]
    content: str


class LLMToolCall(BaseModel):
    """A tool invocation requested by the model.

    Args:
        id: Unique identifier for this tool call (provider-assigned).
        name: Name of the tool to invoke.
        arguments: Parsed JSON arguments for the tool.
    """

    id: str
    name: str
    arguments: dict[str, Any]


class LLMResponse(BaseModel):
    """Normalised response from a non-streaming :meth:`LLMProvider.chat` call.

    Args:
        text: The full text response from the model.
        tool_calls: Any tool calls the model requested; empty when none.
        input_tokens: Number of prompt tokens consumed.
        output_tokens: Number of completion tokens generated.
        cost_usd: Estimated cost in US dollars for the call.
        finish_reason: Reason the model stopped (e.g. ``"stop"``, ``"length"``).
    """

    text: str
    tool_calls: list[LLMToolCall] = []
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    finish_reason: str | None = None


class LLMChunk(BaseModel):
    """A single delta emitted during a streaming :meth:`LLMProvider.stream_chat` call.

    Args:
        text_delta: Incremental text fragment.  Empty string when the chunk
            carries a tool-call delta instead.
        tool_call_delta: Partial tool call emitted mid-stream, if any.
        finish_reason: Set on the final chunk; ``None`` for intermediate chunks.
    """

    text_delta: str = ""
    tool_call_delta: LLMToolCall | None = None
    finish_reason: str | None = None


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class LLMProviderError(RuntimeError):
    """Raised when an LLM provider call fails.

    Concrete shims catch provider-specific exceptions and re-raise them as this
    type so callers have a single exception surface to handle.
    """


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class LLMProvider:
    """Structural Protocol for LLM provider shims.

    All concrete providers must expose the three class-level capability flags
    and implement :meth:`chat` and :meth:`stream_chat`.

    Class variables:
        provider_id: Unique string identifier (e.g. ``"anthropic"``).
        supports_structured_output: ``True`` when the provider has native
            support for constrained JSON generation (tool-use or
            ``response_format``).  Providers with ``False`` expect the caller
            to embed the JSON schema in the system prompt instead.
        supports_tool_use: ``True`` when the provider supports the tool-call
            protocol (model can request tool invocations).

    Example::

        class MyProvider:
            provider_id = "my-provider"
            supports_structured_output = False
            supports_tool_use = False

            async def chat(self, messages, ...) -> LLMResponse: ...
            async def stream_chat(self, messages, ...) -> AsyncIterator[LLMChunk]: ...
    """

    provider_id: ClassVar[str]
    supports_structured_output: ClassVar[bool]
    supports_tool_use: ClassVar[bool]

    async def chat(
        self,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 8192,
        temperature: float = 0.0,
        json_schema: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """Send *messages* to the model and return the full response.

        Args:
            messages: Ordered list of conversation turns.
            tools: Optional list of tool definitions (OpenAI function format).
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature; ``0.0`` for deterministic output.
            json_schema: When set and ``supports_structured_output`` is ``True``,
                instruct the model to produce JSON matching this schema.

        Returns:
            :class:`LLMResponse` with the model's reply and token usage.

        Raises:
            LLMProviderError: If the provider API returns an error.
        """
        ...

    async def stream_chat(
        self,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 8192,
        temperature: float = 0.0,
    ) -> AsyncIterator[LLMChunk]:
        """Stream *messages* to the model and yield incremental chunks.

        Args:
            messages: Ordered list of conversation turns.
            tools: Optional list of tool definitions.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.

        Yields:
            :class:`LLMChunk` deltas ending with a final chunk where
            :attr:`LLMChunk.finish_reason` is set.

        Raises:
            LLMProviderError: If the provider API returns an error.
        """
        ...
        # Make this a generator at the type level.
        return
        yield LLMChunk()  # pragma: no cover — satisfies AsyncIterator typing
