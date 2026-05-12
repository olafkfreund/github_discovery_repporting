"""Thin service shim for built-in agent profile access.

Delegates to :mod:`backend.agent_profiles` so that routers and other
service consumers have a stable import path that is independent of the
underlying registry implementation.
"""

from __future__ import annotations

from backend.agent_profiles import (
    ProfileMetadata,
    get_profile_registry,
    load_profile_content,
)


def list_profiles() -> list[ProfileMetadata]:
    """Return all built-in profiles as an ordered list.

    Order follows :data:`backend.agent_profiles.PROFILES_LIST`.

    Returns:
        A list of :class:`~backend.agent_profiles.ProfileMetadata` instances,
        one per built-in profile.
    """
    return list(get_profile_registry().values())


def get_profile_content(slug: str) -> str:
    """Return the markdown body for *slug*.

    Args:
        slug: One of the four built-in profile slugs (``"standard"``,
            ``"banking"``, ``"public-sector"``, ``"strict"``).

    Returns:
        The full UTF-8 markdown text of the profile file.

    Raises:
        KeyError: If *slug* is not a known profile slug.
    """
    body, _sha = load_profile_content(slug)
    return body
