from __future__ import annotations

"""CIS Software Supply Chain Security benchmark mappings.

The `CIS Software Supply Chain Security Guide
<https://www.cisecurity.org/benchmark/software-supply-chain-security>`_
organises supply-chain controls into five domains.  :data:`CIS_CONTROLS` maps
each domain to the internal check IDs that satisfy its requirements.

Use :func:`calculate_cis_compliance` to produce a structured compliance report
suitable for inclusion in a generated assessment report.
"""

CIS_CONTROLS: dict[str, dict[str, object]] = {
    "source-code": {
        "description": "Source Code Management",
        "checks": ["SEC-001", "SEC-002", "SEC-006", "COLLAB-001"],
    },
    "build-pipelines": {
        "description": "Build Pipelines",
        "checks": ["CICD-001", "CICD-003", "CICD-005"],
    },
    "dependencies": {
        "description": "Dependencies",
        "checks": ["SEC-010", "SEC-011", "SEC-012"],
    },
    "artifacts": {
        "description": "Artifacts",
        "checks": ["SEC-020", "SEC-007"],
    },
    "deployment": {
        "description": "Deployment",
        "checks": ["CICD-006", "CICD-007"],
    },
}


def calculate_cis_compliance(
    passed_check_ids: set[str],
) -> dict[str, dict[str, object]]:
    """Return CIS control-domain compliance status for *passed_check_ids*.

    For each domain the returned dict contains:

    * ``description`` — human-readable domain name.
    * ``total``       — number of checks in this domain.
    * ``passed``      — number of those checks present in *passed_check_ids*.
    * ``percentage``  — ``(passed / total) * 100``, or ``0`` when total is 0.
    * ``compliant``   — ``True`` only when every check in the domain is passed.

    Args:
        passed_check_ids: The set of check IDs that produced a ``passed``
            result during the scan.

    Returns:
        A dict keyed by CIS domain identifier (e.g. ``"source-code"``) whose
        values contain the compliance breakdown described above.

    Examples:
        >>> result = calculate_cis_compliance({"SEC-001", "SEC-002", "SEC-006", "COLLAB-001"})
        >>> result["source-code"]["compliant"]
        True
        >>> result["build-pipelines"]["compliant"]
        False
    """
    result: dict[str, dict[str, object]] = {}
    for control_id, control in CIS_CONTROLS.items():
        checks: list[str] = control["checks"]  # type: ignore[assignment]
        passed = [c for c in checks if c in passed_check_ids]
        total = len(checks)
        result[control_id] = {
            "description": control["description"],
            "total": total,
            "passed": len(passed),
            "percentage": (len(passed) / total * 100) if total else 0,
            "compliant": len(passed) == total,
        }
    return result
