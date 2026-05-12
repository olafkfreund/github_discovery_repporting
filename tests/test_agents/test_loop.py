from __future__ import annotations

"""Unit tests for backend.agents.loop (issue #24).

All LLM calls are intercepted by FakeLLM, which replays scripted LLMResponse
objects.  PlatformProvider is a MagicMock.  FakeTool allows assertions on
argument passing and call counts.

Run with::

    uv run python -m pytest tests/test_agents/test_loop.py -v
"""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import MagicMock, patch

import pytest

from backend.agents.loop import (
    LoopBudgetExceeded,
    LoopCancelled,
    LoopCaps,
    LoopEvent,
    run_loop,
)
from backend.agents.tools.base import ToolError, ToolResult, WorkspaceContext
from backend.agents.workspace import WorkspaceInfo
from backend.llm.base import LLMMessage, LLMResponse, LLMToolCall
from backend.models.enums import AgentStepType

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


@dataclass
class FakeLLM:
    """Replays scripted LLMResponses sequentially.

    Each call to :meth:`chat` pops the next response from *responses*.
    An ``IndexError`` is propagated when the list is exhausted, which
    helps diagnose tests that allow more LLM calls than expected.
    """

    responses: list[LLMResponse]
    _idx: int = field(default=0, init=False)

    # Protocol flags required by type-checkers.
    provider_id: ClassVar[str] = "fake"
    supports_structured_output: ClassVar[bool] = True
    supports_tool_use: ClassVar[bool] = True

    async def chat(
        self,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 8192,
        temperature: float = 0.0,
        json_schema: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """Return the next scripted response."""
        idx = self._idx
        self._idx += 1
        return self.responses[idx]

    async def stream_chat(self, *args: Any, **kwargs: Any) -> None:
        """Not used by the loop."""
        raise NotImplementedError


@dataclass
class FakeTool:
    """A configurable no-op tool for testing.

    Attributes:
        tool_name: Tool identifier exposed via the ``name`` class var.
        output: Text returned by a successful invocation.
        ok: Whether the result is flagged as successful.
        raise_error: When set, raises :class:`ToolError` instead of returning.
        calls: Records the ``args`` passed to each invocation.
    """

    tool_name: str = "fake_tool"
    output: str = "tool output"
    ok: bool = True
    raise_error: str | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    # Tool Protocol requires these class vars; we emulate them as instance attrs
    # because @dataclass does not support ClassVar fields with defaults easily.
    @property
    def name(self) -> str:  # type: ignore[override]
        """Return the tool name."""
        return self.tool_name

    description: ClassVar[str] = "A fake tool for testing"
    arguments_schema: ClassVar[dict[str, Any]] = {"type": "object", "properties": {}}

    async def __call__(
        self,
        args: dict[str, Any],
        *,
        workspace: WorkspaceContext,
        provider: Any,
    ) -> ToolResult:
        """Record the call and return or raise as configured."""
        self.calls.append(dict(args))
        if self.raise_error is not None:
            raise ToolError(self.raise_error)
        return ToolResult(name=self.tool_name, ok=self.ok, output=self.output)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def make_workspace() -> WorkspaceInfo:
    """Return a minimal WorkspaceInfo for testing."""
    return WorkspaceInfo(
        path=Path("/tmp/fake-repo"),
        repo_external_id="owner/repo",
        branch="main",
        head_sha="a" * 40,
        bytes_on_disk=1024,
    )


def make_caps(**overrides: Any) -> LoopCaps:
    """Return LoopCaps with safe defaults overridden by *overrides*."""
    defaults = {
        "max_iterations": 10,
        "max_tokens_total": 1_000_000,
        "max_cost_usd": 100.0,
        "max_runtime_seconds": 300,
    }
    defaults.update(overrides)
    return LoopCaps(**defaults)


def make_tool_call(name: str = "fake_tool", args: dict[str, Any] | None = None) -> LLMToolCall:
    """Return an LLMToolCall with the given name and args."""
    return LLMToolCall(id="tc-1", name=name, arguments=args or {})


def text_response(text: str, tokens: int = 10, cost: float = 0.001) -> LLMResponse:
    """Return an LLMResponse with text and no tool calls."""
    return LLMResponse(
        text=text,
        tool_calls=[],
        input_tokens=tokens,
        output_tokens=tokens,
        cost_usd=cost,
    )


def tool_response(name: str = "fake_tool", args: dict[str, Any] | None = None) -> LLMResponse:
    """Return an LLMResponse requesting one tool call."""
    return LLMResponse(
        text="",
        tool_calls=[make_tool_call(name, args)],
        input_tokens=10,
        output_tokens=10,
        cost_usd=0.001,
    )


async def _make_sink() -> tuple[list[LoopEvent], Any]:
    """Return (events_list, async_sink_callable)."""
    events: list[LoopEvent] = []

    async def sink(event: LoopEvent) -> None:
        events.append(event)

    return events, sink


def _make_provider() -> MagicMock:
    """Return a MagicMock with PlatformProvider spec."""
    from backend.providers.base import PlatformProvider

    return MagicMock(spec=PlatformProvider)


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_no_tools() -> None:
    """LLM returns a text answer on the first call — no tools involved."""
    llm = FakeLLM(responses=[text_response("All done!")])
    events, sink = await _make_sink()
    cancel = asyncio.Event()

    result = await run_loop(
        llm=llm,
        workspace=make_workspace(),
        provider=_make_provider(),
        system_prompt="sys",
        user_prompt="user",
        tools={},
        caps=make_caps(),
        event_sink=sink,
        cancel_event=cancel,
        prompt_hash="abc",
    )

    assert result.success is True
    assert result.final_message == "All done!"
    assert result.iterations == 1
    assert result.error is None

    # Exactly 2 events: llm_call(0) + final(1).
    assert len(events) == 2
    assert events[0].step_type == AgentStepType.llm_call
    assert events[0].step_index == 0
    assert events[0].prompt_hash == "abc"
    assert events[1].step_type == AgentStepType.final
    assert events[1].step_index == 1
    assert events[1].status == "ok"


@pytest.mark.asyncio
async def test_tool_call_then_final_answer() -> None:
    """LLM calls a tool on iteration 1 and gives a final answer on iteration 2."""
    fake_tool = FakeTool(tool_name="fake_tool", output="tool result")
    tools = {"fake_tool": fake_tool}  # type: ignore[dict-item]

    llm = FakeLLM(
        responses=[
            tool_response("fake_tool", {"arg": "value"}),
            text_response("Final answer."),
        ]
    )
    events, sink = await _make_sink()
    cancel = asyncio.Event()

    result = await run_loop(
        llm=llm,
        workspace=make_workspace(),
        provider=_make_provider(),
        system_prompt="sys",
        user_prompt="user",
        tools=tools,
        caps=make_caps(),
        event_sink=sink,
        cancel_event=cancel,
        prompt_hash="xyz",
    )

    assert result.success is True
    assert result.iterations == 2
    assert result.final_message == "Final answer."

    # 5 events: llm_call(0), tool_call(1), tool_result(2), llm_call(3), final(4).
    assert len(events) == 5
    types = [e.step_type for e in events]
    assert types == [
        AgentStepType.llm_call,
        AgentStepType.tool_call,
        AgentStepType.tool_result,
        AgentStepType.llm_call,
        AgentStepType.final,
    ]

    # Tool was invoked exactly once with the expected args.
    assert len(fake_tool.calls) == 1
    assert fake_tool.calls[0] == {"arg": "value"}

    # The tool_result event carries the tool output.
    tool_result_event = events[2]
    assert tool_result_event.tool_result == "tool result"
    assert tool_result_event.status == "ok"

    # The second llm_call must NOT carry the prompt_hash.
    assert events[3].prompt_hash is None


@pytest.mark.asyncio
async def test_disallowed_tool_does_not_terminate_loop() -> None:
    """A tool not in the allow-list should produce an error result, not a crash."""
    llm = FakeLLM(
        responses=[
            tool_response("dangerous_tool"),
            text_response("Recovered."),
        ]
    )
    events, sink = await _make_sink()
    cancel = asyncio.Event()

    result = await run_loop(
        llm=llm,
        workspace=make_workspace(),
        provider=_make_provider(),
        system_prompt="sys",
        user_prompt="user",
        tools={},  # empty allow-list
        caps=make_caps(),
        event_sink=sink,
        cancel_event=cancel,
    )

    assert result.success is True
    assert result.final_message == "Recovered."

    # Find the tool_result event.
    tr_event = next(e for e in events if e.step_type == AgentStepType.tool_result)
    assert tr_event.status == "error"
    assert tr_event.tool_result is not None
    assert "dangerous_tool" in tr_event.tool_result
    assert "allow-list" in tr_event.tool_result


# ---------------------------------------------------------------------------
# Cap / budget tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_iteration_cap() -> None:
    """When the LLM always returns tool_calls the iteration cap fires."""
    fake_tool = FakeTool(tool_name="fake_tool")
    # Provide many responses so we never hit an IndexError.
    responses = [tool_response("fake_tool")] * 20
    llm = FakeLLM(responses=responses)
    events, sink = await _make_sink()
    cancel = asyncio.Event()

    result = await run_loop(
        llm=llm,
        workspace=make_workspace(),
        provider=_make_provider(),
        system_prompt="sys",
        user_prompt="user",
        tools={"fake_tool": fake_tool},  # type: ignore[dict-item]
        caps=make_caps(max_iterations=3),
        event_sink=sink,
        cancel_event=cancel,
    )

    assert result.success is False
    assert result.error == "iteration_cap"
    assert result.iterations == 3

    # Terminal event is final with status="error".
    final = events[-1]
    assert final.step_type == AgentStepType.final
    assert final.status == "error"


@pytest.mark.asyncio
async def test_token_cap_raises() -> None:
    """Exceeding the token budget raises LoopBudgetExceeded('tokens')."""
    llm = FakeLLM(
        responses=[
            LLMResponse(text="", tool_calls=[], input_tokens=400, output_tokens=200, cost_usd=0.001)
        ]
    )
    events, sink = await _make_sink()
    cancel = asyncio.Event()

    with pytest.raises(LoopBudgetExceeded) as exc_info:
        await run_loop(
            llm=llm,
            workspace=make_workspace(),
            provider=_make_provider(),
            system_prompt="sys",
            user_prompt="user",
            tools={},
            caps=make_caps(max_tokens_total=500),  # 400+200=600 > 500
            event_sink=sink,
            cancel_event=cancel,
        )

    assert exc_info.value.reason == "tokens"
    # Terminal event must be emitted BEFORE the raise.
    assert any(e.step_type == AgentStepType.final and e.status == "budget" for e in events)
    # llm_call event was emitted too.
    assert any(e.step_type == AgentStepType.llm_call for e in events)


@pytest.mark.asyncio
async def test_cost_cap_raises() -> None:
    """Exceeding the cost budget raises LoopBudgetExceeded('cost')."""
    llm = FakeLLM(
        responses=[
            LLMResponse(text="", tool_calls=[], input_tokens=1, output_tokens=1, cost_usd=10.0)
        ]
    )
    events, sink = await _make_sink()
    cancel = asyncio.Event()

    with pytest.raises(LoopBudgetExceeded) as exc_info:
        await run_loop(
            llm=llm,
            workspace=make_workspace(),
            provider=_make_provider(),
            system_prompt="sys",
            user_prompt="user",
            tools={},
            caps=make_caps(max_cost_usd=5.0),
            event_sink=sink,
            cancel_event=cancel,
        )

    assert exc_info.value.reason == "cost"
    assert any(e.step_type == AgentStepType.final and e.status == "budget" for e in events)


@pytest.mark.asyncio
async def test_runtime_cap_raises() -> None:
    """Exceeding the wall-clock limit raises LoopBudgetExceeded('runtime').

    We patch time.monotonic so that the second iteration sees elapsed > cap.
    """
    # Iteration 1: succeeds; iteration 2: runtime check fires before llm.chat.
    llm = FakeLLM(
        responses=[
            tool_response("fake_tool"),  # iteration 1
            text_response("Done."),  # iteration 2 (should not be reached)
        ]
    )
    fake_tool = FakeTool(tool_name="fake_tool")
    events, sink = await _make_sink()
    cancel = asyncio.Event()

    call_count = 0

    def fake_monotonic() -> float:
        nonlocal call_count
        call_count += 1
        # First few calls return small elapsed; after iteration 1's llm call
        # advance the clock past the cap.
        if call_count <= 3:
            return 0.0
        return 400.0  # 400s > max_runtime_seconds=300

    with patch("backend.agents.loop.time.monotonic", side_effect=fake_monotonic):
        with pytest.raises(LoopBudgetExceeded) as exc_info:
            await run_loop(
                llm=llm,
                workspace=make_workspace(),
                provider=_make_provider(),
                system_prompt="sys",
                user_prompt="user",
                tools={"fake_tool": fake_tool},  # type: ignore[dict-item]
                caps=make_caps(max_runtime_seconds=300),
                event_sink=sink,
                cancel_event=cancel,
            )

    assert exc_info.value.reason == "runtime"
    # The terminal budget event must have been emitted.
    assert any(e.step_type == AgentStepType.final and e.status == "budget" for e in events)
    # The second llm.chat should NOT have been called.
    assert llm._idx == 1


# ---------------------------------------------------------------------------
# Cancellation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancellation_before_first_call() -> None:
    """Setting cancel_event before the loop starts raises LoopCancelled."""
    llm = FakeLLM(responses=[text_response("Never reached.")])
    events, sink = await _make_sink()
    cancel = asyncio.Event()
    cancel.set()  # pre-cancelled

    with pytest.raises(LoopCancelled):
        await run_loop(
            llm=llm,
            workspace=make_workspace(),
            provider=_make_provider(),
            system_prompt="sys",
            user_prompt="user",
            tools={},
            caps=make_caps(),
            event_sink=sink,
            cancel_event=cancel,
        )

    # Terminal event emitted with status="cancelled" before raise.
    assert any(e.step_type == AgentStepType.final and e.status == "cancelled" for e in events)
    # LLM was never called.
    assert llm._idx == 0


@pytest.mark.asyncio
async def test_cancellation_mid_loop() -> None:
    """cancel_event set after iteration 1 fires at the boundary of iteration 2."""

    cancel = asyncio.Event()

    class CancellingFakeLLM(FakeLLM):
        """Sets cancel after the first response is returned."""

        async def chat(self, *args: Any, **kwargs: Any) -> LLMResponse:
            resp = await super().chat(*args, **kwargs)
            if self._idx == 1:
                # After returning the first response, signal cancellation.
                cancel.set()
            return resp

    llm = CancellingFakeLLM(
        responses=[
            tool_response("fake_tool"),  # iteration 1
            text_response("Not reached."),  # would be iteration 2
        ]
    )
    fake_tool = FakeTool(tool_name="fake_tool")
    events, sink = await _make_sink()

    with pytest.raises(LoopCancelled):
        await run_loop(
            llm=llm,
            workspace=make_workspace(),
            provider=_make_provider(),
            system_prompt="sys",
            user_prompt="user",
            tools={"fake_tool": fake_tool},  # type: ignore[dict-item]
            caps=make_caps(),
            event_sink=sink,
            cancel_event=cancel,
        )

    # Only 1 LLM call should have been made.
    assert llm._idx == 1
    assert any(e.step_type == AgentStepType.final and e.status == "cancelled" for e in events)


# ---------------------------------------------------------------------------
# Step-index monotonic test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_step_index_monotonic_no_gaps() -> None:
    """step_index across all events must form a contiguous 0-based sequence."""
    fake_tool = FakeTool(tool_name="my_tool", output="result")
    tools = {"my_tool": fake_tool}  # type: ignore[dict-item]
    llm = FakeLLM(
        responses=[
            tool_response("my_tool"),
            text_response("Done!"),
        ]
    )
    events, sink = await _make_sink()
    cancel = asyncio.Event()

    await run_loop(
        llm=llm,
        workspace=make_workspace(),
        provider=_make_provider(),
        system_prompt="sys",
        user_prompt="user",
        tools=tools,
        caps=make_caps(),
        event_sink=sink,
        cancel_event=cancel,
    )

    indices = [e.step_index for e in events]
    assert indices == list(range(len(events))), f"Non-monotonic: {indices}"


# ---------------------------------------------------------------------------
# Empty / error response tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_response_returns_failure() -> None:
    """An LLM response with no text and no tool_calls → error='empty_response'."""
    llm = FakeLLM(responses=[LLMResponse(text="", tool_calls=[], input_tokens=5, output_tokens=0)])
    events, sink = await _make_sink()
    cancel = asyncio.Event()

    result = await run_loop(
        llm=llm,
        workspace=make_workspace(),
        provider=_make_provider(),
        system_prompt="sys",
        user_prompt="user",
        tools={},
        caps=make_caps(),
        event_sink=sink,
        cancel_event=cancel,
    )

    assert result.success is False
    assert result.error == "empty_response"
    assert result.iterations == 1
    assert result.final_message == ""

    final = events[-1]
    assert final.step_type == AgentStepType.final
    assert final.status == "error"


# ---------------------------------------------------------------------------
# Prompt hash attachment test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prompt_hash_only_on_first_llm_call() -> None:
    """prompt_hash is set only on the first llm_call event."""
    fake_tool = FakeTool(tool_name="t")
    tools = {"t": fake_tool}  # type: ignore[dict-item]
    llm = FakeLLM(
        responses=[
            tool_response("t"),
            text_response("Done!"),
        ]
    )
    events, sink = await _make_sink()
    cancel = asyncio.Event()

    await run_loop(
        llm=llm,
        workspace=make_workspace(),
        provider=_make_provider(),
        system_prompt="sys",
        user_prompt="user",
        tools=tools,
        caps=make_caps(),
        event_sink=sink,
        cancel_event=cancel,
        prompt_hash="myhash",
    )

    llm_call_events = [e for e in events if e.step_type == AgentStepType.llm_call]
    assert len(llm_call_events) == 2
    assert llm_call_events[0].prompt_hash == "myhash"
    assert llm_call_events[1].prompt_hash is None


# ---------------------------------------------------------------------------
# ToolError recovery test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_error_does_not_propagate() -> None:
    """ToolError from a tool is caught; loop continues with status='error'."""
    boom_tool = FakeTool(tool_name="boom", raise_error="boom")
    tools = {"boom": boom_tool}  # type: ignore[dict-item]
    llm = FakeLLM(
        responses=[
            tool_response("boom"),
            text_response("Recovered."),
        ]
    )
    events, sink = await _make_sink()
    cancel = asyncio.Event()

    result = await run_loop(
        llm=llm,
        workspace=make_workspace(),
        provider=_make_provider(),
        system_prompt="sys",
        user_prompt="user",
        tools=tools,
        caps=make_caps(),
        event_sink=sink,
        cancel_event=cancel,
    )

    assert result.success is True
    assert result.final_message == "Recovered."

    tr_event = next(e for e in events if e.step_type == AgentStepType.tool_result)
    assert tr_event.status == "error"
    assert tr_event.tool_result is not None
    assert "ToolError: boom" in tr_event.tool_result


# ---------------------------------------------------------------------------
# Multiple tool calls in one response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiple_tool_calls_in_one_response() -> None:
    """Two tool calls in a single LLM response are dispatched in order."""
    tool_a = FakeTool(tool_name="tool_a", output="output_a")
    tool_b = FakeTool(tool_name="tool_b", output="output_b")
    tools = {
        "tool_a": tool_a,  # type: ignore[dict-item]
        "tool_b": tool_b,  # type: ignore[dict-item]
    }

    multi_response = LLMResponse(
        text="",
        tool_calls=[
            LLMToolCall(id="tc-1", name="tool_a", arguments={"x": 1}),
            LLMToolCall(id="tc-2", name="tool_b", arguments={"y": 2}),
        ],
        input_tokens=10,
        output_tokens=10,
        cost_usd=0.001,
    )
    llm = FakeLLM(responses=[multi_response, text_response("Done!")])
    events, sink = await _make_sink()
    cancel = asyncio.Event()

    result = await run_loop(
        llm=llm,
        workspace=make_workspace(),
        provider=_make_provider(),
        system_prompt="sys",
        user_prompt="user",
        tools=tools,
        caps=make_caps(),
        event_sink=sink,
        cancel_event=cancel,
    )

    assert result.success is True

    # Both tools called once each.
    assert len(tool_a.calls) == 1
    assert tool_a.calls[0] == {"x": 1}
    assert len(tool_b.calls) == 1
    assert tool_b.calls[0] == {"y": 2}

    # tool_result events carry correct outputs.
    tr_events = [e for e in events if e.step_type == AgentStepType.tool_result]
    assert len(tr_events) == 2
    assert tr_events[0].tool_result == "output_a"
    assert tr_events[1].tool_result == "output_b"


# ---------------------------------------------------------------------------
# Accumulation totals test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_and_cost_accumulated_across_iterations() -> None:
    """Total tokens and cost in LoopResult are summed across all LLM calls."""
    fake_tool = FakeTool(tool_name="t")
    tools = {"t": fake_tool}  # type: ignore[dict-item]

    llm = FakeLLM(
        responses=[
            LLMResponse(
                text="",
                tool_calls=[LLMToolCall(id="1", name="t", arguments={})],
                input_tokens=100,
                output_tokens=50,
                cost_usd=0.5,
            ),
            LLMResponse(
                text="Final.",
                tool_calls=[],
                input_tokens=200,
                output_tokens=80,
                cost_usd=0.8,
            ),
        ]
    )
    events, sink = await _make_sink()
    cancel = asyncio.Event()

    result = await run_loop(
        llm=llm,
        workspace=make_workspace(),
        provider=_make_provider(),
        system_prompt="sys",
        user_prompt="user",
        tools=tools,
        caps=make_caps(),
        event_sink=sink,
        cancel_event=cancel,
    )

    assert result.total_input_tokens == 300
    assert result.total_output_tokens == 130
    assert abs(result.total_cost_usd - 1.3) < 1e-9


# ---------------------------------------------------------------------------
# Whitespace-only response is treated as empty
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_whitespace_only_response_treated_as_empty() -> None:
    """An LLM response containing only whitespace is not a valid final answer."""
    llm = FakeLLM(
        responses=[LLMResponse(text="   \n\t  ", tool_calls=[], input_tokens=1, output_tokens=1)]
    )
    events, sink = await _make_sink()
    cancel = asyncio.Event()

    result = await run_loop(
        llm=llm,
        workspace=make_workspace(),
        provider=_make_provider(),
        system_prompt="sys",
        user_prompt="user",
        tools={},
        caps=make_caps(),
        event_sink=sink,
        cancel_event=cancel,
    )

    assert result.success is False
    assert result.error == "empty_response"


# ---------------------------------------------------------------------------
# Budget events emitted before exception
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_cap_events_order() -> None:
    """When tokens are exceeded, llm_call event appears before budget final event."""
    llm = FakeLLM(
        responses=[
            LLMResponse(text="", tool_calls=[], input_tokens=300, output_tokens=300, cost_usd=0.0)
        ]
    )
    events, sink = await _make_sink()
    cancel = asyncio.Event()

    with pytest.raises(LoopBudgetExceeded):
        await run_loop(
            llm=llm,
            workspace=make_workspace(),
            provider=_make_provider(),
            system_prompt="sys",
            user_prompt="user",
            tools={},
            caps=make_caps(max_tokens_total=100),  # 600 > 100
            event_sink=sink,
            cancel_event=cancel,
        )

    # Order: llm_call first, then final(budget).
    assert events[0].step_type == AgentStepType.llm_call
    assert events[-1].step_type == AgentStepType.final
    assert events[-1].status == "budget"


# ---------------------------------------------------------------------------
# Tool result in conversation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_result_appended_to_conversation() -> None:
    """After a tool call the tool output appears as role='tool' in messages."""
    recorded_messages: list[list[LLMMessage]] = []

    class RecordingFakeLLM(FakeLLM):
        async def chat(self, messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
            recorded_messages.append(list(messages))
            return await super().chat(messages, **kwargs)

    fake_tool = FakeTool(tool_name="reader", output="file contents here")
    tools = {"reader": fake_tool}  # type: ignore[dict-item]
    llm = RecordingFakeLLM(
        responses=[
            tool_response("reader"),
            text_response("Done."),
        ]
    )
    events, sink = await _make_sink()
    cancel = asyncio.Event()

    await run_loop(
        llm=llm,
        workspace=make_workspace(),
        provider=_make_provider(),
        system_prompt="sys",
        user_prompt="user",
        tools=tools,
        caps=make_caps(),
        event_sink=sink,
        cancel_event=cancel,
    )

    # The second LLM call should have a role=tool message with the tool output.
    second_call_messages = recorded_messages[1]
    tool_messages = [m for m in second_call_messages if m.role == "tool"]
    assert len(tool_messages) == 1
    assert tool_messages[0].content == "file contents here"
