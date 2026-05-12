from __future__ import annotations

"""In-process pub/sub for AgentRun events.

A queue is lazily created per agent_run_id. Subscribers (SSE handlers in
issue #27) drain the queue; publishers (the runner's event_sink) push.

Queue lifecycle: created on first publish OR subscribe; cleaned up when
the run reaches a terminal state and the last subscriber disconnects.

This module ships in #26 as a minimal stub; issue #27 expands the
subscriber side with proper ref-counting + asynccontextmanager support.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

logger = logging.getLogger(__name__)


class EventBus:
    """Per-AgentRun event queue registry with subscriber ref-counting."""

    def __init__(self) -> None:
        self._queues: dict[UUID, asyncio.Queue] = {}
        self._subscriber_counts: dict[UUID, int] = {}

    def get_queue(self, run_id: UUID) -> asyncio.Queue:
        """Return (creating if needed) the queue for *run_id*. Buffer size 1000."""
        q = self._queues.get(run_id)
        if q is None:
            q = asyncio.Queue(maxsize=1000)
            self._queues[run_id] = q
        return q

    async def publish(self, run_id: UUID, event: dict) -> None:
        """Put *event* on the queue for *run_id*.

        If the buffer is full this coroutine blocks until a slot is consumed
        (backpressure).  Callers in the event_sink should ``await`` this so
        that the runner cannot outpace the subscriber.

        Args:
            run_id: UUID of the agent run that produced *event*.
            event: Arbitrary dict describing the event (serialisable).
        """
        queue = self.get_queue(run_id)
        await queue.put(event)

    @asynccontextmanager
    async def subscribe(self, run_id: UUID) -> AsyncIterator[asyncio.Queue]:
        """Acquire the queue for *run_id* and bump the subscriber ref count.

        On exit the count is decremented.  Cleanup of the queue is NOT
        automatic here — the runner is responsible for calling
        :meth:`cleanup` when the run reaches a terminal state, to avoid
        discarding events that arrive after the last subscriber exits.

        Args:
            run_id: UUID of the agent run to subscribe to.

        Yields:
            The :class:`asyncio.Queue` for *run_id*.
        """
        queue = self.get_queue(run_id)
        self._subscriber_counts[run_id] = self._subscriber_counts.get(run_id, 0) + 1
        try:
            yield queue
        finally:
            self._subscriber_counts[run_id] = max(0, self._subscriber_counts.get(run_id, 1) - 1)

    def subscriber_count(self, run_id: UUID) -> int:
        """Return the number of active subscribers for *run_id*.

        Args:
            run_id: UUID of the agent run to query.

        Returns:
            Integer subscriber count; 0 if *run_id* has no active subscribers.
        """
        return self._subscriber_counts.get(run_id, 0)

    def cleanup(self, run_id: UUID) -> None:
        """Remove the queue for *run_id*.

        Called by the runner when the run reaches a terminal state.  Any
        pending items in the buffer are silently discarded.

        Args:
            run_id: UUID of the agent run whose queue should be removed.
        """
        discarded = self._queues.pop(run_id, None)
        self._subscriber_counts.pop(run_id, None)
        if discarded is not None and not discarded.empty():
            logger.debug(
                "EventBus.cleanup: discarded %d unread events for run %s",
                discarded.qsize(),
                run_id,
            )


_event_bus = EventBus()


def get_event_bus() -> EventBus:
    """Return the application-wide :class:`EventBus` singleton."""
    return _event_bus


class CancelEventRegistry:
    """Per-AgentRun cancellation flags.

    The runner creates its own :class:`asyncio.Event` via
    :meth:`get_or_create` before starting the loop.  The cancel endpoint
    (issue #27 router) calls :meth:`trigger` to request a graceful stop.
    """

    def __init__(self) -> None:
        self._events: dict[UUID, asyncio.Event] = {}

    def get_or_create(self, run_id: UUID) -> asyncio.Event:
        """Return (creating if needed) the cancellation event for *run_id*.

        Args:
            run_id: UUID of the agent run.

        Returns:
            The :class:`asyncio.Event` that the loop polls on each iteration.
        """
        if run_id not in self._events:
            self._events[run_id] = asyncio.Event()
        return self._events[run_id]

    def trigger(self, run_id: UUID) -> bool:
        """Set the cancellation event for *run_id*, if it exists.

        Args:
            run_id: UUID of the run to cancel.

        Returns:
            ``True`` if the event was found and set.  ``False`` if the run
            is not registered (already in a terminal state or never started).
        """
        event = self._events.get(run_id)
        if event is None:
            return False
        event.set()
        return True

    def cleanup(self, run_id: UUID) -> None:
        """Remove the cancellation event for *run_id*.

        Args:
            run_id: UUID of the run to deregister.
        """
        self._events.pop(run_id, None)


_cancel_registry = CancelEventRegistry()


def get_cancel_registry() -> CancelEventRegistry:
    """Return the application-wide :class:`CancelEventRegistry` singleton."""
    return _cancel_registry
