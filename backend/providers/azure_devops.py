from __future__ import annotations

from backend.models.enums import Platform
from backend.schemas.platform_data import NormalizedRepo, OrgAssessmentData, RepoAssessmentData


class AzureDevOpsProvider:
    """Stub Azure DevOps implementation of the PlatformProvider protocol.

    This class satisfies the structural interface required by
    :class:`~backend.providers.base.PlatformProvider` but raises
    :exc:`NotImplementedError` for every method.  It exists as a placeholder
    so that the factory and routing layers can reference it without failing at
    import time.

    Args:
        token: A Personal Access Token (PAT) with at minimum ``Code (Read)``
            and ``Project and Team (Read)`` scopes.
        org_name: The Azure DevOps organisation name as it appears in the URL
            (e.g. ``"myorg"`` for ``dev.azure.com/myorg``).
        base_url: Optional override for the Azure DevOps REST API base URL.
            Useful for Azure DevOps Server (on-premises) deployments.
    """

    platform: Platform = Platform.azure_devops

    def __init__(
        self,
        token: str,
        org_name: str,
        base_url: str | None = None,
    ) -> None:
        self._token = token
        self._org_name = org_name
        self._base_url = base_url

    async def validate_connection(self) -> bool:
        """Not yet implemented.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError("Azure DevOps provider not yet implemented")

    async def list_repos(self) -> list[NormalizedRepo]:
        """Not yet implemented.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError("Azure DevOps provider not yet implemented")

    async def get_repo_assessment_data(
        self,
        repo: NormalizedRepo,
    ) -> RepoAssessmentData:
        """Not yet implemented.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError("Azure DevOps provider not yet implemented")

    async def get_org_assessment_data(self) -> OrgAssessmentData:
        """Not yet implemented.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError("Azure DevOps provider not yet implemented")
