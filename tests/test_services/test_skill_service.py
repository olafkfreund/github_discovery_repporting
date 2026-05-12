from __future__ import annotations

"""Unit tests for skill_service (direct service layer, no HTTP)."""

import uuid
from json import dumps

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.customer import Customer, PlatformConnection
from backend.models.enums import AuthType, Platform
from backend.models.skill import Skill, SkillToggle
from backend.services import skill_service as svc
from backend.services.secrets_service import secrets_service
from backend.skills import get_skill_registry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_customer(db: AsyncSession, name: str = "Skill Corp") -> Customer:
    slug = name.lower().replace(" ", "-")
    customer = Customer(name=name, slug=slug)
    db.add(customer)
    await db.flush()
    return customer


async def _make_connection(
    db: AsyncSession,
    customer_id: uuid.UUID,
    *,
    skills_override: dict[str, bool] | None = None,
) -> PlatformConnection:
    conn = PlatformConnection(
        customer_id=customer_id,
        platform=Platform.github,
        display_name="Test Connection",
        auth_type=AuthType.token,
        credentials_encrypted=secrets_service.encrypt(dumps({"token": "test"})),
        org_or_group="test-org",
        skills_override=skills_override,
    )
    db.add(conn)
    await db.flush()
    return conn


async def _make_skill(
    db: AsyncSession,
    customer_id: uuid.UUID,
    *,
    name: str = "custom-test-skill",
    applies_to: list[str] | None = None,
    triggers: list[str] | None = None,
    enabled: bool = True,
    body: str = "# Custom Skill\n\nCustom body.",
) -> Skill:
    skill = Skill(
        customer_id=customer_id,
        name=name,
        description="A custom test skill.",
        category="general",
        applies_to_check_ids=applies_to or [],
        triggers=triggers or ["remediation", "scan_enrichment"],
        body=body,
        enabled=enabled,
    )
    db.add(skill)
    await db.flush()
    return skill


# ---------------------------------------------------------------------------
# list_available_skills
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_available_skills_includes_builtins(db_session: AsyncSession) -> None:
    """list_available_skills returns all 15 built-in skills for a new customer."""
    customer = await _make_customer(db_session)
    summaries = await svc.list_available_skills(db_session, customer.id)

    builtin_names = {s.name for s in summaries if s.source == "builtin"}
    registry = get_skill_registry()
    assert builtin_names == set(registry.keys())


@pytest.mark.asyncio
async def test_list_available_skills_includes_custom(db_session: AsyncSession) -> None:
    """list_available_skills includes custom skills after built-ins."""
    customer = await _make_customer(db_session)
    await _make_skill(db_session, customer.id, name="my-custom-skill")

    summaries = await svc.list_available_skills(db_session, customer.id)
    custom_names = {s.name for s in summaries if s.source == "custom"}
    assert "my-custom-skill" in custom_names


@pytest.mark.asyncio
async def test_list_available_skills_custom_overrides_builtin(db_session: AsyncSession) -> None:
    """A custom skill with a name matching a built-in replaces the built-in in the list."""
    customer = await _make_customer(db_session)
    # Use a name that clashes with a known built-in.
    await _make_skill(db_session, customer.id, name="codeowners-team-mapping")

    summaries = await svc.list_available_skills(db_session, customer.id)
    matching = [s for s in summaries if s.name == "codeowners-team-mapping"]

    # Should appear exactly once, and it should be marked custom.
    assert len(matching) == 1
    assert matching[0].source == "custom"


@pytest.mark.asyncio
async def test_skill_toggle_flips_effective_enabled(db_session: AsyncSession) -> None:
    """A SkillToggle row with enabled=False makes the skill appear disabled."""
    customer = await _make_customer(db_session)

    # Disable a well-known built-in via toggle.
    toggle = SkillToggle(
        customer_id=customer.id, skill_name="branch-protection-baseline", enabled=False
    )
    db_session.add(toggle)
    await db_session.flush()

    summaries = await svc.list_available_skills(db_session, customer.id)
    bpb = next(s for s in summaries if s.name == "branch-protection-baseline")
    assert bpb.enabled is False


# ---------------------------------------------------------------------------
# upsert_skill_toggle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_skill_toggle_creates_row(db_session: AsyncSession) -> None:
    """upsert_skill_toggle creates a new SkillToggle row when none exists."""
    customer = await _make_customer(db_session)

    toggle = await svc.upsert_skill_toggle(
        db_session, customer.id, "branch-protection-baseline", False
    )
    assert toggle.id is not None
    assert toggle.enabled is False


@pytest.mark.asyncio
async def test_upsert_skill_toggle_updates_existing(db_session: AsyncSession) -> None:
    """upsert_skill_toggle updates an existing row without creating a duplicate."""
    customer = await _make_customer(db_session)

    first = await svc.upsert_skill_toggle(
        db_session, customer.id, "branch-protection-baseline", False
    )
    second = await svc.upsert_skill_toggle(
        db_session, customer.id, "branch-protection-baseline", True
    )

    # Same row ID, updated value.
    assert first.id == second.id
    assert second.enabled is True

    # Confirm only one row exists.
    result = await db_session.execute(
        select(SkillToggle).where(
            SkillToggle.customer_id == customer.id,
            SkillToggle.skill_name == "branch-protection-baseline",
        )
    )
    rows = result.scalars().all()
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# resolve_for_check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_for_check_returns_applicable_builtin(db_session: AsyncSession) -> None:
    """resolve_for_check returns a built-in skill whose applies_to contains the check_id."""
    customer = await _make_customer(db_session)
    connection = await _make_connection(db_session, customer.id)

    resolved = await svc.resolve_for_check(db_session, connection.id, "REPO-001")
    names = {r.name for r in resolved}

    # branch-protection-baseline applies_to [REPO-001, REPO-002, REPO-003]
    # and has remediation trigger.
    assert "branch-protection-baseline" in names


@pytest.mark.asyncio
async def test_resolve_for_check_general_skill_always_included(db_session: AsyncSession) -> None:
    """A skill with empty applies_to (always-on) appears for any check_id."""
    customer = await _make_customer(db_session)
    connection = await _make_connection(db_session, customer.id)

    # Use an obscure check_id that no specific skill targets.
    resolved = await svc.resolve_for_check(db_session, connection.id, "MON-011")
    names = {r.name for r in resolved}

    # general-pr-style has applies_to=[] and triggers=[remediation, scan_enrichment].
    assert "general-pr-style" in names


@pytest.mark.asyncio
async def test_resolve_for_check_disabled_skill_excluded(db_session: AsyncSession) -> None:
    """A disabled skill is excluded from resolve_for_check results."""
    customer = await _make_customer(db_session)
    connection = await _make_connection(db_session, customer.id)

    # Disable branch-protection-baseline.
    await svc.upsert_skill_toggle(db_session, customer.id, "branch-protection-baseline", False)

    resolved = await svc.resolve_for_check(db_session, connection.id, "REPO-001")
    names = {r.name for r in resolved}
    assert "branch-protection-baseline" not in names


@pytest.mark.asyncio
async def test_resolve_for_check_connection_override_beats_toggle(
    db_session: AsyncSession,
) -> None:
    """PlatformConnection.skills_override[name]=False wins over a SkillToggle enabled=True."""
    customer = await _make_customer(db_session)
    # Toggle says enabled, but connection override says disabled.
    connection = await _make_connection(
        db_session,
        customer.id,
        skills_override={"general-pr-style": False},
    )
    await svc.upsert_skill_toggle(db_session, customer.id, "general-pr-style", True)

    resolved = await svc.resolve_for_check(db_session, connection.id, "REPO-001")
    names = {r.name for r in resolved}
    assert "general-pr-style" not in names


@pytest.mark.asyncio
async def test_resolve_for_check_scan_enrichment_only_skill_excluded(
    db_session: AsyncSession,
) -> None:
    """A skill with only scan_enrichment trigger is excluded from resolve_for_check."""
    customer = await _make_customer(db_session)
    connection = await _make_connection(db_session, customer.id)

    # workflow-pinned-actions has triggers=[scan_enrichment] only.
    resolved = await svc.resolve_for_check(db_session, connection.id, "CICD-005")
    names = {r.name for r in resolved}
    assert "workflow-pinned-actions" not in names


# ---------------------------------------------------------------------------
# resolve_for_scan
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_for_scan_returns_scan_enrichment_skills(
    db_session: AsyncSession,
) -> None:
    """resolve_for_scan returns only scan_enrichment-triggered skills."""
    customer = await _make_customer(db_session)
    connection = await _make_connection(db_session, customer.id)

    result = await svc.resolve_for_scan(db_session, connection.id, {"CICD-005"})
    # workflow-pinned-actions applies_to [CICD-005, CICD-006] and has scan_enrichment.
    assert "CICD-005" in result
    names = {r.name for r in result["CICD-005"]}
    assert "workflow-pinned-actions" in names


@pytest.mark.asyncio
async def test_resolve_for_scan_general_skill_appears_everywhere(
    db_session: AsyncSession,
) -> None:
    """An always-on skill with scan_enrichment trigger appears under every check_id."""
    customer = await _make_customer(db_session)
    connection = await _make_connection(db_session, customer.id)

    check_ids = {"MON-001", "DR-002", "SAST-005"}
    result = await svc.resolve_for_scan(db_session, connection.id, check_ids)

    for cid in check_ids:
        names = {r.name for r in result[cid]}
        # general-pr-style has applies_to=[] and scan_enrichment trigger.
        assert "general-pr-style" in names, f"general-pr-style missing from check_id {cid!r}"


@pytest.mark.asyncio
async def test_resolve_for_scan_empty_check_ids(db_session: AsyncSession) -> None:
    """resolve_for_scan with empty finding_check_ids returns an empty dict."""
    customer = await _make_customer(db_session)
    connection = await _make_connection(db_session, customer.id)

    result = await svc.resolve_for_scan(db_session, connection.id, set())
    assert result == {}


@pytest.mark.asyncio
async def test_resolve_for_scan_missing_connection_returns_empty(
    db_session: AsyncSession,
) -> None:
    """resolve_for_scan with a non-existent connection_id returns empty lists."""
    fake_id = uuid.uuid4()
    result = await svc.resolve_for_scan(db_session, fake_id, {"REPO-001"})
    assert result == {"REPO-001": []}


# ---------------------------------------------------------------------------
# Cascade delete via Customer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skill_and_toggle_cascade_deleted_with_customer(
    db_session: AsyncSession,
) -> None:
    """Deleting a Customer removes its Skill and SkillToggle rows."""
    customer = await _make_customer(db_session)
    skill = await _make_skill(db_session, customer.id)
    toggle = await svc.upsert_skill_toggle(db_session, customer.id, "some-skill", False)
    await db_session.commit()

    skill_id = skill.id
    toggle_id = toggle.id

    await db_session.delete(customer)
    await db_session.commit()

    r_skill = await db_session.execute(select(Skill).where(Skill.id == skill_id))
    r_toggle = await db_session.execute(select(SkillToggle).where(SkillToggle.id == toggle_id))

    assert r_skill.scalar_one_or_none() is None
    assert r_toggle.scalar_one_or_none() is None
