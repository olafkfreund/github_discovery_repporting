from __future__ import annotations

"""DORA (DevOps Research and Assessment) metrics reference data.

The four key DORA metrics are:

* **Deployment Frequency** — how often an organisation successfully releases
  to production.
* **Lead Time for Changes** — the time it takes a commit to get into
  production.
* **Change Failure Rate** — the percentage of deployments causing a failure
  in production.
* **Mean Time to Restore (MTTR)** — how long it takes to recover from a
  failure in production.

The ``score_threshold`` values map our internal 0–100 scoring system onto the
four DORA performance bands so that any :class:`~backend.models.scan.Scan`
result can be classified without manual comparison.
"""

DORA_LEVELS: dict[str, dict[str, object]] = {
    "elite": {
        "deployment_frequency": "On-demand (multiple deploys per day)",
        "lead_time": "Less than one hour",
        "change_failure_rate": "0-15%",
        "mttr": "Less than one hour",
        "score_threshold": 85,
    },
    "high": {
        "deployment_frequency": "Between once per day and once per week",
        "lead_time": "Between one day and one week",
        "change_failure_rate": "16-30%",
        "mttr": "Less than one day",
        "score_threshold": 70,
    },
    "medium": {
        "deployment_frequency": "Between once per week and once per month",
        "lead_time": "Between one week and one month",
        "change_failure_rate": "31-45%",
        "mttr": "Between one day and one week",
        "score_threshold": 50,
    },
    "low": {
        "deployment_frequency": "Between once per month and once per six months",
        "lead_time": "Between one month and six months",
        "change_failure_rate": "46-60%",
        "mttr": "More than one week",
        "score_threshold": 0,
    },
}


def classify_dora_level(overall_score: float) -> str:
    """Return the DORA performance level for a given overall assessment score.

    Levels are evaluated from highest to lowest threshold so that the first
    match is always the most favourable level the score qualifies for.

    Args:
        overall_score: A float in the range ``[0.0, 100.0]`` representing the
            weighted overall score produced by
            :meth:`~backend.scanners.orchestrator.ScanOrchestrator.calculate_overall_score`.

    Returns:
        One of ``"elite"``, ``"high"``, ``"medium"``, or ``"low"``.

    Examples:
        >>> classify_dora_level(90.0)
        'elite'
        >>> classify_dora_level(72.5)
        'high'
        >>> classify_dora_level(55.0)
        'medium'
        >>> classify_dora_level(30.0)
        'low'
    """
    for level in ("elite", "high", "medium", "low"):
        threshold = DORA_LEVELS[level]["score_threshold"]
        if overall_score >= threshold:  # type: ignore[operator]
            return level
    # Unreachable: "low" has score_threshold=0, so every finite float matches above.
    raise AssertionError(f"classify_dora_level: no level matched score {overall_score!r}")
