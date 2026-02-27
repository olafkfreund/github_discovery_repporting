from __future__ import annotations

import json

from backend.models.customer import PlatformConnection
from backend.models.enums import Platform
from backend.providers.base import PlatformProvider
from backend.services.secrets_service import secrets_service


def create_provider(connection: PlatformConnection) -> PlatformProvider:
    """Instantiate the correct :class:`~backend.providers.base.PlatformProvider`
    for the given *connection*.

    Credentials are decrypted from ``connection.credentials_encrypted`` and
    parsed as JSON.  The expected shape is platform-specific:

    * **GitHub** — ``{"token": "<pat>"}``
    * **GitLab** — ``{"token": "<pat>"}``  *(not yet implemented)*
    * **Azure DevOps** — ``{"token": "<pat>"}``  *(not yet implemented)*

    Args:
        connection: A :class:`~backend.models.customer.PlatformConnection` ORM
            instance with populated ``credentials_encrypted`` bytes.

    Returns:
        A concrete provider implementing the
        :class:`~backend.providers.base.PlatformProvider` protocol.

    Raises:
        NotImplementedError: If the platform is not yet implemented.
        ValueError: If the decrypted credentials cannot be parsed as JSON or
            the expected keys are missing.
    """
    # Decrypt and parse credentials — stored as a JSON-encoded dict.
    raw = secrets_service.decrypt(connection.credentials_encrypted)
    try:
        creds: dict[str, str] = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Credentials for connection {connection.id} are not valid JSON. "
            "Expected a JSON object with at minimum a 'token' key."
        ) from exc

    platform = connection.platform

    if platform == Platform.github:
        # Import here to avoid a hard top-level dependency cycle if modules
        # are loaded in unusual orders during testing.
        from backend.providers.github import GitHubProvider  # noqa: PLC0415

        token = creds.get("token", "")
        if not token:
            raise ValueError(
                f"GitHub credentials for connection {connection.id} are missing "
                "the required 'token' key."
            )
        return GitHubProvider(
            token=token,
            org_name=connection.org_or_group,
            base_url=connection.base_url,
        )

    if platform == Platform.gitlab:
        from backend.providers.gitlab import GitLabProvider  # noqa: PLC0415

        return GitLabProvider(
            token=creds.get("token", ""),
            group=connection.org_or_group,
            base_url=connection.base_url,
        )

    if platform == Platform.azure_devops:
        from backend.providers.azure_devops import AzureDevOpsProvider  # noqa: PLC0415

        return AzureDevOpsProvider(
            token=creds.get("token", ""),
            org_name=connection.org_or_group,
            base_url=connection.base_url,
        )

    raise NotImplementedError(f"No provider implemented for platform: {platform!r}")
