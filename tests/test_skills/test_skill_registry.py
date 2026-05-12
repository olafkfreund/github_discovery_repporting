from __future__ import annotations

"""Tests for the built-in skill registry loader."""


from backend.skills import get_skill_registry


def test_registry_returns_15_skills() -> None:
    """get_skill_registry returns exactly 15 built-in skills."""
    registry = get_skill_registry()
    assert len(registry) == 15


def test_registry_is_cached() -> None:
    """get_skill_registry returns the same dict object on repeated calls (lru_cache)."""
    first = get_skill_registry()
    second = get_skill_registry()
    assert first is second


def test_known_skill_exists() -> None:
    """The codeowners-team-mapping skill is present in the registry."""
    registry = get_skill_registry()
    assert "codeowners-team-mapping" in registry


def test_all_skills_have_sha256() -> None:
    """Every skill in the registry has a non-empty sha256 digest."""
    registry = get_skill_registry()
    for name, skill in registry.items():
        assert len(skill.sha256) == 64, f"Skill {name!r} has unexpected sha256 length"
        assert all(c in "0123456789abcdef" for c in skill.sha256), (
            f"Skill {name!r} sha256 contains non-hex characters"
        )


def test_all_skills_have_non_empty_body() -> None:
    """Every skill in the registry has a non-empty body."""
    registry = get_skill_registry()
    for name, skill in registry.items():
        assert skill.body.strip(), f"Skill {name!r} has an empty body"


def test_general_skill_has_empty_applies_to() -> None:
    """The general-pr-style skill has an empty applies_to list (always-on)."""
    registry = get_skill_registry()
    assert "general-pr-style" in registry
    assert registry["general-pr-style"].frontmatter.applies_to == []


def test_skills_have_valid_triggers() -> None:
    """Every skill trigger value is one of the allowed literals."""
    allowed = {"remediation", "scan_enrichment"}
    registry = get_skill_registry()
    for name, skill in registry.items():
        for trigger in skill.frontmatter.triggers:
            assert trigger in allowed, f"Skill {name!r} has unexpected trigger {trigger!r}"
