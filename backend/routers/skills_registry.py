from __future__ import annotations

"""Read-only router for the built-in skill library catalogue.

Exposes the static skill registry (markdown files under
``backend/skills/library/``) without any customer context.  Used by the
in-app Help & Docs live Skills Library browser.
"""

from fastapi import APIRouter, HTTPException, status

from backend.schemas.skill import SkillRegistryEntry
from backend.skills import get_skill_registry

router = APIRouter(prefix="/api", tags=["skills-registry"])


@router.get(
    "/skills-registry",
    response_model=list[SkillRegistryEntry],
    summary="List built-in skill catalogue",
)
async def list_skills_registry() -> list[SkillRegistryEntry]:
    """Return every built-in skill from the static library.

    Read-only and customer-agnostic.  Does not include skill bodies; call
    :func:`get_skill_registry_content` to fetch the markdown body for a
    specific skill.

    Returns:
        A list of :class:`~backend.schemas.skill.SkillRegistryEntry`, one per
        ``.md`` file in ``backend/skills/library/``.
    """
    registry = get_skill_registry()
    return [
        SkillRegistryEntry(
            name=skill.name,
            description=skill.frontmatter.description,
            category=skill.frontmatter.category,
            applies_to=list(skill.frontmatter.applies_to),
            triggers=list(skill.frontmatter.triggers),
            version=skill.frontmatter.version,
        )
        for skill in registry.values()
    ]


@router.get(
    "/skills-registry/{name}/content",
    response_model=dict,
    summary="Get the markdown body of a built-in skill",
)
async def get_skill_registry_content(name: str) -> dict:
    """Return the markdown body of one built-in skill.

    Args:
        name: Skill slug (matches the source file stem).

    Returns:
        ``{"name": str, "body": str}`` — the slug and the raw markdown body.

    Raises:
        HTTPException: 404 when *name* is not a known built-in skill.
    """
    registry = get_skill_registry()
    skill = registry.get(name)
    if skill is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill {name!r} not found in built-in registry.",
        )
    return {"name": skill.name, "body": skill.body}
