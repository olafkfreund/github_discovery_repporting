from __future__ import annotations

import ipaddress
import logging
import socket
from typing import Protocol, runtime_checkable
from urllib.parse import urlparse

from backend.models.enums import Platform
from backend.schemas.platform_data import NormalizedRepo, OrgAssessmentData, RepoAssessmentData

logger = logging.getLogger(__name__)


def validate_base_url(url: str, allowed_hosts: list[str] | None = None) -> str:
    """Validate a base URL against SSRF attacks.

    Checks that the URL uses HTTPS, does not point to private/reserved IP
    ranges, and optionally matches an allowlist of known hosts.

    Self-hosted instances (GitHub Enterprise, GitLab self-managed) are
    permitted as long as they use HTTPS and do not resolve to private or
    reserved IP addresses.  The *allowed_hosts* list, when provided, is
    checked first as a fast-path -- hosts on the allowlist skip DNS
    resolution.

    Args:
        url: The base URL to validate.
        allowed_hosts: Optional list of trusted hostnames.  Entries may be
            exact (``"github.com"``) or wildcard-prefixed
            (``"*.github.com"``).  Hosts matching the allowlist bypass the
            DNS-resolution check but still must use HTTPS.

    Returns:
        The validated URL (unchanged) if all checks pass.

    Raises:
        ValueError: If the URL fails any validation check.

    OWASP reference: A10:2021 -- Server-Side Request Forgery (SSRF)
    """
    if not url or not isinstance(url, str):
        raise ValueError("base_url must be a non-empty string.")

    parsed = urlparse(url)

    # --- Scheme check: HTTPS only -------------------------------------------
    if parsed.scheme != "https":
        raise ValueError(
            f"base_url must use HTTPS to protect credentials in transit. "
            f"Got scheme: {parsed.scheme!r}"
        )

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("base_url does not contain a valid hostname.")

    # Strip trailing dot from FQDN (e.g. "github.com." -> "github.com")
    hostname = hostname.rstrip(".")

    # --- Block obviously dangerous hostnames --------------------------------
    _blocked_names = {"localhost", "metadata.google.internal"}
    if hostname.lower() in _blocked_names:
        raise ValueError(
            f"base_url hostname {hostname!r} is blocked. "
            "Requests to localhost and cloud metadata endpoints are not permitted."
        )

    # --- Allowlist fast path ------------------------------------------------
    if allowed_hosts and _matches_allowlist(hostname, allowed_hosts):
        logger.debug("base_url host %r matched allowlist -- skipping DNS check.", hostname)
        return url

    # --- DNS resolution + IP range check ------------------------------------
    # For hosts not on the allowlist we resolve the hostname and verify
    # that none of the returned addresses fall within private/reserved
    # ranges.  This catches DNS rebinding attacks where an attacker
    # registers a public domain that resolves to 169.254.169.254 etc.
    try:
        addr_infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValueError(
            f"Could not resolve hostname {hostname!r}: {exc}. "
            "Ensure the base_url points to a reachable host."
        ) from exc

    if not addr_infos:
        raise ValueError(f"DNS resolution for {hostname!r} returned no addresses.")

    for _family, _type, _proto, _canonname, sockaddr in addr_infos:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue

        if _is_dangerous_ip(ip):
            raise ValueError(
                f"base_url hostname {hostname!r} resolves to {ip_str} which is "
                "a private, loopback, or reserved IP address. "
                "SSRF protection blocks requests to internal network addresses."
            )

    return url


def _matches_allowlist(hostname: str, allowed_hosts: list[str]) -> bool:
    """Check whether *hostname* matches any entry in *allowed_hosts*.

    Supports exact matches and wildcard prefixes (``"*.example.com"``
    matches ``"sub.example.com"`` and ``"deep.sub.example.com"`` but
    **not** ``"example.com"`` itself).
    """
    hostname_lower = hostname.lower()
    for pattern in allowed_hosts:
        pattern_lower = pattern.lower()
        if pattern_lower.startswith("*."):
            # Wildcard: *.github.com matches foo.github.com
            suffix = pattern_lower[1:]  # ".github.com"
            if hostname_lower.endswith(suffix) and hostname_lower != suffix.lstrip("."):
                return True
        else:
            if hostname_lower == pattern_lower:
                return True
    return False


def _is_dangerous_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return ``True`` if *ip* falls within a private or reserved range.

    Blocked ranges:
    - RFC 1918 private:  10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16
    - Loopback:          127.0.0.0/8 (IPv4), ::1 (IPv6)
    - Link-local:        169.254.0.0/16 (IPv4), fe80::/10 (IPv6)
    - Reserved/special:  0.0.0.0/8, 100.64.0.0/10 (CGN), 192.0.0.0/24,
                         192.0.2.0/24 (TEST-NET-1), 198.51.100.0/24,
                         203.0.113.0/24, 240.0.0.0/4, and IPv6 equivalents

    Uses Python's :mod:`ipaddress` module which covers all RFC 5735/6890
    special-purpose ranges.
    """
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


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

    async def get_org_assessment_data(self) -> OrgAssessmentData:
        """Collect organisation-level assessment data.

        Returns:
            An :class:`~backend.schemas.platform_data.OrgAssessmentData`
            instance with org-level security settings, membership info, etc.
        """
        ...
