from __future__ import annotations

"""Tests for backend.services.kill_switch_service."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.customer import Customer
from backend.models.remediation_policy import RemediationPolicy
from backend.schemas.setting import SettingUpdate
from backend.services import kill_switch_service as svc
from backend.services import settings_service

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_customer(db: AsyncSession, suffix: str = "") -> Customer:
    uid = uuid.uuid4().hex[:8]
    customer = Customer(name=f"KSCorp {uid}{suffix}", slug=f"kscorp-{uid}{suffix}")
    db.add(customer)
    await db.flush()
    return customer


async def _add_policy(
    db: AsyncSession,
    customer_id: uuid.UUID,
    *,
    kill_switch_enabled: bool,
) -> RemediationPolicy:
    policy = RemediationPolicy(
        customer_id=customer_id,
        kill_switch_enabled=kill_switch_enabled,
    )
    db.add(policy)
    await db.flush()
    return policy


# ---------------------------------------------------------------------------
# Layer 1: global kill switch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_global_kill_switch_off_no_policy(db_session: AsyncSession) -> None:
    """With global off and no customer policy, check returns not engaged."""
    customer = await _make_customer(db_session)
    await db_session.commit()

    state = await svc.check(db_session, customer.id)

    assert state.engaged is False
    assert state.layer == "none"
    assert state.reason is None


@pytest.mark.asyncio
async def test_global_kill_switch_engaged(db_session: AsyncSession) -> None:
    """Global kill switch engaged → KillSwitchState(engaged=True, layer='global')."""
    customer = await _make_customer(db_session)
    await settings_service.update_settings(
        db_session, SettingUpdate(global_kill_switch_enabled=True)
    )
    await db_session.commit()

    state = await svc.check(db_session, customer.id)

    assert state.engaged is True
    assert state.layer == "global"
    assert state.reason is not None
    assert "global" in state.reason.lower()


@pytest.mark.asyncio
async def test_global_kill_switch_trumps_customer_policy_off(
    db_session: AsyncSession,
) -> None:
    """Global switch engaged even when customer policy kill switch is OFF."""
    customer = await _make_customer(db_session)
    await _add_policy(db_session, customer.id, kill_switch_enabled=False)
    await settings_service.update_settings(
        db_session, SettingUpdate(global_kill_switch_enabled=True)
    )
    await db_session.commit()

    state = await svc.check(db_session, customer.id)

    assert state.engaged is True
    assert state.layer == "global"


# ---------------------------------------------------------------------------
# Layer 2: customer kill switch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_customer_kill_switch_engaged(db_session: AsyncSession) -> None:
    """Customer-level policy kill switch engaged → layer='customer'."""
    customer = await _make_customer(db_session)
    await _add_policy(db_session, customer.id, kill_switch_enabled=True)
    await db_session.commit()
    # Reload so relationship is available.
    await db_session.refresh(customer)

    state = await svc.check(db_session, customer.id)

    assert state.engaged is True
    assert state.layer == "customer"
    assert state.reason is not None
    assert str(customer.id) in state.reason


@pytest.mark.asyncio
async def test_customer_kill_switch_off_not_engaged(db_session: AsyncSession) -> None:
    """Customer policy with kill_switch_enabled=False → not engaged."""
    customer = await _make_customer(db_session)
    await _add_policy(db_session, customer.id, kill_switch_enabled=False)
    await db_session.commit()
    await db_session.refresh(customer)

    state = await svc.check(db_session, customer.id)

    assert state.engaged is False
    assert state.layer == "none"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_customer_id_returns_not_engaged(db_session: AsyncSession) -> None:
    """Non-existent customer_id → not engaged (safe fallback)."""
    state = await svc.check(db_session, uuid.uuid4())

    assert state.engaged is False
    assert state.layer == "none"


@pytest.mark.asyncio
async def test_kill_switch_state_is_frozen() -> None:
    """KillSwitchState is a frozen dataclass — attribute assignment raises."""
    from backend.services.kill_switch_service import KillSwitchState

    ks = KillSwitchState(engaged=False, layer="none", reason=None)
    with pytest.raises((AttributeError, TypeError)):
        ks.engaged = True  # type: ignore[misc]
