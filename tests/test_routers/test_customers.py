from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _create_customer(
    client: AsyncClient,
    name: str = "Acme Corp",
    contact_email: str | None = None,
    notes: str | None = None,
) -> dict:
    """POST /api/customers and return the parsed JSON body."""
    payload: dict = {"name": name}
    if contact_email is not None:
        payload["contact_email"] = contact_email
    if notes is not None:
        payload["notes"] = notes

    resp = await client.post("/api/customers/", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_customer(client: AsyncClient) -> None:
    """POST /api/customers creates a customer and auto-generates a slug."""
    data = await _create_customer(client, name="Acme Corp")

    assert data["name"] == "Acme Corp"
    assert data["slug"] == "acme-corp"
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data
    # Optional fields default to None.
    assert data["contact_email"] is None
    assert data["notes"] is None


@pytest.mark.asyncio
async def test_create_customer_with_optional_fields(client: AsyncClient) -> None:
    """POST /api/customers persists optional contact_email and notes."""
    data = await _create_customer(
        client,
        name="Beta Ltd",
        contact_email="admin@beta.io",
        notes="VIP customer",
    )

    assert data["contact_email"] == "admin@beta.io"
    assert data["notes"] == "VIP customer"
    assert data["slug"] == "beta-ltd"


@pytest.mark.asyncio
async def test_list_customers(client: AsyncClient) -> None:
    """GET /api/customers returns all created customers."""
    await _create_customer(client, name="Alpha Inc")
    await _create_customer(client, name="Zeta LLC")

    resp = await client.get("/api/customers/")
    assert resp.status_code == 200

    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 2
    names = {c["name"] for c in body}
    assert names == {"Alpha Inc", "Zeta LLC"}


@pytest.mark.asyncio
async def test_list_customers_empty(client: AsyncClient) -> None:
    """GET /api/customers returns an empty list when no customers exist."""
    resp = await client.get("/api/customers/")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_get_customer(client: AsyncClient) -> None:
    """GET /api/customers/{id} returns the correct customer record."""
    created = await _create_customer(client, name="Gamma SA")

    resp = await client.get(f"/api/customers/{created['id']}")
    assert resp.status_code == 200

    body = resp.json()
    assert body["id"] == created["id"]
    assert body["name"] == "Gamma SA"
    assert body["slug"] == "gamma-sa"


@pytest.mark.asyncio
async def test_get_customer_not_found(client: AsyncClient) -> None:
    """GET /api/customers/{id} returns 404 for a non-existent UUID."""
    random_id = str(uuid.uuid4())
    resp = await client.get(f"/api/customers/{random_id}")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_customer(client: AsyncClient) -> None:
    """PUT /api/customers/{id} updates name and regenerates slug."""
    created = await _create_customer(client, name="Old Name Ltd")
    customer_id = created["id"]

    resp = await client.put(
        f"/api/customers/{customer_id}",
        json={"name": "New Name Corp"},
    )
    assert resp.status_code == 200

    body = resp.json()
    assert body["id"] == customer_id
    assert body["name"] == "New Name Corp"
    assert body["slug"] == "new-name-corp"


@pytest.mark.asyncio
async def test_update_customer_partial_fields(client: AsyncClient) -> None:
    """PUT /api/customers/{id} with only notes leaves name and slug unchanged."""
    created = await _create_customer(client, name="Stable Name")
    customer_id = created["id"]

    resp = await client.put(
        f"/api/customers/{customer_id}",
        json={"notes": "Updated notes only"},
    )
    assert resp.status_code == 200

    body = resp.json()
    assert body["name"] == "Stable Name"
    assert body["slug"] == "stable-name"
    assert body["notes"] == "Updated notes only"


@pytest.mark.asyncio
async def test_update_customer_not_found(client: AsyncClient) -> None:
    """PUT /api/customers/{id} returns 404 for a non-existent UUID."""
    random_id = str(uuid.uuid4())
    resp = await client.put(
        f"/api/customers/{random_id}",
        json={"name": "Ghost"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_customer(client: AsyncClient) -> None:
    """DELETE /api/customers/{id} removes the record and subsequent GET returns 404."""
    created = await _create_customer(client, name="Ephemeral Ltd")
    customer_id = created["id"]

    delete_resp = await client.delete(f"/api/customers/{customer_id}")
    assert delete_resp.status_code == 204

    get_resp = await client.get(f"/api/customers/{customer_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_customer_not_found(client: AsyncClient) -> None:
    """DELETE /api/customers/{id} returns 404 for a non-existent UUID."""
    random_id = str(uuid.uuid4())
    resp = await client.delete(f"/api/customers/{random_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_slug_special_characters(client: AsyncClient) -> None:
    """Slug generation strips non-alphanumeric characters correctly."""
    data = await _create_customer(client, name="O'Brien & Sons, Inc.")
    assert data["slug"] == "obrien-sons-inc"


@pytest.mark.asyncio
async def test_list_customers_alphabetical_order(client: AsyncClient) -> None:
    """GET /api/customers returns records in alphabetical order by name."""
    await _create_customer(client, name="Zebra Co")
    await _create_customer(client, name="Apple Corp")
    await _create_customer(client, name="Mango Ltd")

    resp = await client.get("/api/customers/")
    body = resp.json()
    names = [c["name"] for c in body]
    assert names == sorted(names)
