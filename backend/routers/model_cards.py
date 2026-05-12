"""Read-only endpoints for model cards and performance metrics (REQ-050, REQ-051)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.model_cards import get_model_card_registry, load_model_card_content
from backend.schemas.model_card import (
    ModelCard,
    ModelCardContent,
    ModelCardsResponse,
    ModelPerformanceRead,
    ModelPerformanceResponse,
)
from backend.services import model_performance_service

router = APIRouter(prefix="/api/model-cards", tags=["model-cards"])


@router.get("/performance", response_model=ModelPerformanceResponse)
async def get_performance(
    customer_id: UUID | None = None,
    since: datetime | None = None,
    db: AsyncSession = Depends(get_db),
) -> ModelPerformanceResponse:
    """Return aggregate performance metrics for all (provider, model) pairs.

    This endpoint aggregates ``AgentRun`` rows by ``(provider, model)`` and
    computes run count, average cost, success rate, PR open rate, and average
    runtime.  Results are ordered by run count descending.

    Query parameters:
        customer_id: When provided, filters metrics to runs belonging to this
            customer's scans.
        since: Lower bound for ``started_at`` (ISO-8601 datetime).  Defaults
            to 30 days before the current time when omitted.

    Returns:
        :class:`~backend.schemas.model_card.ModelPerformanceResponse` with a
        ``metrics`` list and ``computed_at`` timestamp.
    """
    if since is None:
        since = datetime.now(UTC) - timedelta(days=30)
    raw = await model_performance_service.compute_metrics(
        db,
        customer_id=customer_id,
        since=since,
    )
    return ModelPerformanceResponse(
        metrics=[ModelPerformanceRead(**m.__dict__) for m in raw],
        computed_at=datetime.now(UTC),
    )


@router.get("/", response_model=ModelCardsResponse)
async def list_cards() -> ModelCardsResponse:
    """List all shipped model cards.

    Returns:
        :class:`~backend.schemas.model_card.ModelCardsResponse` containing
        one :class:`~backend.schemas.model_card.ModelCard` entry per built-in
        model card slug.
    """
    registry = get_model_card_registry()
    return ModelCardsResponse(cards=[ModelCard(**md.__dict__) for md in registry.values()])


@router.get("/{slug}/content", response_model=ModelCardContent)
async def get_card(slug: str) -> ModelCardContent:
    """Return the full markdown body for a named model card.

    Args:
        slug: Model card slug in ``<provider>__<model>`` format
            (e.g. ``"anthropic__claude-opus-4-7"``).

    Returns:
        :class:`~backend.schemas.model_card.ModelCardContent` with ``slug``
        and the full markdown ``body`` of the card file.

    Raises:
        HTTPException: 404 when *slug* does not match any built-in card.
    """
    try:
        body, _sha = load_model_card_content(slug)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown model card: {slug!r}",
        ) from None
    return ModelCardContent(slug=slug, body=body)
