from __future__ import annotations

"""SLSA (Supply-chain Levels for Software Artifacts) build-level reference data.

SLSA (pronounced "salsa") defines four incremental levels of supply-chain
security guarantees for software build processes.  Each higher level requires
that all checks from lower levels are also satisfied.

:data:`SLSA_LEVELS` maps each integer level (1–3) to a human-readable name,
description, and the set of internal check IDs whose presence indicates the
level's requirements are met.

Note: SLSA Level 4 is intentionally omitted — it requires hermetic,
reproducible builds that cannot be reliably inferred from repository metadata
alone.
"""

SLSA_LEVELS: dict[int, dict[str, object]] = {
    1: {
        "name": "Build L1",
        "description": "Provenance exists",
        "required_checks": ["CICD-001"],
    },
    2: {
        "name": "Build L2",
        "description": "Hosted build platform",
        "required_checks": ["CICD-001", "CICD-002"],
    },
    3: {
        "name": "Build L3",
        "description": "Hardened builds",
        "required_checks": ["CICD-001", "CICD-002", "SEC-022", "SEC-005"],
    },
}


def calculate_slsa_level(passed_check_ids: set[str]) -> int:
    """Return the highest SLSA build level achieved by *passed_check_ids*.

    Levels are evaluated in ascending order.  A level is achieved only when
    **all** of its ``required_checks`` are present in *passed_check_ids*.

    Args:
        passed_check_ids: The set of check IDs that produced a ``passed``
            result during the scan.

    Returns:
        An integer in ``{0, 1, 2, 3}``.  ``0`` means no SLSA level is
        satisfied.

    Examples:
        >>> calculate_slsa_level({"CICD-001"})
        1
        >>> calculate_slsa_level({"CICD-001", "CICD-002"})
        2
        >>> calculate_slsa_level({"CICD-001", "CICD-002", "SEC-022", "SEC-005"})
        3
        >>> calculate_slsa_level(set())
        0
    """
    highest = 0
    for level, data in SLSA_LEVELS.items():
        required: list[str] = data["required_checks"]  # type: ignore[assignment]
        if all(cid in passed_check_ids for cid in required):
            highest = level
    return highest
