from __future__ import annotations

"""Tests that every built-in skill markdown file loads and validates correctly."""

from pathlib import Path

import pytest

from backend.scanners.registry import CATEGORY_DISPLAY_NAMES, get_scanner_registry
from backend.skills import _LIBRARY_DIR, _parse_skill_file, get_skill_registry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_CATEGORIES = set(CATEGORY_DISPLAY_NAMES.keys()) | {"general"}

_LIBRARY_PATH = Path(__file__).parent.parent.parent / "backend" / "skills" / "library"
_ALL_MD_FILES = sorted(_LIBRARY_PATH.glob("*.md")) if _LIBRARY_PATH.exists() else []


def _all_check_ids() -> set[str]:
    ids: set[str] = set()
    for cat in get_scanner_registry():
        for check in cat.checks:
            ids.add(check.check_id)
    return ids


# ---------------------------------------------------------------------------
# Per-file parametrised tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", _ALL_MD_FILES, ids=lambda p: p.stem)
def test_skill_file_parses_successfully(path: Path) -> None:
    """Each file in the library directory parses without error."""
    skill = _parse_skill_file(path)
    assert skill is not None
    assert skill.name == path.stem


@pytest.mark.parametrize("path", _ALL_MD_FILES, ids=lambda p: p.stem)
def test_skill_applies_to_are_valid_check_ids(path: Path) -> None:
    """Every applies_to entry in every skill file corresponds to a real check ID."""
    all_ids = _all_check_ids()
    skill = _parse_skill_file(path)
    for cid in skill.frontmatter.applies_to:
        assert cid in all_ids, f"Skill {skill.name!r} references unknown check_id {cid!r}"


@pytest.mark.parametrize("path", _ALL_MD_FILES, ids=lambda p: p.stem)
def test_skill_category_is_valid(path: Path) -> None:
    """The category field in every skill file is a recognised category key."""
    skill = _parse_skill_file(path)
    assert skill.frontmatter.category in _VALID_CATEGORIES, (
        f"Skill {skill.name!r} has unrecognised category {skill.frontmatter.category!r}"
    )


# ---------------------------------------------------------------------------
# Library-level assertions
# ---------------------------------------------------------------------------


def test_library_contains_15_skills() -> None:
    """The built-in skill library contains exactly 15 skills."""
    get_skill_registry.cache_clear()
    registry = get_skill_registry()
    assert len(registry) == 15, (
        f"Expected 15 skills, found {len(registry)}: {sorted(registry.keys())}"
    )


def test_skill_name_matches_file_stem() -> None:
    """For every skill in the registry, name matches the file stem."""
    get_skill_registry.cache_clear()
    registry = get_skill_registry()
    for name, skill in registry.items():
        assert skill.name == name
        assert (_LIBRARY_DIR / f"{name}.md").exists()
