"""Tests asserting every built-in model card file meets minimum quality requirements."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.model_cards import _CARDS_DIR, _parse_card_file

_REQUIRED_FM_KEYS = {
    "provider",
    "model",
    "display_name",
    "context_window",
    "supports_tool_use",
    "supports_structured_output",
    "training_data_class",
    "license",
    "refreshed_at",
}


def _card_paths() -> list[Path]:
    return sorted(Path(_CARDS_DIR).glob("*.md"))


def _card_stems() -> list[str]:
    return [p.stem for p in _card_paths()]


@pytest.mark.parametrize("path", _card_paths(), ids=lambda p: p.name)
def test_card_file_parse_succeeds(path: Path) -> None:
    """_parse_card_file must succeed without error for every shipped card."""
    metadata, body, sha = _parse_card_file(path)
    assert metadata is not None
    assert body
    assert len(sha) == 64


@pytest.mark.parametrize("path", _card_paths(), ids=lambda p: p.name)
def test_card_body_minimum_length(path: Path) -> None:
    """Every card body must be at least 30 lines long."""
    _metadata, body, _sha = _parse_card_file(path)
    lines = body.splitlines()
    assert len(lines) >= 30, f"{path.name}: body has only {len(lines)} lines; expected >= 30"


@pytest.mark.parametrize("path", _card_paths(), ids=lambda p: p.name)
def test_card_has_all_required_frontmatter_keys(path: Path) -> None:
    """Every card frontmatter must contain all required keys."""
    import yaml

    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    fm = yaml.safe_load(parts[1])
    missing = _REQUIRED_FM_KEYS - fm.keys()
    assert not missing, f"{path.name}: missing frontmatter keys {sorted(missing)}"


@pytest.mark.parametrize("path", _card_paths(), ids=lambda p: p.name)
def test_card_slug_matches_filename(path: Path) -> None:
    """provider + '__' + model in frontmatter must equal the filename stem."""
    metadata, _body, _sha = _parse_card_file(path)
    derived = f"{metadata.provider}__{metadata.model}"
    assert derived == path.stem, (
        f"{path.name}: derived slug '{derived}' != filename stem '{path.stem}'"
    )


def test_eight_card_files_exist() -> None:
    """Exactly eight .md card files must be present in the model_cards directory."""
    paths = _card_paths()
    assert len(paths) == 8, f"Expected 8 card files, found {len(paths)}: {[p.name for p in paths]}"
