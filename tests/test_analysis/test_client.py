from __future__ import annotations

"""Unit tests for :mod:`backend.analysis.client`.

Tests verify:

- :class:`AnalysisClient` delegates to the underlying :class:`LLMProvider`
  and returns the response text.
- :class:`AnalysisClientError` is raised on :class:`LLMProviderError` and
  on unexpected exceptions.
- :class:`AnalysisClientError` is raised when the provider returns empty text.
- :func:`get_analysis_client` returns a cached client for the same provider.
- :func:`get_analysis_client` accepts a custom provider and wraps it.
- An :class:`AnalysisClient` backed by a mock OpenAI provider works
  identically to one backed by a mock Anthropic provider.
"""


import pytest

from backend.analysis.client import AnalysisClient, AnalysisClientError, get_analysis_client
from backend.llm.base import LLMMessage, LLMProviderError, LLMResponse

# ---------------------------------------------------------------------------
# Fake provider implementations
# ---------------------------------------------------------------------------


class FakeAnthropicProvider:
    """Minimal LLMProvider stand-in backed by a mock chat coroutine."""

    provider_id = "anthropic"
    supports_structured_output = True
    supports_tool_use = True

    def __init__(self, response_text: str = "Analysis result text.") -> None:
        self._response_text = response_text
        # Record calls for assertion.
        self.chat_calls: list[dict] = []

    async def chat(
        self,
        messages: list[LLMMessage],
        tools=None,
        max_tokens: int = 8192,
        temperature: float = 0.0,
        json_schema=None,
    ) -> LLMResponse:
        self.chat_calls.append(
            {
                "messages": messages,
                "max_tokens": max_tokens,
                "json_schema": json_schema,
            }
        )
        return LLMResponse(
            text=self._response_text,
            input_tokens=50,
            output_tokens=100,
            finish_reason="stop",
        )

    async def stream_chat(self, messages, tools=None, max_tokens=8192, temperature=0.0):
        return
        yield  # pragma: no cover


class FakeOpenAIProvider:
    """Minimal LLMProvider stand-in representing an OpenAI-backed provider."""

    provider_id = "openai"
    supports_structured_output = True
    supports_tool_use = True

    def __init__(self, response_text: str = "OpenAI analysis result.") -> None:
        self._response_text = response_text
        self.chat_calls: list[dict] = []

    async def chat(
        self,
        messages: list[LLMMessage],
        tools=None,
        max_tokens: int = 8192,
        temperature: float = 0.0,
        json_schema=None,
    ) -> LLMResponse:
        self.chat_calls.append(
            {
                "messages": messages,
                "max_tokens": max_tokens,
                "json_schema": json_schema,
            }
        )
        return LLMResponse(
            text=self._response_text,
            input_tokens=40,
            output_tokens=90,
            finish_reason="stop",
        )

    async def stream_chat(self, messages, tools=None, max_tokens=8192, temperature=0.0):
        return
        yield  # pragma: no cover


class FailingProvider:
    """Provider that always raises LLMProviderError."""

    provider_id = "failing"
    supports_structured_output = False
    supports_tool_use = False

    async def chat(self, messages, tools=None, max_tokens=8192, temperature=0.0, json_schema=None):
        raise LLMProviderError("simulated API failure")

    async def stream_chat(self, messages, tools=None, max_tokens=8192, temperature=0.0):
        return
        yield  # pragma: no cover


class EmptyResponseProvider:
    """Provider that returns an empty text response."""

    provider_id = "empty"
    supports_structured_output = False
    supports_tool_use = False

    async def chat(self, messages, tools=None, max_tokens=8192, temperature=0.0, json_schema=None):
        return LLMResponse(text="", finish_reason="stop")

    async def stream_chat(self, messages, tools=None, max_tokens=8192, temperature=0.0):
        return
        yield  # pragma: no cover


class UnexpectedErrorProvider:
    """Provider that raises a non-LLMProviderError exception."""

    provider_id = "unexpected"
    supports_structured_output = False
    supports_tool_use = False

    async def chat(self, messages, tools=None, max_tokens=8192, temperature=0.0, json_schema=None):
        raise ValueError("unexpected internal error")

    async def stream_chat(self, messages, tools=None, max_tokens=8192, temperature=0.0):
        return
        yield  # pragma: no cover


# ---------------------------------------------------------------------------
# Tests: AnalysisClient construction
# ---------------------------------------------------------------------------


class TestAnalysisClientInit:
    """Tests for :class:`AnalysisClient` initialisation."""

    def test_stores_provider(self) -> None:
        provider = FakeAnthropicProvider()
        client = AnalysisClient(provider=provider)
        assert client._provider is provider

    def test_default_max_tokens(self) -> None:
        client = AnalysisClient(provider=FakeAnthropicProvider())
        assert client._max_tokens == 8192

    def test_custom_max_tokens(self) -> None:
        client = AnalysisClient(provider=FakeAnthropicProvider(), max_tokens=4096)
        assert client._max_tokens == 4096


# ---------------------------------------------------------------------------
# Tests: AnalysisClient.analyze — happy path
# ---------------------------------------------------------------------------


class TestAnalysisClientAnalyze:
    """Tests for :meth:`AnalysisClient.analyze` happy path."""

    @pytest.mark.asyncio
    async def test_returns_response_text(self) -> None:
        """analyze() returns the text from the provider response."""
        provider = FakeAnthropicProvider(response_text="my analysis")
        client = AnalysisClient(provider=provider)
        result = await client.analyze(prompt="scan data", system="you are an expert")
        assert result == "my analysis"

    @pytest.mark.asyncio
    async def test_builds_correct_messages(self) -> None:
        """analyze() sends system + user messages in the correct order."""
        provider = FakeAnthropicProvider()
        client = AnalysisClient(provider=provider)
        await client.analyze(prompt="user content", system="system content")

        assert len(provider.chat_calls) == 1
        call = provider.chat_calls[0]
        messages = call["messages"]
        assert len(messages) == 2
        assert messages[0].role == "system"
        assert messages[0].content == "system content"
        assert messages[1].role == "user"
        assert messages[1].content == "user content"

    @pytest.mark.asyncio
    async def test_passes_max_tokens(self) -> None:
        """analyze() forwards max_tokens to chat()."""
        provider = FakeAnthropicProvider()
        client = AnalysisClient(provider=provider, max_tokens=2048)
        await client.analyze(prompt="p", system="s")
        assert provider.chat_calls[0]["max_tokens"] == 2048

    @pytest.mark.asyncio
    async def test_passes_json_schema_when_given(self) -> None:
        """analyze() forwards json_schema to chat() when provided."""
        provider = FakeAnthropicProvider()
        client = AnalysisClient(provider=provider)
        schema = {"type": "object", "properties": {}}
        await client.analyze(prompt="p", system="s", json_schema=schema)
        assert provider.chat_calls[0]["json_schema"] == schema

    @pytest.mark.asyncio
    async def test_json_schema_defaults_to_none(self) -> None:
        """analyze() passes json_schema=None by default."""
        provider = FakeAnthropicProvider()
        client = AnalysisClient(provider=provider)
        await client.analyze(prompt="p", system="s")
        assert provider.chat_calls[0]["json_schema"] is None


# ---------------------------------------------------------------------------
# Tests: AnalysisClient.analyze — error handling
# ---------------------------------------------------------------------------


class TestAnalysisClientErrors:
    """Tests for error handling in :meth:`AnalysisClient.analyze`."""

    @pytest.mark.asyncio
    async def test_llm_provider_error_raises_analysis_client_error(self) -> None:
        """LLMProviderError is re-raised as AnalysisClientError."""
        client = AnalysisClient(provider=FailingProvider())
        with pytest.raises(AnalysisClientError, match="simulated API failure"):
            await client.analyze(prompt="p", system="s")

    @pytest.mark.asyncio
    async def test_unexpected_exception_raises_analysis_client_error(self) -> None:
        """Non-LLMProviderError exceptions are wrapped as AnalysisClientError."""
        client = AnalysisClient(provider=UnexpectedErrorProvider())
        with pytest.raises(AnalysisClientError, match="unexpected internal error"):
            await client.analyze(prompt="p", system="s")

    @pytest.mark.asyncio
    async def test_empty_response_raises_analysis_client_error(self) -> None:
        """An empty provider response raises AnalysisClientError."""
        client = AnalysisClient(provider=EmptyResponseProvider())
        with pytest.raises(AnalysisClientError, match="empty response"):
            await client.analyze(prompt="p", system="s")

    @pytest.mark.asyncio
    async def test_analysis_client_error_is_runtime_error(self) -> None:
        """AnalysisClientError is a subclass of RuntimeError for backwards compat."""
        assert issubclass(AnalysisClientError, RuntimeError)


# ---------------------------------------------------------------------------
# Tests: get_analysis_client factory
# ---------------------------------------------------------------------------


class TestGetAnalysisClientFactory:
    """Tests for :func:`get_analysis_client`."""

    def test_returns_analysis_client_instance(self) -> None:
        provider = FakeAnthropicProvider()
        client = get_analysis_client(provider=provider)
        assert isinstance(client, AnalysisClient)

    def test_same_provider_returns_cached_client(self) -> None:
        """Calling get_analysis_client twice with the same provider object
        returns the same AnalysisClient instance."""
        provider = FakeAnthropicProvider()
        client_a = get_analysis_client(provider=provider)
        client_b = get_analysis_client(provider=provider)
        assert client_a is client_b

    def test_different_providers_return_different_clients(self) -> None:
        """Different provider objects yield distinct AnalysisClient instances."""
        provider_a = FakeAnthropicProvider()
        provider_b = FakeAnthropicProvider()
        client_a = get_analysis_client(provider=provider_a)
        client_b = get_analysis_client(provider=provider_b)
        assert client_a is not client_b

    def test_custom_provider_is_stored(self) -> None:
        """The returned client's _provider is the one supplied."""
        provider = FakeOpenAIProvider()
        client = get_analysis_client(provider=provider)
        assert client._provider is provider


# ---------------------------------------------------------------------------
# Tests: provider-agnostic — OpenAI provider works identically to Anthropic
# ---------------------------------------------------------------------------


class TestAnalysisClientWorksAgainstOpenAIProvider:
    """Prove provider-agnostic behaviour by exercising with an OpenAI provider.

    This test constructs an AnalysisClient with a mock OpenAI provider and
    verifies it behaves identically to one backed by a mock Anthropic provider.
    """

    @pytest.mark.asyncio
    async def test_analysis_client_works_against_openai_provider(self) -> None:
        """AnalysisClient backed by a mock OpenAI provider returns text correctly."""
        openai_provider = FakeOpenAIProvider(response_text="OpenAI output")
        client = AnalysisClient(provider=openai_provider)
        result = await client.analyze(prompt="findings data", system="be an expert")
        assert result == "OpenAI output"

    @pytest.mark.asyncio
    async def test_openai_and_anthropic_clients_produce_same_interface(self) -> None:
        """Both providers result in identical call patterns through AnalysisClient."""
        anthropic_provider = FakeAnthropicProvider(response_text="anthropic output")
        openai_provider = FakeOpenAIProvider(response_text="openai output")

        anthropic_client = AnalysisClient(provider=anthropic_provider)
        openai_client = AnalysisClient(provider=openai_provider)

        prompt = "scan findings here"
        system = "you are a DevOps expert"

        anthropic_result = await anthropic_client.analyze(prompt=prompt, system=system)
        openai_result = await openai_client.analyze(prompt=prompt, system=system)

        # Both return strings.
        assert isinstance(anthropic_result, str)
        assert isinstance(openai_result, str)

        # Both providers received the same message structure.
        assert len(anthropic_provider.chat_calls) == 1
        assert len(openai_provider.chat_calls) == 1

        anth_msgs = anthropic_provider.chat_calls[0]["messages"]
        oai_msgs = openai_provider.chat_calls[0]["messages"]

        assert len(anth_msgs) == len(oai_msgs) == 2
        assert anth_msgs[0].role == oai_msgs[0].role == "system"
        assert anth_msgs[1].role == oai_msgs[1].role == "user"
        assert anth_msgs[0].content == oai_msgs[0].content == system
        assert anth_msgs[1].content == oai_msgs[1].content == prompt

    @pytest.mark.asyncio
    async def test_openai_provider_error_surfaces_as_analysis_client_error(self) -> None:
        """LLMProviderError from an OpenAI-backed provider becomes AnalysisClientError."""

        class FailingOpenAIProvider:
            provider_id = "openai"
            supports_structured_output = True
            supports_tool_use = True

            async def chat(
                self, messages, tools=None, max_tokens=8192, temperature=0.0, json_schema=None
            ):
                raise LLMProviderError("OpenAI rate limit exceeded")

            async def stream_chat(self, messages, tools=None, max_tokens=8192, temperature=0.0):
                return
                yield  # pragma: no cover

        client = AnalysisClient(provider=FailingOpenAIProvider())
        with pytest.raises(AnalysisClientError, match="OpenAI rate limit exceeded"):
            await client.analyze(prompt="p", system="s")
