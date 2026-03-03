from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.scan_profile import ScanProfile
from backend.scanners.registry import get_scanner_registry, registry_to_dicts
from backend.schemas.scan_profile import (
    ScanProfileCreate,
    ScanProfileResponse,
    ScanProfileUpdate,
)
from backend.services import customer_service

router = APIRouter(tags=["scan-profiles"])


# ---------------------------------------------------------------------------
# Scanner registry (read-only, auto-generated)
# ---------------------------------------------------------------------------


@router.get(
    "/scanners/registry",
    summary="Get the full scanner registry",
)
async def scanner_registry() -> list[dict[str, Any]]:
    """Return all scanner categories, checks, and threshold defaults.

    This endpoint reflects scanner code at runtime — nothing is manually
    maintained.  It is used by the frontend profile editor to populate
    category/check listings and threshold input defaults.
    """
    return registry_to_dicts(get_scanner_registry())


# ---------------------------------------------------------------------------
# Scan profile CRUD
# ---------------------------------------------------------------------------


@router.get(
    "/customers/{customer_id}/scan-profiles",
    response_model=list[ScanProfileResponse],
    summary="List scan profiles for a customer",
)
async def list_profiles(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[ScanProfileResponse]:
    customer = await customer_service.get_customer(db, customer_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Customer {customer_id} not found.")

    result = await db.execute(
        select(ScanProfile)
        .where(ScanProfile.customer_id == customer_id)
        .order_by(ScanProfile.created_at.desc())
    )
    profiles = list(result.scalars().all())
    return [ScanProfileResponse.model_validate(p) for p in profiles]


@router.post(
    "/customers/{customer_id}/scan-profiles",
    response_model=ScanProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a scan profile",
)
async def create_profile(
    customer_id: UUID,
    payload: ScanProfileCreate,
    db: AsyncSession = Depends(get_db),
) -> ScanProfileResponse:
    customer = await customer_service.get_customer(db, customer_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Customer {customer_id} not found.")

    profile = ScanProfile(
        customer_id=customer_id,
        name=payload.name,
        description=payload.description,
        is_default=payload.is_default,
        config=payload.config,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return ScanProfileResponse.model_validate(profile)


@router.get(
    "/scan-profiles/{profile_id}",
    response_model=ScanProfileResponse,
    summary="Get a scan profile by ID",
)
async def get_profile(
    profile_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ScanProfileResponse:
    result = await db.execute(select(ScanProfile).where(ScanProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Scan profile {profile_id} not found.")
    return ScanProfileResponse.model_validate(profile)


@router.put(
    "/scan-profiles/{profile_id}",
    response_model=ScanProfileResponse,
    summary="Update a scan profile",
)
async def update_profile(
    profile_id: UUID,
    payload: ScanProfileUpdate,
    db: AsyncSession = Depends(get_db),
) -> ScanProfileResponse:
    result = await db.execute(select(ScanProfile).where(ScanProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Scan profile {profile_id} not found.")

    if payload.name is not None:
        profile.name = payload.name
    if payload.description is not None:
        profile.description = payload.description
    if payload.is_default is not None:
        profile.is_default = payload.is_default
    if payload.config is not None:
        profile.config = payload.config

    await db.commit()
    await db.refresh(profile)
    return ScanProfileResponse.model_validate(profile)


@router.delete(
    "/scan-profiles/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a scan profile",
)
async def delete_profile(
    profile_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(select(ScanProfile).where(ScanProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Scan profile {profile_id} not found.")

    await db.delete(profile)
    await db.commit()
