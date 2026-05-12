from __future__ import annotations

"""Unit tests for the six LLM provider shims.

Each test patches :func:`litellm.acompletion` with a canned
:class:`litellm.types.utils.ModelResponse` so no real API calls are made.

Tests verify:
- The correct model prefix is passed to ``acompletion``.
- Input messages are translated correctly.
- The returned :class:`~backend.llm.base.LLMResponse` carries the expected
  text and token counts.
- Provider-specific credential keys are forwarded.
- :class:`~backend.llm.base.LLMProviderError` is raised when ``acompletion``
  raises.
- Factory raises :class:`ValueError` for unknown provider names.
- ``supports_structured_output`` is ``False`` for Bedrock and OpenAI-compat.
"""

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from litellm.types.utils import Choices, Message, ModelResponse, Usage

from backend.llm.base import LLMMessage, LLMProviderError, LLMResponse
from backend.llm.factory import get_llm_provider
from backend.llm.providers.anthropic_provider import AnthropicProvider
from backend.llm.providers.azure_openai_provider import AzureOpenAIProvider
from backend.llm.providers.bedrock_provider import BedrockProvider
from backend.llm.providers.openai_compat_provider import OpenAICompatProvider
from backend.llm.providers.openai_provider import OpenAIProvider
from backend.llm.providers.vertex_provider import VertexProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(
    text: str = "Hello, world!",
    model: str = "test-model",
    input_tokens: int = 10,
    output_tokens: int = 20,
    finish_reason: str = "stop",
) -> ModelResponse:
    """Build a minimal LiteLLM ModelResponse for use in monkeypatching."""
    usage = Usage(
        prompt_tokens=input_tokens,
        completion_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
    )
    message = Message(content=text, role="assistant")
    choice = Choices(finish_reason=finish_reason, index=0, message=message)
    return ModelResponse(
        id="canned-id",
        choices=[choice],
        created=1_700_000_000,
        model=model,
        object="chat.completion",
        usage=usage,
    )


_MESSAGES = [LLMMessage(role="user", content="Summarise findings.")]


def _assert_response(result: LLMResponse, *, text: str = "Hello, world!") -> None:
    """Common assertions on a translated LLMResponse."""
    assert isinstance(result, LLMResponse)
    assert result.text == text
    assert result.input_tokens == 10
    assert result.output_tokens == 20
    assert result.finish_reason == "stop"


# ---------------------------------------------------------------------------
# Anthropic provider
# ---------------------------------------------------------------------------


class TestAnthropicProvider:
    """Tests for :class:`AnthropicProvider`."""

    def _provider(self, **overrides: Any) -> AnthropicProvider:
        config: dict[str, Any] = {
            "provider": "anthropic",
            "model": "claude-opus-4-7",
            "api_key": "sk-ant-test",
            "endpoint_url": None,
            "extra_config": None,
            **overrides,
        }
        return AnthropicProvider(config)

    def test_class_vars(self) -> None:
        assert AnthropicProvider.provider_id == "anthropic"
        assert AnthropicProvider.supports_structured_output is True
        assert AnthropicProvider.supports_tool_use is True

    @pytest.mark.asyncio
    async def test_chat_calls_acompletion_with_correct_prefix(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """acompletion is called with the ``anthropic/`` prefix."""
        canned = _make_response()
        mock_ac = AsyncMock(return_value=canned)
        monkeypatch.setattr("litellm.acompletion", mock_ac)
        monkeypatch.setattr("litellm.completion_cost", MagicMock(return_value=0.001))

        provider = self._provider()
        result = await provider.chat(_MESSAGES)

        mock_ac.assert_awaited_once()
        call_kwargs = mock_ac.call_args.kwargs
        assert call_kwargs["model"] == "anthropic/claude-opus-4-7"
        assert call_kwargs["api_key"] == "sk-ant-test"
        assert call_kwargs["messages"] == [m.model_dump() for m in _MESSAGES]
        _assert_response(result)

    @pytest.mark.asyncio
    async def test_chat_raises_llm_provider_error_on_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Network errors are wrapped as LLMProviderError."""
        monkeypatch.setattr(
            "litellm.acompletion", AsyncMock(side_effect=RuntimeError("network failure"))
        )
        provider = self._provider()
        with pytest.raises(LLMProviderError, match="network failure"):
            await provider.chat(_MESSAGES)

    @pytest.mark.asyncio
    async def test_stream_chat_yields_chunks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """stream_chat yields LLMChunk objects."""

        async def _fake_stream_iter() -> AsyncIterator[Any]:
            for chunk in [
                _make_stream_chunk("Hello"),
                _make_stream_chunk(" world", finish_reason="stop"),
            ]:
                yield chunk

        # acompletion(stream=True) returns a coroutine → async iterator
        mock_ac = AsyncMock(return_value=_fake_stream_iter())
        monkeypatch.setattr("litellm.acompletion", mock_ac)

        provider = self._provider()
        chunks = [chunk async for chunk in provider.stream_chat(_MESSAGES)]
        assert chunks[0].text_delta == "Hello"
        assert chunks[1].text_delta == " world"
        assert chunks[1].finish_reason == "stop"


# ---------------------------------------------------------------------------
# OpenAI provider
# ---------------------------------------------------------------------------


class TestOpenAIProvider:
    """Tests for :class:`OpenAIProvider`."""

    def _provider(self, **overrides: Any) -> OpenAIProvider:
        config: dict[str, Any] = {
            "provider": "openai",
            "model": "gpt-4o",
            "api_key": "sk-openai-test",
            "endpoint_url": None,
            "extra_config": None,
            **overrides,
        }
        return OpenAIProvider(config)

    def test_class_vars(self) -> None:
        assert OpenAIProvider.provider_id == "openai"
        assert OpenAIProvider.supports_structured_output is True
        assert OpenAIProvider.supports_tool_use is True

    @pytest.mark.asyncio
    async def test_chat_uses_openai_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        canned = _make_response(model="openai/gpt-4o")
        mock_ac = AsyncMock(return_value=canned)
        monkeypatch.setattr("litellm.acompletion", mock_ac)
        monkeypatch.setattr("litellm.completion_cost", MagicMock(return_value=0.0))

        provider = self._provider()
        result = await provider.chat(_MESSAGES)

        call_kwargs = mock_ac.call_args.kwargs
        assert call_kwargs["model"] == "openai/gpt-4o"
        _assert_response(result)

    @pytest.mark.asyncio
    async def test_chat_honours_endpoint_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """api_base is set when endpoint_url is provided."""
        canned = _make_response()
        mock_ac = AsyncMock(return_value=canned)
        monkeypatch.setattr("litellm.acompletion", mock_ac)
        monkeypatch.setattr("litellm.completion_cost", MagicMock(return_value=0.0))

        provider = self._provider(endpoint_url="https://my-proxy.example.com/v1")
        await provider.chat(_MESSAGES)

        call_kwargs = mock_ac.call_args.kwargs
        assert call_kwargs["api_base"] == "https://my-proxy.example.com/v1"

    @pytest.mark.asyncio
    async def test_chat_raises_on_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "litellm.acompletion", AsyncMock(side_effect=ConnectionError("timeout"))
        )
        with pytest.raises(LLMProviderError, match="timeout"):
            await self._provider().chat(_MESSAGES)


# ---------------------------------------------------------------------------
# Bedrock provider
# ---------------------------------------------------------------------------


class TestBedrockProvider:
    """Tests for :class:`BedrockProvider`."""

    def _provider(self, **overrides: Any) -> BedrockProvider:
        config: dict[str, Any] = {
            "provider": "bedrock",
            "model": "anthropic.claude-3-5-sonnet-20241022-v2:0",
            "api_key": None,
            "endpoint_url": None,
            "extra_config": {
                "aws_access_key_id": "AKIAIOSFODNN7EXAMPLE",
                "aws_secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                "aws_region": "us-east-1",
            },
            **overrides,
        }
        return BedrockProvider(config)

    def test_class_vars(self) -> None:
        assert BedrockProvider.provider_id == "bedrock"
        assert BedrockProvider.supports_structured_output is False
        assert BedrockProvider.supports_tool_use is True

    @pytest.mark.asyncio
    async def test_chat_uses_bedrock_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        canned = _make_response()
        mock_ac = AsyncMock(return_value=canned)
        monkeypatch.setattr("litellm.acompletion", mock_ac)
        monkeypatch.setattr("litellm.completion_cost", MagicMock(return_value=0.0))

        provider = self._provider()
        result = await provider.chat(_MESSAGES)

        call_kwargs = mock_ac.call_args.kwargs
        assert call_kwargs["model"] == "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0"
        assert call_kwargs["aws_access_key_id"] == "AKIAIOSFODNN7EXAMPLE"
        assert call_kwargs["aws_region_name"] == "us-east-1"
        _assert_response(result)

    @pytest.mark.asyncio
    async def test_chat_raises_on_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "litellm.acompletion", AsyncMock(side_effect=RuntimeError("creds error"))
        )
        with pytest.raises(LLMProviderError, match="creds error"):
            await self._provider().chat(_MESSAGES)

    def test_supports_structured_output_is_false(self) -> None:
        """Bedrock must not advertise native structured output support."""
        assert BedrockProvider.supports_structured_output is False


# ---------------------------------------------------------------------------
# Azure OpenAI provider
# ---------------------------------------------------------------------------


class TestAzureOpenAIProvider:
    """Tests for :class:`AzureOpenAIProvider`."""

    def _provider(self, **overrides: Any) -> AzureOpenAIProvider:
        config: dict[str, Any] = {
            "provider": "azure_openai",
            "model": "gpt-4o",
            "api_key": "azure-key-123",
            "endpoint_url": "https://my-resource.openai.azure.com",
            "extra_config": {
                "azure_deployment": "my-gpt4o",
                "api_version": "2024-02-01",
            },
            **overrides,
        }
        return AzureOpenAIProvider(config)

    def test_class_vars(self) -> None:
        assert AzureOpenAIProvider.provider_id == "azure_openai"
        assert AzureOpenAIProvider.supports_structured_output is True
        assert AzureOpenAIProvider.supports_tool_use is True

    @pytest.mark.asyncio
    async def test_chat_uses_azure_prefix_and_deployment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        canned = _make_response()
        mock_ac = AsyncMock(return_value=canned)
        monkeypatch.setattr("litellm.acompletion", mock_ac)
        monkeypatch.setattr("litellm.completion_cost", MagicMock(return_value=0.0))

        provider = self._provider()
        result = await provider.chat(_MESSAGES)

        call_kwargs = mock_ac.call_args.kwargs
        assert call_kwargs["model"] == "azure/my-gpt4o"
        assert call_kwargs["api_key"] == "azure-key-123"
        assert call_kwargs["api_base"] == "https://my-resource.openai.azure.com"
        assert call_kwargs["api_version"] == "2024-02-01"
        _assert_response(result)

    @pytest.mark.asyncio
    async def test_chat_raises_on_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "litellm.acompletion", AsyncMock(side_effect=OSError("connection refused"))
        )
        with pytest.raises(LLMProviderError, match="connection refused"):
            await self._provider().chat(_MESSAGES)


# ---------------------------------------------------------------------------
# Vertex provider
# ---------------------------------------------------------------------------


class TestVertexProvider:
    """Tests for :class:`VertexProvider`."""

    def _provider(self, **overrides: Any) -> VertexProvider:
        config: dict[str, Any] = {
            "provider": "vertex",
            "model": "gemini-1.5-pro",
            "api_key": None,
            "endpoint_url": None,
            "extra_config": {
                "vertex_project": "my-gcp-project",
                "vertex_location": "us-central1",
            },
            **overrides,
        }
        return VertexProvider(config)

    def test_class_vars(self) -> None:
        assert VertexProvider.provider_id == "vertex"
        assert VertexProvider.supports_structured_output is True
        assert VertexProvider.supports_tool_use is True

    @pytest.mark.asyncio
    async def test_chat_uses_vertex_ai_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        canned = _make_response()
        mock_ac = AsyncMock(return_value=canned)
        monkeypatch.setattr("litellm.acompletion", mock_ac)
        monkeypatch.setattr("litellm.completion_cost", MagicMock(return_value=0.0))

        provider = self._provider()
        result = await provider.chat(_MESSAGES)

        call_kwargs = mock_ac.call_args.kwargs
        assert call_kwargs["model"] == "vertex_ai/gemini-1.5-pro"
        assert call_kwargs["vertex_project"] == "my-gcp-project"
        assert call_kwargs["vertex_location"] == "us-central1"
        _assert_response(result)

    @pytest.mark.asyncio
    async def test_chat_raises_on_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("litellm.acompletion", AsyncMock(side_effect=ValueError("auth failed")))
        with pytest.raises(LLMProviderError, match="auth failed"):
            await self._provider().chat(_MESSAGES)


# ---------------------------------------------------------------------------
# OpenAI-compatible provider
# ---------------------------------------------------------------------------


class TestOpenAICompatProvider:
    """Tests for :class:`OpenAICompatProvider`."""

    def _provider(self, **overrides: Any) -> OpenAICompatProvider:
        config: dict[str, Any] = {
            "provider": "openai_compatible",
            "model": "mistralai/Mistral-7B-Instruct-v0.3",
            "api_key": "no-key",
            "endpoint_url": "http://localhost:8000/v1",
            "extra_config": None,
            **overrides,
        }
        return OpenAICompatProvider(config)

    def test_class_vars(self) -> None:
        assert OpenAICompatProvider.provider_id == "openai_compatible"
        assert OpenAICompatProvider.supports_structured_output is False
        assert OpenAICompatProvider.supports_tool_use is True

    @pytest.mark.asyncio
    async def test_chat_uses_openai_prefix_with_api_base(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The model uses openai/ prefix and api_base points to endpoint_url."""
        canned = _make_response()
        mock_ac = AsyncMock(return_value=canned)
        monkeypatch.setattr("litellm.acompletion", mock_ac)
        monkeypatch.setattr("litellm.completion_cost", MagicMock(return_value=0.0))

        provider = self._provider()
        result = await provider.chat(_MESSAGES)

        call_kwargs = mock_ac.call_args.kwargs
        assert call_kwargs["model"] == "openai/mistralai/Mistral-7B-Instruct-v0.3"
        assert call_kwargs["api_base"] == "http://localhost:8000/v1"
        _assert_response(result)

    @pytest.mark.asyncio
    async def test_chat_raises_on_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "litellm.acompletion", AsyncMock(side_effect=RuntimeError("server unavailable"))
        )
        with pytest.raises(LLMProviderError, match="server unavailable"):
            await self._provider().chat(_MESSAGES)

    def test_supports_structured_output_is_false(self) -> None:
        """OpenAI-compat must not advertise native structured output support."""
        assert OpenAICompatProvider.supports_structured_output is False


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestGetLLMProvider:
    """Tests for :func:`~backend.llm.factory.get_llm_provider`."""

    @pytest.mark.parametrize(
        ("provider_name", "expected_cls"),
        [
            ("anthropic", AnthropicProvider),
            ("openai", OpenAIProvider),
            ("bedrock", BedrockProvider),
            ("azure_openai", AzureOpenAIProvider),
            ("vertex", VertexProvider),
            ("openai_compatible", OpenAICompatProvider),
        ],
    )
    def test_returns_correct_class(self, provider_name: str, expected_cls: type) -> None:
        """Factory returns an instance of the correct provider class."""
        config = {
            "provider": provider_name,
            "model": "test-model",
            "api_key": "dummy",
            "endpoint_url": None,
            "extra_config": None,
        }
        instance = get_llm_provider(config)
        assert isinstance(instance, expected_cls)

    def test_unknown_provider_raises_value_error(self) -> None:
        """An unrecognised provider name raises ValueError with a helpful message."""
        with pytest.raises(ValueError, match="Unknown LLM provider 'unicorn'"):
            get_llm_provider(
                {
                    "provider": "unicorn",
                    "model": "gpt-X",
                    "api_key": None,
                    "endpoint_url": None,
                    "extra_config": None,
                }
            )

    def test_error_message_lists_valid_providers(self) -> None:
        """The ValueError message lists all valid provider names."""
        with pytest.raises(ValueError, match="anthropic"):
            get_llm_provider(
                {
                    "provider": "invalid",
                    "model": "x",
                    "api_key": None,
                    "endpoint_url": None,
                    "extra_config": None,
                }
            )


# ---------------------------------------------------------------------------
# Cross-provider: supports_structured_output
# ---------------------------------------------------------------------------


class TestStructuredOutputFlags:
    """Verify which providers advertise native structured output support."""

    @pytest.mark.parametrize(
        ("provider_name", "expected"),
        [
            ("anthropic", True),
            ("openai", True),
            ("bedrock", False),
            ("azure_openai", True),
            ("vertex", True),
            ("openai_compatible", False),
        ],
    )
    def test_structured_output_flag(self, provider_name: str, expected: bool) -> None:
        config = {
            "provider": provider_name,
            "model": "test-model",
            "api_key": "x",
            "endpoint_url": "http://localhost",
            "extra_config": None,
        }
        provider = get_llm_provider(config)
        assert type(provider).supports_structured_output is expected


# ---------------------------------------------------------------------------
# Streaming helper
# ---------------------------------------------------------------------------


def _make_stream_chunk(text: str, finish_reason: str | None = None) -> MagicMock:
    """Build a mock streaming chunk compatible with the provider shims."""
    delta = MagicMock()
    delta.content = text
    choice = MagicMock()
    choice.delta = delta
    choice.finish_reason = finish_reason
    chunk = MagicMock()
    chunk.choices = [choice]
    return chunk
