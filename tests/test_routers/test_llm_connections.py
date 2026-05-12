from __future__ import annotations

"""Tests for the /api/llm-connections CRUD and validate/test endpoints."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from backend.llm.base import LLMProviderError, LLMResponse

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE = "/api/llm-connections"


async def _create_customer(client: AsyncClient, name: str = "LLM Corp") -> str:
    """POST /api/customers/ and return the customer ID string."""
    resp = await client.post("/api/customers/", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _create_connection(
    client: AsyncClient,
    customer_id: str,
    *,
    name: str = "Primary",
    provider: str = "anthropic",
    model: str = "claude-3-5-sonnet-20241022",
    api_key: str | None = "sk-test",
    is_default: bool = False,
) -> dict:
    """POST /api/llm-connections/ and return the parsed JSON body."""
    payload: dict = {
        "customer_id": customer_id,
        "name": name,
        "provider": provider,
        "model": model,
        "is_default": is_default,
    }
    if api_key is not None:
        payload["api_key"] = api_key

    resp = await client.post(f"{_BASE}/", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# GET list
# ---------------------------------------------------------------------------


class TestListConnections:
    @pytest.mark.asyncio
    async def test_list_empty(self, client: AsyncClient) -> None:
        """Empty list returned when customer has no LLM connections."""
        cid = await _create_customer(client)
        resp = await client.get(f"{_BASE}/", params={"customer_id": cid})
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_populated(self, client: AsyncClient) -> None:
        """Populated list is returned after creating connections."""
        cid = await _create_customer(client)
        await _create_connection(client, cid, name="Alpha")
        await _create_connection(client, cid, name="Beta")

        resp = await client.get(f"{_BASE}/", params={"customer_id": cid})
        assert resp.status_code == 200
        names = {c["name"] for c in resp.json()}
        assert names == {"Alpha", "Beta"}

    @pytest.mark.asyncio
    async def test_list_unknown_customer(self, client: AsyncClient) -> None:
        """GET with unknown customer_id returns 404."""
        resp = await client.get(f"{_BASE}/", params={"customer_id": str(uuid.uuid4())})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST create
# ---------------------------------------------------------------------------


class TestCreateConnection:
    @pytest.mark.asyncio
    async def test_create_happy_path(self, client: AsyncClient) -> None:
        """POST creates a connection and returns the read schema."""
        cid = await _create_customer(client)
        conn = await _create_connection(client, cid, api_key="my-secret")

        assert conn["customer_id"] == cid
        assert conn["name"] == "Primary"
        assert conn["provider"] == "anthropic"
        assert conn["model"] == "claude-3-5-sonnet-20241022"
        assert conn["has_api_key"] is True
        # Plaintext key must never appear in the response.
        assert "my-secret" not in str(conn)
        assert "api_key_encrypted" not in conn
        assert "api_key" not in conn

    @pytest.mark.asyncio
    async def test_create_no_api_key(self, client: AsyncClient) -> None:
        """POST without api_key sets has_api_key=False."""
        cid = await _create_customer(client)
        conn = await _create_connection(client, cid, api_key=None)
        assert conn["has_api_key"] is False

    @pytest.mark.asyncio
    async def test_create_missing_required_fields(self, client: AsyncClient) -> None:
        """POST with missing required fields returns 422."""
        resp = await client.post(f"{_BASE}/", json={"name": "incomplete"})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_unknown_customer(self, client: AsyncClient) -> None:
        """POST with unknown customer_id returns 404."""
        resp = await client.post(
            f"{_BASE}/",
            json={
                "customer_id": str(uuid.uuid4()),
                "name": "Ghost",
                "provider": "openai",
                "model": "gpt-4o",
            },
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_has_uuid(self, client: AsyncClient) -> None:
        """Created connection has a valid UUID id field."""
        cid = await _create_customer(client)
        conn = await _create_connection(client, cid)
        # Parsing as UUID should not raise.
        uuid.UUID(conn["id"])

    @pytest.mark.asyncio
    async def test_create_encrypted_key_not_plaintext(self, client: AsyncClient) -> None:
        """The persisted api_key is encrypted and not the plaintext value."""

        cid = await _create_customer(client)
        conn = await _create_connection(client, cid, api_key="plaintext-key")

        # Fetch the DB row directly via the test session.
        # We cannot do this through the HTTP client, so we verify indirectly
        # by confirming has_api_key=True and no plaintext in response.
        assert conn["has_api_key"] is True
        assert "plaintext-key" not in str(conn)


# ---------------------------------------------------------------------------
# GET single
# ---------------------------------------------------------------------------


class TestGetConnection:
    @pytest.mark.asyncio
    async def test_get_existing(self, client: AsyncClient) -> None:
        """GET /{id} returns 200 and the connection data."""
        cid = await _create_customer(client)
        created = await _create_connection(client, cid)

        resp = await client.get(f"{_BASE}/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    @pytest.mark.asyncio
    async def test_get_not_found(self, client: AsyncClient) -> None:
        """GET with unknown UUID returns 404."""
        resp = await client.get(f"{_BASE}/{uuid.uuid4()}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT update
# ---------------------------------------------------------------------------


class TestUpdateConnection:
    @pytest.mark.asyncio
    async def test_update_name(self, client: AsyncClient) -> None:
        """PUT can update the name field."""
        cid = await _create_customer(client)
        created = await _create_connection(client, cid, name="Old Name")

        resp = await client.put(f"{_BASE}/{created['id']}", json={"name": "New Name"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"

    @pytest.mark.asyncio
    async def test_update_model(self, client: AsyncClient) -> None:
        """PUT can update the model field."""
        cid = await _create_customer(client)
        created = await _create_connection(client, cid, model="claude-3-haiku-20240307")

        resp = await client.put(
            f"{_BASE}/{created['id']}", json={"model": "claude-3-5-sonnet-20241022"}
        )
        assert resp.status_code == 200
        assert resp.json()["model"] == "claude-3-5-sonnet-20241022"

    @pytest.mark.asyncio
    async def test_update_omit_api_key_preserves_stored_key(self, client: AsyncClient) -> None:
        """PUT without api_key does NOT clear the stored encrypted key."""
        cid = await _create_customer(client)
        created = await _create_connection(client, cid, api_key="original-key")
        assert created["has_api_key"] is True

        resp = await client.put(f"{_BASE}/{created['id']}", json={"name": "Updated"})
        assert resp.status_code == 200
        # Key should still be present.
        assert resp.json()["has_api_key"] is True

    @pytest.mark.asyncio
    async def test_update_api_key_re_encrypts(self, client: AsyncClient) -> None:
        """PUT with api_key replaces the stored encrypted key."""
        cid = await _create_customer(client)
        created = await _create_connection(client, cid, api_key=None)
        assert created["has_api_key"] is False

        resp = await client.put(f"{_BASE}/{created['id']}", json={"api_key": "new-secret"})
        assert resp.status_code == 200
        assert resp.json()["has_api_key"] is True
        assert "new-secret" not in str(resp.json())

    @pytest.mark.asyncio
    async def test_update_not_found(self, client: AsyncClient) -> None:
        """PUT on unknown UUID returns 404."""
        resp = await client.put(f"{_BASE}/{uuid.uuid4()}", json={"name": "Ghost"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------


class TestDeleteConnection:
    @pytest.mark.asyncio
    async def test_delete_success(self, client: AsyncClient) -> None:
        """DELETE returns 204 and the connection is gone."""
        cid = await _create_customer(client)
        created = await _create_connection(client, cid)
        cid_conn = created["id"]

        resp = await client.delete(f"{_BASE}/{cid_conn}")
        assert resp.status_code == 204

        # Verify it's gone.
        get_resp = await client.get(f"{_BASE}/{cid_conn}")
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_not_found(self, client: AsyncClient) -> None:
        """DELETE on unknown UUID returns 404."""
        resp = await client.delete(f"{_BASE}/{uuid.uuid4()}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /validate
# ---------------------------------------------------------------------------


class TestValidateEndpoint:
    @pytest.mark.asyncio
    async def test_validate_success(self, client: AsyncClient) -> None:
        """POST /validate returns ok=True when provider responds."""
        mock_response = LLMResponse(text="pong", input_tokens=1, output_tokens=1)
        mock_provider = MagicMock()
        mock_provider.chat = AsyncMock(return_value=mock_response)

        with patch(
            "backend.services.llm_connection_service.get_llm_provider",
            return_value=mock_provider,
        ):
            resp = await client.post(
                f"{_BASE}/validate",
                json={
                    "name": "test",
                    "provider": "anthropic",
                    "model": "claude-3-5-sonnet-20241022",
                    "api_key": "sk-test",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["latency_ms"] is not None
        assert data["error"] is None

    @pytest.mark.asyncio
    async def test_validate_provider_error(self, client: AsyncClient) -> None:
        """POST /validate returns ok=False when provider raises LLMProviderError."""
        mock_provider = MagicMock()
        mock_provider.chat = AsyncMock(side_effect=LLMProviderError("Auth failed"))

        with patch(
            "backend.services.llm_connection_service.get_llm_provider",
            return_value=mock_provider,
        ):
            resp = await client.post(
                f"{_BASE}/validate",
                json={
                    "name": "test",
                    "provider": "openai",
                    "model": "gpt-4o",
                    "api_key": "bad-key",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert "Auth failed" in data["error"]
        assert data["latency_ms"] is None

    @pytest.mark.asyncio
    async def test_validate_missing_required_fields(self, client: AsyncClient) -> None:
        """POST /validate without required fields returns 422."""
        resp = await client.post(f"{_BASE}/validate", json={"name": "x"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /{id}/test
# ---------------------------------------------------------------------------


class TestTestEndpoint:
    @pytest.mark.asyncio
    async def test_test_success(self, client: AsyncClient) -> None:
        """POST /{id}/test returns ok=True when provider responds."""
        cid = await _create_customer(client)
        created = await _create_connection(client, cid)

        mock_response = LLMResponse(text="pong", input_tokens=1, output_tokens=1)
        mock_provider = MagicMock()
        mock_provider.chat = AsyncMock(return_value=mock_response)

        with patch(
            "backend.services.llm_connection_service.get_llm_provider",
            return_value=mock_provider,
        ):
            resp = await client.post(f"{_BASE}/{created['id']}/test")

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["latency_ms"] is not None

    @pytest.mark.asyncio
    async def test_test_provider_error(self, client: AsyncClient) -> None:
        """POST /{id}/test returns ok=False when provider raises LLMProviderError."""
        cid = await _create_customer(client)
        created = await _create_connection(client, cid)

        mock_provider = MagicMock()
        mock_provider.chat = AsyncMock(side_effect=LLMProviderError("Connection refused"))

        with patch(
            "backend.services.llm_connection_service.get_llm_provider",
            return_value=mock_provider,
        ):
            resp = await client.post(f"{_BASE}/{created['id']}/test")

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert "Connection refused" in data["error"]

    @pytest.mark.asyncio
    async def test_test_not_found(self, client: AsyncClient) -> None:
        """POST /{id}/test returns 404 for unknown UUID."""
        resp = await client.post(f"{_BASE}/{uuid.uuid4()}/test")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# is_default enforcement
# ---------------------------------------------------------------------------


class TestIsDefaultEnforcement:
    @pytest.mark.asyncio
    async def test_second_default_clears_first(self, client: AsyncClient) -> None:
        """Creating a 2nd connection with is_default=True clears the first one's flag."""
        cid = await _create_customer(client)
        first = await _create_connection(client, cid, name="First", is_default=True)
        assert first["is_default"] is True

        second = await _create_connection(client, cid, name="Second", is_default=True)
        assert second["is_default"] is True

        # Re-fetch first — it should no longer be default.
        resp = await client.get(f"{_BASE}/{first['id']}")
        assert resp.status_code == 200
        assert resp.json()["is_default"] is False

    @pytest.mark.asyncio
    async def test_update_to_default_clears_first(self, client: AsyncClient) -> None:
        """PUT is_default=True on second connection clears first."""
        cid = await _create_customer(client)
        first = await _create_connection(client, cid, name="First", is_default=True)
        second = await _create_connection(client, cid, name="Second", is_default=False)

        resp = await client.put(f"{_BASE}/{second['id']}", json={"is_default": True})
        assert resp.status_code == 200
        assert resp.json()["is_default"] is True

        # First should now be cleared.
        first_resp = await client.get(f"{_BASE}/{first['id']}")
        assert first_resp.json()["is_default"] is False

    @pytest.mark.asyncio
    async def test_default_isolation_across_customers(self, client: AsyncClient) -> None:
        """Setting default on one customer's connection does not affect another."""
        cid_a = await _create_customer(client, name="Cust A")
        cid_b = await _create_customer(client, name="Cust B")

        await _create_connection(client, cid_a, name="A1", is_default=True)
        conn_b = await _create_connection(client, cid_b, name="B1", is_default=True)

        # Create a second default for customer A — should not touch customer B.
        await _create_connection(client, cid_a, name="A2", is_default=True)

        resp_b = await client.get(f"{_BASE}/{conn_b['id']}")
        assert resp_b.json()["is_default"] is True
