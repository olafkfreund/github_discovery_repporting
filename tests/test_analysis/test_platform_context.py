from __future__ import annotations

"""Unit tests for the platform context module."""

import pytest

from backend.analysis.platform_context import get_display_name, get_platform_context
from backend.models.enums import Platform

# ---------------------------------------------------------------------------
# Required keys that every platform context dict must contain.
# ---------------------------------------------------------------------------

_REQUIRED_KEYS = {
    "display_name",
    "ci_cd_name",
    "branch_protection_name",
    "merge_mechanism",
    "security_suite",
    "sast_tool",
    "dependency_tool",
    "container_registry",
    "secret_scanning",
    "best_practices_references",
    "terminology",
}

_REQUIRED_TERMINOLOGY_KEYS = {
    "pipeline",
    "merge_request",
    "pipeline_file",
    "approval_rules",
    "project",
    "group",
}


class TestGetPlatformContext:
    """Tests for :func:`get_platform_context`."""

    @pytest.mark.parametrize("platform", list(Platform))
    def test_all_platforms_have_context(self, platform: Platform) -> None:
        ctx = get_platform_context(platform)
        assert isinstance(ctx, dict)

    @pytest.mark.parametrize("platform", list(Platform))
    def test_all_required_keys_present(self, platform: Platform) -> None:
        ctx = get_platform_context(platform)
        missing = _REQUIRED_KEYS - set(ctx.keys())
        assert not missing, f"Missing keys for {platform.value}: {missing}"

    @pytest.mark.parametrize("platform", list(Platform))
    def test_terminology_has_required_keys(self, platform: Platform) -> None:
        ctx = get_platform_context(platform)
        terminology = ctx["terminology"]
        missing = _REQUIRED_TERMINOLOGY_KEYS - set(terminology.keys())
        assert not missing, f"Missing terminology keys for {platform.value}: {missing}"

    @pytest.mark.parametrize("platform", list(Platform))
    def test_best_practices_is_nonempty_list(self, platform: Platform) -> None:
        ctx = get_platform_context(platform)
        bp = ctx["best_practices_references"]
        assert isinstance(bp, list)
        assert len(bp) >= 3

    @pytest.mark.parametrize("platform", list(Platform))
    def test_display_name_is_nonempty_string(self, platform: Platform) -> None:
        ctx = get_platform_context(platform)
        assert isinstance(ctx["display_name"], str)
        assert len(ctx["display_name"]) > 0


class TestGetDisplayName:
    """Tests for :func:`get_display_name`."""

    def test_github_display_name(self) -> None:
        assert get_display_name(Platform.github) == "GitHub"

    def test_gitlab_display_name(self) -> None:
        assert get_display_name(Platform.gitlab) == "GitLab"

    def test_azure_devops_display_name(self) -> None:
        assert get_display_name(Platform.azure_devops) == "Azure DevOps"
