from __future__ import annotations

import time
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from backend.agents.tools.base import ToolError, ToolResult, WorkspaceContext

# Methods the LLM agent is permitted to call on the platform provider.
# Forbidden at all times: merge_pull_request, repo.delete, branch.protection.revoke,
# and get_pr_status (reserved for the runner to poll PR state, not the agent).
_ALLOWED_PROVIDER_METHODS: frozenset[str] = frozenset(
    {
        "create_branch",
        "commit_files",
        "create_pull_request",
        "set_branch_protection",
    }
)


class ProviderApiArgs(BaseModel):
    method: str = Field(
        ...,
        description=(
            "Provider method to invoke. One of: " + ", ".join(sorted(_ALLOWED_PROVIDER_METHODS))
        ),
    )
    args: dict[str, Any] = Field(
        default_factory=dict,
        description="Keyword arguments forwarded to the provider method.",
    )


class ProviderApi:
    """Call an allow-listed method on the platform provider (GitHub/GitLab/Azure)."""

    name: ClassVar[str] = "provider_api"
    description: ClassVar[str] = (
        "Call an allow-listed write method on the platform provider. "
        "Allowed: create_branch, commit_files, create_pull_request, set_branch_protection. "
        "merge_pull_request, repo.delete, and get_pr_status are explicitly forbidden."
    )
    arguments_schema: ClassVar[dict[str, Any]] = ProviderApiArgs.model_json_schema()

    _ALLOWED_PROVIDER_METHODS: ClassVar[frozenset[str]] = _ALLOWED_PROVIDER_METHODS

    async def __call__(
        self,
        args: dict[str, Any],
        *,
        workspace: WorkspaceContext,
        provider: Any,
    ) -> ToolResult:
        validated = ProviderApiArgs.model_validate(args)

        if validated.method not in self._ALLOWED_PROVIDER_METHODS:
            raise ToolError(
                f"provider_api: method '{validated.method}' is not allow-listed. "
                f"Allowed: {sorted(self._ALLOWED_PROVIDER_METHODS)}"
            )

        method = getattr(provider, validated.method, None)
        if not callable(method):
            raise ToolError(f"provider_api: provider has no method '{validated.method}'")

        start = time.monotonic()
        try:
            result = await method(**validated.args)
        except Exception as exc:
            raise ToolError(f"provider_api: {validated.method} raised: {exc}") from exc
        latency = int((time.monotonic() - start) * 1000)

        # Serialise the result for storage; Pydantic models have model_dump,
        # other types fall through to str().
        serialised: Any
        if hasattr(result, "model_dump"):
            serialised = result.model_dump()
        else:
            serialised = str(result)

        return ToolResult(
            name=self.name,
            ok=True,
            output=f"{validated.method} succeeded",
            metadata={"method": validated.method, "result": serialised},
            latency_ms=latency,
        )
