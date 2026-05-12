"""Tests for the backend.model_cards registry and content loader (REQ-050)."""

from __future__ import annotations

import hashlib

import pytest

from backend.model_cards import (
    ModelCardMetadata,
    get_model_card_registry,
    load_model_card_content,
)

_EXPECTED_SLUGS = {
    "anthropic__claude-opus-4-7",
    "anthropic__claude-sonnet-4-6",
    "anthropic__claude-haiku-4-5",
    "openai__gpt-4o",
    "openai__gpt-4o-mini",
    "openai__gpt-4.1",
    "bedrock__anthropic.claude-3-5-sonnet-20241022-v2-0",
    "vertex__gemini-2-0-flash",
}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_get_model_card_registry_returns_eight_entries() -> None:
    """get_model_card_registry() must return exactly eight cards."""
    registry = get_model_card_registry()
    assert len(registry) == 8, f"Expected 8 cards, got {len(registry)}: {list(registry.keys())}"


def test_get_model_card_registry_contains_expected_slugs() -> None:
    """get_model_card_registry() must contain all eight expected slugs."""
    registry = get_model_card_registry()
    assert set(registry.keys()) == _EXPECTED_SLUGS


def test_get_model_card_registry_values_are_metadata_instances() -> None:
    """Every registry value must be a ModelCardMetadata instance with a matching slug."""
    for slug, meta in get_model_card_registry().items():
        assert isinstance(meta, ModelCardMetadata), (
            f"Registry value for {slug!r} is not a ModelCardMetadata"
        )
        assert meta.slug == slug


def test_get_model_card_registry_is_cached() -> None:
    """get_model_card_registry() must return the same dict object on repeat calls."""
    first = get_model_card_registry()
    second = get_model_card_registry()
    assert first is second, "get_model_card_registry() should return the cached dict"


def test_opus_card_has_expected_metadata() -> None:
    """The Opus 4.7 card has the expected provider, model, and context_window."""
    registry = get_model_card_registry()
    slug = "anthropic__claude-opus-4-7"
    assert slug in registry
    meta = registry[slug]
    assert meta.provider == "anthropic"
    assert meta.model == "claude-opus-4-7"
    assert meta.context_window == 200000
    assert meta.supports_tool_use is True
    assert meta.supports_structured_output is True
    assert meta.license == "proprietary"


# ---------------------------------------------------------------------------
# Content loader
# ---------------------------------------------------------------------------


def test_load_model_card_content_returns_non_empty_body() -> None:
    """load_model_card_content returns a non-empty body string."""
    body, sha = load_model_card_content("openai__gpt-4o")
    assert len(body) > 0, "Body should not be empty"


def test_load_model_card_content_returns_64_char_sha() -> None:
    """load_model_card_content returns a 64-character hex SHA-256 digest."""
    body, sha = load_model_card_content("openai__gpt-4o")
    assert len(sha) == 64, f"SHA has length {len(sha)}; expected 64"
    assert all(c in "0123456789abcdef" for c in sha), "SHA contains non-hex characters"


def test_load_model_card_content_sha_is_whole_file_hash() -> None:
    """SHA returned by load_model_card_content must match the hash of the full file."""
    from pathlib import Path

    from backend.model_cards import _CARDS_DIR

    slug = "openai__gpt-4o"
    _body, sha = load_model_card_content(slug)
    full_text = (Path(_CARDS_DIR) / f"{slug}.md").read_text(encoding="utf-8")
    expected = hashlib.sha256(full_text.encode("utf-8")).hexdigest()
    assert sha == expected, f"SHA mismatch: got {sha!r}, expected {expected!r}"


def test_load_model_card_content_unknown_slug_raises_key_error() -> None:
    """load_model_card_content raises KeyError for an unknown slug."""
    with pytest.raises(KeyError, match="unknown-model"):
        load_model_card_content("unknown-model")


def test_load_model_card_content_is_cached() -> None:
    """load_model_card_content returns the same tuple object on repeat calls."""
    first = load_model_card_content("anthropic__claude-sonnet-4-6")
    second = load_model_card_content("anthropic__claude-sonnet-4-6")
    assert first is second, "load_model_card_content should return a cached tuple"
