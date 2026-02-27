from __future__ import annotations

"""OpenSSF Scorecard benchmark mapping.

The `OpenSSF Scorecard <https://securityscorecards.dev/>`_ project provides an
automated way to assess the security posture of open-source projects across a
standardised set of categories (called *checks* in Scorecard terminology).

:data:`OPENSSF_MAPPING` links each Scorecard category to the internal check
IDs used by our scanner pipeline.  A category is considered *satisfied* when
every mapped check ID appears in the caller's set of passed checks.

Updated for the 16-domain scanner architecture.
"""

OPENSSF_MAPPING: dict[str, list[str]] = {
    "Branch-Protection": ["REPO-001", "REPO-002", "REPO-003", "REPO-005", "REPO-006"],
    "Code-Review": ["SDLC-003", "REPO-002"],
    "CI-Tests": ["CICD-001", "CICD-003"],
    "Vulnerabilities": ["DEP-002", "DEP-003"],
    "Dependency-Update-Tool": ["DEP-001"],
    "Security-Policy": ["COMP-004"],
    "Signed-Releases": ["REPO-007"],
    "Token-Permissions": ["IAM-008"],
    "SAST": ["CICD-005", "SAST-001"],
    "License": ["COMP-001"],
}


def calculate_openssf_alignment(passed_check_ids: set[str]) -> dict[str, bool]:
    """Return which OpenSSF Scorecard categories are satisfied by *passed_check_ids*.

    A category is ``True`` only when **all** of its required check IDs are
    present in *passed_check_ids*.  Categories whose required checks are only
    partially present yield ``False``.

    Args:
        passed_check_ids: The set of check IDs (e.g. ``{"REPO-001", "CICD-001"}``)
            that produced a ``passed`` result during the scan.

    Returns:
        A mapping of OpenSSF category name to a boolean indicating whether the
        category is fully satisfied.

    Examples:
        >>> calculate_openssf_alignment({"COMP-001"})
        {'Branch-Protection': False, ..., 'License': True}
    """
    return {
        category: all(check_id in passed_check_ids for check_id in check_ids)
        for category, check_ids in OPENSSF_MAPPING.items()
    }
