from __future__ import annotations

# Re-export every public symbol from the canonical schema location so that
# provider implementations can use a single, short import path:
#
#     from backend.providers.models import NormalizedRepo, RepoAssessmentData
#
# instead of the longer:
#
#     from backend.schemas.platform_data import NormalizedRepo, RepoAssessmentData
from backend.schemas.platform_data import *  # noqa: F401, F403
