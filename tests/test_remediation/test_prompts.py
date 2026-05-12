"""Tests for backend.agents.prompts (prompt loader with SHA256 hash pinning)."""

from __future__ import annotations

import pytest

from backend.agents.prompts import load_prompt

_FIRST_CLASS_PROMPTS = [
    "REPO-001.md",
    "REPO-008.md",
    "SEC-003.md",
    "CICD-001.md",
    "CQ-004.md",
]


class TestLoadPrompt:
    def test_generic_returns_non_empty_content(self) -> None:
        content, sha = load_prompt("generic.md")
        assert isinstance(content, str)
        assert len(content) > 0

    def test_generic_returns_64_char_sha256(self) -> None:
        _content, sha = load_prompt("generic.md")
        assert isinstance(sha, str)
        assert len(sha) == 64
        assert all(c in "0123456789abcdef" for c in sha)

    def test_same_file_returns_identical_sha_on_repeated_calls(self) -> None:
        _content1, sha1 = load_prompt("generic.md")
        _content2, sha2 = load_prompt("generic.md")
        assert sha1 == sha2

    def test_load_is_cached_returns_same_tuple_object(self) -> None:
        """The LRU cache must return the identical tuple object on repeated calls."""
        result1 = load_prompt("generic.md")
        result2 = load_prompt("generic.md")
        assert result1 is result2

    def test_missing_file_raises_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_prompt("does-not-exist.md")

    @pytest.mark.parametrize("filename", _FIRST_CLASS_PROMPTS)
    def test_first_class_prompt_loads_successfully(self, filename: str) -> None:
        content, sha = load_prompt(filename)
        assert len(content) > 0
        assert len(sha) == 64

    @pytest.mark.parametrize(
        "filename,expected_id",
        [
            ("REPO-001.md", "REPO-001"),
            ("REPO-008.md", "REPO-008"),
            ("SEC-003.md", "SEC-003"),
            ("CICD-001.md", "CICD-001"),
            ("CQ-004.md", "CQ-004"),
        ],
    )
    def test_first_class_prompt_contains_check_id(self, filename: str, expected_id: str) -> None:
        """Each first-class prompt must mention its own check_id in the content."""
        content, _sha = load_prompt(filename)
        assert expected_id in content, (
            f"Prompt {filename!r} does not mention check_id {expected_id!r}."
        )

    def test_different_files_produce_different_shas(self) -> None:
        _, sha_generic = load_prompt("generic.md")
        _, sha_repo001 = load_prompt("REPO-001.md")
        assert sha_generic != sha_repo001
