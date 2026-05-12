from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from backend.providers.azure_devops import AzureDevOpsProvider
from backend.providers.base import ProviderWriteError
from backend.schemas.platform_data import (
    BranchProtectionRules,
    FileChange,
    NormalizedRepo,
    PRStatus,
    PullRequestRef,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ZERO_SHA = "0000000000000000000000000000000000000000"
_FROM_SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_TIP_SHA = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
_COMMIT_SHA = "cccccccccccccccccccccccccccccccccccccccc"

_EXTERNAL_ID = "MyProject:repo-guid-001"


def _make_repo(
    external_id: str = _EXTERNAL_ID,
    name: str = "my-repo",
    default_branch: str = "main",
) -> NormalizedRepo:
    return NormalizedRepo(
        external_id=external_id,
        name=name,
        url="https://dev.azure.com/test-org/MyProject/_git/my-repo",
        default_branch=default_branch,
        is_private=True,
    )


def _mock_response(
    json_data: dict | list,
    status_code: int = 200,
    *,
    method: str = "POST",
) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=json_data,
        request=httpx.Request(method, "https://example.com"),
    )


def _mock_error(status_code: int = 422, *, method: str = "POST") -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        text="unprocessable entity",
        request=httpx.Request(method, "https://example.com"),
    )


@pytest.fixture()
def provider() -> AzureDevOpsProvider:
    return AzureDevOpsProvider(token="test-pat", org_name="test-org")


@pytest.fixture()
def repo() -> NormalizedRepo:
    return _make_repo()


# ---------------------------------------------------------------------------
# _post helper tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_returns_json_on_success(provider: AzureDevOpsProvider) -> None:
    """_post parses and returns the JSON body on a 2xx response."""
    mock_post = AsyncMock(return_value=_mock_response({"id": 42}))
    with patch.object(provider._client, "post", mock_post):
        result = await provider._post("https://dev.azure.com/test-org/x", json={"a": 1})
    assert result == {"id": 42}


@pytest.mark.asyncio
async def test_post_raises_provider_write_error_on_4xx(provider: AzureDevOpsProvider) -> None:
    """_post raises ProviderWriteError when the server returns 4xx."""
    mock_post = AsyncMock(return_value=_mock_error(400))
    with patch.object(provider._client, "post", mock_post):
        with pytest.raises(ProviderWriteError, match="400"):
            await provider._post("https://dev.azure.com/test-org/x")


@pytest.mark.asyncio
async def test_post_returns_empty_dict_on_no_content(provider: AzureDevOpsProvider) -> None:
    """_post returns an empty dict when the response body is empty (HTTP 204)."""
    empty_resp = httpx.Response(
        status_code=204,
        content=b"",
        request=httpx.Request("POST", "https://example.com"),
    )
    mock_post = AsyncMock(return_value=empty_resp)
    with patch.object(provider._client, "post", mock_post):
        result = await provider._post("https://dev.azure.com/test-org/x")
    assert result == {}


# ---------------------------------------------------------------------------
# _delete helper tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_raises_provider_write_error_on_4xx(provider: AzureDevOpsProvider) -> None:
    """_delete raises ProviderWriteError when the server returns 4xx."""
    bad_resp = httpx.Response(
        status_code=404,
        text="not found",
        request=httpx.Request("DELETE", "https://example.com"),
    )
    mock_delete = AsyncMock(return_value=bad_resp)
    with patch.object(provider._client, "delete", mock_delete):
        with pytest.raises(ProviderWriteError, match="404"):
            await provider._delete("https://dev.azure.com/test-org/x/1")


# ---------------------------------------------------------------------------
# create_branch tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_branch_success(provider: AzureDevOpsProvider, repo: NormalizedRepo) -> None:
    """create_branch sends the correct refs payload and returns None on success."""
    success_resp = _mock_response({"value": [{"success": True}]})
    mock_post = AsyncMock(return_value=success_resp)

    with patch.object(provider._client, "post", mock_post):
        await provider.create_branch(repo, "feature/new", _FROM_SHA)

    mock_post.assert_awaited_once()
    call_kwargs = mock_post.call_args
    body = call_kwargs.kwargs.get("json") or call_kwargs.args[1]
    assert isinstance(body, list)
    assert body[0]["name"] == "refs/heads/feature/new"
    assert body[0]["newObjectId"] == _FROM_SHA
    assert body[0]["oldObjectId"] == _ZERO_SHA


@pytest.mark.asyncio
async def test_create_branch_api_failure_raises(
    provider: AzureDevOpsProvider, repo: NormalizedRepo
) -> None:
    """create_branch raises ProviderWriteError when the API returns 4xx."""
    mock_post = AsyncMock(return_value=_mock_error(422))
    with patch.object(provider._client, "post", mock_post):
        with pytest.raises(ProviderWriteError):
            await provider.create_branch(repo, "duplicate", _FROM_SHA)


@pytest.mark.asyncio
async def test_create_branch_success_false_raises(
    provider: AzureDevOpsProvider, repo: NormalizedRepo
) -> None:
    """create_branch raises ProviderWriteError when value[0].success is False."""
    fail_resp = _mock_response(
        {"value": [{"success": False, "customMessage": "Branch already exists."}]}
    )
    mock_post = AsyncMock(return_value=fail_resp)
    with patch.object(provider._client, "post", mock_post):
        with pytest.raises(ProviderWriteError, match="Branch already exists"):
            await provider.create_branch(repo, "main", _FROM_SHA)


# ---------------------------------------------------------------------------
# commit_files tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commit_files_success(provider: AzureDevOpsProvider, repo: NormalizedRepo) -> None:
    """commit_files resolves branch tip and pushes, returning the new commit SHA."""
    refs_resp = _mock_response({"value": [{"objectId": _TIP_SHA}]}, method="GET")
    push_resp = _mock_response({"commits": [{"commitId": _COMMIT_SHA}]})

    get_mock = AsyncMock(return_value=refs_resp)
    post_mock = AsyncMock(return_value=push_resp)

    files = [FileChange(path="README.md", content="# Hello", action="update")]

    with (
        patch.object(provider._client, "get", get_mock),
        patch.object(provider._client, "post", post_mock),
    ):
        sha = await provider.commit_files(repo, "main", files, "Update README")

    assert sha == _COMMIT_SHA
    post_mock.assert_awaited_once()
    push_body = post_mock.call_args.kwargs.get("json") or post_mock.call_args.args[1]
    assert push_body["refUpdates"][0]["oldObjectId"] == _TIP_SHA
    changes = push_body["commits"][0]["changes"]
    assert len(changes) == 1
    assert changes[0]["changeType"] == "edit"
    assert changes[0]["newContent"]["content"] == "# Hello"


@pytest.mark.asyncio
async def test_commit_files_empty_list_raises(
    provider: AzureDevOpsProvider, repo: NormalizedRepo
) -> None:
    """commit_files raises ProviderWriteError immediately when files is empty."""
    with pytest.raises(ProviderWriteError, match="No file changes"):
        await provider.commit_files(repo, "main", [], "No-op")


@pytest.mark.asyncio
async def test_commit_files_missing_content_raises(
    provider: AzureDevOpsProvider, repo: NormalizedRepo
) -> None:
    """commit_files raises ProviderWriteError when create/update file has no content."""
    refs_resp = _mock_response({"value": [{"objectId": _TIP_SHA}]}, method="GET")
    get_mock = AsyncMock(return_value=refs_resp)
    files = [FileChange(path="file.txt", content=None, action="create")]

    with patch.object(provider._client, "get", get_mock):
        with pytest.raises(ProviderWriteError, match="content is None"):
            await provider.commit_files(repo, "main", files, "Bad commit")


@pytest.mark.asyncio
async def test_commit_files_branch_not_found_raises(
    provider: AzureDevOpsProvider, repo: NormalizedRepo
) -> None:
    """commit_files raises ProviderWriteError when branch refs return empty."""
    refs_resp = _mock_response({"value": []}, method="GET")
    get_mock = AsyncMock(return_value=refs_resp)
    files = [FileChange(path="f.txt", content="x", action="create")]

    with patch.object(provider._client, "get", get_mock):
        with pytest.raises(ProviderWriteError, match="not found"):
            await provider.commit_files(repo, "ghost-branch", files, "msg")


@pytest.mark.asyncio
async def test_commit_files_delete_action(
    provider: AzureDevOpsProvider, repo: NormalizedRepo
) -> None:
    """commit_files maps 'delete' action to 'delete' changeType with no newContent."""
    refs_resp = _mock_response({"value": [{"objectId": _TIP_SHA}]}, method="GET")
    push_resp = _mock_response({"commits": [{"commitId": _COMMIT_SHA}]})

    get_mock = AsyncMock(return_value=refs_resp)
    post_mock = AsyncMock(return_value=push_resp)
    files = [FileChange(path="old.txt", content=None, action="delete")]

    with (
        patch.object(provider._client, "get", get_mock),
        patch.object(provider._client, "post", post_mock),
    ):
        sha = await provider.commit_files(repo, "main", files, "Remove old.txt")

    push_body = post_mock.call_args.kwargs.get("json") or post_mock.call_args.args[1]
    change = push_body["commits"][0]["changes"][0]
    assert change["changeType"] == "delete"
    assert "newContent" not in change
    assert sha == _COMMIT_SHA


@pytest.mark.asyncio
async def test_commit_files_author_warning_is_logged(
    provider: AzureDevOpsProvider, repo: NormalizedRepo, caplog: pytest.LogCaptureFixture
) -> None:
    """commit_files logs a warning when author_name/email are provided."""
    import logging

    refs_resp = _mock_response({"value": [{"objectId": _TIP_SHA}]}, method="GET")
    push_resp = _mock_response({"commits": [{"commitId": _COMMIT_SHA}]})

    with (
        patch.object(provider._client, "get", AsyncMock(return_value=refs_resp)),
        patch.object(provider._client, "post", AsyncMock(return_value=push_resp)),
        caplog.at_level(logging.WARNING, logger="backend.providers.azure_devops"),
    ):
        await provider.commit_files(
            repo,
            "main",
            [FileChange(path="f.py", content="x", action="create")],
            "msg",
            author_name="Alice",
            author_email="alice@example.com",
        )

    assert any("not supported" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# create_pull_request tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_pull_request_success(
    provider: AzureDevOpsProvider, repo: NormalizedRepo
) -> None:
    """create_pull_request returns a PullRequestRef with correct fields."""
    pr_resp = _mock_response(
        {
            "pullRequestId": 99,
            "repository": {"webUrl": "https://dev.azure.com/test-org/MyProject/_git/my-repo"},
        }
    )
    mock_post = AsyncMock(return_value=pr_resp)

    with patch.object(provider._client, "post", mock_post):
        ref = await provider.create_pull_request(
            repo, head="feature/x", base="main", title="My PR", body="Details", draft=True
        )

    assert isinstance(ref, PullRequestRef)
    assert ref.pr_number == 99
    assert ref.pr_url.endswith("/pullrequest/99")
    assert ref.head_branch == "feature/x"
    assert ref.base_branch == "main"
    assert ref.is_draft is True

    call_body = mock_post.call_args.kwargs.get("json") or mock_post.call_args.args[1]
    assert call_body["sourceRefName"] == "refs/heads/feature/x"
    assert call_body["targetRefName"] == "refs/heads/main"
    assert call_body["isDraft"] is True


@pytest.mark.asyncio
async def test_create_pull_request_api_failure_raises(
    provider: AzureDevOpsProvider, repo: NormalizedRepo
) -> None:
    """create_pull_request raises ProviderWriteError on API failure."""
    mock_post = AsyncMock(return_value=_mock_error(409))
    with patch.object(provider._client, "post", mock_post):
        with pytest.raises(ProviderWriteError):
            await provider.create_pull_request(repo, head="f", base="main", title="T", body="B")


# ---------------------------------------------------------------------------
# get_pr_status tests
# ---------------------------------------------------------------------------


def _pr_response(
    *,
    status: str = "active",
    merge_status: str = "queued",
    is_draft: bool = False,
    source_sha: str = _FROM_SHA,
    source_ref: str = "refs/heads/feature/x",
    target_ref: str = "refs/heads/main",
    closed_date: str | None = None,
) -> httpx.Response:
    data: dict = {
        "status": status,
        "mergeStatus": merge_status,
        "isDraft": is_draft,
        "lastMergeSourceCommit": {"commitId": source_sha},
        "sourceRefName": source_ref,
        "targetRefName": target_ref,
    }
    if closed_date is not None:
        data["closedDate"] = closed_date
    return _mock_response(data, method="GET")


@pytest.mark.asyncio
async def test_get_pr_status_active(provider: AzureDevOpsProvider, repo: NormalizedRepo) -> None:
    """get_pr_status maps 'active' to state='open'."""
    mock_get = AsyncMock(return_value=_pr_response(status="active", merge_status="queued"))
    with patch.object(provider._client, "get", mock_get):
        status = await provider.get_pr_status(repo, 7)

    assert isinstance(status, PRStatus)
    assert status.state == "open"
    assert status.mergeable is None
    assert status.merged_at is None


@pytest.mark.asyncio
async def test_get_pr_status_abandoned(provider: AzureDevOpsProvider, repo: NormalizedRepo) -> None:
    """get_pr_status maps 'abandoned' to state='closed'."""
    mock_get = AsyncMock(return_value=_pr_response(status="abandoned"))
    with patch.object(provider._client, "get", mock_get):
        status = await provider.get_pr_status(repo, 8)
    assert status.state == "closed"
    assert status.merged_at is None


@pytest.mark.asyncio
async def test_get_pr_status_completed(provider: AzureDevOpsProvider, repo: NormalizedRepo) -> None:
    """get_pr_status maps 'completed' to state='merged' and parses merged_at."""
    mock_get = AsyncMock(
        return_value=_pr_response(
            status="completed",
            merge_status="succeeded",
            closed_date="2024-08-15T12:00:00Z",
        )
    )
    with patch.object(provider._client, "get", mock_get):
        status = await provider.get_pr_status(repo, 9)

    assert status.state == "merged"
    assert status.mergeable is True
    assert status.merged_at is not None
    assert status.merged_at.year == 2024


@pytest.mark.asyncio
async def test_get_pr_status_conflicts(provider: AzureDevOpsProvider, repo: NormalizedRepo) -> None:
    """get_pr_status maps mergeStatus='conflicts' to mergeable=False."""
    mock_get = AsyncMock(return_value=_pr_response(status="active", merge_status="conflicts"))
    with patch.object(provider._client, "get", mock_get):
        status = await provider.get_pr_status(repo, 10)

    assert status.mergeable is False


@pytest.mark.asyncio
async def test_get_pr_status_not_found_raises(
    provider: AzureDevOpsProvider, repo: NormalizedRepo
) -> None:
    """get_pr_status raises ProviderWriteError when the PR is not found (404)."""
    not_found = httpx.Response(
        status_code=404,
        text="not found",
        request=httpx.Request("GET", "https://example.com"),
    )
    mock_get = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "Not found", request=not_found.request, response=not_found
        )
    )
    with patch.object(provider._client, "get", mock_get):
        with pytest.raises(ProviderWriteError, match="not found or inaccessible"):
            await provider.get_pr_status(repo, 9999)


# ---------------------------------------------------------------------------
# set_branch_protection tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_set_branch_protection_creates_reviewer_policy(
    provider: AzureDevOpsProvider, repo: NormalizedRepo
) -> None:
    """set_branch_protection creates a minimum-reviewer policy when require_pr=True."""
    empty_policies = _mock_response({"value": []}, method="GET")
    created_policy = _mock_response({"id": 100})

    get_mock = AsyncMock(return_value=empty_policies)
    post_mock = AsyncMock(return_value=created_policy)

    rules = BranchProtectionRules(
        require_pull_request_review=True,
        required_reviewer_count=2,
        require_status_checks=[],
    )

    with (
        patch.object(provider._client, "get", get_mock),
        patch.object(provider._client, "post", post_mock),
    ):
        await provider.set_branch_protection(repo, "main", rules)

    post_mock.assert_awaited_once()
    body = post_mock.call_args.kwargs.get("json") or post_mock.call_args.args[1]
    assert body["settings"]["minimumApproverCount"] == 2
    assert body["settings"]["scope"][0]["refName"] == "refs/heads/main"


@pytest.mark.asyncio
async def test_set_branch_protection_deletes_old_reviewer_policies(
    provider: AzureDevOpsProvider, repo: NormalizedRepo
) -> None:
    """set_branch_protection deletes existing reviewer policies before creating new ones."""
    existing_policies = _mock_response(
        {
            "value": [
                {
                    "id": 50,
                    "settings": {"scope": [{"refName": "refs/heads/main"}]},
                }
            ]
        },
        method="GET",
    )
    created_policy = _mock_response({"id": 51})
    delete_resp = httpx.Response(
        status_code=204,
        content=b"",
        request=httpx.Request("DELETE", "https://example.com"),
    )

    get_mock = AsyncMock(return_value=existing_policies)
    post_mock = AsyncMock(return_value=created_policy)
    delete_mock = AsyncMock(return_value=delete_resp)

    rules = BranchProtectionRules(require_pull_request_review=True, required_reviewer_count=1)

    with (
        patch.object(provider._client, "get", get_mock),
        patch.object(provider._client, "post", post_mock),
        patch.object(provider._client, "delete", delete_mock),
    ):
        await provider.set_branch_protection(repo, "main", rules)

    delete_mock.assert_awaited_once()
    assert "/50" in str(delete_mock.call_args)


@pytest.mark.asyncio
async def test_set_branch_protection_no_pr_review_only_deletes(
    provider: AzureDevOpsProvider, repo: NormalizedRepo
) -> None:
    """set_branch_protection with require_pr=False deletes existing policies without creating."""
    existing_policies = _mock_response(
        {
            "value": [
                {
                    "id": 55,
                    "settings": {"scope": [{"refName": "refs/heads/main"}]},
                }
            ]
        },
        method="GET",
    )
    delete_resp = httpx.Response(
        status_code=204,
        content=b"",
        request=httpx.Request("DELETE", "https://example.com"),
    )

    get_mock = AsyncMock(return_value=existing_policies)
    post_mock = AsyncMock(return_value=_mock_response({"id": 0}))
    delete_mock = AsyncMock(return_value=delete_resp)

    rules = BranchProtectionRules(require_pull_request_review=False, require_status_checks=[])

    with (
        patch.object(provider._client, "get", get_mock),
        patch.object(provider._client, "post", post_mock),
        patch.object(provider._client, "delete", delete_mock),
    ):
        await provider.set_branch_protection(repo, "main", rules)

    delete_mock.assert_awaited_once()
    # POST should not be called for reviewer policy (require_pr=False) or status checks (empty)
    post_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_branch_protection_skips_status_checks_when_empty(
    provider: AzureDevOpsProvider, repo: NormalizedRepo
) -> None:
    """set_branch_protection does not create status-check policies when list is empty."""
    empty_policies = _mock_response({"value": []}, method="GET")
    created = _mock_response({"id": 200})

    get_mock = AsyncMock(return_value=empty_policies)
    post_mock = AsyncMock(return_value=created)

    rules = BranchProtectionRules(require_pull_request_review=True, require_status_checks=[])

    with (
        patch.object(provider._client, "get", get_mock),
        patch.object(provider._client, "post", post_mock),
    ):
        await provider.set_branch_protection(repo, "develop", rules)

    # Only one POST: the reviewer policy
    assert post_mock.await_count == 1


@pytest.mark.asyncio
async def test_set_branch_protection_creates_status_check_policies(
    provider: AzureDevOpsProvider, repo: NormalizedRepo
) -> None:
    """set_branch_protection creates one policy per status-check name."""
    empty_policies = _mock_response({"value": []}, method="GET")
    created = _mock_response({"id": 300})

    get_mock = AsyncMock(return_value=empty_policies)
    post_mock = AsyncMock(return_value=created)

    rules = BranchProtectionRules(
        require_pull_request_review=False,
        require_status_checks=["ci/build", "ci/test"],
    )

    with (
        patch.object(provider._client, "get", get_mock),
        patch.object(provider._client, "post", post_mock),
    ):
        await provider.set_branch_protection(repo, "main", rules)

    # Two status-check policies, no reviewer policy (require_pr=False)
    assert post_mock.await_count == 2
    display_names = [
        (c.kwargs.get("json") or c.args[1])["settings"]["displayName"]
        for c in post_mock.call_args_list
    ]
    assert set(display_names) == {"ci/build", "ci/test"}
