from __future__ import annotations

"""Unified 3-layer kill-switch helper.

Checks kill-switch engagement in priority order:

1. **Global** — :attr:`~backend.models.setting.Setting.global_kill_switch_enabled`
   (blocks all customers when engaged).
2. **Customer** — :attr:`~backend.models.remediation_policy.RemediationPolicy.kill_switch_enabled`
   for the specific customer's remediation policy.

The result is a frozen :class:`KillSwitchState` dataclass indicating whether
the switch is engaged, at which layer, and why.
"""

import logging
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models.customer import Customer
from backend.services import settings_service

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KillSwitchState:
    """Result of a kill-switch check.

    Attributes:
        engaged: ``True`` when any kill-switch layer is engaged.
        layer: Which layer tripped the switch — ``"global"``, ``"customer"``,
            or ``"none"`` when the switch is not engaged.
        reason: Human-readable explanation when :attr:`engaged` is ``True``,
            ``None`` otherwise.
    """

    engaged: bool
    layer: Literal["global", "customer", "none"]
    reason: str | None


async def check(db: AsyncSession, customer_id: UUID) -> KillSwitchState:
    """Check kill-switch engagement for *customer_id* across all layers.

    Checks are performed in priority order — global first, then customer-level.
    The first engaged layer short-circuits; remaining layers are not evaluated.

    Args:
        db: Active async database session.
        customer_id: UUID of the customer whose remediation run is being
            evaluated.

    Returns:
        A :class:`KillSwitchState` describing the outcome.
    """
    # Layer 1: global kill switch.
    settings = await settings_service.get_settings(db)
    if settings.global_kill_switch_enabled:
        logger.warning(
            "kill_switch_service: global kill switch engaged — blocking customer %s",
            customer_id,
        )
        return KillSwitchState(
            engaged=True,
            layer="global",
            reason="Global kill switch is engaged.",
        )

    # Layer 2: customer-level policy.
    # Use a select() with selectinload so the remediation_policy relationship
    # is eager-loaded within the async context.  db.get() does not trigger
    # selectin loading, causing MissingGreenlet when the relationship is
    # accessed lazily in async code.
    result = await db.execute(
        select(Customer)
        .where(Customer.id == customer_id)
        .options(selectinload(Customer.remediation_policy))
    )
    customer = result.scalar_one_or_none()
    if customer is None:
        # Customer doesn't exist — won't reach here in normal flow, but be safe.
        return KillSwitchState(engaged=False, layer="none", reason=None)

    policy = customer.remediation_policy
    if policy and policy.kill_switch_enabled:
        logger.warning(
            "kill_switch_service: customer kill switch engaged — blocking customer %s",
            customer_id,
        )
        return KillSwitchState(
            engaged=True,
            layer="customer",
            reason=f"Customer kill switch is engaged for {customer_id}.",
        )

    return KillSwitchState(engaged=False, layer="none", reason=None)
