from __future__ import annotations

"""SQLAlchemy model for global application settings — singleton row."""

from uuid import UUID

from sqlalchemy import Boolean, Integer, String, TypeDecorator
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, TimestampMixin, UUIDMixin

#: Fixed primary key for the singleton row.  Only one row should ever exist in
#: the ``settings`` table.  The service layer enforces this invariant via
#: :func:`~backend.services.settings_service.get_settings`.
SINGLETON_ID: UUID = UUID("00000000-0000-0000-0000-000000000001")


class _RobustUUID(TypeDecorator):  # type: ignore[type-arg]
    """PostgreSQL UUID type that tolerates integer values from SQLite.

    SQLite's NUMERIC affinity coerces the all-zero UUID string
    ``00000000000000000000000000000001`` to integer ``1`` before the
    ``postgresql.UUID`` type processor can handle it.  This decorator
    intercepts the raw result value BEFORE the ``impl`` type processor runs,
    converting integers to their UUID equivalents.

    On PostgreSQL the underlying type handles everything correctly and this
    decorator adds no overhead.
    """

    impl = PG_UUID
    cache_ok = True

    def __init__(self) -> None:
        super().__init__(as_uuid=True)

    def result_processor(self, dialect: object, coltype: object) -> object:  # type: ignore[override]
        """Return a processor that converts raw DB values to :class:`~uuid.UUID`.

        Intercepts the raw result before the impl's processor runs so that
        SQLite integer values (from NUMERIC affinity coercion) are converted
        using ``UUID(int=value)`` rather than being passed to
        ``UUID(hex=value)`` which fails for integer inputs.
        """

        def process(value: object) -> UUID | None:
            if value is None:
                return None
            if isinstance(value, UUID):
                return value
            if isinstance(value, int):
                return UUID(int=value)
            # String / bytes — let the standard path handle it.
            raw = str(value)
            return UUID(raw.replace("-", "")) if "-" in raw else UUID(hex=raw)

        return process


class Setting(UUIDMixin, TimestampMixin, Base):
    """Global application settings — singleton row.

    Identified by the constant :data:`SINGLETON_ID`.
    :func:`~backend.services.settings_service.get_settings` ensures one row
    exists; the service layer never inserts a second.

    Attributes:
        global_kill_switch_enabled: When ``True`` all agent runs are blocked
            across every customer, regardless of per-customer policy.
        default_data_residency_region: ISO region tag for the default data
            residency zone (e.g. ``"eu-west"``).  Maximum 32 characters.
        audit_log_retention_days: How many days audit log entries are retained
            before scheduled pruning.  Range: 30–3 650 days.
        streaming_log_retention_hours: How many hours streaming run logs are
            retained before pruning.  Range: 1–720 hours.
        default_llm_connection_id: Optional UUID of the global fallback LLM
            connection used when a customer has not configured one.
    """

    __tablename__ = "settings"

    # Override UUIDMixin.id with _RobustUUID so that SQLite's numeric-affinity
    # coercion of the all-zero UUID string back to integer is handled safely.
    # The _RobustUUID TypeDecorator wraps postgresql.UUID and converts integer
    # result values via UUID(int=value).
    id: Mapped[UUID] = mapped_column(
        _RobustUUID(),
        primary_key=True,
        default=lambda: SINGLETON_ID,
    )

    global_kill_switch_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    default_data_residency_region: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="eu-west",
        server_default="'eu-west'",
    )
    audit_log_retention_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=180,
        server_default="180",
    )
    streaming_log_retention_hours: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=72,
        server_default="72",
    )
    default_llm_connection_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
