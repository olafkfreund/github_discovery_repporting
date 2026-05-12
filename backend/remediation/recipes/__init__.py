"""Aggregated remediation recipes from all 16 scanner domains.

``ALL_RECIPES`` is the merged dict of every check_id -> RemediationRecipe
across all domains.  The :mod:`backend.remediation.registry` module imports
this at first call and caches the result.
"""

from __future__ import annotations

from backend.remediation.recipe import RemediationRecipe
from backend.remediation.recipes.cicd import recipes as _cicd
from backend.remediation.recipes.code_quality import recipes as _code_quality
from backend.remediation.recipes.collaboration import recipes as _collaboration
from backend.remediation.recipes.compliance import recipes as _compliance
from backend.remediation.recipes.container_security import recipes as _container_security
from backend.remediation.recipes.dast import recipes as _dast
from backend.remediation.recipes.dependencies import recipes as _dependencies
from backend.remediation.recipes.disaster_recovery import recipes as _disaster_recovery
from backend.remediation.recipes.identity_access import recipes as _identity_access
from backend.remediation.recipes.migration import recipes as _migration
from backend.remediation.recipes.monitoring import recipes as _monitoring
from backend.remediation.recipes.platform_arch import recipes as _platform_arch
from backend.remediation.recipes.repo_governance import recipes as _repo_governance
from backend.remediation.recipes.sast import recipes as _sast
from backend.remediation.recipes.sdlc_process import recipes as _sdlc_process
from backend.remediation.recipes.secrets_mgmt import recipes as _secrets_mgmt

ALL_RECIPES: dict[str, RemediationRecipe] = {
    **_platform_arch,
    **_identity_access,
    **_repo_governance,
    **_cicd,
    **_secrets_mgmt,
    **_dependencies,
    **_sast,
    **_dast,
    **_container_security,
    **_code_quality,
    **_sdlc_process,
    **_compliance,
    **_collaboration,
    **_disaster_recovery,
    **_monitoring,
    **_migration,
}

__all__ = ["ALL_RECIPES"]
