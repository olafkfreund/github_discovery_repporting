"""Remediation recipe registry for the BPS-tool agent subsystem.

Provides :func:`~backend.remediation.registry.get_recipe_registry` and
:func:`~backend.remediation.registry.get_recipe` as the public API for
looking up per-check remediation recipes.
"""

from __future__ import annotations

from backend.remediation.recipe import ProviderCtx, RemediationRecipe, WorkspaceProto
from backend.remediation.registry import get_recipe, get_recipe_registry

__all__ = [
    "ProviderCtx",
    "RemediationRecipe",
    "WorkspaceProto",
    "get_recipe",
    "get_recipe_registry",
]
