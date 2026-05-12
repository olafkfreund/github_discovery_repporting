from __future__ import annotations

"""Tests for the RemediationPolicy SQLAlchemy model."""

import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.customer import Customer
from backend.models.remediation_policy import RemediationPolicy
from backend.schemas.remediation_policy import RemediationPolicyUpsert

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_customer(db: AsyncSession, name: str = "Policy Corp") -> Customer:
    """Create and persist a minimal Customer for FK dependencies."""
    slug = f"{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}"
    customer = Customer(name=name, slug=slug)
    db.add(customer)
    await db.flush()
    return customer


async def _make_policy(
    db: AsyncSession,
    customer_id: uuid.UUID,
    *,
    auto_dispatch: bool = False,
    kill_switch_enabled: bool = False,
) -> RemediationPolicy:
    """Create and persist a minimal RemediationPolicy row."""
    policy = RemediationPolicy(
        customer_id=customer_id,
        auto_dispatch=auto_dispatch,
        kill_switch_enabled=kill_switch_enabled,
    )
    db.add(policy)
    await db.flush()
    return policy


# ---------------------------------------------------------------------------
# Default values
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remediation_policy_default_values(db_session: AsyncSession) -> None:
    """RemediationPolicy created with no explicit fields uses safe defaults."""
    customer = await _make_customer(db_session)
    policy = RemediationPolicy(customer_id=customer.id)
    db_session.add(policy)
    await db_session.flush()

    assert policy.id is not None
    assert policy.customer_id == customer.id
    assert policy.enabled is False
    assert policy.auto_dispatch is False
    assert policy.kill_switch_enabled is False
    assert policy.allowed_check_ids == []
    assert policy.blocked_check_ids == []
    assert policy.max_prs_per_scan == 10
    assert policy.max_cost_usd_per_month == 100.0
    assert policy.allowed_path_globs == []
    assert policy.denied_path_globs == []
    assert policy.runtime_mode == "backend"
    assert policy.oversight_mode == "strict"
    assert policy.llm_input_scope == "hunk"


@pytest.mark.asyncio
async def test_remediation_policy_explicit_values(db_session: AsyncSession) -> None:
    """RemediationPolicy stores all explicitly set fields correctly."""
    customer = await _make_customer(db_session)
    policy = RemediationPolicy(
        customer_id=customer.id,
        enabled=True,
        auto_dispatch=True,
        kill_switch_enabled=True,
        allowed_check_ids=["CICD-001", "CICD-002"],
        blocked_check_ids=["SAST-003"],
        max_prs_per_scan=5,
        max_cost_usd_per_month=50.0,
        allowed_path_globs=["src/**"],
        denied_path_globs=["*.lock"],
        runtime_mode="ci",
        oversight_mode="standard",
        llm_input_scope="file",
    )
    db_session.add(policy)
    await db_session.flush()

    assert policy.enabled is True
    assert policy.auto_dispatch is True
    assert policy.kill_switch_enabled is True
    assert policy.allowed_check_ids == ["CICD-001", "CICD-002"]
    assert policy.blocked_check_ids == ["SAST-003"]
    assert policy.max_prs_per_scan == 5
    assert policy.max_cost_usd_per_month == 50.0
    assert policy.allowed_path_globs == ["src/**"]
    assert policy.denied_path_globs == ["*.lock"]
    assert policy.runtime_mode == "ci"
    assert policy.oversight_mode == "standard"
    assert policy.llm_input_scope == "file"


# ---------------------------------------------------------------------------
# UniqueConstraint on customer_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remediation_policy_unique_per_customer(db_session: AsyncSession) -> None:
    """Creating two RemediationPolicy rows for the same customer raises IntegrityError."""
    customer = await _make_customer(db_session)
    await _make_policy(db_session, customer.id)

    duplicate = RemediationPolicy(customer_id=customer.id)
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_remediation_policy_different_customers_allowed(db_session: AsyncSession) -> None:
    """Two RemediationPolicy rows with different customers are allowed."""
    customer_a = await _make_customer(db_session, name="Customer A")
    customer_b = await _make_customer(db_session, name="Customer B")

    policy_a = await _make_policy(db_session, customer_a.id)
    policy_b = await _make_policy(db_session, customer_b.id)

    assert policy_a.id != policy_b.id
    assert policy_a.customer_id != policy_b.customer_id


# ---------------------------------------------------------------------------
# Cascade delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remediation_policy_cascade_delete(db_session: AsyncSession) -> None:
    """Deleting a Customer removes its RemediationPolicy row."""
    customer = await _make_customer(db_session)
    policy_id = (await _make_policy(db_session, customer.id)).id
    await db_session.commit()

    await db_session.delete(customer)
    await db_session.commit()

    result = await db_session.execute(
        select(RemediationPolicy).where(RemediationPolicy.id == policy_id)
    )
    assert result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# Timestamps
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remediation_policy_timestamps_set(db_session: AsyncSession) -> None:
    """created_at and updated_at are populated after flush."""
    customer = await _make_customer(db_session)
    policy = await _make_policy(db_session, customer.id)
    await db_session.commit()

    assert policy.created_at is not None
    assert policy.updated_at is not None


# ---------------------------------------------------------------------------
# Pydantic schema validation (Literal constraints)
# ---------------------------------------------------------------------------


def test_schema_invalid_runtime_mode_rejected() -> None:
    """RemediationPolicyUpsert with runtime_mode='cloud' raises ValidationError."""
    with pytest.raises(ValidationError):
        RemediationPolicyUpsert(runtime_mode="cloud")  # type: ignore[arg-type]


def test_schema_invalid_oversight_mode_rejected() -> None:
    """RemediationPolicyUpsert with oversight_mode='lax' raises ValidationError."""
    with pytest.raises(ValidationError):
        RemediationPolicyUpsert(oversight_mode="lax")  # type: ignore[arg-type]


def test_schema_invalid_llm_input_scope_rejected() -> None:
    """RemediationPolicyUpsert with llm_input_scope='everything' raises ValidationError."""
    with pytest.raises(ValidationError):
        RemediationPolicyUpsert(llm_input_scope="everything")  # type: ignore[arg-type]


def test_schema_max_prs_per_scan_ge_1_enforced() -> None:
    """RemediationPolicyUpsert with max_prs_per_scan=0 raises ValidationError."""
    with pytest.raises(ValidationError):
        RemediationPolicyUpsert(max_prs_per_scan=0)


def test_schema_max_prs_per_scan_le_100_enforced() -> None:
    """RemediationPolicyUpsert with max_prs_per_scan=101 raises ValidationError."""
    with pytest.raises(ValidationError):
        RemediationPolicyUpsert(max_prs_per_scan=101)


def test_schema_max_cost_ge_0_enforced() -> None:
    """RemediationPolicyUpsert with max_cost_usd_per_month=-1 raises ValidationError."""
    with pytest.raises(ValidationError):
        RemediationPolicyUpsert(max_cost_usd_per_month=-1.0)


def test_schema_valid_defaults_accepted() -> None:
    """RemediationPolicyUpsert with no arguments uses safe defaults."""
    schema = RemediationPolicyUpsert()
    assert schema.enabled is False
    assert schema.auto_dispatch is False
    assert schema.kill_switch_enabled is False
    assert schema.runtime_mode == "backend"
    assert schema.oversight_mode == "strict"
    assert schema.llm_input_scope == "hunk"
    assert schema.max_prs_per_scan == 10
    assert schema.max_cost_usd_per_month == 100.0
