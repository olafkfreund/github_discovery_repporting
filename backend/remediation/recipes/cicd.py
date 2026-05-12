"""Remediation recipes for the CI/CD Pipeline scanner domain.

First-class recipes:
- CICD-001: CI pipeline exists (CodeQL workflow creation)
"""

from __future__ import annotations

from backend.remediation.recipe import RemediationRecipe
from backend.remediation.success_checks import cicd001_success
from backend.scanners.registry import get_scanner_registry

_REGISTRY = get_scanner_registry()
_CATEGORY = "cicd"

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
    "CICD-001": RemediationRecipe(
        check_id="CICD-001",
        severity=_SEVERITY_MAP["CICD-001"],
        default_strategy="deterministic_template",
        file_glob_hints=[".github/workflows/codeql.yml"],
        max_files_changed=1,
        max_lines_changed=50,
        operator_prompt_path="CICD-001.md",
        success_check=cicd001_success,
    ),
}

recipes: dict[str, RemediationRecipe] = {
    **{cid: _stub(cid) for cid in _SEVERITY_MAP if cid not in _FIRST_CLASS},
    **_FIRST_CLASS,
}
