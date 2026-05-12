from __future__ import annotations

"""Read-only endpoints exposing the four built-in agent profile presets."""

from fastapi import APIRouter, HTTPException, status

from backend.agent_profiles import get_profile_registry, load_profile_content
from backend.schemas.agent_instructions import (
    AgentProfile,
    AgentProfileContent,
    AgentProfilesResponse,
)

router = APIRouter(prefix="/api/agent-profiles", tags=["agent-profiles"])


@router.get("/", response_model=AgentProfilesResponse)
async def list_profiles() -> AgentProfilesResponse:
    """List the four shipped agent profiles for the picker UI.

    Returns:
        :class:`~backend.schemas.agent_instructions.AgentProfilesResponse`
        containing one :class:`~backend.schemas.agent_instructions.AgentProfile`
        entry per built-in profile slug.
    """
    registry = get_profile_registry()
    return AgentProfilesResponse(
        profiles=[
            AgentProfile(
                slug=p.slug,
                display_name=p.display_name,
                short_description=p.short_description,
            )
            for p in registry.values()
        ]
    )


@router.get("/{slug}/content", response_model=AgentProfileContent)
async def get_profile(slug: str) -> AgentProfileContent:
    """Return the full markdown body for a named agent profile.

    Args:
        slug: One of the four built-in profile slugs (``"standard"``,
            ``"banking"``, ``"public-sector"``, ``"strict"``).

    Returns:
        :class:`~backend.schemas.agent_instructions.AgentProfileContent`
        with ``slug`` and the full UTF-8 ``body`` of the profile file.

    Raises:
        HTTPException: 404 when *slug* does not match any built-in profile.
    """
    try:
        body, _sha = load_profile_content(slug)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown agent profile: {slug!r}",
        ) from exc
    return AgentProfileContent(slug=slug, body=body)
