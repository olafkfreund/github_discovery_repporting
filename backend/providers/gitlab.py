from __future__ import annotations

from backend.models.enums import Platform
from backend.schemas.platform_data import NormalizedRepo, OrgAssessmentData, RepoAssessmentData


class GitLabProvider:
    """Stub GitLab implementation of the PlatformProvider protocol.

    This class satisfies the structural interface required by
    :class:`~backend.providers.base.PlatformProvider` but raises
    :exc:`NotImplementedError` for every method.  It exists as a placeholder
    so that the factory and routing layers can reference it without failing at
    import time.

    Args:
        token: A GitLab personal access token or group access token.
        group: The GitLab group (or sub-group) path whose projects will be
            enumerated once the provider is implemented.
        base_url: Optional GitLab self-managed instance URL
            (e.g. ``"https://gitlab.example.com"``).  ``None`` targets
            ``gitlab.com``.
    """

    platform: Platform = Platform.gitlab

    def __init__(
        self,
        token: str,
        group: str,
        base_url: str | None = None,
    ) -> None:
        self._token = token
        self._group = group
        self._base_url = base_url

    async def validate_connection(self) -> bool:
        """Not yet implemented.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError("GitLab provider not yet implemented")

    async def list_repos(self) -> list[NormalizedRepo]:
        """Not yet implemented.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError("GitLab provider not yet implemented")

    async def get_repo_assessment_data(
        self,
        repo: NormalizedRepo,
    ) -> RepoAssessmentData:
        """Not yet implemented.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError("GitLab provider not yet implemented")

    async def get_org_assessment_data(self) -> OrgAssessmentData:
        """Not yet implemented.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError("GitLab provider not yet implemented")
