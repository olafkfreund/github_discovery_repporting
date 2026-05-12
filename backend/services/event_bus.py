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
from uuid import UUID

logger = logging.getLogger(__name__)


class EventBus:
    """Per-AgentRun event queue registry."""

    def __init__(self) -> None:
        self._queues: dict[UUID, asyncio.Queue] = {}

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

    def cleanup(self, run_id: UUID) -> None:
        """Remove the queue for *run_id*.

        Called by the runner when the run reaches a terminal state.  Any
        pending items in the buffer are silently discarded; issue #27 will
        add subscriber ref-counting to guarantee delivery before cleanup.

        Args:
            run_id: UUID of the agent run whose queue should be removed.
        """
        discarded = self._queues.pop(run_id, None)
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
