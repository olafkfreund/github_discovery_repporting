from __future__ import annotations

"""Tests for the /api/customers/{id}/agent-instructions CRUD endpoints."""

import uuid

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_customer(client: AsyncClient, name: str = "Agent Corp") -> dict:
    """POST /api/customers/ and return the parsed JSON body."""
    resp = await client.post(
        "/api/customers/",
        json={"name": name, "contact_email": "test@example.com"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


SAMPLE_CONTENT = "# Agent Instructions\n\nFollow our standards when writing code."


# ---------------------------------------------------------------------------
# GET — no row yet
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_no_instructions(client: AsyncClient) -> None:
    """GET returns 404 when no instructions row exists for the customer."""
    customer = await _create_customer(client)
    resp = await client.get(f"/api/customers/{customer['id']}/agent-instructions")
    assert resp.status_code == 404
    assert "agent instructions" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_unknown_customer(client: AsyncClient) -> None:
    """GET returns 404 when the customer itself does not exist."""
    random_id = str(uuid.uuid4())
    resp = await client.get(f"/api/customers/{random_id}/agent-instructions")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT — create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_creates_instructions(client: AsyncClient) -> None:
    """First PUT creates a new AgentInstructions row and returns 200."""
    customer = await _create_customer(client)
    resp = await client.put(
        f"/api/customers/{customer['id']}/agent-instructions",
        json={"content": SAMPLE_CONTENT, "enabled": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["content"] == SAMPLE_CONTENT
    assert data["enabled"] is True
    assert data["customer_id"] == customer["id"]
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_put_unknown_customer(client: AsyncClient) -> None:
    """PUT returns 404 when the customer does not exist."""
    random_id = str(uuid.uuid4())
    resp = await client.put(
        f"/api/customers/{random_id}/agent-instructions",
        json={"content": SAMPLE_CONTENT},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT — update (idempotent)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_second_time_updates(client: AsyncClient) -> None:
    """Second PUT updates content and updated_at on the existing row."""
    customer = await _create_customer(client)
    base_url = f"/api/customers/{customer['id']}/agent-instructions"

    first = await client.put(base_url, json={"content": "Original content"})
    assert first.status_code == 200
    first_data = first.json()

    updated = await client.put(base_url, json={"content": "Updated content", "enabled": False})
    assert updated.status_code == 200
    updated_data = updated.json()

    # Same row (same id).
    assert updated_data["id"] == first_data["id"]
    assert updated_data["content"] == "Updated content"
    assert updated_data["enabled"] is False


# ---------------------------------------------------------------------------
# GET — after PUT
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_after_put_returns_row(client: AsyncClient) -> None:
    """GET returns the persisted row after a successful PUT."""
    customer = await _create_customer(client)
    base_url = f"/api/customers/{customer['id']}/agent-instructions"

    await client.put(base_url, json={"content": SAMPLE_CONTENT})

    resp = await client.get(base_url)
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == SAMPLE_CONTENT
    assert data["customer_id"] == customer["id"]


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_empty_content_rejected(client: AsyncClient) -> None:
    """PUT with content='' fails Pydantic min_length=1 validation."""
    customer = await _create_customer(client)
    resp = await client.put(
        f"/api/customers/{customer['id']}/agent-instructions",
        json={"content": ""},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_content_too_long_rejected(client: AsyncClient) -> None:
    """PUT with content > 100 000 characters fails validation."""
    customer = await _create_customer(client)
    resp = await client.put(
        f"/api/customers/{customer['id']}/agent-instructions",
        json={"content": "x" * 100_001},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_returns_204(client: AsyncClient) -> None:
    """DELETE returns 204 after a successful PUT."""
    customer = await _create_customer(client)
    base_url = f"/api/customers/{customer['id']}/agent-instructions"

    await client.put(base_url, json={"content": SAMPLE_CONTENT})

    resp = await client.delete(base_url)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_get_after_delete_returns_404(client: AsyncClient) -> None:
    """GET after DELETE returns 404."""
    customer = await _create_customer(client)
    base_url = f"/api/customers/{customer['id']}/agent-instructions"

    await client.put(base_url, json={"content": SAMPLE_CONTENT})
    await client.delete(base_url)

    resp = await client.get(base_url)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_not_found_returns_404(client: AsyncClient) -> None:
    """DELETE when no row exists returns 404 (consistent with GET)."""
    customer = await _create_customer(client)
    resp = await client.delete(f"/api/customers/{customer['id']}/agent-instructions")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_double_delete_second_returns_404(client: AsyncClient) -> None:
    """Second DELETE after the first returns 404 (row is gone)."""
    customer = await _create_customer(client)
    base_url = f"/api/customers/{customer['id']}/agent-instructions"

    await client.put(base_url, json={"content": SAMPLE_CONTENT})
    first_del = await client.delete(base_url)
    assert first_del.status_code == 204

    second_del = await client.delete(base_url)
    assert second_del.status_code == 404
