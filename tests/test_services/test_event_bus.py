from __future__ import annotations

"""Unit tests for the EventBus in backend/services/event_bus.py (issue #27).

Tests cover the subscriber ref-counting, asynccontextmanager subscribe(),
publish with zero subscribers, and cleanup.
"""

import uuid

import pytest

from backend.services.event_bus import EventBus


@pytest.fixture
def bus() -> EventBus:
    """Return a fresh EventBus instance per test."""
    return EventBus()


# ---------------------------------------------------------------------------
# subscribe — ref-counting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subscribe_increments_count(bus: EventBus) -> None:
    """Entering the subscribe context increments the subscriber count."""
    run_id = uuid.uuid4()
    assert bus.subscriber_count(run_id) == 0

    async with bus.subscribe(run_id):
        assert bus.subscriber_count(run_id) == 1


@pytest.mark.asyncio
async def test_subscribe_decrements_on_exit(bus: EventBus) -> None:
    """Exiting the subscribe context decrements the subscriber count back to 0."""
    run_id = uuid.uuid4()

    async with bus.subscribe(run_id):
        pass  # enter and exit

    assert bus.subscriber_count(run_id) == 0


@pytest.mark.asyncio
async def test_two_subscribers_same_run(bus: EventBus) -> None:
    """Two concurrent subscribers share the same queue and ref-count adds up."""
    run_id = uuid.uuid4()

    async with bus.subscribe(run_id) as q1:
        async with bus.subscribe(run_id) as q2:
            assert bus.subscriber_count(run_id) == 2  # noqa: PLR2004
            # Both context managers must return the same queue object.
            assert q1 is q2

        # After inner exit, count drops to 1.
        assert bus.subscriber_count(run_id) == 1

    # After outer exit, count drops to 0.
    assert bus.subscriber_count(run_id) == 0


# ---------------------------------------------------------------------------
# publish with zero subscribers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_no_subscriber(bus: EventBus) -> None:
    """publish() enqueues the event even when no subscriber is attached."""
    run_id = uuid.uuid4()
    event = {"step_index": 0, "step_type": "llm_call"}

    # No subscriber present — should not raise.
    await bus.publish(run_id, event)

    # Retrieve via get_queue to confirm the item is buffered.
    q = bus.get_queue(run_id)
    assert not q.empty()
    received = q.get_nowait()
    assert received == event


@pytest.mark.asyncio
async def test_publish_delivers_to_subscriber(bus: EventBus) -> None:
    """Events published during a subscribe context are receivable from the queue."""
    run_id = uuid.uuid4()
    events_in = [{"step_index": i} for i in range(3)]

    async with bus.subscribe(run_id) as queue:
        for ev in events_in:
            await bus.publish(run_id, ev)

        received: list[dict] = []
        while not queue.empty():
            received.append(queue.get_nowait())

    assert received == events_in


# ---------------------------------------------------------------------------
# cleanup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cleanup_removes_queue_and_count(bus: EventBus) -> None:
    """cleanup() removes the queue entry and the subscriber count entry."""
    run_id = uuid.uuid4()

    # Create queue by publishing.
    await bus.publish(run_id, {"step_index": 0})
    assert run_id in bus._queues  # noqa: SLF001

    bus.cleanup(run_id)
    assert run_id not in bus._queues  # noqa: SLF001
    assert bus.subscriber_count(run_id) == 0


@pytest.mark.asyncio
async def test_cleanup_idempotent(bus: EventBus) -> None:
    """cleanup() on an unknown run_id does not raise."""
    bus.cleanup(uuid.uuid4())  # must not raise KeyError


# ---------------------------------------------------------------------------
# subscriber_count edge cases
# ---------------------------------------------------------------------------


def test_subscriber_count_unknown_run_returns_zero(bus: EventBus) -> None:
    """subscriber_count returns 0 for a run_id that has never been registered."""
    assert bus.subscriber_count(uuid.uuid4()) == 0
