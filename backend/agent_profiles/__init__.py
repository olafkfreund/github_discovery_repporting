"""Built-in AGENT instruction profiles + loader."""

from __future__ import annotations

import functools
import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProfileMetadata:
    """Immutable metadata descriptor for a built-in agent profile.

    Attributes:
        slug: URL-safe identifier used as a filename stem and foreign-key
            value on ``AgentInstructions.profile_slug``.
        display_name: Human-readable name shown in the UI profile picker.
        short_description: One-sentence summary shown alongside the name.
    """

    slug: str
    display_name: str
    short_description: str


_PROFILES_DIR = Path(__file__).parent


PROFILES_LIST: tuple[ProfileMetadata, ...] = (
    ProfileMetadata(
        slug="standard",
        display_name="Standard",
        short_description=("Sensible defaults for most software teams; human review required."),
    ),
    ProfileMetadata(
        slug="banking",
        display_name="Banking / Fintech",
        short_description=(
            "Stricter controls, audit-heavy, no auto-merge, change-control language."
        ),
    ),
    ProfileMetadata(
        slug="public-sector",
        display_name="Public Sector / Air-gapped",
        short_description=("WCAG 2.2 AA, plain English, no third-party data flows."),
    ),
    ProfileMetadata(
        slug="strict",
        display_name="Strict (Opt-in only)",
        short_description=("Agent refuses by default; every action requires per-finding approval."),
    ),
)


@functools.lru_cache(maxsize=1)
def get_profile_registry() -> dict[str, ProfileMetadata]:
    """Return ``{slug: ProfileMetadata}`` for all four shipped profiles.

    The result is cached for the lifetime of the process. The same dict
    object is returned on every call.

    Returns:
        A mapping from profile slug to :class:`ProfileMetadata`.
    """
    return {p.slug: p for p in PROFILES_LIST}


@functools.lru_cache(maxsize=8)
def load_profile_content(slug: str) -> tuple[str, str]:
    """Return ``(body, sha256_hex)`` for *slug*.

    The file is read from disk once per unique slug per process lifetime.
    Pattern mirrors :func:`backend.agents.prompts.load_prompt`.

    Args:
        slug: One of the four built-in profile slugs (``"standard"``,
            ``"banking"``, ``"public-sector"``, ``"strict"``).

    Returns:
        A 2-tuple of:
        - ``body``: Full UTF-8 text of the profile markdown file.
        - ``sha256_hex``: 64-character lowercase hex digest of the body,
          suitable for prompt-versioning audit (REQ-052).

    Raises:
        KeyError: If *slug* is not a known profile slug.
        FileNotFoundError: If the backing ``.md`` file is missing from the
            package (should not occur in a correctly installed package).
    """
    if slug not in get_profile_registry():
        raise KeyError(f"Unknown profile slug: {slug!r}")
    path = _PROFILES_DIR / f"{slug}.md"
    body = path.read_text(encoding="utf-8")
    sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return body, sha
