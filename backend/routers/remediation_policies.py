from __future__ import annotations

"""CRUD router for per-customer remediation policy configuration."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.schemas.remediation_policy import RemediationPolicyRead, RemediationPolicyUpsert
from backend.services import customer_service
from backend.services import remediation_policy_service as svc

router = APIRouter(prefix="/api/customers", tags=["remediation-policies"])


@router.get(
    "/{customer_id}/remediation-policy",
    response_model=RemediationPolicyRead,
    summary="Get the remediation policy for a customer",
)
async def get_remediation_policy(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> RemediationPolicyRead:
    """Return the customer's remediation policy row.

    # TODO: gate behind require_role("customer_admin")

    Args:
        customer_id: UUID of the owning customer.
        db: Injected async database session.

    Returns:
        Serialised :class:`~backend.schemas.remediation_policy.RemediationPolicyRead`.

    Raises:
        HTTPException: 404 when the customer does not exist or when no
            remediation policy row has been created yet for this customer.
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
            detail=f"No remediation policy found for customer {customer_id}.",
        )

    return RemediationPolicyRead.model_validate(row)


@router.put(
    "/{customer_id}/remediation-policy",
    response_model=RemediationPolicyRead,
    summary="Create or replace the remediation policy for a customer",
)
async def upsert_remediation_policy(
    customer_id: UUID,
    payload: RemediationPolicyUpsert,
    db: AsyncSession = Depends(get_db),
) -> RemediationPolicyRead:
    """Create or atomically replace the customer's remediation policy.

    # TODO: gate behind require_role("customer_admin")

    If no row exists for the customer a new one is created; if a row already
    exists all policy fields are replaced.

    Args:
        customer_id: UUID of the owning customer.
        payload: Upsert payload containing all policy fields.
        db: Injected async database session.

    Returns:
        Serialised :class:`~backend.schemas.remediation_policy.RemediationPolicyRead`
        reflecting the stored state.

    Raises:
        HTTPException: 404 when the customer does not exist.
    """
    # TODO: gate behind require_role("customer_admin")
    customer = await customer_service.get_customer(db, customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found.",
        )

    row = await svc.upsert(db, customer_id, payload)
    return RemediationPolicyRead.model_validate(row)


@router.delete(
    "/{customer_id}/remediation-policy",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete the remediation policy for a customer",
)
async def delete_remediation_policy(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete the customer's remediation policy row.

    # TODO: gate behind require_role("customer_admin")

    Args:
        customer_id: UUID of the owning customer.
        db: Injected async database session.

    Raises:
        HTTPException: 404 when no remediation policy row exists for this customer.
    """
    # TODO: gate behind require_role("customer_admin")
    deleted = await svc.delete(db, customer_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No remediation policy found for customer {customer_id}.",
        )
