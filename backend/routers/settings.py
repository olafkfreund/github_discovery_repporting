from __future__ import annotations

"""Router for the global settings singleton (GET / PUT /api/settings)."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.schemas.setting import SettingRead, SettingUpdate
from backend.services import settings_service as svc

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get(
    "",
    response_model=SettingRead,
    summary="Get the global application settings",
)
async def get_settings(
    db: AsyncSession = Depends(get_db),
) -> SettingRead:
    """Return the global settings singleton.

    Creates the row with default values if it does not yet exist (e.g. in
    test environments that skip Alembic migrations).

    Args:
        db: Injected async database session.

    Returns:
        Serialised :class:`~backend.schemas.setting.SettingRead`.
    """
    row = await svc.get_settings(db)
    return SettingRead.model_validate(row)


@router.put(
    "",
    response_model=SettingRead,
    summary="Partially update the global application settings",
)
async def update_settings(
    payload: SettingUpdate,
    db: AsyncSession = Depends(get_db),
) -> SettingRead:
    """Apply a partial update to the global settings singleton.

    Only fields provided with non-``None`` values are written; absent fields
    retain their current stored values.

    Args:
        payload: Partial update body.
        db: Injected async database session.

    Returns:
        Serialised :class:`~backend.schemas.setting.SettingRead` reflecting
        the updated state.
    """
    row = await svc.update_settings(db, payload)
    return SettingRead.model_validate(row)
