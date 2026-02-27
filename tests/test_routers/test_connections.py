from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_customer(client: AsyncClient, name: str = "Test Corp") -> dict:
    """POST /api/customers and return the parsed JSON body."""
    resp = await client.post("/api/customers/", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _add_connection(
    client: AsyncClient,
    customer_id: str,
    *,
    platform: str = "github",
    display_name: str = "My GitHub Org",
    auth_type: str = "token",
    credentials: str = "test-token",
    org_or_group: str = "test-org",
    base_url: str | None = None,
) -> dict:
    """POST /api/customers/{id}/connections and return the parsed JSON body."""
    payload: dict = {
        "platform": platform,
        "display_name": display_name,
        "auth_type": auth_type,
        "credentials": credentials,
        "org_or_group": org_or_group,
    }
    if base_url is not None:
        payload["base_url"] = base_url

    resp = await client.post(
        f"/api/customers/{customer_id}/connections",
        json=payload,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Connection CRUD tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_connection(client: AsyncClient) -> None:
    """POST /api/customers/{id}/connections creates a connection record.

    Credentials are encrypted before persistence and must NOT appear in
    the response body in any form.
    """
    customer = await _create_customer(client)
    connection = await _add_connection(
        client,
        customer["id"],
        credentials="super-secret-token",
    )

    assert connection["customer_id"] == customer["id"]
    assert connection["platform"] == "github"
    assert connection["auth_type"] == "token"
    assert connection["org_or_group"] == "test-org"
    assert connection["is_active"] is True

    # Credentials must never leak into the response.
    body_str = str(connection)
    assert "super-secret-token" not in body_str
    assert "credentials" not in connection  # key must be absent


@pytest.mark.asyncio
async def test_add_connection_customer_not_found(client: AsyncClient) -> None:
    """POST /api/customers/{id}/connections returns 404 if customer missing."""
    random_id = str(uuid.uuid4())
    resp = await client.post(
        f"/api/customers/{random_id}/connections",
        json={
            "platform": "github",
            "display_name": "Ghost Org",
            "auth_type": "token",
            "credentials": "any-token",
            "org_or_group": "ghost-org",
        },
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_connections(client: AsyncClient) -> None:
    """GET /api/customers/{id}/connections returns all connections for the customer."""
    customer = await _create_customer(client)
    cid = customer["id"]

    await _add_connection(client, cid, display_name="Org A", org_or_group="org-a")
    await _add_connection(client, cid, display_name="Org B", org_or_group="org-b")

    resp = await client.get(f"/api/customers/{cid}/connections")
    assert resp.status_code == 200

    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 2

    org_groups = {c["org_or_group"] for c in body}
    assert org_groups == {"org-a", "org-b"}


@pytest.mark.asyncio
async def test_list_connections_empty(client: AsyncClient) -> None:
    """GET /api/customers/{id}/connections returns an empty list initially."""
    customer = await _create_customer(client)
    resp = await client.get(f"/api/customers/{customer['id']}/connections")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_connections_customer_not_found(client: AsyncClient) -> None:
    """GET /api/customers/{id}/connections returns 404 if customer missing."""
    random_id = str(uuid.uuid4())
    resp = await client.get(f"/api/customers/{random_id}/connections")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_connections_isolation(client: AsyncClient) -> None:
    """Connections belong only to their owner customer and are not shared."""
    customer_a = await _create_customer(client, name="Customer A")
    customer_b = await _create_customer(client, name="Customer B")

    await _add_connection(client, customer_a["id"], org_or_group="org-of-a")

    resp_b = await client.get(f"/api/customers/{customer_b['id']}/connections")
    assert resp_b.status_code == 200
    assert resp_b.json() == []


@pytest.mark.asyncio
async def test_delete_connection(client: AsyncClient) -> None:
    """DELETE /connections/{id} removes the connection record."""
    customer = await _create_customer(client)
    connection = await _add_connection(client, customer["id"])
    connection_id = connection["id"]

    delete_resp = await client.delete(f"/api/connections/{connection_id}")
    assert delete_resp.status_code == 204

    # The connection should no longer be listed.
    list_resp = await client.get(f"/api/customers/{customer['id']}/connections")
    assert list_resp.status_code == 200
    assert list_resp.json() == []


@pytest.mark.asyncio
async def test_delete_connection_not_found(client: AsyncClient) -> None:
    """DELETE /connections/{id} returns 404 for a non-existent UUID."""
    random_id = str(uuid.uuid4())
    resp = await client.delete(f"/api/connections/{random_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_connection(client: AsyncClient) -> None:
    """PUT /connections/{id} applies a partial update to a connection."""
    customer = await _create_customer(client)
    connection = await _add_connection(
        client,
        customer["id"],
        org_or_group="original-org",
    )
    connection_id = connection["id"]

    resp = await client.put(
        f"/api/connections/{connection_id}",
        json={"org_or_group": "updated-org", "is_active": False},
    )
    assert resp.status_code == 200

    body = resp.json()
    assert body["org_or_group"] == "updated-org"
    assert body["is_active"] is False


@pytest.mark.asyncio
async def test_add_connection_gitlab_platform(client: AsyncClient) -> None:
    """POST /api/customers/{id}/connections accepts 'gitlab' as a platform."""
    customer = await _create_customer(client)
    connection = await _add_connection(
        client,
        customer["id"],
        platform="gitlab",
        auth_type="pat",
        org_or_group="my-gitlab-group",
    )

    assert connection["platform"] == "gitlab"
    assert connection["auth_type"] == "pat"


@pytest.mark.asyncio
async def test_connection_response_fields(client: AsyncClient) -> None:
    """ConnectionResponse includes all expected keys and excludes sensitive ones."""
    customer = await _create_customer(client)
    connection = await _add_connection(client, customer["id"])

    expected_keys = {
        "id",
        "customer_id",
        "platform",
        "display_name",
        "base_url",
        "auth_type",
        "org_or_group",
        "is_active",
        "last_validated_at",
        "created_at",
        "updated_at",
    }
    forbidden_keys = {"credentials", "credentials_encrypted"}

    assert expected_keys.issubset(connection.keys())
    assert not forbidden_keys.intersection(connection.keys())
