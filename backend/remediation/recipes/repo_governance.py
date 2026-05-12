"""Remediation recipes for the Repository Governance scanner domain.

First-class recipes:
- REPO-001: Default branch protected (provider-API change, no file edits)
- REPO-008: CODEOWNERS file present (file creation)
"""

from __future__ import annotations

from backend.remediation.recipe import RemediationRecipe
from backend.remediation.success_checks import repo001_success, repo008_success
from backend.scanners.registry import get_scanner_registry

_REGISTRY = get_scanner_registry()
_CATEGORY = "repo_governance"

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
    "REPO-001": RemediationRecipe(
        check_id="REPO-001",
        severity=_SEVERITY_MAP["REPO-001"],
        default_strategy="deterministic_template",
        file_glob_hints=[],
        max_files_changed=0,
        operator_prompt_path="REPO-001.md",
        requires_provider_api=True,
        success_check=repo001_success,
    ),
    "REPO-008": RemediationRecipe(
        check_id="REPO-008",
        severity=_SEVERITY_MAP["REPO-008"],
        default_strategy="deterministic_template",
        file_glob_hints=[".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"],
        max_files_changed=1,
        max_lines_changed=20,
        operator_prompt_path="REPO-008.md",
        success_check=repo008_success,
    ),
}

recipes: dict[str, RemediationRecipe] = {
    **{cid: _stub(cid) for cid in _SEVERITY_MAP if cid not in _FIRST_CLASS},
    **_FIRST_CLASS,
}
