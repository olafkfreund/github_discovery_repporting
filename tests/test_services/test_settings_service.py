from __future__ import annotations

"""Tests for backend.services.settings_service."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.setting import SINGLETON_ID, Setting
from backend.schemas.setting import SettingUpdate
from backend.services import settings_service as svc

# ---------------------------------------------------------------------------
# get_settings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_settings_creates_row_if_missing(db_session: AsyncSession) -> None:
    """get_settings creates the singleton row when it does not exist."""
    settings = await svc.get_settings(db_session)

    assert settings.id == SINGLETON_ID
    assert settings.global_kill_switch_enabled is False
    assert settings.default_data_residency_region == "eu-west"
    assert settings.audit_log_retention_days == 180
    assert settings.streaming_log_retention_hours == 72
    assert settings.default_llm_connection_id is None


@pytest.mark.asyncio
async def test_get_settings_returns_existing_row(db_session: AsyncSession) -> None:
    """get_settings returns the existing row without creating a duplicate."""
    # Manually insert the singleton row.
    row = Setting(id=SINGLETON_ID, global_kill_switch_enabled=True)
    db_session.add(row)
    await db_session.commit()

    # Now call via the service — must return same row, not a new one.
    settings = await svc.get_settings(db_session)
    assert settings.id == SINGLETON_ID
    assert settings.global_kill_switch_enabled is True


@pytest.mark.asyncio
async def test_get_settings_idempotent(db_session: AsyncSession) -> None:
    """Calling get_settings twice returns the same singleton row both times."""
    first = await svc.get_settings(db_session)
    second = await svc.get_settings(db_session)

    assert first.id == second.id == SINGLETON_ID


# ---------------------------------------------------------------------------
# update_settings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_settings_partial_update(db_session: AsyncSession) -> None:
    """update_settings applies only non-None fields and leaves others unchanged."""
    # Ensure the singleton exists.
    await svc.get_settings(db_session)

    patch = SettingUpdate(global_kill_switch_enabled=True)
    updated = await svc.update_settings(db_session, patch)

    assert updated.global_kill_switch_enabled is True
    # Other fields retain defaults.
    assert updated.default_data_residency_region == "eu-west"
    assert updated.audit_log_retention_days == 180


@pytest.mark.asyncio
async def test_update_settings_multiple_fields(db_session: AsyncSession) -> None:
    """update_settings writes multiple provided fields in a single call."""
    await svc.get_settings(db_session)

    patch = SettingUpdate(
        audit_log_retention_days=365,
        streaming_log_retention_hours=48,
        default_data_residency_region="us-east",
    )
    updated = await svc.update_settings(db_session, patch)

    assert updated.audit_log_retention_days == 365
    assert updated.streaming_log_retention_hours == 48
    assert updated.default_data_residency_region == "us-east"
    # Unchanged fields.
    assert updated.global_kill_switch_enabled is False


@pytest.mark.asyncio
async def test_update_settings_with_llm_connection_id(db_session: AsyncSession) -> None:
    """update_settings stores a UUID for default_llm_connection_id."""
    await svc.get_settings(db_session)
    fake_id = uuid.uuid4()

    patch = SettingUpdate(default_llm_connection_id=fake_id)
    updated = await svc.update_settings(db_session, patch)

    assert updated.default_llm_connection_id == fake_id


@pytest.mark.asyncio
async def test_update_settings_empty_patch_no_op(db_session: AsyncSession) -> None:
    """An empty SettingUpdate (all None) leaves the row unchanged."""
    original = await svc.get_settings(db_session)
    original_region = original.default_data_residency_region

    patch = SettingUpdate()
    updated = await svc.update_settings(db_session, patch)

    assert updated.default_data_residency_region == original_region


# ---------------------------------------------------------------------------
# is_global_kill_switch_engaged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kill_switch_false_by_default(db_session: AsyncSession) -> None:
    """is_global_kill_switch_engaged returns False when not set."""
    result = await svc.is_global_kill_switch_engaged(db_session)
    assert result is False


@pytest.mark.asyncio
async def test_kill_switch_true_after_enable(db_session: AsyncSession) -> None:
    """is_global_kill_switch_engaged returns True after enabling the switch."""
    await svc.update_settings(db_session, SettingUpdate(global_kill_switch_enabled=True))
    result = await svc.is_global_kill_switch_engaged(db_session)
    assert result is True
