from __future__ import annotations

"""Service layer for the Skill system.

Provides read/write helpers for custom :class:`~backend.models.skill.Skill` rows and
:class:`~backend.models.skill.SkillToggle` overrides, plus resolution functions that
merge built-in and custom skills for a given customer connection.

The effective-enabled precedence (per skill) is:

1. ``PlatformConnection.skills_override[name]`` — connection-level bool wins if set.
2. :class:`~backend.models.skill.SkillToggle` row for this ``(customer_id, name)``
   pair — customer-level toggle wins next.
3. Default — built-in skills are ON by default; custom ``Skill.enabled`` field applies.
"""

import hashlib
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.customer import PlatformConnection
from backend.models.skill import Skill, SkillToggle
from backend.skills import BuiltinSkill, get_skill_registry  # noqa: F401

# ---------------------------------------------------------------------------
# Data-transfer objects (no ORM dependency in callers).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SkillSummaryDC:
    """Lightweight summary of a skill, usable without a DB round-trip.

    Attributes:
        name: Skill slug.
        description: One-sentence summary.
        category: Scanner category key or ``"general"``.
        applies_to_check_ids: Check IDs this skill addresses.
        triggers: Contexts in which the skill body is injected.
        source: ``"builtin"`` for library files; ``"custom"`` for DB rows.
        enabled: Effective enabled state for the requesting customer.
        version: Schema or row version integer.
    """

    name: str
    description: str
    category: str
    applies_to_check_ids: list[str]
    triggers: list[str]
    source: Literal["builtin", "custom"]
    enabled: bool
    version: int


@dataclass(frozen=True)
class ResolvedSkill:
    """A skill whose body is ready to be injected into an agent context.

    Attributes:
        name: Skill slug.
        body: Full markdown body text.
        sha256: Content hash (for caching / deduplication).
        source: Origin of the skill content.
        applies_to: Check IDs this skill addresses (may be empty for always-on).
    """

    name: str
    body: str
    sha256: str
    source: Literal["builtin", "custom"]
    applies_to: list[str]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _load_connection(db: AsyncSession, connection_id: UUID) -> PlatformConnection | None:
    """Return the :class:`PlatformConnection` for *connection_id*, or ``None``."""
    result = await db.execute(
        select(PlatformConnection).where(PlatformConnection.id == connection_id)
    )
    return result.scalar_one_or_none()


async def _load_toggles(db: AsyncSession, customer_id: UUID) -> dict[str, bool]:
    """Return a dict of ``{skill_name: enabled}`` from SkillToggle rows."""
    result = await db.execute(select(SkillToggle).where(SkillToggle.customer_id == customer_id))
    return {row.skill_name: row.enabled for row in result.scalars()}


async def _load_custom_skills(db: AsyncSession, customer_id: UUID) -> list[Skill]:
    """Return all custom Skill rows for *customer_id*."""
    result = await db.execute(select(Skill).where(Skill.customer_id == customer_id))
    return list(result.scalars())


def _effective_enabled(
    name: str,
    *,
    skills_override: dict[str, bool] | None,
    toggles: dict[str, bool],
    default_enabled: bool,
) -> bool:
    """Compute the effective enabled state for a skill.

    Precedence (highest first):

    1. ``skills_override[name]`` — connection-level bool, if present.
    2. ``toggles[name]`` — customer-level SkillToggle row, if present.
    3. ``default_enabled`` — the fallback.

    Args:
        name: Skill slug.
        skills_override: Parsed ``PlatformConnection.skills_override`` dict or ``None``.
        toggles: Pre-loaded ``{name: enabled}`` dict from SkillToggle rows.
        default_enabled: Default value (``True`` for built-in; ``Skill.enabled`` for
            custom rows).

    Returns:
        The resolved ``bool`` enabled state.
    """
    if skills_override is not None and name in skills_override:
        return bool(skills_override[name])
    if name in toggles:
        return toggles[name]
    return default_enabled


def _custom_sha256(body: str) -> str:
    """Return the hex SHA-256 digest of the UTF-8 encoded body text."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def list_available_skills(
    db: AsyncSession,
    customer_id: UUID,
) -> list[SkillSummaryDC]:
    """Return a merged list of built-in and custom skills for *customer_id*.

    Built-in skills appear first (sorted by name), followed by custom skills that
    do not share a slug with any built-in.  Custom skills whose name duplicates a
    built-in take precedence — the built-in version is omitted.

    Args:
        db: Active async database session.
        customer_id: UUID of the requesting customer.

    Returns:
        List of :class:`SkillSummaryDC` instances covering all available skills.
    """
    toggles = await _load_toggles(db, customer_id)
    custom_skills = await _load_custom_skills(db, customer_id)
    custom_by_name = {s.name: s for s in custom_skills}

    registry = get_skill_registry()
    summaries: list[SkillSummaryDC] = []

    # Built-in skills (skip if overridden by a custom skill of the same name).
    for name, skill in sorted(registry.items()):
        if name in custom_by_name:
            continue
        enabled = _effective_enabled(
            name, skills_override=None, toggles=toggles, default_enabled=True
        )
        summaries.append(
            SkillSummaryDC(
                name=name,
                description=skill.frontmatter.description,
                category=skill.frontmatter.category,
                applies_to_check_ids=list(skill.frontmatter.applies_to),
                triggers=list(skill.frontmatter.triggers),
                source="builtin",
                enabled=enabled,
                version=skill.frontmatter.version,
            )
        )

    # Custom skills.
    for skill in sorted(custom_by_name.values(), key=lambda s: s.name):
        enabled = _effective_enabled(
            skill.name, skills_override=None, toggles=toggles, default_enabled=skill.enabled
        )
        summaries.append(
            SkillSummaryDC(
                name=skill.name,
                description=skill.description,
                category=skill.category,
                applies_to_check_ids=list(skill.applies_to_check_ids),
                triggers=list(skill.triggers),
                source="custom",
                enabled=enabled,
                version=skill.version,
            )
        )

    return summaries


async def get_skill_content(
    db: AsyncSession,
    customer_id: UUID,
    name: str,
) -> str:
    """Return the body text for a skill by slug.

    Custom skill rows take precedence over built-in skills of the same name.
    Does not check effective-enabled state — callers must verify that separately.

    Args:
        db: Active async database session.
        customer_id: UUID of the requesting customer.
        name: Skill slug.

    Returns:
        The skill body as a string.

    Raises:
        KeyError: When no skill with *name* exists for this customer.
    """
    result = await db.execute(
        select(Skill).where(Skill.customer_id == customer_id, Skill.name == name)
    )
    custom = result.scalar_one_or_none()
    if custom is not None:
        return custom.body

    registry = get_skill_registry()
    if name in registry:
        return registry[name].body

    raise KeyError(f"No skill named {name!r} found for customer {customer_id}")


async def get_skill_summary(
    db: AsyncSession,
    customer_id: UUID,
    name: str,
) -> SkillSummaryDC | None:
    """Return the summary for a single skill, or ``None`` if it does not exist.

    Args:
        db: Active async database session.
        customer_id: UUID of the requesting customer.
        name: Skill slug.

    Returns:
        :class:`SkillSummaryDC` or ``None``.
    """
    summaries = await list_available_skills(db, customer_id)
    for summary in summaries:
        if summary.name == name:
            return summary
    return None


async def upsert_skill_toggle(
    db: AsyncSession,
    customer_id: UUID,
    name: str,
    enabled: bool,
) -> SkillToggle:
    """Create or update a :class:`~backend.models.skill.SkillToggle` row.

    If a toggle already exists for ``(customer_id, name)`` it is updated in-place;
    otherwise a new row is created.  The result is committed before returning.

    Args:
        db: Active async database session.
        customer_id: UUID of the owning customer.
        name: Skill slug to toggle.
        enabled: Desired enabled state.

    Returns:
        The created or updated :class:`SkillToggle` ORM instance.
    """
    result = await db.execute(
        select(SkillToggle).where(
            SkillToggle.customer_id == customer_id,
            SkillToggle.skill_name == name,
        )
    )
    toggle = result.scalar_one_or_none()

    if toggle is not None:
        toggle.enabled = enabled
        await db.commit()
        await db.refresh(toggle)
        return toggle

    toggle = SkillToggle(customer_id=customer_id, skill_name=name, enabled=enabled)
    db.add(toggle)
    await db.commit()
    await db.refresh(toggle)
    return toggle


async def resolve_for_check(
    db: AsyncSession,
    connection_id: UUID,
    check_id: str,
) -> list[ResolvedSkill]:
    """Return skills relevant to *check_id* that have the ``remediation`` trigger.

    Effective-enabled state is evaluated for each skill using the full precedence
    chain (connection override > customer toggle > default).

    Inclusion criteria:
    - Effective enabled is ``True``.
    - ``"remediation"`` is in the skill's triggers.
    - ``applies_to`` contains *check_id*, OR ``applies_to`` is empty (always-on).

    Args:
        db: Active async database session.
        connection_id: UUID of the :class:`~backend.models.customer.PlatformConnection`.
        check_id: The check ID to match (e.g. ``"REPO-001"``).

    Returns:
        List of :class:`ResolvedSkill` instances, sorted by name for determinism.
    """
    connection = await _load_connection(db, connection_id)
    if connection is None:
        return []

    customer_id = connection.customer_id
    skills_override: dict[str, bool] | None = connection.skills_override
    toggles = await _load_toggles(db, customer_id)
    custom_skills = await _load_custom_skills(db, customer_id)
    custom_by_name = {s.name: s for s in custom_skills}
    registry = get_skill_registry()

    resolved: list[ResolvedSkill] = []

    def _include(
        name: str,
        body: str,
        sha: str,
        source: Literal["builtin", "custom"],
        applies_to: list[str],
        triggers: list[str],
        effective: bool,
    ) -> None:
        if not effective:
            return
        if "remediation" not in triggers:
            return
        if applies_to and check_id not in applies_to:
            return
        resolved.append(
            ResolvedSkill(name=name, body=body, sha256=sha, source=source, applies_to=applies_to)
        )

    for name, skill in registry.items():
        if name in custom_by_name:
            continue
        enabled = _effective_enabled(
            name, skills_override=skills_override, toggles=toggles, default_enabled=True
        )
        _include(
            name=name,
            body=skill.body,
            sha=skill.sha256,
            source="builtin",
            applies_to=list(skill.frontmatter.applies_to),
            triggers=list(skill.frontmatter.triggers),
            effective=enabled,
        )

    for skill in custom_by_name.values():
        enabled = _effective_enabled(
            skill.name,
            skills_override=skills_override,
            toggles=toggles,
            default_enabled=skill.enabled,
        )
        _include(
            name=skill.name,
            body=skill.body,
            sha=_custom_sha256(skill.body),
            source="custom",
            applies_to=list(skill.applies_to_check_ids),
            triggers=list(skill.triggers),
            effective=enabled,
        )

    resolved.sort(key=lambda r: r.name)
    return resolved


async def resolve_for_scan(
    db: AsyncSession,
    connection_id: UUID,
    finding_check_ids: set[str],
) -> dict[str, list[ResolvedSkill]]:
    """Return a dict mapping each check_id to relevant ``scan_enrichment`` skills.

    Only skills with ``"scan_enrichment"`` in triggers are included.  Always-on
    skills (empty ``applies_to``) appear under every check_id in *finding_check_ids*.

    Args:
        db: Active async database session.
        connection_id: UUID of the :class:`~backend.models.customer.PlatformConnection`.
        finding_check_ids: Set of check IDs from the scan findings to resolve for.

    Returns:
        Dict keyed by check_id; each value is a list of :class:`ResolvedSkill` sorted
        by name.  Check IDs with no matching skills are included with an empty list.
    """
    connection = await _load_connection(db, connection_id)
    if connection is None:
        return {cid: [] for cid in finding_check_ids}

    customer_id = connection.customer_id
    skills_override: dict[str, bool] | None = connection.skills_override
    toggles = await _load_toggles(db, customer_id)
    custom_skills = await _load_custom_skills(db, customer_id)
    custom_by_name = {s.name: s for s in custom_skills}
    registry = get_skill_registry()

    candidates: list[ResolvedSkill] = []

    for name, skill in registry.items():
        if name in custom_by_name:
            continue
        enabled = _effective_enabled(
            name, skills_override=skills_override, toggles=toggles, default_enabled=True
        )
        if enabled and "scan_enrichment" in skill.frontmatter.triggers:
            candidates.append(
                ResolvedSkill(
                    name=name,
                    body=skill.body,
                    sha256=skill.sha256,
                    source="builtin",
                    applies_to=list(skill.frontmatter.applies_to),
                )
            )

    for skill in custom_by_name.values():
        enabled = _effective_enabled(
            skill.name,
            skills_override=skills_override,
            toggles=toggles,
            default_enabled=skill.enabled,
        )
        if enabled and "scan_enrichment" in skill.triggers:
            candidates.append(
                ResolvedSkill(
                    name=skill.name,
                    body=skill.body,
                    sha256=_custom_sha256(skill.body),
                    source="custom",
                    applies_to=list(skill.applies_to_check_ids),
                )
            )

    result: dict[str, list[ResolvedSkill]] = {cid: [] for cid in finding_check_ids}

    for candidate in candidates:
        if not candidate.applies_to:
            for cid in finding_check_ids:
                result[cid].append(candidate)
        else:
            for cid in candidate.applies_to:
                if cid in result:
                    result[cid].append(candidate)

    for cid in result:
        result[cid].sort(key=lambda r: r.name)

    return result
