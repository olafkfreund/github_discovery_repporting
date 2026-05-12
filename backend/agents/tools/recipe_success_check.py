from __future__ import annotations

import time
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from backend.agents.tools.base import ToolError, ToolResult, WorkspaceContext


class RecipeSuccessCheckArgs(BaseModel):
    check_id: str = Field(
        ...,
        description="The scanner check ID (e.g. CICD-008) to verify remediation for.",
    )


class RecipeSuccessCheck:
    """Verify that a remediation recipe's success condition is met.

    Delegates to ``backend.remediation.registry.get_recipe``, which is built
    in a parallel workstream (issue #25). Until that module lands, every call
    raises :class:`~backend.agents.tools.base.ToolError` with an informative
    message.
    """

    name: ClassVar[str] = "recipe_success_check"
    description: ClassVar[str] = (
        "Check whether the remediation recipe for a given check_id has succeeded. "
        "Requires the remediation registry (issue #25) to be wired before use."
    )
    arguments_schema: ClassVar[dict[str, Any]] = RecipeSuccessCheckArgs.model_json_schema()

    async def __call__(
        self,
        args: dict[str, Any],
        *,
        workspace: WorkspaceContext,
        provider: Any,
    ) -> ToolResult:
        validated = RecipeSuccessCheckArgs.model_validate(args)

        try:
            from backend.remediation.registry import get_recipe  # noqa: PLC0415
        except ImportError as exc:
            raise ToolError(
                "recipe_success_check: remediation registry not yet wired (issue #25)"
            ) from exc

        recipe = get_recipe(validated.check_id)
        if recipe.success_check is None:
            raise ToolError(
                f"recipe_success_check: no success_check defined for {validated.check_id}"
            )

        # Construct a minimal ProviderCtx — issue #25 will define its shape.
        # For now, pass the platform provider directly.
        start = time.monotonic()
        success = await recipe.success_check(workspace, provider)
        latency = int((time.monotonic() - start) * 1000)

        return ToolResult(
            name=self.name,
            ok=success,
            output=f"success_check({validated.check_id}) -> {success}",
            metadata={"check_id": validated.check_id, "success": success},
            latency_ms=latency,
        )
