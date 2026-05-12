from __future__ import annotations

"""Service layer for the global settings singleton.

There is exactly one :class:`~backend.models.setting.Setting` row in the
database, identified by :data:`~backend.models.setting.SINGLETON_ID`.
``get_settings`` is the canonical entry point for reads; it creates the row
when it is missing (test databases bootstrapped via ``create_all`` skip
migrations and therefore never receive the INSERT from migration 010).
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.setting import SINGLETON_ID, Setting
from backend.schemas.setting import SettingUpdate

logger = logging.getLogger(__name__)


async def get_settings(db: AsyncSession) -> Setting:
    """Return the singleton :class:`~backend.models.setting.Setting` row.

    Creates the row if it is missing.  The Alembic migration inserts the row on
    ``upgrade``, but this guard handles test databases that skip migrations and
    use ``metadata.create_all()`` instead.

    Args:
        db: Active async database session.

    Returns:
        The singleton :class:`~backend.models.setting.Setting` row.
    """
    row = await db.get(Setting, SINGLETON_ID)
    if row is None:
        now = datetime.now(tz=UTC)
        row = Setting(id=SINGLETON_ID, created_at=now, updated_at=now)
        db.add(row)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            row = await db.get(Setting, SINGLETON_ID)
            if row is None:  # pragma: no cover — race-condition safety net
                raise
        # expire_on_commit=False means all Python-side attribute values are
        # retained after commit — no refresh needed.  Explicitly setting
        # created_at / updated_at above avoids a server-side round-trip that
        # exposes a SQLite type-affinity issue with the all-zero singleton UUID.
    return row


async def update_settings(db: AsyncSession, patch: SettingUpdate) -> Setting:
    """Apply non-``None`` fields from *patch* to the singleton row.

    Only fields explicitly provided (non-``None``) are written; absent fields
    retain their stored values.  The updated row is returned.

    Args:
        db: Active async database session.
        patch: Partial update payload.

    Returns:
        The updated :class:`~backend.models.setting.Setting` row.
    """
    # Load (or create) the singleton to get the current state Python-side.
    row = await get_settings(db)
    update_data = patch.model_dump(exclude_none=True)
    if not update_data:
        return row

    now = datetime.now(tz=UTC)
    update_data["updated_at"] = now

    # Use a core UPDATE statement instead of ORM setattr+commit to avoid the
    # post-UPDATE SELECT that SQLAlchemy issues for columns with
    # ``onupdate=func.now()``.  That SELECT reads ``id`` from SQLite as integer
    # ``1`` (NUMERIC affinity coerces the all-zero UUID string) which breaks
    # the PostgreSQL UUID type processor.
    # Mirror the changes Python-side BEFORE the DB write so the ORM identity
    # map stays consistent (synchronize_session=False skips the ORM sync step
    # which would otherwise issue a SELECT on the singleton row and hit
    # SQLite's integer-coercion issue for all-zero UUID strings).
    for field, value in update_data.items():
        setattr(row, field, value)

    await db.execute(
        update(Setting)
        .where(Setting.id == SINGLETON_ID)
        .values(**update_data)
        .execution_options(synchronize_session=False)
    )
    await db.commit()

    logger.info("settings_service: updated settings fields=%s", list(update_data))
    return row


async def is_global_kill_switch_engaged(db: AsyncSession) -> bool:
    """Return ``True`` when the global kill switch is engaged.

    Convenience wrapper around :func:`get_settings` for callers that only need
    the boolean flag without loading the full settings object.

    Args:
        db: Active async database session.

    Returns:
        ``True`` if :attr:`~backend.models.setting.Setting.global_kill_switch_enabled`
        is set, ``False`` otherwise.
    """
    settings = await get_settings(db)
    return settings.global_kill_switch_enabled
