"""Concurrency limiters for background tasks.

Module-level semaphores are created lazily on first access and shared for the
full application lifetime.  Keeping them at module scope means every call to
:func:`get_scan_semaphore` or :func:`get_report_semaphore` returns the *same*
:class:`asyncio.Semaphore` instance, so the limit is enforced across all
concurrent callers regardless of where in the codebase the helper is invoked.

The semaphores are intentionally *not* created at import time because
:class:`asyncio.Semaphore` must be created inside a running event loop (a
restriction that was relaxed in Python 3.10 but the lazy pattern keeps the
module safe across all supported versions and avoids subtle issues when
importing from sync test fixtures).
"""

from __future__ import annotations

import asyncio

from backend.config import settings

# Module-level semaphores — shared across the application lifetime.
_scan_semaphore: asyncio.Semaphore | None = None
_report_semaphore: asyncio.Semaphore | None = None
_agent_semaphore: asyncio.Semaphore | None = None


def get_scan_semaphore() -> asyncio.Semaphore:
    """Return the shared scan concurrency semaphore, creating it if needed.

    The semaphore allows at most :attr:`~backend.config.Settings.MAX_CONCURRENT_SCANS`
    scans to run simultaneously.  Additional scans will be queued and will
    start as soon as a slot becomes available — they are never rejected.

    Returns:
        The application-wide :class:`asyncio.Semaphore` for scan tasks.
    """
    global _scan_semaphore
    if _scan_semaphore is None:
        _scan_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_SCANS)
    return _scan_semaphore


def get_report_semaphore() -> asyncio.Semaphore:
    """Return the shared report concurrency semaphore, creating it if needed.

    The semaphore allows at most :attr:`~backend.config.Settings.MAX_CONCURRENT_REPORTS`
    report generation jobs to run simultaneously.  Additional jobs queue and
    start as soon as a slot becomes available — they are never rejected.

    Returns:
        The application-wide :class:`asyncio.Semaphore` for report tasks.
    """
    global _report_semaphore
    if _report_semaphore is None:
        _report_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_REPORTS)
    return _report_semaphore


def get_agent_semaphore() -> asyncio.Semaphore:
    """Return the shared agent-run concurrency semaphore, creating it if needed.

    Sized by :attr:`~backend.config.Settings.MAX_CONCURRENT_AGENT_RUNS`
    (default 2). Excess agent runs queue inside ``async with`` rather than
    being rejected.

    Returns:
        The application-wide :class:`asyncio.Semaphore` for agent-run tasks.
    """
    global _agent_semaphore
    if _agent_semaphore is None:
        _agent_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_AGENT_RUNS)
    return _agent_semaphore


def reset_semaphores() -> None:
    """Reset all semaphores to ``None`` so they are recreated on next access.

    Intended for use in tests only — resetting between test runs prevents a
    semaphore created in one test from carrying its internal counter state
    (and its event-loop association) into the next test.
    """
    global _scan_semaphore, _report_semaphore, _agent_semaphore
    _scan_semaphore = None
    _report_semaphore = None
    _agent_semaphore = None
