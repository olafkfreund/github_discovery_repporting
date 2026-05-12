from __future__ import annotations

"""Unit tests for remediation_policy_service (direct service layer, no HTTP)."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.customer import Customer
from backend.schemas.remediation_policy import RemediationPolicyUpsert
from backend.services import remediation_policy_service as svc

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_customer(db: AsyncSession, name: str = "Policy Svc Corp") -> Customer:
    """Create and persist a minimal Customer for FK dependencies."""
    slug = f"{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}"
    customer = Customer(name=name, slug=slug)
    db.add(customer)
    await db.flush()
    return customer


# ---------------------------------------------------------------------------
# get_for_customer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_for_customer_returns_none_when_absent(db_session: AsyncSession) -> None:
    """get_for_customer returns None when no policy row exists."""
    customer = await _create_customer(db_session)
    result = await svc.get_for_customer(db_session, customer.id)
    assert result is None


@pytest.mark.asyncio
async def test_get_for_customer_returns_row(db_session: AsyncSession) -> None:
    """get_for_customer returns the persisted row."""
    customer = await _create_customer(db_session)
    payload = RemediationPolicyUpsert(auto_dispatch=True)
    await svc.upsert(db_session, customer.id, payload)

    result = await svc.get_for_customer(db_session, customer.id)
    assert result is not None
    assert result.auto_dispatch is True
    assert result.customer_id == customer.id


# ---------------------------------------------------------------------------
# upsert
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_creates_row_when_absent(db_session: AsyncSession) -> None:
    """upsert creates a new row when none exists."""
    customer = await _create_customer(db_session)
    payload = RemediationPolicyUpsert(enabled=True, auto_dispatch=True, max_prs_per_scan=5)

    row = await svc.upsert(db_session, customer.id, payload)

    assert row.id is not None
    assert row.customer_id == customer.id
    assert row.enabled is True
    assert row.auto_dispatch is True
    assert row.max_prs_per_scan == 5


@pytest.mark.asyncio
async def test_upsert_updates_row_when_present(db_session: AsyncSession) -> None:
    """upsert replaces all fields on an existing row; row id is preserved."""
    customer = await _create_customer(db_session)
    payload_a = RemediationPolicyUpsert(enabled=False, auto_dispatch=False)
    original = await svc.upsert(db_session, customer.id, payload_a)
    original_id = original.id

    payload_b = RemediationPolicyUpsert(enabled=True, auto_dispatch=True, max_prs_per_scan=20)
    updated = await svc.upsert(db_session, customer.id, payload_b)

    assert updated.id == original_id
    assert updated.enabled is True
    assert updated.auto_dispatch is True
    assert updated.max_prs_per_scan == 20


@pytest.mark.asyncio
async def test_upsert_is_idempotent(db_session: AsyncSession) -> None:
    """Calling upsert twice with the same payload produces the same result."""
    customer = await _create_customer(db_session)
    payload = RemediationPolicyUpsert(runtime_mode="ci")

    first = await svc.upsert(db_session, customer.id, payload)
    second = await svc.upsert(db_session, customer.id, payload)

    assert first.id == second.id
    assert second.runtime_mode == "ci"


@pytest.mark.asyncio
async def test_upsert_stores_list_fields(db_session: AsyncSession) -> None:
    """upsert correctly stores JSON list fields."""
    customer = await _create_customer(db_session)
    payload = RemediationPolicyUpsert(
        allowed_check_ids=["CICD-001", "REPO-002"],
        blocked_check_ids=["SAST-003"],
        allowed_path_globs=["src/**"],
        denied_path_globs=["*.lock"],
    )

    row = await svc.upsert(db_session, customer.id, payload)
    assert row.allowed_check_ids == ["CICD-001", "REPO-002"]
    assert row.blocked_check_ids == ["SAST-003"]
    assert row.allowed_path_globs == ["src/**"]
    assert row.denied_path_globs == ["*.lock"]


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_returns_true_when_row_exists(db_session: AsyncSession) -> None:
    """delete returns True when a row exists and is deleted."""
    customer = await _create_customer(db_session)
    await svc.upsert(db_session, customer.id, RemediationPolicyUpsert())

    result = await svc.delete(db_session, customer.id)
    assert result is True

    remaining = await svc.get_for_customer(db_session, customer.id)
    assert remaining is None


@pytest.mark.asyncio
async def test_delete_returns_false_when_absent(db_session: AsyncSession) -> None:
    """delete returns False when no row exists."""
    customer = await _create_customer(db_session)
    result = await svc.delete(db_session, customer.id)
    assert result is False


@pytest.mark.asyncio
async def test_delete_then_upsert_creates_new_row(db_session: AsyncSession) -> None:
    """After delete, upsert creates a fresh row with a new id."""
    customer = await _create_customer(db_session)
    first = await svc.upsert(db_session, customer.id, RemediationPolicyUpsert())
    first_id = first.id

    await svc.delete(db_session, customer.id)

    second = await svc.upsert(db_session, customer.id, RemediationPolicyUpsert())
    assert second.id != first_id
