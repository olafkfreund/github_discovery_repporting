from __future__ import annotations

"""Pydantic schema for the cost-status API response."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class CostStatusRead(BaseModel):
    """Read-only snapshot of a customer's monthly cost-cap state.

    Attributes:
        customer_id: UUID of the customer this snapshot belongs to.
        month_start: First day of the current calendar month in UTC.
        spent_usd: Aggregated LLM cost in USD for this customer this month.
        cap_usd: Monthly cap from ``RemediationPolicy``; default 100.0.
        remaining_usd: ``max(0.0, cap_usd - spent_usd)``.
        exceeded: ``True`` when ``spent_usd >= cap_usd``.
    """

    customer_id: UUID
    month_start: datetime
    spent_usd: float
    cap_usd: float
    remaining_usd: float
    exceeded: bool
