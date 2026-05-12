"""Pydantic schemas for model card and model performance endpoints (REQ-050, REQ-051)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ModelCard(BaseModel):
    """Public metadata for a single model card."""

    slug: str
    provider: str
    model: str
    display_name: str
    context_window: int
    supports_tool_use: bool
    supports_structured_output: bool
    training_data_class: str
    training_data_cutoff: str | None = None
    license: str
    refreshed_at: str


class ModelCardContent(BaseModel):
    """Full markdown body for a named model card."""

    slug: str
    body: str


class ModelCardsResponse(BaseModel):
    """Response envelope for the model card list endpoint."""

    cards: list[ModelCard]


class ModelPerformanceRead(BaseModel):
    """Aggregate performance metrics for a single (provider, model) pair."""

    provider: str
    model: str
    run_count: int
    avg_cost_usd: float
    avg_input_tokens: float
    avg_output_tokens: float
    success_rate: float
    pr_open_rate: float
    avg_runtime_seconds: float | None = None
    last_run_at: datetime | None = None


class ModelPerformanceResponse(BaseModel):
    """Response envelope for the model performance dashboard endpoint."""

    metrics: list[ModelPerformanceRead]
    computed_at: datetime
