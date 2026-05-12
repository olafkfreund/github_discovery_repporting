"""Remediation recipes for the Dynamic Application Security Testing scanner domain."""

from __future__ import annotations

from backend.remediation.recipe import RemediationRecipe
from backend.scanners.registry import get_scanner_registry

_REGISTRY = get_scanner_registry()
_CATEGORY = "dast"

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


recipes: dict[str, RemediationRecipe] = {cid: _stub(cid) for cid in _SEVERITY_MAP}
