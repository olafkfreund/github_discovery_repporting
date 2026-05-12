"""Remediation recipe registry.

Aggregates all per-domain recipe dicts into a single immutable mapping of
``check_id -> RemediationRecipe``.  The registry is populated lazily on first
call and cached for the process lifetime via :func:`functools.lru_cache`.

Usage::

    from backend.remediation.registry import get_recipe, get_recipe_registry

    recipe = get_recipe("REPO-001")   # first-class recipe
    stub   = get_recipe("PLAT-001")   # llm_freeform stub
"""

from __future__ import annotations

import functools

from backend.remediation.recipe import RemediationRecipe


@functools.lru_cache(maxsize=1)
def get_recipe_registry() -> dict[str, RemediationRecipe]:
    """Return the immutable map of ``check_id -> RemediationRecipe``.

    Populated lazily on first call by merging all 16 domain recipe dicts.
    Result is cached for the process lifetime — the underlying scanner-registry
    walk only happens once.

    Returns:
        A dict mapping every scanner check_id to its corresponding
        :class:`~backend.remediation.recipe.RemediationRecipe`.
    """
    # Import lazily to avoid import-time side-effects during module loading.
    from backend.remediation.recipes import ALL_RECIPES  # noqa: PLC0415

    return dict(ALL_RECIPES)


def get_recipe(check_id: str) -> RemediationRecipe:
    """Look up the :class:`~backend.remediation.recipe.RemediationRecipe` for *check_id*.

    Args:
        check_id: A scanner check identifier such as ``"REPO-001"`` or ``"PLAT-003"``.

    Returns:
        The corresponding :class:`~backend.remediation.recipe.RemediationRecipe`.

    Raises:
        KeyError: If *check_id* is not registered in the recipe registry.
    """
    return get_recipe_registry()[check_id]
