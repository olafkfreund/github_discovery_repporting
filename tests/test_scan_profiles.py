"""Tests for scan profile CRUD API endpoints."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_customer(client: AsyncClient) -> str:
    """POST /api/customers/ and return the customer ID."""
    resp = await client.post(
        "/api/customers/",
        json={"name": "Test Org", "contact_email": "test@example.com"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest_asyncio.fixture()
async def customer_id(client: AsyncClient) -> str:
    """Create a test customer and return its ID."""
    return await _create_customer(client)


SAMPLE_CONFIG = {
    "categories": {
        "cicd": {
            "enabled": True,
            "weight": 0.15,
            "checks": {
                "CICD-008": {
                    "enabled": True,
                    "thresholds": {"pass_threshold": 0.90, "warning_threshold": 0.75},
                }
            },
        },
        "dast": {"enabled": False},
    }
}


# ---------------------------------------------------------------------------
# Scanner registry endpoint
# ---------------------------------------------------------------------------


class TestScannerRegistry:
    @pytest.mark.asyncio()
    async def test_get_registry(self, client: AsyncClient) -> None:
        resp = await client.get("/api/scanners/registry")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 16
        # Verify structure of first entry
        first = data[0]
        assert "category" in first
        assert "display_name" in first
        assert "weight" in first
        assert "checks" in first
        assert isinstance(first["checks"], list)


# ---------------------------------------------------------------------------
# Scan profile CRUD
# ---------------------------------------------------------------------------


class TestScanProfileCRUD:
    @pytest.mark.asyncio()
    async def test_create_profile(self, client: AsyncClient, customer_id: str) -> None:
        resp = await client.post(
            f"/api/customers/{customer_id}/scan-profiles",
            json={"name": "Security Focus", "description": "Strict checks", "config": SAMPLE_CONFIG},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Security Focus"
        assert data["description"] == "Strict checks"
        assert data["customer_id"] == customer_id
        assert data["config"]["categories"]["dast"]["enabled"] is False

    @pytest.mark.asyncio()
    async def test_list_profiles(self, client: AsyncClient, customer_id: str) -> None:
        # Create two profiles
        await client.post(
            f"/api/customers/{customer_id}/scan-profiles",
            json={"name": "Profile A", "config": {}},
        )
        await client.post(
            f"/api/customers/{customer_id}/scan-profiles",
            json={"name": "Profile B", "config": SAMPLE_CONFIG},
        )
        resp = await client.get(f"/api/customers/{customer_id}/scan-profiles")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    @pytest.mark.asyncio()
    async def test_get_profile(self, client: AsyncClient, customer_id: str) -> None:
        create_resp = await client.post(
            f"/api/customers/{customer_id}/scan-profiles",
            json={"name": "Get Me", "config": SAMPLE_CONFIG},
        )
        profile_id = create_resp.json()["id"]
        resp = await client.get(f"/api/scan-profiles/{profile_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Get Me"

    @pytest.mark.asyncio()
    async def test_update_profile(self, client: AsyncClient, customer_id: str) -> None:
        create_resp = await client.post(
            f"/api/customers/{customer_id}/scan-profiles",
            json={"name": "Old Name", "config": {}},
        )
        profile_id = create_resp.json()["id"]
        resp = await client.put(
            f"/api/scan-profiles/{profile_id}",
            json={"name": "New Name", "config": SAMPLE_CONFIG},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"
        assert resp.json()["config"]["categories"]["dast"]["enabled"] is False

    @pytest.mark.asyncio()
    async def test_delete_profile(self, client: AsyncClient, customer_id: str) -> None:
        create_resp = await client.post(
            f"/api/customers/{customer_id}/scan-profiles",
            json={"name": "Delete Me", "config": {}},
        )
        profile_id = create_resp.json()["id"]
        resp = await client.delete(f"/api/scan-profiles/{profile_id}")
        assert resp.status_code == 204
        # Verify it's gone
        get_resp = await client.get(f"/api/scan-profiles/{profile_id}")
        assert get_resp.status_code == 404

    @pytest.mark.asyncio()
    async def test_get_nonexistent_profile(self, client: AsyncClient) -> None:
        resp = await client.get("/api/scan-profiles/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Scan trigger with profile_id
# ---------------------------------------------------------------------------


class TestScanWithProfile:
    @pytest.mark.asyncio()
    async def test_trigger_scan_with_missing_profile(
        self, client: AsyncClient, customer_id: str
    ) -> None:
        """Scan trigger with a non-existent profile_id should return 404."""
        # First create a connection so we have a valid connection_id
        conn_resp = await client.post(
            f"/api/customers/{customer_id}/connections",
            json={
                "platform": "github",
                "display_name": "Test",
                "org_or_group": "test-org",
                "auth_type": "token",
                "credentials": "ghp_test123",
            },
        )
        assert conn_resp.status_code == 201
        conn_id = conn_resp.json()["id"]

        resp = await client.post(
            f"/api/customers/{customer_id}/scans",
            json={
                "connection_id": conn_id,
                "profile_id": "00000000-0000-0000-0000-000000000000",
            },
        )
        assert resp.status_code == 404
        assert "profile" in resp.json()["detail"].lower()
