from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.models.enums import Platform
from backend.schemas.platform_data import (
    BranchProtectionRules,
    FileChange,
    PRStatus,
    PullRequestRef,
)

# ---------------------------------------------------------------------------
# FileChange
# ---------------------------------------------------------------------------


class TestFileChange:
    """Tests for the FileChange schema."""

    def test_defaults(self) -> None:
        """action defaults to 'update' and mode defaults to '100644'."""
        fc = FileChange(path="README.md")
        assert fc.action == "update"
        assert fc.mode == "100644"
        assert fc.content is None

    def test_content_optional(self) -> None:
        """content may be provided or omitted."""
        fc_with = FileChange(path="foo.txt", content="hello")
        assert fc_with.content == "hello"
        fc_without = FileChange(path="foo.txt")
        assert fc_without.content is None

    @pytest.mark.parametrize("action", ["create", "update", "delete"])
    def test_valid_actions(self, action: str) -> None:
        """All three allowed action literals are accepted."""
        fc = FileChange(path="x.py", action=action)
        assert fc.action == action

    def test_invalid_action_rejected(self) -> None:
        """An unrecognised action literal raises ValidationError."""
        with pytest.raises(ValidationError):
            FileChange(path="x.py", action="rename")  # type: ignore[arg-type]

    def test_path_required(self) -> None:
        """path is required; omitting it raises ValidationError."""
        with pytest.raises(ValidationError):
            FileChange()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# PullRequestRef
# ---------------------------------------------------------------------------


class TestPullRequestRef:
    def _valid_kwargs(self) -> dict:
        return {
            "provider": Platform.github,
            "repo_external_id": "42",
            "pr_number": 7,
            "pr_url": "https://github.com/org/repo/pull/7",
            "head_branch": "feature/x",
            "base_branch": "main",
            "title": "My PR",
        }

    def test_is_draft_defaults_true(self) -> None:
        """is_draft should default to True."""
        ref = PullRequestRef(**self._valid_kwargs())
        assert ref.is_draft is True

    def test_is_draft_can_be_false(self) -> None:
        ref = PullRequestRef(**self._valid_kwargs(), is_draft=False)
        assert ref.is_draft is False

    def test_accepts_platform_enum(self) -> None:
        """provider accepts any Platform enum value."""
        for plat in Platform:
            ref = PullRequestRef(**{**self._valid_kwargs(), "provider": plat})
            assert ref.provider == plat

    @pytest.mark.parametrize(
        "missing_field",
        [
            "provider",
            "repo_external_id",
            "pr_number",
            "pr_url",
            "head_branch",
            "base_branch",
            "title",
        ],
    )
    def test_required_fields_raise_when_missing(self, missing_field: str) -> None:
        """Each required field raises ValidationError when absent."""
        kwargs = self._valid_kwargs()
        del kwargs[missing_field]
        with pytest.raises(ValidationError):
            PullRequestRef(**kwargs)


# ---------------------------------------------------------------------------
# PRStatus
# ---------------------------------------------------------------------------


class TestPRStatus:
    def _valid_kwargs(self) -> dict:
        return {
            "pr_number": 1,
            "state": "open",
            "is_draft": False,
            "head_sha": "abc123",
            "head_branch": "feat",
            "base_branch": "main",
        }

    @pytest.mark.parametrize("state", ["open", "closed", "merged"])
    def test_valid_states(self, state: str) -> None:
        """All three allowed state literals are accepted."""
        status = PRStatus(**{**self._valid_kwargs(), "state": state})
        assert status.state == state

    def test_invalid_state_rejected(self) -> None:
        """An unrecognised state raises ValidationError."""
        with pytest.raises(ValidationError):
            PRStatus(**{**self._valid_kwargs(), "state": "draft"})  # type: ignore[arg-type]

    def test_mergeable_defaults_none(self) -> None:
        """mergeable is None when not provided."""
        status = PRStatus(**self._valid_kwargs())
        assert status.mergeable is None

    def test_mergeable_accepts_bool(self) -> None:
        for val in (True, False):
            status = PRStatus(**{**self._valid_kwargs(), "mergeable": val})
            assert status.mergeable is val

    def test_merged_at_defaults_none(self) -> None:
        status = PRStatus(**self._valid_kwargs())
        assert status.merged_at is None


# ---------------------------------------------------------------------------
# BranchProtectionRules
# ---------------------------------------------------------------------------


class TestBranchProtectionRules:
    def test_all_defaults_applied(self) -> None:
        """Constructing with no arguments applies all documented defaults."""
        rules = BranchProtectionRules()
        assert rules.require_pull_request_review is True
        assert rules.required_reviewer_count == 1
        assert rules.require_codeowner_review is False
        assert rules.require_status_checks == []
        assert rules.enforce_admins is True
        assert rules.allow_force_pushes is False
        assert rules.allow_deletions is False
        assert rules.restrict_push_users == []

    @pytest.mark.parametrize("count", [0, 1, 3, 6])
    def test_reviewer_count_valid_range(self, count: int) -> None:
        """required_reviewer_count accepts 0 through 6 inclusive."""
        rules = BranchProtectionRules(required_reviewer_count=count)
        assert rules.required_reviewer_count == count

    @pytest.mark.parametrize("bad_count", [-1, 7, 100])
    def test_reviewer_count_out_of_range(self, bad_count: int) -> None:
        """required_reviewer_count outside [0, 6] raises ValidationError."""
        with pytest.raises(ValidationError):
            BranchProtectionRules(required_reviewer_count=bad_count)

    def test_require_status_checks_not_shared_between_instances(self) -> None:
        """Verify default_factory — list instances are independent."""
        a = BranchProtectionRules()
        b = BranchProtectionRules()
        a.require_status_checks.append("ci/build")
        assert b.require_status_checks == []

    def test_restrict_push_users_not_shared_between_instances(self) -> None:
        """Verify default_factory — list instances are independent."""
        a = BranchProtectionRules()
        b = BranchProtectionRules()
        a.restrict_push_users.append("alice")
        assert b.restrict_push_users == []

    def test_custom_values_accepted(self) -> None:
        rules = BranchProtectionRules(
            require_pull_request_review=False,
            required_reviewer_count=2,
            require_codeowner_review=True,
            require_status_checks=["ci/test", "ci/lint"],
            enforce_admins=False,
            allow_force_pushes=True,
            allow_deletions=True,
            restrict_push_users=["bob"],
        )
        assert rules.required_reviewer_count == 2
        assert rules.require_status_checks == ["ci/test", "ci/lint"]
        assert rules.restrict_push_users == ["bob"]
