from __future__ import annotations

"""Unit tests for :mod:`backend.llm.base`.

Covers Protocol runtime-checkability, Pydantic model validation, and the
LLMProviderError exception hierarchy.
"""

import pytest

from backend.llm.base import (
    LLMChunk,
    LLMMessage,
    LLMProvider,
    LLMProviderError,
    LLMResponse,
    LLMToolCall,
)

# ---------------------------------------------------------------------------
# LLMProvider Protocol
# ---------------------------------------------------------------------------


class TestLLMProviderProtocol:
    """Tests for the LLMProvider structural Protocol."""

    def test_concrete_class_satisfies_protocol(self) -> None:
        """A class with the required class vars and methods satisfies LLMProvider."""

        class _FakeProvider:
            provider_id = "fake"
            supports_structured_output = False
            supports_tool_use = False

            async def chat(
                self, messages, tools=None, max_tokens=8192, temperature=0.0, json_schema=None
            ):  # type: ignore[override]
                ...

            async def stream_chat(self, messages, tools=None, max_tokens=8192, temperature=0.0):  # type: ignore[override]
                ...
                return
                yield  # noqa: B901

        provider = _FakeProvider()
        # LLMProvider is not a runtime_checkable Protocol — we verify structural
        # compatibility by duck-typing: the object must have the required attributes.
        assert hasattr(provider, "provider_id")
        assert hasattr(provider, "supports_structured_output")
        assert hasattr(provider, "supports_tool_use")
        assert hasattr(provider, "chat")
        assert hasattr(provider, "stream_chat")

    def test_llm_provider_has_class_vars(self) -> None:
        """LLMProvider base class defines the expected ClassVar annotations."""
        annotations = LLMProvider.__annotations__
        assert "provider_id" in annotations
        assert "supports_structured_output" in annotations
        assert "supports_tool_use" in annotations


# ---------------------------------------------------------------------------
# LLMMessage
# ---------------------------------------------------------------------------


class TestLLMMessage:
    """Pydantic validation tests for LLMMessage."""

    @pytest.mark.parametrize("role", ["system", "user", "assistant", "tool"])
    def test_valid_roles(self, role: str) -> None:
        """All four defined roles are accepted."""
        msg = LLMMessage(role=role, content="hello")  # type: ignore[arg-type]
        assert msg.role == role
        assert msg.content == "hello"

    def test_invalid_role_raises(self) -> None:
        """An unknown role raises a ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            LLMMessage(role="unknown", content="hello")  # type: ignore[arg-type]

    def test_empty_content_allowed(self) -> None:
        """Empty string content is valid."""
        msg = LLMMessage(role="user", content="")
        assert msg.content == ""

    def test_model_dump_round_trip(self) -> None:
        """model_dump() produces a dict that reconstructs the same object."""
        original = LLMMessage(role="assistant", content="I can help.")
        reconstructed = LLMMessage(**original.model_dump())
        assert reconstructed == original


# ---------------------------------------------------------------------------
# LLMToolCall
# ---------------------------------------------------------------------------


class TestLLMToolCall:
    """Pydantic validation tests for LLMToolCall."""

    def test_basic_construction(self) -> None:
        tc = LLMToolCall(id="call_abc", name="search", arguments={"query": "foo"})
        assert tc.id == "call_abc"
        assert tc.name == "search"
        assert tc.arguments == {"query": "foo"}

    def test_empty_arguments(self) -> None:
        tc = LLMToolCall(id="x", name="noop", arguments={})
        assert tc.arguments == {}

    def test_nested_arguments(self) -> None:
        """Complex nested argument dicts are stored without transformation."""
        args = {"filters": {"type": "pr", "state": "open"}, "limit": 10}
        tc = LLMToolCall(id="y", name="list_prs", arguments=args)
        assert tc.arguments == args


# ---------------------------------------------------------------------------
# LLMResponse
# ---------------------------------------------------------------------------


class TestLLMResponse:
    """Pydantic validation tests for LLMResponse."""

    def test_defaults(self) -> None:
        """Non-required fields have sensible defaults."""
        resp = LLMResponse(text="hello")
        assert resp.text == "hello"
        assert resp.tool_calls == []
        assert resp.input_tokens == 0
        assert resp.output_tokens == 0
        assert resp.cost_usd == 0.0
        assert resp.finish_reason is None

    def test_full_construction(self) -> None:
        tc = LLMToolCall(id="c1", name="fn", arguments={"k": "v"})
        resp = LLMResponse(
            text="done",
            tool_calls=[tc],
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.001,
            finish_reason="stop",
        )
        assert resp.tool_calls == [tc]
        assert resp.input_tokens == 100
        assert resp.cost_usd == pytest.approx(0.001)
        assert resp.finish_reason == "stop"

    def test_negative_tokens_accepted(self) -> None:
        """Pydantic does not restrict token counts to non-negative values by default."""
        resp = LLMResponse(text="x", input_tokens=-1, output_tokens=-1)
        assert resp.input_tokens == -1


# ---------------------------------------------------------------------------
# LLMChunk
# ---------------------------------------------------------------------------


class TestLLMChunk:
    """Pydantic validation tests for LLMChunk."""

    def test_defaults(self) -> None:
        chunk = LLMChunk()
        assert chunk.text_delta == ""
        assert chunk.tool_call_delta is None
        assert chunk.finish_reason is None

    def test_text_delta(self) -> None:
        chunk = LLMChunk(text_delta="Hello")
        assert chunk.text_delta == "Hello"

    def test_finish_reason_on_final_chunk(self) -> None:
        chunk = LLMChunk(text_delta="", finish_reason="stop")
        assert chunk.finish_reason == "stop"

    def test_tool_call_delta(self) -> None:
        tc = LLMToolCall(id="t1", name="search", arguments={})
        chunk = LLMChunk(tool_call_delta=tc)
        assert chunk.tool_call_delta == tc


# ---------------------------------------------------------------------------
# LLMProviderError
# ---------------------------------------------------------------------------


class TestLLMProviderError:
    """Tests for the LLMProviderError exception class."""

    def test_is_runtime_error_subclass(self) -> None:
        assert issubclass(LLMProviderError, RuntimeError)

    def test_can_be_raised_and_caught(self) -> None:
        with pytest.raises(LLMProviderError, match="something went wrong"):
            raise LLMProviderError("something went wrong")

    def test_caught_as_runtime_error(self) -> None:
        with pytest.raises(RuntimeError):
            raise LLMProviderError("also a runtime error")

    def test_preserves_cause(self) -> None:
        """Exception chaining works as expected."""
        original = ValueError("original cause")
        try:
            raise LLMProviderError("wrapped") from original
        except LLMProviderError as exc:
            assert exc.__cause__ is original
