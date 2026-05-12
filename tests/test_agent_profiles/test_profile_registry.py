"""Tests for the backend.agent_profiles registry and loader."""

from __future__ import annotations

import pytest

from backend.agent_profiles import (
    ProfileMetadata,
    get_profile_registry,
    load_profile_content,
)

_EXPECTED_SLUGS = {"standard", "banking", "public-sector", "strict"}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_get_profile_registry_returns_four_entries() -> None:
    """get_profile_registry() must return exactly four profiles."""
    registry = get_profile_registry()
    assert len(registry) == 4


def test_get_profile_registry_contains_expected_slugs() -> None:
    """get_profile_registry() must contain all four expected slugs as keys."""
    registry = get_profile_registry()
    assert set(registry.keys()) == _EXPECTED_SLUGS


def test_get_profile_registry_values_are_profile_metadata() -> None:
    """Every value in the registry must be a ProfileMetadata instance."""
    for slug, meta in get_profile_registry().items():
        assert isinstance(meta, ProfileMetadata), (
            f"Registry value for {slug!r} is not a ProfileMetadata"
        )
        assert meta.slug == slug
        assert meta.display_name
        assert meta.short_description


def test_get_profile_registry_is_cached() -> None:
    """get_profile_registry() must return the same dict object on repeat calls."""
    first = get_profile_registry()
    second = get_profile_registry()
    assert first is second, (
        "get_profile_registry() should return the cached dict on subsequent calls"
    )


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def test_load_profile_content_standard_returns_non_empty_body() -> None:
    """load_profile_content('standard') returns a body of at least 1000 chars."""
    body, sha = load_profile_content("standard")
    assert len(body) >= 1000, f"Standard profile body is only {len(body)} chars; expected >= 1000"


def test_load_profile_content_returns_64_char_sha() -> None:
    """load_profile_content returns a 64-character hex SHA-256 digest."""
    for slug in _EXPECTED_SLUGS:
        body, sha = load_profile_content(slug)
        assert len(sha) == 64, f"SHA for {slug!r} has length {len(sha)}; expected 64"
        assert all(c in "0123456789abcdef" for c in sha), (
            f"SHA for {slug!r} contains non-hex characters"
        )


def test_load_profile_content_sha_matches_body() -> None:
    """SHA returned by load_profile_content must match the body content."""
    import hashlib

    for slug in _EXPECTED_SLUGS:
        body, sha = load_profile_content(slug)
        expected = hashlib.sha256(body.encode("utf-8")).hexdigest()
        assert sha == expected, f"SHA mismatch for {slug!r}: got {sha!r}, expected {expected!r}"


def test_load_profile_content_unknown_slug_raises_key_error() -> None:
    """load_profile_content raises KeyError for an unknown slug."""
    with pytest.raises(KeyError, match="unknown-slug"):
        load_profile_content("unknown-slug")


def test_load_profile_content_is_cached() -> None:
    """load_profile_content returns the same tuple object on repeat calls."""
    first = load_profile_content("standard")
    second = load_profile_content("standard")
    assert first is second, (
        "load_profile_content('standard') should return the cached tuple on subsequent calls"
    )
