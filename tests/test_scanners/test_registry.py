"""Tests for the scanner registry module."""
from __future__ import annotations

from backend.scanners.registry import (
    CATEGORY_DISPLAY_NAMES,
    THRESHOLD_REGISTRY,
    get_scanner_registry,
    registry_to_dicts,
)


class TestScannerRegistry:
    """Verify the auto-generated scanner registry is correct."""

    def test_returns_16_categories(self) -> None:
        registry = get_scanner_registry()
        assert len(registry) == 16

    def test_all_categories_have_checks(self) -> None:
        registry = get_scanner_registry()
        for cat in registry:
            assert len(cat.checks) > 0, f"{cat.category} has no checks"

    def test_total_check_count(self) -> None:
        """The codebase has ~169 checks across all categories."""
        registry = get_scanner_registry()
        total = sum(len(cat.checks) for cat in registry)
        assert total >= 150, f"Expected ~169 checks, got {total}"

    def test_org_and_repo_scopes(self) -> None:
        registry = get_scanner_registry()
        scopes = {cat.scope for cat in registry}
        assert "org" in scopes
        assert "repo" in scopes
        org_cats = [cat for cat in registry if cat.scope == "org"]
        assert len(org_cats) == 2  # platform_arch, identity_access

    def test_weights_sum_to_one(self) -> None:
        registry = get_scanner_registry()
        total = sum(cat.weight for cat in registry)
        assert abs(total - 1.0) < 0.01, f"Weights sum to {total}, expected ~1.0"

    def test_threshold_checks_are_present(self) -> None:
        """Every check_id in THRESHOLD_REGISTRY must appear in the registry."""
        registry = get_scanner_registry()
        all_check_ids = set()
        for cat in registry:
            for check in cat.checks:
                all_check_ids.add(check.check_id)

        for check_id in THRESHOLD_REGISTRY:
            assert check_id in all_check_ids, f"{check_id} not found in registry"

    def test_threshold_info_populated(self) -> None:
        """Checks with entries in THRESHOLD_REGISTRY must have thresholds in the registry."""
        registry = get_scanner_registry()
        for cat in registry:
            for check in cat.checks:
                if check.check_id in THRESHOLD_REGISTRY:
                    expected_keys = set(THRESHOLD_REGISTRY[check.check_id].keys())
                    actual_keys = {t.key for t in check.thresholds}
                    assert expected_keys == actual_keys, (
                        f"{check.check_id}: threshold keys mismatch: {expected_keys} vs {actual_keys}"
                    )

    def test_display_names_cover_all_categories(self) -> None:
        registry = get_scanner_registry()
        for cat in registry:
            assert cat.display_name, f"{cat.category} has no display name"
            assert cat.category in CATEGORY_DISPLAY_NAMES

    def test_registry_to_dicts(self) -> None:
        registry = get_scanner_registry()
        dicts = registry_to_dicts(registry)
        assert isinstance(dicts, list)
        assert len(dicts) == 16
        first = dicts[0]
        assert "category" in first
        assert "checks" in first
        assert "weight" in first


class TestThresholdHelper:
    """Verify that BaseScanner._threshold() works correctly."""

    def test_returns_default_when_no_config(self) -> None:
        from backend.scanners.base import BaseScanner

        scanner = BaseScanner()
        assert scanner._threshold("CICD-008", "pass_threshold", 0.95) == 0.95

    def test_returns_override_from_config(self) -> None:
        from backend.scanners.base import BaseScanner

        scanner = BaseScanner()
        scanner._check_config = {
            "CICD-008": {"thresholds": {"pass_threshold": 0.90}},
        }
        assert scanner._threshold("CICD-008", "pass_threshold", 0.95) == 0.90

    def test_returns_default_for_missing_key(self) -> None:
        from backend.scanners.base import BaseScanner

        scanner = BaseScanner()
        scanner._check_config = {
            "CICD-008": {"thresholds": {"pass_threshold": 0.90}},
        }
        # warning_threshold is not in config, should fall back to default
        assert scanner._threshold("CICD-008", "warning_threshold", 0.80) == 0.80
