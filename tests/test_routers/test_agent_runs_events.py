from __future__ import annotations

"""Tests for POST /api/agent-runs/{id}/events (issue #47).

Covers:
  1. Happy path — valid HMAC + new step_index → 200, row persisted.
  2. Invalid HMAC signature → 401.
  3. Missing X-BPS-Signature header → 401.
  4. Malformed signature header (no sha256= prefix) → 401.
  5. Run not found → 404 (no HMAC processing).
  6. Idempotent retry — same (run_id, step_index) twice → both 200, one row.
  7. IntegrityError race — mock db.commit to raise IntegrityError, then
     _get_step finds the pre-existing row → 200 with that row.
  8. SSE publish — valid event reaches event_bus queue.
  9. Validation — step_index=-1 and input_tokens=-100 → 422.
  10. Invalid step_type → 422.
"""

import asyncio
import hashlib
import hmac
import json
import secrets
import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.agent_runs import AgentRun, AgentStep
from backend.models.customer import Customer, PlatformConnection
from backend.models.enums import (
    AgentRunStatus,
    AgentStepType,
    AuthType,
    LLMProviderEnum,
    Platform,
    ScanStatus,
)
from backend.models.llm import LLMConnection
from backend.models.scan import Scan
from backend.services.event_bus import get_event_bus
from backend.services.secrets_service import secrets_service

# ---------------------------------------------------------------------------
# Signing helper
# ---------------------------------------------------------------------------

_ENDPOINT = "/api/agent-runs/{id}/events"


def _sign(body: bytes, secret: bytes) -> str:
    """Return ``sha256=<hex_digest>`` for *body* signed with *secret*."""
    return "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Factories (self-contained; no import from test_agent_runs to avoid coupling)
# ---------------------------------------------------------------------------


async def _make_customer(db: AsyncSession) -> Customer:
    uid = uuid.uuid4().hex[:8]
    customer = Customer(name=f"EventsCorp {uid}", slug=f"eventscorp-{uid}")
    db.add(customer)
    await db.flush()
    return customer


async def _make_connection(db: AsyncSession, customer_id: uuid.UUID) -> PlatformConnection:
    conn = PlatformConnection(
        customer_id=customer_id,
        platform=Platform.github,
        display_name="Test GitHub",
        auth_type=AuthType.token,
        credentials_encrypted=secrets_service.encrypt(json.dumps({"token": "ghp_test"})),
        org_or_group="test-org",
        is_active=True,
    )
    db.add(conn)
    await db.flush()
    return conn


async def _make_llm(db: AsyncSession, customer_id: uuid.UUID) -> LLMConnection:
    llm = LLMConnection(
        customer_id=customer_id,
        name=f"llm-{uuid.uuid4().hex[:6]}",
        provider=LLMProviderEnum.anthropic,
        model="claude-sonnet-4-6",
        is_default=True,
    )
    db.add(llm)
    await db.flush()
    return llm


async def _make_scan(
    db: AsyncSession,
    customer_id: uuid.UUID,
    connection_id: uuid.UUID,
) -> Scan:
    scan = Scan(
        customer_id=customer_id,
        connection_id=connection_id,
        status=ScanStatus.completed,
    )
    db.add(scan)
    await db.flush()
    return scan


async def _make_run(
    db: AsyncSession,
    scan_id: uuid.UUID,
    llm_id: uuid.UUID,
    *,
    cb_secret: bytes | None = None,
) -> AgentRun:
    """Create an AgentRun with a known callback_secret for HMAC tests."""
    secret = cb_secret if cb_secret is not None else secrets.token_bytes(32)
    run = AgentRun(
        scan_id=scan_id,
        llm_connection_id=llm_id,
        provider="anthropic",
        model="claude-sonnet-4-6",
        status=AgentRunStatus.running,
        runtime_mode="ci",
        callback_secret=secret,
    )
    db.add(run)
    await db.flush()
    return run


async def _full_setup(db: AsyncSession) -> tuple[AgentRun, bytes]:
    """Return a committed AgentRun and its callback_secret."""
    secret = secrets.token_bytes(32)
    customer = await _make_customer(db)
    conn = await _make_connection(db, customer.id)
    llm = await _make_llm(db, customer.id)
    scan = await _make_scan(db, customer.id, conn.id)
    run = await _make_run(db, scan.id, llm.id, cb_secret=secret)
    await db.commit()
    return run, secret


def _body(step_index: int = 0, step_type: str = "llm_call", **extra) -> bytes:
    """Build a minimal valid JSON payload body."""
    data: dict = {"step_index": step_index, "step_type": step_type, **extra}
    return json.dumps(data).encode()


# ---------------------------------------------------------------------------
# 1. Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_receive_event_happy_path(db_session: AsyncSession, client: AsyncClient) -> None:
    """Valid HMAC + new step_index → 200 with the persisted AgentStep."""
    run, secret = await _full_setup(db_session)
    body = _body(step_index=0, step_type="llm_call", input_tokens=50, output_tokens=100)
    sig = _sign(body, secret)

    resp = await client.post(
        _ENDPOINT.format(id=run.id),
        content=body,
        headers={"X-BPS-Signature": sig, "Content-Type": "application/json"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["step_index"] == 0
    assert data["step_type"] == "llm_call"
    assert data["input_tokens"] == 50
    assert data["output_tokens"] == 100
    assert data["agent_run_id"] == str(run.id)

    # Verify the row appears in the detail endpoint.
    detail = await client.get(f"/api/agent-runs/{run.id}")
    assert detail.status_code == 200
    steps = detail.json()["steps"]
    assert len(steps) == 1
    assert steps[0]["id"] == data["id"]


# ---------------------------------------------------------------------------
# 2. Invalid signature
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_receive_event_invalid_signature(
    db_session: AsyncSession, client: AsyncClient
) -> None:
    """Wrong HMAC digest → 401."""
    run, secret = await _full_setup(db_session)
    body = _body(step_index=0)
    wrong_sig = _sign(body, secrets.token_bytes(32))  # different key

    resp = await client.post(
        _ENDPOINT.format(id=run.id),
        content=body,
        headers={"X-BPS-Signature": wrong_sig, "Content-Type": "application/json"},
    )

    assert resp.status_code == 401
    assert "signature" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 3. Missing X-BPS-Signature header
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_receive_event_missing_signature_header(
    db_session: AsyncSession, client: AsyncClient
) -> None:
    """Absent X-BPS-Signature header → 401."""
    run, _secret = await _full_setup(db_session)
    body = _body(step_index=0)

    resp = await client.post(
        _ENDPOINT.format(id=run.id),
        content=body,
        headers={"Content-Type": "application/json"},
    )

    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 4. Malformed signature header (no sha256= prefix)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_receive_event_malformed_signature_prefix(
    db_session: AsyncSession, client: AsyncClient
) -> None:
    """Header that lacks the 'sha256=' prefix → 401."""
    run, secret = await _full_setup(db_session)
    body = _body(step_index=0)
    # Provide the raw hex without the required prefix.
    bad_sig = hmac.new(secret, body, hashlib.sha256).hexdigest()

    resp = await client.post(
        _ENDPOINT.format(id=run.id),
        content=body,
        headers={"X-BPS-Signature": bad_sig, "Content-Type": "application/json"},
    )

    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 5. Run not found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_receive_event_run_not_found(db_session: AsyncSession, client: AsyncClient) -> None:
    """Unknown run UUID → 404; no HMAC processing should occur."""
    unknown_id = uuid.uuid4()
    body = _body(step_index=0)
    # Signature is irrelevant — the run lookup happens first.
    sig = "sha256=deadbeef"

    resp = await client.post(
        _ENDPOINT.format(id=unknown_id),
        content=body,
        headers={"X-BPS-Signature": sig, "Content-Type": "application/json"},
    )

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 6. Idempotent retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_receive_event_idempotent_retry(
    db_session: AsyncSession, client: AsyncClient
) -> None:
    """Same (run_id, step_index) posted twice → both 200, exactly one DB row."""
    run, secret = await _full_setup(db_session)
    body = _body(step_index=3, step_type="tool_call")
    sig = _sign(body, secret)
    headers = {"X-BPS-Signature": sig, "Content-Type": "application/json"}

    resp1 = await client.post(_ENDPOINT.format(id=run.id), content=body, headers=headers)
    resp2 = await client.post(_ENDPOINT.format(id=run.id), content=body, headers=headers)

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    # Both responses must reference the same row.
    assert resp1.json()["id"] == resp2.json()["id"]

    # Detail endpoint must show exactly one step with step_index=3.
    detail = await client.get(f"/api/agent-runs/{run.id}")
    steps = detail.json()["steps"]
    matching = [s for s in steps if s["step_index"] == 3]
    assert len(matching) == 1


# ---------------------------------------------------------------------------
# 7. IntegrityError race — mocked commit path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_receive_event_integrity_error_race(
    db_session: AsyncSession, client: AsyncClient
) -> None:
    """When db.commit raises IntegrityError the handler rolls back and re-reads."""
    run, secret = await _full_setup(db_session)

    # Pre-insert the step so _get_step finds it after the rollback.
    pre_step = AgentStep(
        agent_run_id=run.id,
        step_index=7,
        step_type=AgentStepType.observation,
        input_tokens=0,
        output_tokens=0,
        latency_ms=0,
        status="ok",
    )
    db_session.add(pre_step)
    await db_session.commit()
    await db_session.refresh(pre_step)
    pre_step_id = str(pre_step.id)

    body = _body(step_index=7, step_type="observation")
    sig = _sign(body, secret)

    # Patch db.commit to raise IntegrityError on the first call inside the
    # endpoint (after our pre-step is already committed above).
    original_commit = db_session.commit

    call_count = 0

    async def _patched_commit():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise IntegrityError(None, None, Exception("unique constraint"))  # type: ignore[arg-type]
        return await original_commit()

    with patch.object(db_session, "commit", side_effect=_patched_commit):
        resp = await client.post(
            _ENDPOINT.format(id=run.id),
            content=body,
            headers={"X-BPS-Signature": sig, "Content-Type": "application/json"},
        )

    assert resp.status_code == 200
    assert resp.json()["id"] == pre_step_id


# ---------------------------------------------------------------------------
# 8. SSE publish
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_receive_event_publishes_to_event_bus(
    db_session: AsyncSession, client: AsyncClient
) -> None:
    """Successful POST publishes an event dict to the EventBus queue."""
    run, secret = await _full_setup(db_session)
    body = _body(step_index=0, step_type="tool_result", tool_name="bash", latency_ms=42)
    sig = _sign(body, secret)

    event_bus = get_event_bus()
    queue = event_bus.get_queue(run.id)

    resp = await client.post(
        _ENDPOINT.format(id=run.id),
        content=body,
        headers={"X-BPS-Signature": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200

    event = await asyncio.wait_for(queue.get(), timeout=2.0)
    assert event["step_index"] == 0
    assert event["step_type"] == "tool_result"
    assert event["tool_name"] == "bash"
    assert event["latency_ms"] == 42


# ---------------------------------------------------------------------------
# 9. Validation — negative step_index and negative input_tokens
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_receive_event_validation_negative_step_index(
    db_session: AsyncSession, client: AsyncClient
) -> None:
    """step_index=-1 → 422 Unprocessable Entity."""
    run, secret = await _full_setup(db_session)
    body = _body(step_index=-1)
    sig = _sign(body, secret)

    resp = await client.post(
        _ENDPOINT.format(id=run.id),
        content=body,
        headers={"X-BPS-Signature": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_receive_event_validation_negative_tokens(
    db_session: AsyncSession, client: AsyncClient
) -> None:
    """input_tokens=-100 → 422 Unprocessable Entity."""
    run, secret = await _full_setup(db_session)
    body = _body(step_index=0, input_tokens=-100)
    sig = _sign(body, secret)

    resp = await client.post(
        _ENDPOINT.format(id=run.id),
        content=body,
        headers={"X-BPS-Signature": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 10. Invalid step_type → 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_receive_event_invalid_step_type(
    db_session: AsyncSession, client: AsyncClient
) -> None:
    """Unknown step_type value → 422 Unprocessable Entity."""
    run, secret = await _full_setup(db_session)
    body = _body(step_index=0, step_type="invalid_type")
    sig = _sign(body, secret)

    resp = await client.post(
        _ENDPOINT.format(id=run.id),
        content=body,
        headers={"X-BPS-Signature": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 422
