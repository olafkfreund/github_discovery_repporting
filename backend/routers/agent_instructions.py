from __future__ import annotations

"""CRUD router for per-customer agent runtime instructions."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.schemas.agent_instructions import (
    AgentInstructionsRead,
    AgentInstructionsUpsertPayload,
)
from backend.services import agent_instructions_service as svc
from backend.services import customer_service

router = APIRouter(prefix="/api/customers", tags=["agent-instructions"])


@router.get(
    "/{customer_id}/agent-instructions",
    response_model=AgentInstructionsRead,
    summary="Get agent instructions for a customer",
)
async def get_agent_instructions(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> AgentInstructionsRead:
    """Return the customer's agent instructions row.

    # TODO: gate behind require_role("customer_admin")

    Args:
        customer_id: UUID of the owning customer.
        db: Injected async database session.

    Returns:
        Serialised :class:`~backend.schemas.agent_instructions.AgentInstructionsRead`.

    Raises:
        HTTPException: 404 when the customer does not exist or when no
            instructions row has been created yet for this customer.
    """
    customer = await customer_service.get_customer(db, customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found.",
        )

    row = await svc.get_for_customer(db, customer_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No agent instructions found for customer {customer_id}.",
        )

    return AgentInstructionsRead.model_validate(row)


@router.put(
    "/{customer_id}/agent-instructions",
    response_model=AgentInstructionsRead,
    summary="Create or replace agent instructions for a customer",
)
async def upsert_agent_instructions(
    customer_id: UUID,
    payload: AgentInstructionsUpsertPayload,
    db: AsyncSession = Depends(get_db),
) -> AgentInstructionsRead:
    """Create or atomically replace the customer's agent instructions.

    # TODO: gate behind require_role("customer_admin")

    If no row exists for the customer a new one is created; if a row already
    exists both ``content`` and ``enabled`` are replaced.

    Args:
        customer_id: UUID of the owning customer.
        payload: Upsert payload containing ``content`` and ``enabled``.
        db: Injected async database session.

    Returns:
        Serialised :class:`~backend.schemas.agent_instructions.AgentInstructionsRead`
        reflecting the stored state.

    Raises:
        HTTPException: 404 when the customer does not exist.
    """
    customer = await customer_service.get_customer(db, customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found.",
        )

    row = await svc.upsert(db, customer_id, payload)
    return AgentInstructionsRead.model_validate(row)


@router.delete(
    "/{customer_id}/agent-instructions",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete agent instructions for a customer",
)
async def delete_agent_instructions(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete the customer's agent instructions row.

    # TODO: gate behind require_role("customer_admin")

    Args:
        customer_id: UUID of the owning customer.
        db: Injected async database session.

    Raises:
        HTTPException: 404 when no instructions row exists for this customer.
    """
    deleted = await svc.delete(db, customer_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No agent instructions found for customer {customer_id}.",
        )
