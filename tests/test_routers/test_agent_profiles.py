from __future__ import annotations

"""Tests for the /api/agent-profiles read-only endpoints (issue #37)."""

import pytest
from httpx import AsyncClient

_EXPECTED_SLUGS = {"standard", "banking", "public-sector", "strict"}


# ---------------------------------------------------------------------------
# GET / — list all profiles
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_profiles_returns_four(client: AsyncClient) -> None:
    """GET /api/agent-profiles/ returns exactly four profile entries."""
    resp = await client.get("/api/agent-profiles/")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["profiles"]) == 4


@pytest.mark.asyncio
async def test_list_profiles_schema(client: AsyncClient) -> None:
    """Each profile entry contains slug, display_name, and short_description."""
    resp = await client.get("/api/agent-profiles/")
    assert resp.status_code == 200, resp.text
    for profile in resp.json()["profiles"]:
        assert "slug" in profile
        assert "display_name" in profile
        assert "short_description" in profile


@pytest.mark.asyncio
async def test_list_profiles_expected_slugs(client: AsyncClient) -> None:
    """GET /api/agent-profiles/ returns exactly the four expected slugs."""
    resp = await client.get("/api/agent-profiles/")
    assert resp.status_code == 200, resp.text
    actual_slugs = {p["slug"] for p in resp.json()["profiles"]}
    assert actual_slugs == _EXPECTED_SLUGS


# ---------------------------------------------------------------------------
# GET /{slug}/content — individual profiles
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_standard_content_is_non_empty(client: AsyncClient) -> None:
    """GET /api/agent-profiles/standard/content returns 200 with non-empty body."""
    resp = await client.get("/api/agent-profiles/standard/content")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["slug"] == "standard"
    assert len(data["body"]) > 0


@pytest.mark.asyncio
async def test_standard_content_has_expected_sections(client: AsyncClient) -> None:
    """Standard profile body contains expected heading markers."""
    resp = await client.get("/api/agent-profiles/standard/content")
    assert resp.status_code == 200, resp.text
    body = resp.json()["body"]
    assert "## Purpose" in body
    assert "## Authority and scope" in body


@pytest.mark.asyncio
async def test_banking_content_has_req_031(client: AsyncClient) -> None:
    """Banking profile body references REQ-031 (hunk-only mode pin)."""
    resp = await client.get("/api/agent-profiles/banking/content")
    assert resp.status_code == 200, resp.text
    assert "REQ-031" in resp.json()["body"]


@pytest.mark.asyncio
async def test_public_sector_content_has_wcag(client: AsyncClient) -> None:
    """Public-sector profile body references WCAG 2.2 AA accessibility standard."""
    resp = await client.get("/api/agent-profiles/public-sector/content")
    assert resp.status_code == 200, resp.text
    assert "WCAG 2.2 AA" in resp.json()["body"]


@pytest.mark.asyncio
async def test_strict_content_has_refusal_language(client: AsyncClient) -> None:
    """Strict profile body contains refusal/refuse language."""
    resp = await client.get("/api/agent-profiles/strict/content")
    assert resp.status_code == 200, resp.text
    body = resp.json()["body"]
    assert "refuse" in body.lower() or "refusal" in body.lower()


# ---------------------------------------------------------------------------
# GET /unknown/content — 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_slug_returns_404(client: AsyncClient) -> None:
    """GET /api/agent-profiles/unknown/content returns 404 with useful detail."""
    resp = await client.get("/api/agent-profiles/unknown-slug/content")
    assert resp.status_code == 404, resp.text
    detail = resp.json()["detail"]
    assert "unknown-slug" in detail
