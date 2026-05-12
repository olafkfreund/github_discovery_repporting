"""Tests for GET /api/model-cards/ and GET /api/model-cards/{slug}/content."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

_EXPECTED_SLUGS = {
    "anthropic__claude-opus-4-7",
    "anthropic__claude-sonnet-4-6",
    "anthropic__claude-haiku-4-5",
    "openai__gpt-4o",
    "openai__gpt-4o-mini",
    "openai__gpt-4.1",
    "bedrock__anthropic.claude-3-5-sonnet-20241022-v2-0",
    "vertex__gemini-2-0-flash",
}


@pytest.mark.asyncio
async def test_list_cards_returns_eight(client: AsyncClient) -> None:
    """GET /api/model-cards/ returns exactly eight cards."""
    resp = await client.get("/api/model-cards/")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["cards"]) == 8


@pytest.mark.asyncio
async def test_list_cards_schema(client: AsyncClient) -> None:
    """Each card entry contains the expected fields."""
    resp = await client.get("/api/model-cards/")
    assert resp.status_code == 200, resp.text
    for card in resp.json()["cards"]:
        for field in (
            "slug",
            "provider",
            "model",
            "display_name",
            "context_window",
            "supports_tool_use",
            "supports_structured_output",
            "training_data_class",
            "license",
            "refreshed_at",
        ):
            assert field in card, f"Field '{field}' missing from card {card.get('slug')!r}"


@pytest.mark.asyncio
async def test_list_cards_expected_slugs(client: AsyncClient) -> None:
    """GET /api/model-cards/ returns exactly the expected eight slugs."""
    resp = await client.get("/api/model-cards/")
    assert resp.status_code == 200, resp.text
    actual_slugs = {c["slug"] for c in resp.json()["cards"]}
    assert actual_slugs == _EXPECTED_SLUGS


@pytest.mark.asyncio
async def test_get_card_content_valid_slug(client: AsyncClient) -> None:
    """GET /api/model-cards/{valid_slug}/content returns 200 with non-empty body."""
    slug = "anthropic__claude-opus-4-7"
    resp = await client.get(f"/api/model-cards/{slug}/content")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["slug"] == slug
    assert len(data["body"]) > 0


@pytest.mark.asyncio
async def test_get_card_content_openai_slug(client: AsyncClient) -> None:
    """GET /api/model-cards/openai__gpt-4o/content returns 200."""
    resp = await client.get("/api/model-cards/openai__gpt-4o/content")
    assert resp.status_code == 200, resp.text
    assert resp.json()["slug"] == "openai__gpt-4o"


@pytest.mark.asyncio
async def test_get_card_content_unknown_slug_returns_404(client: AsyncClient) -> None:
    """GET /api/model-cards/unknown/content returns 404 with useful detail."""
    resp = await client.get("/api/model-cards/unknown-provider__unknown-model/content")
    assert resp.status_code == 404, resp.text
    detail = resp.json()["detail"]
    assert "unknown-provider__unknown-model" in detail
