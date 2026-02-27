from __future__ import annotations

from typing import Protocol, runtime_checkable

from backend.models.enums import Platform
from backend.schemas.platform_data import NormalizedRepo, RepoAssessmentData


@runtime_checkable
class PlatformProvider(Protocol):
    """Structural interface that every DevOps platform provider must satisfy.

    Implementations are discovered at runtime via the factory in
    :mod:`backend.providers.factory`.  The protocol is marked
    ``@runtime_checkable`` so ``isinstance`` checks work in tests.

    All methods are ``async`` because external API calls must not block the
    event loop.  Synchronous SDKs (e.g. PyGithub) should wrap their calls
    with :func:`asyncio.get_event_loop().run_in_executor`.

    Class attributes
    ----------------
    platform:
        The :class:`~backend.models.enums.Platform` enum value that uniquely
        identifies this provider implementation.
    """

    platform: Platform

    async def validate_connection(self) -> bool:
        """Verify that the stored credentials are valid and the target is reachable.

        Returns:
            ``True`` if the connection is healthy, ``False`` otherwise.
            Implementations should never raise on auth failures; instead they
            should catch those exceptions and return ``False``.
        """
        ...

    async def list_repos(self) -> list[NormalizedRepo]:
        """Enumerate every repository visible to the authenticated principal.

        Returns:
            A list of :class:`~backend.schemas.platform_data.NormalizedRepo`
            instances representing all discoverable repositories.
        """
        ...

    async def get_repo_assessment_data(
        self,
        repo: NormalizedRepo,
    ) -> RepoAssessmentData:
        """Collect all assessment data for a single repository.

        This is the primary data-collection entry point used by the scanning
        pipeline.  Implementations are expected to fetch branch protection
        rules, CI workflow definitions, security feature states, file presence
        checks, and recent pull-request metadata.

        Args:
            repo: A :class:`~backend.schemas.platform_data.NormalizedRepo`
                previously returned by :meth:`list_repos`.

        Returns:
            A fully populated
            :class:`~backend.schemas.platform_data.RepoAssessmentData`
            instance ready for the analysis pipeline.
        """
        ...
