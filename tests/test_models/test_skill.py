from __future__ import annotations

"""Tests for the Skill and SkillToggle SQLAlchemy models."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.customer import Customer
from backend.models.skill import Skill, SkillToggle

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_customer(db: AsyncSession, name: str = "Test Corp") -> Customer:
    slug = name.lower().replace(" ", "-")
    customer = Customer(name=name, slug=slug)
    db.add(customer)
    await db.flush()
    return customer


async def _make_skill(
    db: AsyncSession,
    customer_id: object,
    *,
    name: str = "test-skill",
    enabled: bool = True,
) -> Skill:

    skill = Skill(
        customer_id=customer_id,
        name=name,
        description="A test skill.",
        category="general",
        applies_to_check_ids=[],
        triggers=["remediation", "scan_enrichment"],
        body="# Test\n\nThis is the body.",
        enabled=enabled,
    )
    db.add(skill)
    await db.flush()
    return skill


# ---------------------------------------------------------------------------
# Skill model
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skill_create_minimal(db_session: AsyncSession) -> None:
    """Skill persists with all required fields."""
    customer = await _make_customer(db_session)
    skill = await _make_skill(db_session, customer.id)

    assert skill.id is not None
    assert skill.customer_id == customer.id
    assert skill.name == "test-skill"
    assert skill.enabled is True
    assert skill.version == 1


@pytest.mark.asyncio
async def test_skill_unique_name_per_customer(db_session: AsyncSession) -> None:
    """Two Skill rows with the same name for the same customer raise IntegrityError."""
    customer = await _make_customer(db_session)
    await _make_skill(db_session, customer.id, name="duplicate-skill")

    duplicate = Skill(
        customer_id=customer.id,
        name="duplicate-skill",
        description="Second skill.",
        category="general",
        applies_to_check_ids=[],
        triggers=["remediation"],
        body="Second body.",
    )
    db_session.add(duplicate)

    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_skill_same_name_different_customers_allowed(db_session: AsyncSession) -> None:
    """Two Skill rows with the same name for different customers are allowed."""
    customer_a = await _make_customer(db_session, "Customer A")
    customer_b = await _make_customer(db_session, "Customer B")

    skill_a = await _make_skill(db_session, customer_a.id, name="shared-name")
    skill_b = await _make_skill(db_session, customer_b.id, name="shared-name")

    assert skill_a.id != skill_b.id


@pytest.mark.asyncio
async def test_skill_cascade_delete(db_session: AsyncSession) -> None:
    """Deleting a Customer removes its Skill rows."""
    customer = await _make_customer(db_session)
    skill_id = (await _make_skill(db_session, customer.id)).id
    await db_session.commit()

    await db_session.delete(customer)
    await db_session.commit()

    result = await db_session.execute(select(Skill).where(Skill.id == skill_id))
    assert result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# SkillToggle model
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skill_toggle_create(db_session: AsyncSession) -> None:
    """SkillToggle persists with the correct fields."""
    customer = await _make_customer(db_session)
    toggle = SkillToggle(
        customer_id=customer.id, skill_name="branch-protection-baseline", enabled=False
    )
    db_session.add(toggle)
    await db_session.flush()

    assert toggle.id is not None
    assert toggle.enabled is False
    assert toggle.skill_name == "branch-protection-baseline"


@pytest.mark.asyncio
async def test_skill_toggle_unique_constraint(db_session: AsyncSession) -> None:
    """Duplicate (customer_id, skill_name) raises IntegrityError."""
    customer = await _make_customer(db_session)
    t1 = SkillToggle(customer_id=customer.id, skill_name="some-skill", enabled=True)
    db_session.add(t1)
    await db_session.flush()

    t2 = SkillToggle(customer_id=customer.id, skill_name="some-skill", enabled=False)
    db_session.add(t2)

    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_skill_toggle_cascade_delete(db_session: AsyncSession) -> None:
    """Deleting a Customer removes its SkillToggle rows."""
    customer = await _make_customer(db_session)
    toggle = SkillToggle(customer_id=customer.id, skill_name="some-skill", enabled=True)
    db_session.add(toggle)
    await db_session.commit()

    toggle_id = toggle.id
    await db_session.delete(customer)
    await db_session.commit()

    result = await db_session.execute(select(SkillToggle).where(SkillToggle.id == toggle_id))
    assert result.scalar_one_or_none() is None
