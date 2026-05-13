from __future__ import annotations

"""Tests for the read-only /api/skills-registry endpoints.

The endpoints expose the built-in skill catalogue without any customer
context.  Used by the in-app Help & Docs live Skills Library browser.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_skills_registry_returns_15(client: AsyncClient) -> None:
    """The registry endpoint should return every built-in skill (15 today)."""
    resp = await client.get("/api/skills-registry")
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 15

    names = {entry["name"] for entry in data}
    assert "branch-protection-baseline" in names
    assert "codeowners-team-mapping" in names

    # Sanity-check the shape of one entry.
    sample = next(entry for entry in data if entry["name"] == "branch-protection-baseline")
    assert isinstance(sample["description"], str) and sample["description"]
    assert isinstance(sample["category"], str) and sample["category"]
    assert isinstance(sample["applies_to"], list)
    assert isinstance(sample["triggers"], list)
    assert isinstance(sample["version"], int)


@pytest.mark.asyncio
async def test_get_skill_registry_content_known(client: AsyncClient) -> None:
    """A known skill slug should return the markdown body."""
    resp = await client.get("/api/skills-registry/branch-protection-baseline/content")
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["name"] == "branch-protection-baseline"
    assert isinstance(body["body"], str)
    assert "branch protection" in body["body"].lower()


@pytest.mark.asyncio
async def test_get_skill_registry_content_unknown_returns_404(client: AsyncClient) -> None:
    """An unknown skill slug should return 404."""
    resp = await client.get("/api/skills-registry/does-not-exist/content")
    assert resp.status_code == 404
    detail = resp.json().get("detail", "")
    assert "not found" in detail.lower()
