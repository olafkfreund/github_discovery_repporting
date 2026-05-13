from __future__ import annotations

"""Router exposing per-customer monthly cost-cap status."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.schemas.cost_status import CostStatusRead
from backend.services import cost_cap_service

router = APIRouter(prefix="/api", tags=["cost-status"])


@router.get(
    "/customers/{customer_id}/cost-status",
    response_model=CostStatusRead,
    summary="Get monthly cost-cap status for a customer",
)
async def get_cost_status(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> CostStatusRead:
    """Return the current monthly cost-cap state for *customer_id*.

    Does **not** 404 on unknown customers — the aggregate returns 0.0 spent
    and the default cap (100.0) which is correct for a brand-new or policy-less
    customer.

    # TODO: gate behind require_role("customer_admin")

    Args:
        customer_id: UUID of the customer to query.
        db: Injected async database session.

    Returns:
        Serialised :class:`~backend.schemas.cost_status.CostStatusRead` with
        the current month's aggregate spend, cap, and remaining budget.
    """
    state = await cost_cap_service.check(db, customer_id)
    return CostStatusRead(
        customer_id=state.customer_id,
        month_start=state.month_start,
        spent_usd=state.spent_usd,
        cap_usd=state.cap_usd,
        remaining_usd=state.remaining_usd,
        exceeded=state.exceeded,
    )
