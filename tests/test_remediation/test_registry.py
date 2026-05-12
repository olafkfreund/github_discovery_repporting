"""Tests for backend.remediation.registry."""

from __future__ import annotations

import pytest

from backend.remediation.registry import get_recipe, get_recipe_registry
from backend.scanners.registry import get_scanner_registry


def _total_scanner_checks() -> int:
    """Return the total number of checks registered across all scanner categories."""
    return sum(len(cat.checks) for cat in get_scanner_registry())


class TestGetRecipeRegistry:
    def test_registry_length_matches_scanner_total(self) -> None:
        """Registry must contain exactly as many entries as scanner checks."""
        registry = get_recipe_registry()
        expected = _total_scanner_checks()
        assert len(registry) == expected, (
            f"Expected {expected} recipes, got {len(registry)}. "
            "If scanner checks changed, re-run the suite."
        )

    def test_registry_length_is_169(self) -> None:
        """Hard-coded sentinel: the scanner suite currently defines 169 checks."""
        assert len(get_recipe_registry()) == 169

    def test_every_scanner_check_has_a_recipe(self) -> None:
        """Every check_id in the scanner registry must have a corresponding recipe."""
        registry = get_recipe_registry()
        for cat in get_scanner_registry():
            for check in cat.checks:
                assert check.check_id in registry, (
                    f"check_id {check.check_id!r} from category {cat.category!r} "
                    "has no recipe in the remediation registry."
                )

    def test_registry_is_cached(self) -> None:
        """Calling get_recipe_registry() twice must return the identical dict object."""
        r1 = get_recipe_registry()
        r2 = get_recipe_registry()
        assert r1 is r2, "get_recipe_registry() should return a cached instance."


class TestGetRecipe:
    def test_repo001_is_first_class(self) -> None:
        recipe = get_recipe("REPO-001")
        assert recipe.default_strategy == "deterministic_template"
        assert recipe.requires_provider_api is True
        assert recipe.success_check is not None
        assert recipe.operator_prompt_path == "REPO-001.md"
        assert recipe.max_files_changed == 0

    def test_repo008_is_first_class(self) -> None:
        recipe = get_recipe("REPO-008")
        assert recipe.default_strategy == "deterministic_template"
        assert recipe.requires_provider_api is False
        assert recipe.success_check is not None
        assert recipe.operator_prompt_path == "REPO-008.md"
        assert ".github/CODEOWNERS" in recipe.file_glob_hints

    def test_sec003_is_first_class(self) -> None:
        """SEC-003 is the actual check_id for push-protection / gitleaks."""
        recipe = get_recipe("SEC-003")
        assert recipe.default_strategy == "deterministic_template"
        assert recipe.success_check is not None
        assert recipe.operator_prompt_path == "SEC-003.md"

    def test_cicd001_is_first_class(self) -> None:
        recipe = get_recipe("CICD-001")
        assert recipe.default_strategy == "deterministic_template"
        assert recipe.success_check is not None
        assert recipe.operator_prompt_path == "CICD-001.md"

    def test_cq004_is_first_class(self) -> None:
        recipe = get_recipe("CQ-004")
        assert recipe.default_strategy == "deterministic_template"
        assert recipe.success_check is not None
        assert recipe.operator_prompt_path == "CQ-004.md"

    def test_stub_recipe_has_llm_freeform_strategy(self) -> None:
        """An arbitrary stub check should have default llm_freeform strategy."""
        recipe = get_recipe("PLAT-001")
        assert recipe.default_strategy == "llm_freeform"
        assert recipe.success_check is None
        assert recipe.operator_prompt_path == "generic.md"

    def test_stub_recipe_requires_no_provider_api(self) -> None:
        recipe = get_recipe("PLAT-001")
        assert recipe.requires_provider_api is False

    def test_unknown_check_raises_key_error(self) -> None:
        with pytest.raises(KeyError):
            get_recipe("UNKNOWN-999")

    def test_all_first_class_recipes_have_correct_check_ids(self) -> None:
        """check_id on the recipe object must match the dict key."""
        for check_id in ("REPO-001", "REPO-008", "SEC-003", "CICD-001", "CQ-004"):
            recipe = get_recipe(check_id)
            assert recipe.check_id == check_id

    def test_all_stub_recipes_have_correct_check_ids(self) -> None:
        """Every recipe's check_id field must match its key in the registry."""
        for check_id, recipe in get_recipe_registry().items():
            assert recipe.check_id == check_id, (
                f"Recipe at key {check_id!r} has check_id={recipe.check_id!r}"
            )

    def test_all_recipes_have_severity_set(self) -> None:
        """No recipe should have a None severity."""
        for check_id, recipe in get_recipe_registry().items():
            assert recipe.severity is not None, f"Recipe {check_id!r} has no severity."
