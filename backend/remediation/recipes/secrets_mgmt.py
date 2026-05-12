"""Remediation recipes for the Secrets Management scanner domain.

First-class recipes:
- SEC-003: Push protection enabled (gitleaks config creation)
"""

from __future__ import annotations

from backend.remediation.recipe import RemediationRecipe
from backend.remediation.success_checks import secrets003_success
from backend.scanners.registry import get_scanner_registry

_REGISTRY = get_scanner_registry()
_CATEGORY = "secrets_mgmt"

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
    "SEC-003": RemediationRecipe(
        check_id="SEC-003",
        severity=_SEVERITY_MAP["SEC-003"],
        default_strategy="deterministic_template",
        file_glob_hints=[".gitleaks.toml"],
        max_files_changed=1,
        max_lines_changed=30,
        operator_prompt_path="SEC-003.md",
        success_check=secrets003_success,
    ),
}

recipes: dict[str, RemediationRecipe] = {
    **{cid: _stub(cid) for cid in _SEVERITY_MAP if cid not in _FIRST_CLASS},
    **_FIRST_CLASS,
}
