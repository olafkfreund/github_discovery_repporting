from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.schemas.customer import CustomerCreate, CustomerResponse, CustomerUpdate
from backend.services import customer_service

router = APIRouter(prefix="/customers", tags=["customers"])


@router.post(
    "/",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new customer",
)
async def create_customer(
    payload: CustomerCreate,
    db: AsyncSession = Depends(get_db),
) -> CustomerResponse:
    """Create and persist a new customer record.

    The ``slug`` is derived automatically from ``name`` and does not need to
    be supplied by the caller.

    Args:
        payload: Validated customer creation payload.
        db: Injected async database session.

    Returns:
        The newly created customer record.
    """
    customer = await customer_service.create_customer(db, payload)
    return CustomerResponse.model_validate(customer)


@router.get(
    "/",
    response_model=list[CustomerResponse],
    summary="List all customers",
)
async def list_customers(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
) -> list[CustomerResponse]:
    """Return a paginated, alphabetically ordered list of customers.

    Args:
        skip: Number of records to skip (offset).
        limit: Maximum number of records to return.
        db: Injected async database session.

    Returns:
        A list of customer records, possibly empty.
    """
    customers = await customer_service.get_customers(db, skip=skip, limit=limit)
    return [CustomerResponse.model_validate(c) for c in customers]


@router.get(
    "/{customer_id}",
    response_model=CustomerResponse,
    summary="Get a customer by ID",
)
async def get_customer(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> CustomerResponse:
    """Fetch a single customer by primary key.

    Args:
        customer_id: UUID of the target customer.
        db: Injected async database session.

    Returns:
        The customer record.

    Raises:
        HTTPException: 404 if no customer with the given ID exists.
    """
    customer = await customer_service.get_customer(db, customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found.",
        )
    return CustomerResponse.model_validate(customer)


@router.put(
    "/{customer_id}",
    response_model=CustomerResponse,
    summary="Update a customer",
)
async def update_customer(
    customer_id: UUID,
    payload: CustomerUpdate,
    db: AsyncSession = Depends(get_db),
) -> CustomerResponse:
    """Apply a partial update to an existing customer.

    Only fields present in *payload* (not ``None``) are written.  When
    ``name`` is updated the ``slug`` is regenerated automatically.

    Args:
        customer_id: UUID of the customer to update.
        payload: Partial update payload.
        db: Injected async database session.

    Returns:
        The updated customer record.

    Raises:
        HTTPException: 404 if no customer with the given ID exists.
    """
    customer = await customer_service.update_customer(db, customer_id, payload)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found.",
        )
    return CustomerResponse.model_validate(customer)


@router.delete(
    "/{customer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a customer",
)
async def delete_customer(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a customer and all cascading records.

    Args:
        customer_id: UUID of the customer to remove.
        db: Injected async database session.

    Raises:
        HTTPException: 404 if no customer with the given ID exists.
    """
    deleted = await customer_service.delete_customer(db, customer_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found.",
        )
