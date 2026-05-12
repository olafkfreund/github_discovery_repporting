"""Tests asserting that the four built-in AGENTS.md profile files exist,
meet minimum length requirements, and contain the expected section headers
and profile-specific content commitments.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_PROFILES_DIR = Path(__file__).parent.parent.parent / "backend" / "agent_profiles"

_SLUGS = ["standard", "banking", "public-sector", "strict"]

_REQUIRED_HEADERS = [
    "## Purpose",
    "## Authority and scope",
    "## Code review and PR conventions",
    "## Security and secrets",
    "## Build, test, and verification",
    "## Code style",
    "## Compliance",
    "## Skills and recipes",
    "## Escalation and refusal",
    "## Audit and logging",
]


@pytest.mark.parametrize("slug", _SLUGS)
def test_profile_file_exists(slug: str) -> None:
    """Each profile markdown file must exist at the expected path."""
    path = _PROFILES_DIR / f"{slug}.md"
    assert path.exists(), f"Profile file missing: {path}"
    assert path.is_file(), f"Expected a file, got something else: {path}"


@pytest.mark.parametrize("slug", _SLUGS)
def test_profile_file_minimum_length(slug: str) -> None:
    """Each profile file must be at least 80 lines long."""
    path = _PROFILES_DIR / f"{slug}.md"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) >= 80, f"{slug}.md has only {len(lines)} lines; expected >= 80"


@pytest.mark.parametrize("slug", _SLUGS)
@pytest.mark.parametrize("header", _REQUIRED_HEADERS)
def test_profile_file_contains_required_header(slug: str, header: str) -> None:
    """Each profile file must contain all eleven standard section headers."""
    content = (_PROFILES_DIR / f"{slug}.md").read_text(encoding="utf-8")
    assert header in content, f"{slug}.md is missing required section header: {header!r}"


def test_public_sector_contains_wcag() -> None:
    """Public Sector profile must document WCAG 2.2 AA commitment."""
    content = (_PROFILES_DIR / "public-sector.md").read_text(encoding="utf-8")
    assert "WCAG 2.2 AA" in content, "public-sector.md must reference WCAG 2.2 AA"


def test_banking_contains_req_031() -> None:
    """Banking profile must pin REQ-031 (hunk-only LLM input)."""
    content = (_PROFILES_DIR / "banking.md").read_text(encoding="utf-8")
    assert "REQ-031" in content, "banking.md must reference REQ-031 (hunk-only LLM input)"


def test_banking_contains_req_052() -> None:
    """Banking profile must pin REQ-052 (versioned prompts)."""
    content = (_PROFILES_DIR / "banking.md").read_text(encoding="utf-8")
    assert "REQ-052" in content, "banking.md must reference REQ-052 (versioned prompts)"


def test_strict_profile_contains_refusal_language() -> None:
    """Strict profile must use 'refuse' or 'refusal' to document defensive posture."""
    content = (_PROFILES_DIR / "strict.md").read_text(encoding="utf-8")
    assert "refuse" in content.lower() or "refusal" in content.lower(), (
        "strict.md must contain 'refuse' or 'refusal' language describing defensive posture"
    )
