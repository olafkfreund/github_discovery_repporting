from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from github import GithubException

from backend.providers.base import ProviderWriteError
from backend.providers.github import GitHubProvider
from backend.schemas.platform_data import (
    BranchProtectionRules,
    FileChange,
    NormalizedRepo,
    PRStatus,
    PullRequestRef,
)

# ---------------------------------------------------------------------------
# Helpers & Fixtures
# ---------------------------------------------------------------------------


def _make_norm_repo(
    *,
    name: str = "my-repo",
    external_id: str = "42",
    default_branch: str = "main",
) -> NormalizedRepo:
    """Build a minimal NormalizedRepo for write-method tests."""
    return NormalizedRepo(
        external_id=external_id,
        name=name,
        url=f"https://github.com/test-org/{name}",
        default_branch=default_branch,
        is_private=False,
    )


@pytest.fixture()
def provider() -> GitHubProvider:
    """GitHubProvider with a MagicMock PyGithub client."""
    prov = GitHubProvider(token="ghp_test", org_name="test-org")
    prov._client = MagicMock()
    return prov


@pytest.fixture()
def norm_repo() -> NormalizedRepo:
    return _make_norm_repo()


def _patch_get_repo(provider: GitHubProvider, gh_repo: MagicMock) -> AsyncMock:
    """Replace _get_repo with an AsyncMock that returns *gh_repo*."""
    mock = AsyncMock(return_value=gh_repo)
    provider._get_repo = mock  # type: ignore[method-assign]
    return mock


# ---------------------------------------------------------------------------
# create_branch — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_branch_calls_create_git_ref(
    provider: GitHubProvider,
    norm_repo: NormalizedRepo,
) -> None:
    """create_branch calls Repository.create_git_ref with the correct ref string."""
    gh_repo = MagicMock()
    _patch_get_repo(provider, gh_repo)

    await provider.create_branch(norm_repo, branch="feat/x", from_sha="abc123")

    gh_repo.create_git_ref.assert_called_once_with(
        ref="refs/heads/feat/x",
        sha="abc123",
    )


# ---------------------------------------------------------------------------
# create_branch — failure paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "message_fragment", "expected_snippet"),
    [
        (422, "Reference already exists", "already exists"),
        (422, "Object does not exist", "not found"),
        (403, "Forbidden", "GitHub error 403"),
    ],
)
async def test_create_branch_raises_provider_write_error(
    provider: GitHubProvider,
    norm_repo: NormalizedRepo,
    status: int,
    message_fragment: str,
    expected_snippet: str,
) -> None:
    """create_branch maps GithubException variants to ProviderWriteError."""
    gh_repo = MagicMock()
    gh_repo.create_git_ref.side_effect = GithubException(
        status=status,
        data={"message": message_fragment},
        headers={},
    )
    _patch_get_repo(provider, gh_repo)

    with pytest.raises(ProviderWriteError, match=expected_snippet):
        await provider.create_branch(norm_repo, branch="feat/x", from_sha="abc123")


# ---------------------------------------------------------------------------
# commit_files — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commit_files_returns_new_sha(
    provider: GitHubProvider,
    norm_repo: NormalizedRepo,
) -> None:
    """commit_files walks the tree API and returns the new commit SHA."""
    gh_repo = MagicMock()
    _patch_get_repo(provider, gh_repo)

    # Wire up the chain of PyGithub calls.
    ref = MagicMock()
    ref.object.sha = "tip_sha"
    gh_repo.get_git_ref.return_value = ref

    parent_commit = MagicMock()
    parent_commit.tree.sha = "tree_sha"
    gh_repo.get_git_commit.return_value = parent_commit

    blob = MagicMock()
    blob.sha = "blob_sha"
    gh_repo.create_git_blob.return_value = blob

    base_tree = MagicMock()
    gh_repo.get_git_tree.return_value = base_tree

    new_tree = MagicMock()
    gh_repo.create_git_tree.return_value = new_tree

    new_commit = MagicMock()
    new_commit.sha = "new_commit_sha"
    gh_repo.create_git_commit.return_value = new_commit

    files = [FileChange(path="README.md", content="hello", action="update")]
    sha = await provider.commit_files(norm_repo, branch="main", files=files, message="msg")

    assert sha == "new_commit_sha"
    gh_repo.get_git_ref.assert_called_once_with("heads/main")
    gh_repo.get_git_commit.assert_called_once_with("tip_sha")
    gh_repo.create_git_blob.assert_called_once_with(content="hello", encoding="utf-8")
    ref.edit.assert_called_once_with(sha="new_commit_sha")


@pytest.mark.asyncio
async def test_commit_files_with_author(
    provider: GitHubProvider,
    norm_repo: NormalizedRepo,
) -> None:
    """commit_files forwards InputGitAuthor when both name and email are given."""
    gh_repo = MagicMock()
    _patch_get_repo(provider, gh_repo)

    ref = MagicMock()
    ref.object.sha = "sha1"
    gh_repo.get_git_ref.return_value = ref
    parent_commit = MagicMock()
    parent_commit.tree.sha = "tree1"
    gh_repo.get_git_commit.return_value = parent_commit
    blob = MagicMock()
    blob.sha = "b1"
    gh_repo.create_git_blob.return_value = blob
    gh_repo.get_git_tree.return_value = MagicMock()
    gh_repo.create_git_tree.return_value = MagicMock()
    new_commit = MagicMock()
    new_commit.sha = "c1"
    gh_repo.create_git_commit.return_value = new_commit

    files = [FileChange(path="a.py", content="x", action="create")]
    await provider.commit_files(
        norm_repo,
        branch="main",
        files=files,
        message="m",
        author_name="Alice",
        author_email="alice@example.com",
    )

    call_kwargs = gh_repo.create_git_commit.call_args.kwargs
    assert "author" in call_kwargs


@pytest.mark.asyncio
async def test_commit_files_delete_action(
    provider: GitHubProvider,
    norm_repo: NormalizedRepo,
) -> None:
    """commit_files builds a tree element with sha=None for delete actions."""
    gh_repo = MagicMock()
    _patch_get_repo(provider, gh_repo)

    ref = MagicMock()
    ref.object.sha = "sha1"
    gh_repo.get_git_ref.return_value = ref
    parent_commit = MagicMock()
    parent_commit.tree.sha = "tree1"
    gh_repo.get_git_commit.return_value = parent_commit
    gh_repo.get_git_tree.return_value = MagicMock()
    new_tree = MagicMock()
    gh_repo.create_git_tree.return_value = new_tree
    new_commit = MagicMock()
    new_commit.sha = "delsha"
    gh_repo.create_git_commit.return_value = new_commit

    files = [FileChange(path="old.py", action="delete")]
    await provider.commit_files(norm_repo, branch="main", files=files, message="delete old.py")

    # Blobs should NOT be created for deletions.
    gh_repo.create_git_blob.assert_not_called()
    tree_call_args = gh_repo.create_git_tree.call_args.kwargs
    entry = tree_call_args["tree"][0]
    assert entry._InputGitTreeElement__sha is None


# ---------------------------------------------------------------------------
# commit_files — validation / failure paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commit_files_empty_raises(
    provider: GitHubProvider,
    norm_repo: NormalizedRepo,
) -> None:
    """commit_files raises ProviderWriteError immediately when files is empty."""
    with pytest.raises(ProviderWriteError, match="No file changes provided"):
        await provider.commit_files(norm_repo, branch="main", files=[], message="x")


@pytest.mark.asyncio
async def test_commit_files_missing_content_raises(
    provider: GitHubProvider,
    norm_repo: NormalizedRepo,
) -> None:
    """commit_files raises ProviderWriteError when create/update has content=None."""
    files = [FileChange(path="foo.py", action="create", content=None)]
    with pytest.raises(ProviderWriteError, match="content is required"):
        await provider.commit_files(norm_repo, branch="main", files=files, message="x")


@pytest.mark.asyncio
async def test_commit_files_github_exception_raises(
    provider: GitHubProvider,
    norm_repo: NormalizedRepo,
) -> None:
    """commit_files wraps GithubException in ProviderWriteError."""
    gh_repo = MagicMock()
    gh_repo.get_git_ref.side_effect = GithubException(
        status=500,
        data={"message": "Internal Server Error"},
        headers={},
    )
    _patch_get_repo(provider, gh_repo)

    files = [FileChange(path="f.txt", content="x", action="update")]
    with pytest.raises(ProviderWriteError, match="GitHub error 500"):
        await provider.commit_files(norm_repo, branch="main", files=files, message="m")


# ---------------------------------------------------------------------------
# create_pull_request — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_pull_request_returns_ref(
    provider: GitHubProvider,
    norm_repo: NormalizedRepo,
) -> None:
    """create_pull_request returns a PullRequestRef with correct fields."""
    gh_repo = MagicMock()
    _patch_get_repo(provider, gh_repo)

    mock_pr = MagicMock()
    mock_pr.number = 7
    mock_pr.html_url = "https://github.com/test-org/my-repo/pull/7"
    gh_repo.create_pull.return_value = mock_pr

    ref = await provider.create_pull_request(
        norm_repo,
        head="feat/add-thing",
        base="main",
        title="Add thing",
        body="Desc",
        draft=True,
    )

    assert isinstance(ref, PullRequestRef)
    assert ref.pr_number == 7
    assert ref.head_branch == "feat/add-thing"
    assert ref.base_branch == "main"
    assert ref.is_draft is True

    gh_repo.create_pull.assert_called_once_with(
        title="Add thing",
        body="Desc",
        head="feat/add-thing",
        base="main",
        draft=True,
    )


# ---------------------------------------------------------------------------
# create_pull_request — failure paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message_fragment", "expected_snippet"),
    [
        ("A pull request already exists", "already exists"),
        ("No commits between", "No diff between"),
        ("Unprocessable Entity", "GitHub PR creation failed"),
    ],
)
async def test_create_pull_request_raises_provider_write_error(
    provider: GitHubProvider,
    norm_repo: NormalizedRepo,
    message_fragment: str,
    expected_snippet: str,
) -> None:
    """create_pull_request maps GithubException 422 variants to ProviderWriteError."""
    gh_repo = MagicMock()
    gh_repo.create_pull.side_effect = GithubException(
        status=422,
        data={"message": message_fragment},
        headers={},
    )
    _patch_get_repo(provider, gh_repo)

    with pytest.raises(ProviderWriteError, match=expected_snippet):
        await provider.create_pull_request(norm_repo, head="feat", base="main", title="T", body="B")


# ---------------------------------------------------------------------------
# get_pr_status — happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("merged", "pr_state", "expected_state"),
    [
        (True, "closed", "merged"),
        (False, "open", "open"),
        (False, "closed", "closed"),
    ],
)
async def test_get_pr_status_state_mapping(
    provider: GitHubProvider,
    norm_repo: NormalizedRepo,
    merged: bool,
    pr_state: str,
    expected_state: str,
) -> None:
    """get_pr_status maps PR merged/state fields to the PRStatus state literal."""
    gh_repo = MagicMock()
    _patch_get_repo(provider, gh_repo)

    mock_pr = MagicMock()
    mock_pr.merged = merged
    mock_pr.state = pr_state
    mock_pr.merged_at = datetime(2024, 1, 1, tzinfo=UTC) if merged else None
    mock_pr.draft = False
    mock_pr.head.sha = "headsha"
    mock_pr.head.ref = "feat/x"
    mock_pr.base.ref = "main"
    mock_pr.mergeable = True
    gh_repo.get_pull.return_value = mock_pr

    status = await provider.get_pr_status(norm_repo, pr_number=1)

    assert isinstance(status, PRStatus)
    assert status.state == expected_state
    assert status.pr_number == 1
    assert status.head_branch == "feat/x"


@pytest.mark.asyncio
async def test_get_pr_status_fields_populated(
    provider: GitHubProvider,
    norm_repo: NormalizedRepo,
) -> None:
    """get_pr_status populates all PRStatus fields from the PyGithub PR object."""
    gh_repo = MagicMock()
    _patch_get_repo(provider, gh_repo)

    mock_pr = MagicMock()
    mock_pr.merged = False
    mock_pr.state = "open"
    mock_pr.merged_at = None
    mock_pr.draft = True
    mock_pr.head.sha = "abc"
    mock_pr.head.ref = "feature"
    mock_pr.base.ref = "main"
    mock_pr.mergeable = None
    gh_repo.get_pull.return_value = mock_pr

    status = await provider.get_pr_status(norm_repo, pr_number=42)

    assert status.is_draft is True
    assert status.head_sha == "abc"
    assert status.base_branch == "main"
    assert status.mergeable is None


# ---------------------------------------------------------------------------
# get_pr_status — failure path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_pr_status_404_raises(
    provider: GitHubProvider,
    norm_repo: NormalizedRepo,
) -> None:
    """get_pr_status raises ProviderWriteError with helpful message on 404."""
    gh_repo = MagicMock()
    gh_repo.get_pull.side_effect = GithubException(
        status=404, data={"message": "Not Found"}, headers={}
    )
    _patch_get_repo(provider, gh_repo)

    with pytest.raises(ProviderWriteError, match="not found"):
        await provider.get_pr_status(norm_repo, pr_number=99)


# ---------------------------------------------------------------------------
# set_branch_protection — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_branch_protection_calls_edit_protection(
    provider: GitHubProvider,
    norm_repo: NormalizedRepo,
) -> None:
    """set_branch_protection delegates to Branch.edit_protection with correct args."""
    gh_repo = MagicMock()
    _patch_get_repo(provider, gh_repo)

    gh_branch = MagicMock()
    gh_repo.get_branch.return_value = gh_branch

    rules = BranchProtectionRules(
        require_pull_request_review=True,
        required_reviewer_count=2,
        require_codeowner_review=True,
        require_status_checks=["ci/tests"],
        enforce_admins=True,
        allow_force_pushes=False,
        allow_deletions=False,
    )

    await provider.set_branch_protection(norm_repo, branch="main", rules=rules)

    gh_repo.get_branch.assert_called_once_with("main")
    gh_branch.edit_protection.assert_called_once()
    call_kwargs = gh_branch.edit_protection.call_args.kwargs
    assert call_kwargs["enforce_admins"] is True
    assert call_kwargs["require_code_owner_reviews"] is True
    assert call_kwargs["contexts"] == ["ci/tests"]
    assert call_kwargs["required_approving_review_count"] == 2


@pytest.mark.asyncio
async def test_set_branch_protection_no_pr_review_removes_requirement(
    provider: GitHubProvider,
    norm_repo: NormalizedRepo,
) -> None:
    """set_branch_protection calls remove_required_pull_request_reviews when require_pr=False."""
    gh_repo = MagicMock()
    _patch_get_repo(provider, gh_repo)

    gh_branch = MagicMock()
    gh_repo.get_branch.return_value = gh_branch

    rules = BranchProtectionRules(require_pull_request_review=False)

    await provider.set_branch_protection(norm_repo, branch="main", rules=rules)

    gh_branch.remove_required_pull_request_reviews.assert_called_once()


@pytest.mark.asyncio
async def test_set_branch_protection_removal_404_ignored(
    provider: GitHubProvider,
    norm_repo: NormalizedRepo,
) -> None:
    """A 404 from remove_required_pull_request_reviews is silently swallowed."""
    gh_repo = MagicMock()
    _patch_get_repo(provider, gh_repo)

    gh_branch = MagicMock()
    gh_repo.get_branch.return_value = gh_branch
    gh_branch.remove_required_pull_request_reviews.side_effect = GithubException(
        status=404, data={"message": "Not Found"}, headers={}
    )

    rules = BranchProtectionRules(require_pull_request_review=False)

    # Should not raise.
    await provider.set_branch_protection(norm_repo, branch="main", rules=rules)


# ---------------------------------------------------------------------------
# set_branch_protection — failure paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected_snippet"),
    [
        (404, "not found"),
        (403, "Insufficient permission"),
    ],
)
async def test_set_branch_protection_raises_on_get_branch_error(
    provider: GitHubProvider,
    norm_repo: NormalizedRepo,
    status: int,
    expected_snippet: str,
) -> None:
    """set_branch_protection maps 404/403 from get_branch to ProviderWriteError."""
    gh_repo = MagicMock()
    gh_repo.get_branch.side_effect = GithubException(
        status=status,
        data={"message": "error"},
        headers={},
    )
    _patch_get_repo(provider, gh_repo)

    rules = BranchProtectionRules()
    with pytest.raises(ProviderWriteError, match=expected_snippet):
        await provider.set_branch_protection(norm_repo, branch="main", rules=rules)


@pytest.mark.asyncio
async def test_set_branch_protection_edit_protection_403_raises(
    provider: GitHubProvider,
    norm_repo: NormalizedRepo,
) -> None:
    """set_branch_protection raises ProviderWriteError on 403 from edit_protection."""
    gh_repo = MagicMock()
    _patch_get_repo(provider, gh_repo)

    gh_branch = MagicMock()
    gh_repo.get_branch.return_value = gh_branch
    gh_branch.edit_protection.side_effect = GithubException(
        status=403,
        data={"message": "Must have admin rights"},
        headers={},
    )

    rules = BranchProtectionRules()
    with pytest.raises(ProviderWriteError, match="Insufficient permission"):
        await provider.set_branch_protection(norm_repo, branch="main", rules=rules)
