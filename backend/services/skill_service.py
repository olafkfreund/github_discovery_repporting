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
import uuid as _uuid_module
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.customer import PlatformConnection
from backend.models.skill import Skill, SkillToggle
from backend.schemas.skill import SkillCreate, SkillRead, SkillUpdate
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


# ---------------------------------------------------------------------------
# Mutating helpers (create / update / delete / connection override)
# ---------------------------------------------------------------------------


async def create_skill(db: AsyncSession, customer_id: UUID, payload: SkillCreate) -> Skill:
    """Create a new custom :class:`~backend.models.skill.Skill` row.

    Args:
        db: Active async database session.
        customer_id: UUID of the owning customer.
        payload: Validated creation payload.

    Returns:
        The newly created and refreshed :class:`Skill` ORM instance.

    Raises:
        ValueError: When *payload.name* matches a built-in skill slug.
        ValueError: When a custom skill with the same name already exists for
            this customer.
    """
    registry = get_skill_registry()
    if payload.name in registry:
        raise ValueError(f"Cannot create custom skill with built-in name {payload.name!r}.")

    existing = await db.execute(
        select(Skill).where(Skill.customer_id == customer_id, Skill.name == payload.name)
    )
    if existing.scalar_one_or_none() is not None:
        raise ValueError(f"A custom skill named {payload.name!r} already exists for this customer.")

    skill = Skill(
        customer_id=customer_id,
        name=payload.name,
        description=payload.description,
        category=payload.category,
        applies_to_check_ids=payload.applies_to_check_ids,
        triggers=payload.triggers,
        body=payload.body,
        enabled=payload.enabled,
        version=1,
    )
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    return skill


async def update_skill(
    db: AsyncSession, customer_id: UUID, name: str, payload: SkillUpdate
) -> Skill:
    """Apply a partial update to a skill, respecting built-in vs custom rules.

    For **built-in** skills only the ``enabled`` field is honoured.  Any other
    field in *payload* triggers a :class:`ValueError`.  The enabled state is
    persisted via an upserted :class:`~backend.models.skill.SkillToggle` row.
    A synthetic :class:`Skill` is NOT returned for built-ins; instead the
    ``SkillToggle`` is written and the original built-in :class:`Skill`-like
    representation is reconstructed from the registry.

    For **custom** skills all optional fields are applied and ``version`` is
    bumped when any field other than ``enabled`` changes.

    Args:
        db: Active async database session.
        customer_id: UUID of the owning customer.
        name: Skill slug to update.
        payload: Partial update payload.

    Returns:
        The updated :class:`Skill` ORM instance (custom skills only).

    Raises:
        ValueError: When *name* is a built-in and non-``enabled`` fields are
            supplied.
        ValueError: When *name* does not exist as either a built-in or a custom
            skill for this customer (callers should convert to 404).
    """
    registry = get_skill_registry()
    if name in registry:
        # Built-in: only enabled changes are allowed.
        non_enabled_fields = {
            k for k, v in payload.model_dump(exclude_none=True).items() if k != "enabled"
        }
        if non_enabled_fields:
            raise ValueError(
                f"Cannot modify {sorted(non_enabled_fields)} on built-in skill {name!r}; "
                "only 'enabled' may be changed."
            )

        if payload.enabled is not None:
            await upsert_skill_toggle(db, customer_id, name, payload.enabled)

        # Return a SkillRead Pydantic model directly for built-ins.
        # We cannot attach a synthetic ORM instance to the session (SQLAlchemy
        # mapper instrumentation prevents it), so we build the schema object
        # directly and return it.  The router calls SkillRead.model_validate()
        # on the result; Pydantic accepts a SkillRead instance unchanged.
        builtin = registry[name]
        toggle_result = await db.execute(
            select(SkillToggle).where(
                SkillToggle.customer_id == customer_id,
                SkillToggle.skill_name == name,
            )
        )
        toggle = toggle_result.scalar_one_or_none()
        effective_enabled = toggle.enabled if toggle is not None else True

        now = datetime.now(tz=UTC)
        return SkillRead(
            id=_uuid_module.uuid4(),
            customer_id=customer_id,
            name=name,
            description=builtin.frontmatter.description,
            category=builtin.frontmatter.category,
            applies_to_check_ids=list(builtin.frontmatter.applies_to),
            triggers=list(builtin.frontmatter.triggers),
            body=builtin.body,
            version=builtin.frontmatter.version,
            enabled=effective_enabled,
            created_at=now,
            updated_at=now,
        )

    # Custom skill path.
    result = await db.execute(
        select(Skill).where(Skill.customer_id == customer_id, Skill.name == name)
    )
    skill = result.scalar_one_or_none()
    if skill is None:
        raise ValueError(f"Skill {name!r} not found for this customer.")

    update_data = payload.model_dump(exclude_none=True)
    body_changed = False
    for field, value in update_data.items():
        if field != "enabled" and getattr(skill, field) != value:
            body_changed = True
        setattr(skill, field, value)

    if body_changed:
        skill.version = skill.version + 1

    await db.commit()
    await db.refresh(skill)
    return skill


async def delete_skill(db: AsyncSession, customer_id: UUID, name: str) -> None:
    """Delete a custom skill row and any associated :class:`SkillToggle`.

    Args:
        db: Active async database session.
        customer_id: UUID of the owning customer.
        name: Skill slug to delete.

    Raises:
        ValueError: When *name* is a built-in skill (use disable instead).
        ValueError: When no custom skill with *name* exists for this customer.
    """
    registry = get_skill_registry()
    if name in registry:
        raise ValueError(f"Cannot delete built-in skill {name!r}; disable it instead.")

    result = await db.execute(
        select(Skill).where(Skill.customer_id == customer_id, Skill.name == name)
    )
    skill = result.scalar_one_or_none()
    if skill is None:
        raise ValueError(f"Skill {name!r} not found for this customer.")

    # Remove any associated SkillToggle.
    toggle_result = await db.execute(
        select(SkillToggle).where(
            SkillToggle.customer_id == customer_id,
            SkillToggle.skill_name == name,
        )
    )
    toggle = toggle_result.scalar_one_or_none()
    if toggle is not None:
        await db.delete(toggle)

    await db.delete(skill)
    await db.commit()


async def set_connection_override(
    db: AsyncSession,
    connection_id: UUID,
    overrides: dict[str, bool],
) -> PlatformConnection:
    """Write *overrides* to :attr:`PlatformConnection.skills_override`.

    An empty *overrides* dict clears the column back to ``NULL`` to keep the
    database tidy.  Every key in *overrides* must resolve to a skill visible
    to the connection's customer; unknown names are rejected.

    Args:
        db: Active async database session.
        connection_id: UUID of the :class:`PlatformConnection` to update.
        overrides: Mapping of ``{skill_name: enabled_bool}`` to persist.
            Pass an empty dict to clear all overrides.

    Returns:
        The refreshed :class:`PlatformConnection` ORM instance.

    Raises:
        ValueError: When *connection_id* does not exist.
        ValueError: When any key in *overrides* is not a known skill for the
            connection's customer.
    """
    connection = await _load_connection(db, connection_id)
    if connection is None:
        raise ValueError(f"PlatformConnection {connection_id} not found.")

    if overrides:
        summaries = await list_available_skills(db, connection.customer_id)
        known_names = {s.name for s in summaries}
        unknown = set(overrides) - known_names
        if unknown:
            raise ValueError(
                f"Unknown skill name(s) in overrides: {sorted(unknown)}. "
                "Only skills visible to this customer may be referenced."
            )

    connection.skills_override = overrides or None
    await db.commit()
    await db.refresh(connection)
    return connection
