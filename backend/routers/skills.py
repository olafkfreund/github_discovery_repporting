from __future__ import annotations

"""CRUD router for the customer Skill system.

Exposes built-in and custom skill listing, custom-skill creation and mutation,
per-skill enable/disable, and connection-level skills_override writes.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.schemas.customer import ConnectionResponse
from backend.schemas.skill import (
    SkillCreate,
    SkillRead,
    SkillsOverridePayload,
    SkillSummary,
    SkillUpdate,
)
from backend.services import customer_service
from backend.services import skill_service as svc

router = APIRouter(prefix="/api", tags=["skills"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _skill_summary_from_dc(dc: svc.SkillSummaryDC) -> SkillSummary:
    """Convert a :class:`~backend.services.skill_service.SkillSummaryDC` to a Pydantic schema."""
    return SkillSummary(
        name=dc.name,
        description=dc.description,
        category=dc.category,
        applies_to_check_ids=dc.applies_to_check_ids,
        triggers=dc.triggers,
        source=dc.source,
        enabled=dc.enabled,
        version=dc.version,
    )


# ---------------------------------------------------------------------------
# List skills for a customer
# ---------------------------------------------------------------------------


@router.get(
    "/customers/{customer_id}/skills",
    response_model=dict,
    summary="List all skills for a customer",
)
async def list_skills(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return all built-in and custom skills for *customer_id*.

    # TODO: gate behind require_role("customer_admin")

    Args:
        customer_id: UUID of the owning customer.
        db: Injected async database session.

    Returns:
        ``{"skills": [SkillSummary, ...]}`` with effective enabled state.

    Raises:
        HTTPException: 404 when the customer does not exist.
    """
    customer = await customer_service.get_customer(db, customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found.",
        )

    summaries = await svc.list_available_skills(db, customer_id)
    return {"skills": [_skill_summary_from_dc(s) for s in summaries]}


# ---------------------------------------------------------------------------
# Create a custom skill
# ---------------------------------------------------------------------------


@router.post(
    "/customers/{customer_id}/skills",
    response_model=SkillRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a custom skill for a customer",
)
async def create_skill(
    customer_id: UUID,
    payload: SkillCreate,
    db: AsyncSession = Depends(get_db),
) -> SkillRead:
    """Create a new customer-authored skill.

    # TODO: gate behind require_role("customer_admin")

    Returns 400 if *payload.name* collides with a built-in skill or an
    existing custom skill for this customer.

    Args:
        customer_id: UUID of the owning customer.
        payload: Validated creation payload.
        db: Injected async database session.

    Returns:
        Serialised :class:`~backend.schemas.skill.SkillRead` of the new row.

    Raises:
        HTTPException: 404 when the customer does not exist.
        HTTPException: 400 on name collision with built-in or existing custom skill.
    """
    customer = await customer_service.get_customer(db, customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found.",
        )

    try:
        skill = await svc.create_skill(db, customer_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return SkillRead.model_validate(skill)


# ---------------------------------------------------------------------------
# Get skill content by name
# ---------------------------------------------------------------------------


@router.get(
    "/skills/{name}/content",
    response_model=dict,
    summary="Get the body content of a skill by slug",
)
async def get_skill_content(
    name: str,
    customer_id: UUID = Query(..., description="UUID of the requesting customer"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the markdown body for a skill by slug.

    # TODO: gate behind require_role("customer_admin")

    Custom skill rows take precedence over built-in skills of the same name.
    The ``source`` field indicates whether the body came from the built-in
    library or a custom DB row.

    Args:
        name: Skill slug.
        customer_id: UUID of the requesting customer (query parameter).
        db: Injected async database session.

    Returns:
        ``{"name": str, "content": str, "source": "builtin"|"custom"}``.

    Raises:
        HTTPException: 404 when the skill does not exist.
    """
    summary = await svc.get_skill_summary(db, customer_id, name)
    if summary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill {name!r} not found.",
        )

    try:
        content = await svc.get_skill_content(db, customer_id, name)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill {name!r} not found.",
        ) from exc

    return {"name": name, "content": content, "source": summary.source}


# ---------------------------------------------------------------------------
# Update a skill (custom full-update; built-in enabled-toggle only)
# ---------------------------------------------------------------------------


@router.put(
    "/customers/{customer_id}/skills/{name}",
    response_model=SkillRead,
    summary="Update a skill for a customer",
)
async def update_skill(
    customer_id: UUID,
    name: str,
    payload: SkillUpdate,
    db: AsyncSession = Depends(get_db),
) -> SkillRead:
    """Update a skill by slug.

    # TODO: gate behind require_role("customer_admin")

    For **custom** skills: all :class:`~backend.schemas.skill.SkillUpdate`
    fields are applied; ``version`` is bumped when any field other than
    ``enabled`` changes.

    For **built-in** skills: only ``enabled`` is accepted.  Supplying any other
    field returns 400.

    Args:
        customer_id: UUID of the owning customer.
        name: Skill slug.
        payload: Partial update payload.
        db: Injected async database session.

    Returns:
        Serialised :class:`~backend.schemas.skill.SkillRead`.

    Raises:
        HTTPException: 404 when the customer or skill does not exist.
        HTTPException: 400 when attempting to modify non-``enabled`` fields on
            a built-in skill.
    """
    customer = await customer_service.get_customer(db, customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found.",
        )

    try:
        result = await svc.update_skill(db, customer_id, name, payload)
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from exc

    # update_skill returns a SkillRead directly for built-in skills and a Skill
    # ORM instance for custom skills.
    if isinstance(result, SkillRead):
        return result
    return SkillRead.model_validate(result)


# ---------------------------------------------------------------------------
# Delete a custom skill
# ---------------------------------------------------------------------------


@router.delete(
    "/customers/{customer_id}/skills/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a custom skill for a customer",
)
async def delete_skill(
    customer_id: UUID,
    name: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a custom skill row.

    # TODO: gate behind require_role("customer_admin")

    Built-in skills cannot be deleted; use the update endpoint to disable them.

    Args:
        customer_id: UUID of the owning customer.
        name: Skill slug to delete.
        db: Injected async database session.

    Raises:
        HTTPException: 404 when the customer or skill does not exist.
        HTTPException: 400 when *name* refers to a built-in skill.
    """
    customer = await customer_service.get_customer(db, customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found.",
        )

    try:
        await svc.delete_skill(db, customer_id, name)
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from exc


# ---------------------------------------------------------------------------
# Per-connection skills_override
# ---------------------------------------------------------------------------


@router.put(
    "/connections/{connection_id}/skills-override",
    response_model=ConnectionResponse,
    summary="Set per-connection skills override map",
)
async def set_skills_override(
    connection_id: UUID,
    payload: SkillsOverridePayload,
    db: AsyncSession = Depends(get_db),
) -> ConnectionResponse:
    """Write a ``{skill_name: bool}`` override map to the platform connection.

    # TODO: gate behind require_role("customer_admin")

    Each entry in *payload.overrides* force-enables (``True``) or
    force-disables (``False``) the named skill for requests made via this
    connection, overriding customer-level toggles.  Skills absent from the
    dict inherit the customer default.  An empty dict clears all overrides.

    Args:
        connection_id: UUID of the :class:`~backend.models.customer.PlatformConnection`.
        payload: Override map payload.
        db: Injected async database session.

    Returns:
        The updated :class:`~backend.schemas.customer.ConnectionResponse`.

    Raises:
        HTTPException: 404 when the connection does not exist.
        HTTPException: 400 when any key in *payload.overrides* is not a skill
            known to the connection's customer.
    """
    try:
        connection = await svc.set_connection_override(db, connection_id, payload.overrides)
    except ValueError as exc:
        msg = str(exc)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from exc

    return ConnectionResponse.model_validate(connection)
