from __future__ import annotations

"""Tests for the /api/customers/{id}/remediation-policy CRUD endpoints."""

import uuid

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_customer(client: AsyncClient, name: str = "Policy Corp") -> dict:
    """POST /api/customers/ and return the parsed JSON body."""
    resp = await client.post(
        "/api/customers/",
        json={"name": name, "contact_email": "policy@example.com"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


SAMPLE_PAYLOAD: dict = {
    "enabled": True,
    "auto_dispatch": False,
    "kill_switch_enabled": False,
    "allowed_check_ids": [],
    "blocked_check_ids": [],
    "max_prs_per_scan": 10,
    "max_cost_usd_per_month": 100.0,
    "allowed_path_globs": [],
    "denied_path_globs": [],
    "runtime_mode": "backend",
    "oversight_mode": "strict",
    "llm_input_scope": "hunk",
}


# ---------------------------------------------------------------------------
# GET — no row yet
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_no_policy_returns_404(client: AsyncClient) -> None:
    """GET returns 404 when no policy row exists for the customer."""
    customer = await _create_customer(client)
    resp = await client.get(f"/api/customers/{customer['id']}/remediation-policy")
    assert resp.status_code == 404
    assert "remediation policy" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_unknown_customer_returns_404(client: AsyncClient) -> None:
    """GET returns 404 when the customer itself does not exist."""
    random_id = str(uuid.uuid4())
    resp = await client.get(f"/api/customers/{random_id}/remediation-policy")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT — create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_creates_policy(client: AsyncClient) -> None:
    """First PUT creates a new RemediationPolicy row and returns 200."""
    customer = await _create_customer(client)
    resp = await client.put(
        f"/api/customers/{customer['id']}/remediation-policy",
        json=SAMPLE_PAYLOAD,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["enabled"] is True
    assert data["auto_dispatch"] is False
    assert data["runtime_mode"] == "backend"
    assert data["oversight_mode"] == "strict"
    assert data["llm_input_scope"] == "hunk"
    assert data["max_prs_per_scan"] == 10
    assert data["customer_id"] == customer["id"]
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_put_unknown_customer_returns_404(client: AsyncClient) -> None:
    """PUT returns 404 when the customer does not exist."""
    random_id = str(uuid.uuid4())
    resp = await client.put(
        f"/api/customers/{random_id}/remediation-policy",
        json=SAMPLE_PAYLOAD,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT — update (idempotent)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_second_time_updates_fields(client: AsyncClient) -> None:
    """Second PUT updates fields; same row id is preserved."""
    customer = await _create_customer(client)
    base_url = f"/api/customers/{customer['id']}/remediation-policy"

    first = await client.put(base_url, json=SAMPLE_PAYLOAD)
    assert first.status_code == 200
    first_data = first.json()

    updated_payload = {**SAMPLE_PAYLOAD, "auto_dispatch": True, "max_prs_per_scan": 25}
    updated = await client.put(base_url, json=updated_payload)
    assert updated.status_code == 200
    updated_data = updated.json()

    # Same row (same id).
    assert updated_data["id"] == first_data["id"]
    assert updated_data["auto_dispatch"] is True
    assert updated_data["max_prs_per_scan"] == 25


# ---------------------------------------------------------------------------
# GET — after PUT
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_after_put_returns_row(client: AsyncClient) -> None:
    """GET returns the persisted row after a successful PUT."""
    customer = await _create_customer(client)
    base_url = f"/api/customers/{customer['id']}/remediation-policy"

    await client.put(base_url, json=SAMPLE_PAYLOAD)

    resp = await client.get(base_url)
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True
    assert data["customer_id"] == customer["id"]
    assert data["runtime_mode"] == "backend"


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_invalid_max_prs_per_scan_zero_rejected(client: AsyncClient) -> None:
    """PUT with max_prs_per_scan=0 fails Pydantic ge=1 validation → 422."""
    customer = await _create_customer(client)
    resp = await client.put(
        f"/api/customers/{customer['id']}/remediation-policy",
        json={**SAMPLE_PAYLOAD, "max_prs_per_scan": 0},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_invalid_runtime_mode_rejected(client: AsyncClient) -> None:
    """PUT with runtime_mode='cloud' fails Literal constraint → 422."""
    customer = await _create_customer(client)
    resp = await client.put(
        f"/api/customers/{customer['id']}/remediation-policy",
        json={**SAMPLE_PAYLOAD, "runtime_mode": "cloud"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_invalid_oversight_mode_rejected(client: AsyncClient) -> None:
    """PUT with oversight_mode='lax' fails Literal constraint → 422."""
    customer = await _create_customer(client)
    resp = await client.put(
        f"/api/customers/{customer['id']}/remediation-policy",
        json={**SAMPLE_PAYLOAD, "oversight_mode": "lax"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_invalid_llm_input_scope_rejected(client: AsyncClient) -> None:
    """PUT with llm_input_scope='everything' fails Literal constraint → 422."""
    customer = await _create_customer(client)
    resp = await client.put(
        f"/api/customers/{customer['id']}/remediation-policy",
        json={**SAMPLE_PAYLOAD, "llm_input_scope": "everything"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_returns_204(client: AsyncClient) -> None:
    """DELETE returns 204 after a successful PUT."""
    customer = await _create_customer(client)
    base_url = f"/api/customers/{customer['id']}/remediation-policy"

    await client.put(base_url, json=SAMPLE_PAYLOAD)

    resp = await client.delete(base_url)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_get_after_delete_returns_404(client: AsyncClient) -> None:
    """GET after DELETE returns 404."""
    customer = await _create_customer(client)
    base_url = f"/api/customers/{customer['id']}/remediation-policy"

    await client.put(base_url, json=SAMPLE_PAYLOAD)
    await client.delete(base_url)

    resp = await client.get(base_url)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_not_found_returns_404(client: AsyncClient) -> None:
    """DELETE when no row exists returns 404."""
    customer = await _create_customer(client)
    resp = await client.delete(f"/api/customers/{customer['id']}/remediation-policy")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_double_delete_second_returns_404(client: AsyncClient) -> None:
    """Second DELETE after the first returns 404 (row is gone)."""
    customer = await _create_customer(client)
    base_url = f"/api/customers/{customer['id']}/remediation-policy"

    await client.put(base_url, json=SAMPLE_PAYLOAD)
    first_del = await client.delete(base_url)
    assert first_del.status_code == 204

    second_del = await client.delete(base_url)
    assert second_del.status_code == 404


# ---------------------------------------------------------------------------
# List field round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_with_list_fields_round_trips(client: AsyncClient) -> None:
    """PUT with non-empty list fields stores and returns them via GET."""
    customer = await _create_customer(client)
    base_url = f"/api/customers/{customer['id']}/remediation-policy"

    payload = {
        **SAMPLE_PAYLOAD,
        "allowed_check_ids": ["CICD-001", "REPO-002"],
        "blocked_check_ids": ["SAST-003"],
        "allowed_path_globs": ["src/**", "tests/**"],
        "denied_path_globs": ["*.lock"],
    }
    put_resp = await client.put(base_url, json=payload)
    assert put_resp.status_code == 200, put_resp.text
    data = put_resp.json()
    assert data["allowed_check_ids"] == ["CICD-001", "REPO-002"]
    assert data["blocked_check_ids"] == ["SAST-003"]
    assert data["allowed_path_globs"] == ["src/**", "tests/**"]
    assert data["denied_path_globs"] == ["*.lock"]

    get_resp = await client.get(base_url)
    assert get_resp.status_code == 200
    assert get_resp.json()["allowed_check_ids"] == ["CICD-001", "REPO-002"]
