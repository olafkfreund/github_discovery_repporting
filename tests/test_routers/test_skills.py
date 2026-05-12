from __future__ import annotations

"""Tests for the /api/customers/{id}/skills CRUD endpoints and the
/api/connections/{id}/skills-override endpoint."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.skill import SkillToggle

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BUILTIN_NAME = "codeowners-team-mapping"
ANOTHER_BUILTIN = "branch-protection-baseline"

VALID_SKILL: dict = {
    "name": "my-custom-skill",
    "description": "A custom skill for testing.",
    "category": "general",
    "applies_to_check_ids": [],
    "triggers": ["remediation"],
    "body": "# My Custom Skill\n\nThis is the body.",
    "enabled": True,
}


async def _create_customer(client: AsyncClient, name: str = "Skill Corp") -> dict:
    resp = await client.post("/api/customers/", json={"name": name, "contact_email": "x@x.com"})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _add_connection(client: AsyncClient, customer_id: str) -> dict:
    resp = await client.post(
        f"/api/customers/{customer_id}/connections",
        json={
            "platform": "github",
            "display_name": "Test Org",
            "auth_type": "token",
            "credentials": "test-token",
            "org_or_group": "test-org",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_skill(
    client: AsyncClient,
    customer_id: str,
    overrides: dict | None = None,
) -> dict:
    payload = {**VALID_SKILL, **(overrides or {})}
    resp = await client.post(f"/api/customers/{customer_id}/skills", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# GET list — happy path (built-ins only)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_skills_returns_builtins(client: AsyncClient) -> None:
    """GET /customers/{id}/skills returns 15 built-in skills for a new customer."""
    customer = await _create_customer(client)
    resp = await client.get(f"/api/customers/{customer['id']}/skills")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "skills" in data
    skills = data["skills"]
    assert len(skills) == 15
    sources = {s["source"] for s in skills}
    assert sources == {"builtin"}
    # All built-ins enabled by default.
    assert all(s["enabled"] for s in skills)


# ---------------------------------------------------------------------------
# GET list — with SkillToggle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_skills_respects_toggle(client: AsyncClient, db_session: AsyncSession) -> None:
    """A SkillToggle row with enabled=False makes the skill appear disabled."""
    customer = await _create_customer(client)
    cid = uuid.UUID(customer["id"])

    # Insert a toggle row directly.
    toggle = SkillToggle(
        customer_id=cid,
        skill_name=BUILTIN_NAME,
        enabled=False,
    )
    db_session.add(toggle)
    await db_session.commit()

    resp = await client.get(f"/api/customers/{customer['id']}/skills")
    assert resp.status_code == 200
    skills_map = {s["name"]: s for s in resp.json()["skills"]}
    assert skills_map[BUILTIN_NAME]["enabled"] is False
    # All others remain enabled.
    for name, s in skills_map.items():
        if name != BUILTIN_NAME:
            assert s["enabled"] is True


# ---------------------------------------------------------------------------
# GET list — with custom skill
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_skills_includes_custom(client: AsyncClient) -> None:
    """After POST, GET returns 16 items including the new custom skill."""
    customer = await _create_customer(client)
    await _create_skill(client, customer["id"])

    resp = await client.get(f"/api/customers/{customer['id']}/skills")
    assert resp.status_code == 200
    skills = resp.json()["skills"]
    assert len(skills) == 16
    custom_skills = [s for s in skills if s["source"] == "custom"]
    assert len(custom_skills) == 1
    assert custom_skills[0]["name"] == VALID_SKILL["name"]


# ---------------------------------------------------------------------------
# GET list — 404 on missing customer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_skills_missing_customer(client: AsyncClient) -> None:
    """GET returns 404 when the customer does not exist."""
    resp = await client.get(f"/api/customers/{uuid.uuid4()}/skills")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST create — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_skill_happy_path(client: AsyncClient) -> None:
    """POST returns 201 with SkillRead; subsequent GET includes the skill."""
    customer = await _create_customer(client)
    resp = await client.post(f"/api/customers/{customer['id']}/skills", json=VALID_SKILL)

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == VALID_SKILL["name"]
    assert data["description"] == VALID_SKILL["description"]
    assert data["version"] == 1
    assert data["customer_id"] == customer["id"]
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data

    # Verify it appears in the list.
    list_resp = await client.get(f"/api/customers/{customer['id']}/skills")
    names = [s["name"] for s in list_resp.json()["skills"]]
    assert VALID_SKILL["name"] in names


# ---------------------------------------------------------------------------
# POST create — name collision with built-in
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_skill_builtin_name_collision(client: AsyncClient) -> None:
    """POST with a built-in name returns 400."""
    customer = await _create_customer(client)
    payload = {**VALID_SKILL, "name": BUILTIN_NAME}
    resp = await client.post(f"/api/customers/{customer['id']}/skills", json=payload)
    assert resp.status_code == 400
    assert BUILTIN_NAME in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST create — name collision with existing custom skill
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_skill_duplicate_custom_name(client: AsyncClient) -> None:
    """POST the same name twice returns 400 on the second request."""
    customer = await _create_customer(client)
    await _create_skill(client, customer["id"])
    resp = await client.post(f"/api/customers/{customer['id']}/skills", json=VALID_SKILL)
    assert resp.status_code == 400
    assert "already exists" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# POST create — invalid name pattern triggers Pydantic 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_skill_invalid_name_pattern(client: AsyncClient) -> None:
    """POST with uppercase/space in name fails Pydantic validation (422)."""
    customer = await _create_customer(client)
    payload = {**VALID_SKILL, "name": "Foo Bar"}
    resp = await client.post(f"/api/customers/{customer['id']}/skills", json=payload)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /skills/{name}/content — built-in
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_skill_content_builtin(client: AsyncClient) -> None:
    """GET /skills/{name}/content returns body from the built-in registry."""
    customer = await _create_customer(client)
    resp = await client.get(
        f"/api/skills/{BUILTIN_NAME}/content",
        params={"customer_id": customer["id"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["name"] == BUILTIN_NAME
    assert data["source"] == "builtin"
    assert len(data["content"]) > 0


# ---------------------------------------------------------------------------
# GET /skills/{name}/content — custom
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_skill_content_custom(client: AsyncClient) -> None:
    """GET /skills/{name}/content for a custom skill returns the DB body."""
    customer = await _create_customer(client)
    created = await _create_skill(client, customer["id"])

    resp = await client.get(
        f"/api/skills/{created['name']}/content",
        params={"customer_id": customer["id"]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["source"] == "custom"
    assert data["content"] == VALID_SKILL["body"]


# ---------------------------------------------------------------------------
# GET /skills/{name}/content — unknown skill 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_skill_content_unknown(client: AsyncClient) -> None:
    """GET /skills/{name}/content returns 404 for an unknown slug."""
    customer = await _create_customer(client)
    resp = await client.get(
        "/api/skills/nonexistent-skill-xyz/content",
        params={"customer_id": customer["id"]},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT update — custom skill full update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_custom_skill(client: AsyncClient) -> None:
    """PUT updates description+body on a custom skill and bumps version."""
    customer = await _create_customer(client)
    created = await _create_skill(client, customer["id"])
    assert created["version"] == 1

    resp = await client.put(
        f"/api/customers/{customer['id']}/skills/{created['name']}",
        json={"description": "Updated description", "body": "# Updated body"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["description"] == "Updated description"
    assert data["body"] == "# Updated body"
    assert data["version"] == 2


# ---------------------------------------------------------------------------
# PUT update — built-in, enabled-only toggle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_builtin_skill_enabled_toggle(client: AsyncClient) -> None:
    """PUT with only enabled=false on a built-in returns 200 and writes a SkillToggle."""
    customer = await _create_customer(client)
    resp = await client.put(
        f"/api/customers/{customer['id']}/skills/{BUILTIN_NAME}",
        json={"enabled": False},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["name"] == BUILTIN_NAME
    assert data["enabled"] is False

    # Confirm the list endpoint reflects the change.
    list_resp = await client.get(f"/api/customers/{customer['id']}/skills")
    skills_map = {s["name"]: s for s in list_resp.json()["skills"]}
    assert skills_map[BUILTIN_NAME]["enabled"] is False


# ---------------------------------------------------------------------------
# PUT update — built-in with non-enabled fields → 400
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_builtin_skill_non_enabled_fields_rejected(client: AsyncClient) -> None:
    """PUT with description on a built-in returns 400."""
    customer = await _create_customer(client)
    resp = await client.put(
        f"/api/customers/{customer['id']}/skills/{BUILTIN_NAME}",
        json={"description": "New description"},
    )
    assert resp.status_code == 400
    assert (
        "description" in resp.json()["detail"].lower() or "enabled" in resp.json()["detail"].lower()
    )


# ---------------------------------------------------------------------------
# DELETE — custom skill
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_custom_skill(client: AsyncClient) -> None:
    """DELETE returns 204; subsequent GET excludes the skill."""
    customer = await _create_customer(client)
    created = await _create_skill(client, customer["id"])

    del_resp = await client.delete(f"/api/customers/{customer['id']}/skills/{created['name']}")
    assert del_resp.status_code == 204

    list_resp = await client.get(f"/api/customers/{customer['id']}/skills")
    names = [s["name"] for s in list_resp.json()["skills"]]
    assert created["name"] not in names
    # Back to 15 built-ins.
    assert len(names) == 15


# ---------------------------------------------------------------------------
# DELETE — custom skill with toggle also cleaned
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_custom_skill_cleans_toggle(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """DELETE removes the Skill row and any associated SkillToggle."""
    from sqlalchemy import select

    customer = await _create_customer(client)
    cid = uuid.UUID(customer["id"])
    created = await _create_skill(client, customer["id"])

    # Add a toggle for the custom skill.
    toggle = SkillToggle(
        customer_id=cid,
        skill_name=created["name"],
        enabled=False,
    )
    db_session.add(toggle)
    await db_session.commit()

    del_resp = await client.delete(f"/api/customers/{customer['id']}/skills/{created['name']}")
    assert del_resp.status_code == 204

    # Toggle row should be gone.
    result = await db_session.execute(
        select(SkillToggle).where(
            SkillToggle.customer_id == cid,
            SkillToggle.skill_name == created["name"],
        )
    )
    assert result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# DELETE — built-in → 400
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_builtin_skill_rejected(client: AsyncClient) -> None:
    """DELETE on a built-in skill returns 400."""
    customer = await _create_customer(client)
    resp = await client.delete(f"/api/customers/{customer['id']}/skills/{BUILTIN_NAME}")
    assert resp.status_code == 400
    assert "disable" in resp.json()["detail"].lower() or "built-in" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# PUT /connections/{id}/skills-override — valid overrides persisted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skills_override_persisted(client: AsyncClient) -> None:
    """PUT skills-override writes the dict and the response reflects it."""
    customer = await _create_customer(client)
    conn = await _add_connection(client, customer["id"])
    conn_id = conn["id"]

    overrides = {BUILTIN_NAME: False, ANOTHER_BUILTIN: True}
    resp = await client.put(
        f"/api/connections/{conn_id}/skills-override",
        json={"overrides": overrides},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["skills_override"] == overrides


# ---------------------------------------------------------------------------
# PUT /connections/{id}/skills-override — unknown skill name → 400
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skills_override_unknown_skill_rejected(client: AsyncClient) -> None:
    """PUT skills-override with an unknown skill name returns 400."""
    customer = await _create_customer(client)
    conn = await _add_connection(client, customer["id"])

    resp = await client.put(
        f"/api/connections/{conn['id']}/skills-override",
        json={"overrides": {"completely-unknown-skill-xyz": True}},
    )
    assert resp.status_code == 400
    assert "unknown" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# PUT /connections/{id}/skills-override — empty dict clears column
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skills_override_empty_dict_clears_column(client: AsyncClient) -> None:
    """PUT skills-override with {} clears the column to null."""
    customer = await _create_customer(client)
    conn = await _add_connection(client, customer["id"])
    conn_id = conn["id"]

    # First set some overrides.
    await client.put(
        f"/api/connections/{conn_id}/skills-override",
        json={"overrides": {BUILTIN_NAME: False}},
    )

    # Now clear them.
    resp = await client.put(
        f"/api/connections/{conn_id}/skills-override",
        json={"overrides": {}},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["skills_override"] is None


# ---------------------------------------------------------------------------
# PUT /connections/{id}/skills-override — missing connection 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skills_override_missing_connection(client: AsyncClient) -> None:
    """PUT skills-override returns 404 when the connection does not exist."""
    resp = await client.put(
        f"/api/connections/{uuid.uuid4()}/skills-override",
        json={"overrides": {}},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT update — custom skill enabled-only does not bump version
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_custom_skill_enabled_only_no_version_bump(client: AsyncClient) -> None:
    """PUT with only enabled=false on a custom skill does NOT bump version."""
    customer = await _create_customer(client)
    created = await _create_skill(client, customer["id"])
    assert created["version"] == 1

    resp = await client.put(
        f"/api/customers/{customer['id']}/skills/{created['name']}",
        json={"enabled": False},
    )
    assert resp.status_code == 200
    assert resp.json()["version"] == 1
    assert resp.json()["enabled"] is False


# ---------------------------------------------------------------------------
# POST create — customer not found returns 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_skill_missing_customer(client: AsyncClient) -> None:
    """POST /customers/{unknown_id}/skills returns 404."""
    resp = await client.post(
        f"/api/customers/{uuid.uuid4()}/skills",
        json=VALID_SKILL,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT update — missing customer returns 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_skill_missing_customer(client: AsyncClient) -> None:
    """PUT /customers/{unknown_id}/skills/{name} returns 404."""
    resp = await client.put(
        f"/api/customers/{uuid.uuid4()}/skills/some-skill",
        json={"enabled": False},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT update — missing custom skill returns 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_nonexistent_custom_skill(client: AsyncClient) -> None:
    """PUT on a skill slug that neither exists as builtin nor custom returns 404."""
    customer = await _create_customer(client)
    resp = await client.put(
        f"/api/customers/{customer['id']}/skills/nonexistent-slug-xyz",
        json={"description": "does not matter"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE — missing customer returns 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_skill_missing_customer(client: AsyncClient) -> None:
    """DELETE /customers/{unknown_id}/skills/{name} returns 404."""
    resp = await client.delete(f"/api/customers/{uuid.uuid4()}/skills/some-skill")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Isolation: skills belong only to their customer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skill_isolation_between_customers(client: AsyncClient) -> None:
    """A skill created for customer A is not visible to customer B."""
    customer_a = await _create_customer(client, name="Customer A")
    customer_b = await _create_customer(client, name="Customer B")

    await _create_skill(client, customer_a["id"])

    resp_b = await client.get(f"/api/customers/{customer_b['id']}/skills")
    names_b = [s["name"] for s in resp_b.json()["skills"]]
    assert VALID_SKILL["name"] not in names_b
