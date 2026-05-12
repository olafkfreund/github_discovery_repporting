from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from gitlab.exceptions import GitlabError

from backend.models.enums import Platform
from backend.providers.base import ProviderWriteError
from backend.providers.gitlab import GitLabProvider
from backend.schemas.platform_data import (
    BranchProtectionRules,
    FileChange,
    NormalizedRepo,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_provider() -> GitLabProvider:
    """Return a GitLabProvider whose python-gitlab client is never contacted."""
    return GitLabProvider(token="glpat-test", group="test-group")


def _make_repo(external_id: str = "42") -> NormalizedRepo:
    """Return a minimal NormalizedRepo with a numeric GitLab project ID."""
    return NormalizedRepo(
        external_id=external_id,
        name="my-repo",
        url="https://gitlab.com/test-group/my-repo",
        default_branch="main",
        is_private=True,
    )


def _gitlab_error(code: int, message: str) -> GitlabError:
    """Build a GitlabError with a given response_code and error_message."""
    exc = GitlabError(message)
    exc.response_code = code  # type: ignore[attr-defined]
    exc.error_message = message  # type: ignore[attr-defined]
    return exc


@pytest.fixture()
def provider() -> GitLabProvider:
    return _make_provider()


@pytest.fixture()
def repo() -> NormalizedRepo:
    return _make_repo()


# ---------------------------------------------------------------------------
# _get_project helper
# ---------------------------------------------------------------------------


async def test_get_project_calls_projects_get(
    provider: GitLabProvider, repo: NormalizedRepo
) -> None:
    """_get_project resolves the integer project ID via client.projects.get."""
    mock_project = MagicMock()
    with patch.object(provider._client.projects, "get", return_value=mock_project) as mock_get:
        result = await provider._get_project(repo)

    mock_get.assert_called_once_with(42)
    assert result is mock_project


# ---------------------------------------------------------------------------
# create_branch
# ---------------------------------------------------------------------------


async def test_create_branch_happy_path(provider: GitLabProvider, repo: NormalizedRepo) -> None:
    """create_branch calls project.branches.create with correct payload."""
    mock_project = MagicMock()
    mock_project.branches.create.return_value = MagicMock()

    with patch.object(provider, "_get_project", new=AsyncMock(return_value=mock_project)):
        await provider.create_branch(repo, "feature/new", "abc123")

    mock_project.branches.create.assert_called_once_with({"branch": "feature/new", "ref": "abc123"})


async def test_create_branch_already_exists(provider: GitLabProvider, repo: NormalizedRepo) -> None:
    """create_branch raises ProviderWriteError when the branch already exists."""
    mock_project = MagicMock()
    mock_project.branches.create.side_effect = _gitlab_error(400, "Branch already exists")

    with patch.object(provider, "_get_project", new=AsyncMock(return_value=mock_project)):
        with pytest.raises(ProviderWriteError, match="already exists"):
            await provider.create_branch(repo, "feature/new", "abc123")


async def test_create_branch_invalid_ref(provider: GitLabProvider, repo: NormalizedRepo) -> None:
    """create_branch raises ProviderWriteError for an invalid base ref."""
    mock_project = MagicMock()
    mock_project.branches.create.side_effect = _gitlab_error(400, "Invalid reference")

    with patch.object(provider, "_get_project", new=AsyncMock(return_value=mock_project)):
        with pytest.raises(ProviderWriteError, match="Invalid base ref"):
            await provider.create_branch(repo, "feature/new", "bad-sha")


async def test_create_branch_generic_error(provider: GitLabProvider, repo: NormalizedRepo) -> None:
    """create_branch raises ProviderWriteError for any other GitlabError."""
    mock_project = MagicMock()
    mock_project.branches.create.side_effect = _gitlab_error(500, "Internal Server Error")

    with patch.object(provider, "_get_project", new=AsyncMock(return_value=mock_project)):
        with pytest.raises(ProviderWriteError, match="GitLab error"):
            await provider.create_branch(repo, "feature/new", "abc123")


# ---------------------------------------------------------------------------
# commit_files
# ---------------------------------------------------------------------------


async def test_commit_files_happy_path_create(
    provider: GitLabProvider, repo: NormalizedRepo
) -> None:
    """commit_files returns the commit SHA for a single 'create' action."""
    mock_commit = MagicMock()
    mock_commit.id = "deadbeef"
    mock_project = MagicMock()
    mock_project.commits.create.return_value = mock_commit

    files = [FileChange(path="README.md", content="# Hello", action="create")]

    with patch.object(provider, "_get_project", new=AsyncMock(return_value=mock_project)):
        sha = await provider.commit_files(repo, "main", files, "Add README")

    assert sha == "deadbeef"
    mock_project.commits.create.assert_called_once()
    payload = mock_project.commits.create.call_args[0][0]
    assert payload["branch"] == "main"
    assert payload["commit_message"] == "Add README"
    assert payload["actions"] == [
        {"action": "create", "file_path": "README.md", "content": "# Hello"}
    ]


async def test_commit_files_with_author(provider: GitLabProvider, repo: NormalizedRepo) -> None:
    """commit_files includes author_name and author_email when both are given."""
    mock_commit = MagicMock()
    mock_commit.id = "cafebabe"
    mock_project = MagicMock()
    mock_project.commits.create.return_value = mock_commit

    files = [FileChange(path="f.txt", content="x", action="update")]

    with patch.object(provider, "_get_project", new=AsyncMock(return_value=mock_project)):
        await provider.commit_files(
            repo, "main", files, "msg", author_name="Alice", author_email="alice@example.com"
        )

    payload = mock_project.commits.create.call_args[0][0]
    assert payload["author_name"] == "Alice"
    assert payload["author_email"] == "alice@example.com"


async def test_commit_files_delete_action(provider: GitLabProvider, repo: NormalizedRepo) -> None:
    """commit_files handles 'delete' actions (no content required)."""
    mock_commit = MagicMock()
    mock_commit.id = "aaa"
    mock_project = MagicMock()
    mock_project.commits.create.return_value = mock_commit

    files = [FileChange(path="old.txt", action="delete")]

    with patch.object(provider, "_get_project", new=AsyncMock(return_value=mock_project)):
        await provider.commit_files(repo, "main", files, "Remove old.txt")

    payload = mock_project.commits.create.call_args[0][0]
    assert payload["actions"] == [{"action": "delete", "file_path": "old.txt"}]


async def test_commit_files_empty_list_raises(
    provider: GitLabProvider, repo: NormalizedRepo
) -> None:
    """commit_files raises ProviderWriteError when the files list is empty."""
    with pytest.raises(ProviderWriteError, match="No file changes provided"):
        await provider.commit_files(repo, "main", [], "empty")


async def test_commit_files_create_missing_content(
    provider: GitLabProvider, repo: NormalizedRepo
) -> None:
    """commit_files raises ProviderWriteError when content is None for 'create'."""
    files = [FileChange(path="f.txt", content=None, action="create")]
    with pytest.raises(ProviderWriteError, match="content required for create"):
        await provider.commit_files(repo, "main", files, "oops")


async def test_commit_files_update_missing_content(
    provider: GitLabProvider, repo: NormalizedRepo
) -> None:
    """commit_files raises ProviderWriteError when content is None for 'update'."""
    files = [FileChange(path="f.txt", content=None, action="update")]
    with pytest.raises(ProviderWriteError, match="content required for update"):
        await provider.commit_files(repo, "main", files, "oops")


async def test_commit_files_api_error(provider: GitLabProvider, repo: NormalizedRepo) -> None:
    """commit_files wraps GitlabError as ProviderWriteError."""
    mock_project = MagicMock()
    mock_project.commits.create.side_effect = _gitlab_error(422, "Unprocessable entity")

    files = [FileChange(path="f.txt", content="x", action="create")]

    with patch.object(provider, "_get_project", new=AsyncMock(return_value=mock_project)):
        with pytest.raises(ProviderWriteError):
            await provider.commit_files(repo, "main", files, "fail")


# ---------------------------------------------------------------------------
# create_pull_request
# ---------------------------------------------------------------------------


async def test_create_pull_request_draft(provider: GitLabProvider, repo: NormalizedRepo) -> None:
    """create_pull_request creates a Draft MR with the 'Draft: ' title prefix."""
    mock_mr = MagicMock()
    mock_mr.iid = 7
    mock_mr.web_url = "https://gitlab.com/test-group/my-repo/-/merge_requests/7"
    mock_project = MagicMock()
    mock_project.mergerequests.create.return_value = mock_mr

    with patch.object(provider, "_get_project", new=AsyncMock(return_value=mock_project)):
        ref = await provider.create_pull_request(repo, "feature/x", "main", "My Feature", "body")

    payload = mock_project.mergerequests.create.call_args[0][0]
    assert payload["title"] == "Draft: My Feature"
    assert payload["source_branch"] == "feature/x"
    assert payload["target_branch"] == "main"
    assert ref.pr_number == 7
    assert ref.title == "My Feature"  # user-supplied title without prefix
    assert ref.is_draft is True
    assert ref.provider == Platform.gitlab


async def test_create_pull_request_non_draft(
    provider: GitLabProvider, repo: NormalizedRepo
) -> None:
    """create_pull_request creates a non-draft MR without the 'Draft: ' prefix."""
    mock_mr = MagicMock()
    mock_mr.iid = 8
    mock_mr.web_url = "https://gitlab.com/test-group/my-repo/-/merge_requests/8"
    mock_project = MagicMock()
    mock_project.mergerequests.create.return_value = mock_mr

    with patch.object(provider, "_get_project", new=AsyncMock(return_value=mock_project)):
        ref = await provider.create_pull_request(
            repo, "feature/x", "main", "My Feature", "body", draft=False
        )

    payload = mock_project.mergerequests.create.call_args[0][0]
    assert payload["title"] == "My Feature"
    assert ref.is_draft is False


async def test_create_pull_request_already_exists(
    provider: GitLabProvider, repo: NormalizedRepo
) -> None:
    """create_pull_request raises ProviderWriteError when MR already exists (409)."""
    mock_project = MagicMock()
    mock_project.mergerequests.create.side_effect = _gitlab_error(409, "MR already exists")

    with patch.object(provider, "_get_project", new=AsyncMock(return_value=mock_project)):
        with pytest.raises(ProviderWriteError, match="already exists"):
            await provider.create_pull_request(repo, "feature/x", "main", "My Feature", "body")


async def test_create_pull_request_generic_error(
    provider: GitLabProvider, repo: NormalizedRepo
) -> None:
    """create_pull_request raises ProviderWriteError for other GitlabErrors."""
    mock_project = MagicMock()
    mock_project.mergerequests.create.side_effect = _gitlab_error(500, "Server error")

    with patch.object(provider, "_get_project", new=AsyncMock(return_value=mock_project)):
        with pytest.raises(ProviderWriteError, match="GitLab MR creation failed"):
            await provider.create_pull_request(repo, "feature/x", "main", "My Feature", "body")


async def test_create_pull_request_iid_not_global_id(
    provider: GitLabProvider, repo: NormalizedRepo
) -> None:
    """create_pull_request uses mr.iid (per-project) not mr.id (global)."""
    mock_mr = MagicMock()
    mock_mr.iid = 3
    mock_mr.id = 99999  # global id — must NOT be used
    mock_mr.web_url = "https://gitlab.com/-/merge_requests/3"
    mock_project = MagicMock()
    mock_project.mergerequests.create.return_value = mock_mr

    with patch.object(provider, "_get_project", new=AsyncMock(return_value=mock_project)):
        ref = await provider.create_pull_request(repo, "a", "main", "T", "B")

    assert ref.pr_number == 3


# ---------------------------------------------------------------------------
# get_pr_status — state mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mr_state", "expected_state"),
    [
        ("opened", "open"),
        ("closed", "closed"),
        ("merged", "merged"),
        ("locked", "closed"),
    ],
)
async def test_get_pr_status_state_mapping(
    provider: GitLabProvider,
    repo: NormalizedRepo,
    mr_state: str,
    expected_state: str,
) -> None:
    """get_pr_status maps GitLab MR states to the canonical tri-state."""
    mock_mr = MagicMock()
    mock_mr.state = mr_state
    mock_mr.iid = 5
    mock_mr.sha = "abcdef"
    mock_mr.source_branch = "feat"
    mock_mr.target_branch = "main"
    mock_mr.merge_status = "can_be_merged"
    mock_mr.merged_at = None
    mock_mr.draft = False

    mock_project = MagicMock()
    mock_project.mergerequests.get.return_value = mock_mr

    with patch.object(provider, "_get_project", new=AsyncMock(return_value=mock_project)):
        status = await provider.get_pr_status(repo, 5)

    assert status.state == expected_state


@pytest.mark.parametrize(
    ("merge_status", "expected_mergeable"),
    [
        ("can_be_merged", True),
        ("cannot_be_merged", False),
        ("unchecked", None),
        ("checking", None),
        ("unknown_future_value", None),
    ],
)
async def test_get_pr_status_mergeable_mapping(
    provider: GitLabProvider,
    repo: NormalizedRepo,
    merge_status: str,
    expected_mergeable: bool | None,
) -> None:
    """get_pr_status correctly maps merge_status to the tri-state mergeable field."""
    mock_mr = MagicMock()
    mock_mr.state = "opened"
    mock_mr.iid = 5
    mock_mr.sha = "abc"
    mock_mr.source_branch = "feat"
    mock_mr.target_branch = "main"
    mock_mr.merge_status = merge_status
    mock_mr.merged_at = None
    mock_mr.draft = False

    mock_project = MagicMock()
    mock_project.mergerequests.get.return_value = mock_mr

    with patch.object(provider, "_get_project", new=AsyncMock(return_value=mock_project)):
        status = await provider.get_pr_status(repo, 5)

    assert status.mergeable == expected_mergeable


async def test_get_pr_status_draft_attribute(
    provider: GitLabProvider, repo: NormalizedRepo
) -> None:
    """get_pr_status prefers mr.draft and falls back to mr.work_in_progress."""
    mock_mr = MagicMock(
        spec=[
            "state",
            "iid",
            "sha",
            "source_branch",
            "target_branch",
            "merge_status",
            "merged_at",
            "work_in_progress",
        ]
    )
    mock_mr.state = "opened"
    mock_mr.iid = 5
    mock_mr.sha = "abc"
    mock_mr.source_branch = "feat"
    mock_mr.target_branch = "main"
    mock_mr.merge_status = "unchecked"
    mock_mr.merged_at = None
    mock_mr.work_in_progress = True  # older GitLab field

    mock_project = MagicMock()
    mock_project.mergerequests.get.return_value = mock_mr

    with patch.object(provider, "_get_project", new=AsyncMock(return_value=mock_project)):
        status = await provider.get_pr_status(repo, 5)

    assert status.is_draft is True


async def test_get_pr_status_merged_at_parsed(
    provider: GitLabProvider, repo: NormalizedRepo
) -> None:
    """get_pr_status parses the ISO-8601 merged_at timestamp."""
    mock_mr = MagicMock()
    mock_mr.state = "merged"
    mock_mr.iid = 10
    mock_mr.sha = "aaa"
    mock_mr.source_branch = "feat"
    mock_mr.target_branch = "main"
    mock_mr.merge_status = "can_be_merged"
    mock_mr.merged_at = "2024-03-15T12:00:00Z"
    mock_mr.draft = False

    mock_project = MagicMock()
    mock_project.mergerequests.get.return_value = mock_mr

    with patch.object(provider, "_get_project", new=AsyncMock(return_value=mock_project)):
        status = await provider.get_pr_status(repo, 10)

    assert status.merged_at is not None
    assert status.merged_at.year == 2024
    assert status.merged_at.month == 3
    assert status.merged_at.day == 15


async def test_get_pr_status_not_found(provider: GitLabProvider, repo: NormalizedRepo) -> None:
    """get_pr_status raises ProviderWriteError when the MR does not exist (404)."""
    mock_project = MagicMock()
    mock_project.mergerequests.get.side_effect = _gitlab_error(404, "404 Not found")

    with patch.object(provider, "_get_project", new=AsyncMock(return_value=mock_project)):
        with pytest.raises(ProviderWriteError, match="not found"):
            await provider.get_pr_status(repo, 999)


# ---------------------------------------------------------------------------
# set_branch_protection
# ---------------------------------------------------------------------------


async def test_set_branch_protection_no_one_push(
    provider: GitLabProvider, repo: NormalizedRepo
) -> None:
    """set_branch_protection sets push_access_level=0 when require_pr_review=True."""
    mock_project = MagicMock()
    mock_project.protectedbranches.delete.side_effect = _gitlab_error(404, "not found")

    rules = BranchProtectionRules(require_pull_request_review=True, allow_force_pushes=False)

    with patch.object(provider, "_get_project", new=AsyncMock(return_value=mock_project)):
        await provider.set_branch_protection(repo, "main", rules)

    mock_project.protectedbranches.create.assert_called_once()
    payload = mock_project.protectedbranches.create.call_args[0][0]
    assert payload["push_access_level"] == 0
    assert payload["merge_access_level"] == 40
    assert payload["allow_force_push"] is False


async def test_set_branch_protection_developer_push_with_users(
    provider: GitLabProvider, repo: NormalizedRepo
) -> None:
    """set_branch_protection sets push_access_level=30 when restrict_push_users is set."""
    mock_project = MagicMock()
    mock_project.protectedbranches.delete.side_effect = _gitlab_error(404, "not found")

    rules = BranchProtectionRules(
        require_pull_request_review=True,
        restrict_push_users=["alice", "bob"],
    )

    with patch.object(provider, "_get_project", new=AsyncMock(return_value=mock_project)):
        await provider.set_branch_protection(repo, "main", rules)

    payload = mock_project.protectedbranches.create.call_args[0][0]
    assert payload["push_access_level"] == 30


async def test_set_branch_protection_force_push_allowed(
    provider: GitLabProvider, repo: NormalizedRepo
) -> None:
    """set_branch_protection honours allow_force_pushes=True."""
    mock_project = MagicMock()
    mock_project.protectedbranches.delete.side_effect = _gitlab_error(404, "not found")

    rules = BranchProtectionRules(allow_force_pushes=True)

    with patch.object(provider, "_get_project", new=AsyncMock(return_value=mock_project)):
        await provider.set_branch_protection(repo, "main", rules)

    payload = mock_project.protectedbranches.create.call_args[0][0]
    assert payload["allow_force_push"] is True


async def test_set_branch_protection_clears_existing(
    provider: GitLabProvider, repo: NormalizedRepo
) -> None:
    """set_branch_protection deletes an existing protection rule before creating a new one."""
    mock_project = MagicMock()
    mock_project.protectedbranches.delete.return_value = None  # success

    rules = BranchProtectionRules()

    with patch.object(provider, "_get_project", new=AsyncMock(return_value=mock_project)):
        await provider.set_branch_protection(repo, "main", rules)

    mock_project.protectedbranches.delete.assert_called_once_with("main")
    mock_project.protectedbranches.create.assert_called_once()


async def test_set_branch_protection_delete_error_non_404(
    provider: GitLabProvider, repo: NormalizedRepo
) -> None:
    """set_branch_protection raises ProviderWriteError on non-404 delete errors."""
    mock_project = MagicMock()
    mock_project.protectedbranches.delete.side_effect = _gitlab_error(403, "Forbidden")

    rules = BranchProtectionRules()

    with patch.object(provider, "_get_project", new=AsyncMock(return_value=mock_project)):
        with pytest.raises(ProviderWriteError, match="Could not clear existing protection"):
            await provider.set_branch_protection(repo, "main", rules)


async def test_set_branch_protection_create_error(
    provider: GitLabProvider, repo: NormalizedRepo
) -> None:
    """set_branch_protection raises ProviderWriteError when protectedbranches.create fails."""
    mock_project = MagicMock()
    mock_project.protectedbranches.delete.side_effect = _gitlab_error(404, "not found")
    mock_project.protectedbranches.create.side_effect = _gitlab_error(422, "Unprocessable")

    rules = BranchProtectionRules()

    with patch.object(provider, "_get_project", new=AsyncMock(return_value=mock_project)):
        with pytest.raises(ProviderWriteError):
            await provider.set_branch_protection(repo, "main", rules)
