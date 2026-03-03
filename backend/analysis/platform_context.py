from __future__ import annotations

"""Platform-specific context for AI analysis and report generation.

Maps :class:`~backend.models.enums.Platform` enum values to structured
dictionaries containing display names, feature terminology, and best-practice
references.  This allows the AI prompt and PDF templates to use the correct
platform-specific language (e.g. "merge requests" on GitLab vs "pull requests"
on GitHub).
"""

from typing import Any

from backend.models.enums import Platform

# ---------------------------------------------------------------------------
# Platform context mapping
# ---------------------------------------------------------------------------

_PLATFORM_CONTEXTS: dict[Platform, dict[str, Any]] = {
    Platform.github: {
        "display_name": "GitHub",
        "ci_cd_name": "GitHub Actions",
        "branch_protection_name": "Branch Protection Rules",
        "merge_mechanism": "pull requests",
        "security_suite": "GitHub Advanced Security (GHAS)",
        "sast_tool": "CodeQL",
        "dependency_tool": "Dependabot",
        "container_registry": "GitHub Container Registry (GHCR)",
        "secret_scanning": "GitHub Secret Scanning",
        "best_practices_references": [
            "Enable branch protection rules with required reviews on default branches",
            "Adopt GitHub Actions reusable workflows for CI/CD standardisation",
            "Enable Dependabot alerts and automatic security updates",
            "Use CodeQL or third-party SAST in GitHub Actions workflows",
            "Enable secret scanning and push protection for all repositories",
        ],
        "terminology": {
            "pipeline": "workflow",
            "merge_request": "pull request",
            "pipeline_file": ".github/workflows/*.yml",
            "approval_rules": "branch protection required reviewers",
            "project": "repository",
            "group": "organisation",
        },
    },
    Platform.gitlab: {
        "display_name": "GitLab",
        "ci_cd_name": "GitLab CI/CD",
        "branch_protection_name": "Protected Branches",
        "merge_mechanism": "merge requests",
        "security_suite": "GitLab Ultimate Security Dashboard",
        "sast_tool": "GitLab SAST",
        "dependency_tool": "GitLab Dependency Scanning",
        "container_registry": "GitLab Container Registry",
        "secret_scanning": "GitLab Secret Detection",
        "best_practices_references": [
            "Configure protected branches with merge request approvals",
            "Use GitLab CI/CD with include templates for pipeline standardisation",
            "Enable GitLab Dependency Scanning in CI pipelines",
            "Activate GitLab SAST and Secret Detection CI jobs",
            "Leverage GitLab Container Scanning for image vulnerability assessment",
        ],
        "terminology": {
            "pipeline": "pipeline",
            "merge_request": "merge request",
            "pipeline_file": ".gitlab-ci.yml",
            "approval_rules": "merge request approval rules",
            "project": "project",
            "group": "group",
        },
    },
    Platform.azure_devops: {
        "display_name": "Azure DevOps",
        "ci_cd_name": "Azure Pipelines",
        "branch_protection_name": "Branch Policies",
        "merge_mechanism": "pull requests",
        "security_suite": "Microsoft Defender for DevOps",
        "sast_tool": "Microsoft Security DevOps (MSDO)",
        "dependency_tool": "Azure Artifacts vulnerability alerts",
        "container_registry": "Azure Container Registry (ACR)",
        "secret_scanning": "Microsoft Defender for DevOps secret scanning",
        "best_practices_references": [
            "Configure branch policies with required reviewers on default branches",
            "Adopt Azure Pipelines YAML templates for pipeline standardisation",
            "Integrate Microsoft Security DevOps (MSDO) task for SAST and SCA",
            "Use Azure Artifacts with upstream sources and vulnerability alerts",
            "Enable service connection approvals and checks for deployment gates",
        ],
        "terminology": {
            "pipeline": "pipeline",
            "merge_request": "pull request",
            "pipeline_file": "azure-pipelines.yml",
            "approval_rules": "branch policy required reviewers",
            "project": "project",
            "group": "organisation",
        },
    },
}


def get_platform_context(platform: Platform) -> dict[str, Any]:
    """Return the full context dictionary for the given platform.

    Args:
        platform: The :class:`~backend.models.enums.Platform` value.

    Returns:
        A dictionary containing display names, feature terminology, and
        best-practice references for the platform.

    Raises:
        KeyError: If *platform* is not a recognised ``Platform`` member.
    """
    return _PLATFORM_CONTEXTS[platform]


def get_display_name(platform: Platform) -> str:
    """Return the human-readable display name for a platform.

    Args:
        platform: The :class:`~backend.models.enums.Platform` value.

    Returns:
        A string like ``"GitHub"``, ``"GitLab"``, or ``"Azure DevOps"``.
    """
    return str(_PLATFORM_CONTEXTS[platform]["display_name"])
