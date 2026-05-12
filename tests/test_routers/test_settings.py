from __future__ import annotations

"""Tests for the GET /api/settings and PUT /api/settings endpoints."""

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# GET /api/settings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_settings_returns_defaults(client: AsyncClient) -> None:
    """GET /api/settings returns the singleton with default values."""
    resp = await client.get("/api/settings")

    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["global_kill_switch_enabled"] is False
    assert data["default_data_residency_region"] == "eu-west"
    assert data["audit_log_retention_days"] == 180
    assert data["streaming_log_retention_hours"] == 72
    assert data["default_llm_connection_id"] is None
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_get_settings_twice_is_idempotent(client: AsyncClient) -> None:
    """Two consecutive GET calls return the same singleton row."""
    r1 = await client.get("/api/settings")
    r2 = await client.get("/api/settings")

    assert r1.status_code == r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]


# ---------------------------------------------------------------------------
# PUT /api/settings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_settings_enable_kill_switch(client: AsyncClient) -> None:
    """PUT can enable the global kill switch."""
    resp = await client.put(
        "/api/settings",
        json={"global_kill_switch_enabled": True},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["global_kill_switch_enabled"] is True
    # Other fields retain defaults.
    assert data["default_data_residency_region"] == "eu-west"


@pytest.mark.asyncio
async def test_put_settings_partial_update(client: AsyncClient) -> None:
    """PUT with one field only changes that field; others are unchanged."""
    # Change region only.
    resp = await client.put(
        "/api/settings",
        json={"default_data_residency_region": "us-east"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["default_data_residency_region"] == "us-east"
    assert data["global_kill_switch_enabled"] is False


@pytest.mark.asyncio
async def test_put_settings_multiple_fields(client: AsyncClient) -> None:
    """PUT with multiple fields updates all provided values."""
    resp = await client.put(
        "/api/settings",
        json={
            "audit_log_retention_days": 90,
            "streaming_log_retention_hours": 12,
        },
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["audit_log_retention_days"] == 90
    assert data["streaming_log_retention_hours"] == 12


@pytest.mark.asyncio
async def test_put_settings_empty_body_is_no_op(client: AsyncClient) -> None:
    """PUT with an empty body leaves the singleton row unchanged."""
    get_before = await client.get("/api/settings")
    region_before = get_before.json()["default_data_residency_region"]

    resp = await client.put("/api/settings", json={})

    assert resp.status_code == 200, resp.text
    assert resp.json()["default_data_residency_region"] == region_before


@pytest.mark.asyncio
async def test_put_settings_validation_retention_days_min(client: AsyncClient) -> None:
    """audit_log_retention_days below 30 returns 422."""
    resp = await client.put(
        "/api/settings",
        json={"audit_log_retention_days": 10},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_settings_validation_retention_days_max(client: AsyncClient) -> None:
    """audit_log_retention_days above 3650 returns 422."""
    resp = await client.put(
        "/api/settings",
        json={"audit_log_retention_days": 9999},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_settings_validation_streaming_hours_min(client: AsyncClient) -> None:
    """streaming_log_retention_hours below 1 returns 422."""
    resp = await client.put(
        "/api/settings",
        json={"streaming_log_retention_hours": 0},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_settings_validation_region_max_length(client: AsyncClient) -> None:
    """default_data_residency_region exceeding 32 chars returns 422."""
    resp = await client.put(
        "/api/settings",
        json={"default_data_residency_region": "x" * 33},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_then_get_reflects_update(client: AsyncClient) -> None:
    """After a PUT, a subsequent GET reflects the updated values."""
    put_resp = await client.put(
        "/api/settings",
        json={"global_kill_switch_enabled": True, "audit_log_retention_days": 60},
    )
    assert put_resp.status_code == 200

    get_resp = await client.get("/api/settings")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["global_kill_switch_enabled"] is True
    assert data["audit_log_retention_days"] == 60
