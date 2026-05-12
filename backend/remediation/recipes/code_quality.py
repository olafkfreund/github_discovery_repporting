"""Remediation recipes for the Code Quality scanner domain.

First-class recipes:
- CQ-004: Code coverage > 60% (coverage workflow creation)
"""

from __future__ import annotations

from backend.remediation.recipe import RemediationRecipe
from backend.remediation.success_checks import cq004_success
from backend.scanners.registry import get_scanner_registry

_REGISTRY = get_scanner_registry()
_CATEGORY = "code_quality"

_SEVERITY_MAP = {
    c.check_id: c.severity for cat in _REGISTRY for c in cat.checks if cat.category == _CATEGORY
}


def _stub(check_id: str) -> RemediationRecipe:
    return RemediationRecipe(
        check_id=check_id,
        severity=_SEVERITY_MAP[check_id],
        default_strategy="llm_freeform",
        operator_prompt_path="generic.md",
    )


_FIRST_CLASS: dict[str, RemediationRecipe] = {
    "CQ-004": RemediationRecipe(
        check_id="CQ-004",
        severity=_SEVERITY_MAP["CQ-004"],
        default_strategy="deterministic_template",
        file_glob_hints=[
            ".github/workflows/coverage.yml",
            ".github/workflows/coverage.yaml",
        ],
        max_files_changed=1,
        max_lines_changed=50,
        operator_prompt_path="CQ-004.md",
        success_check=cq004_success,
    ),
}

recipes: dict[str, RemediationRecipe] = {
    **{cid: _stub(cid) for cid in _SEVERITY_MAP if cid not in _FIRST_CLASS},
    **_FIRST_CLASS,
}
