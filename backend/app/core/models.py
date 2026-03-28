"""Pydantic models for API request/response schemas."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────

class RiskTier(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class LayerName(str, enum.Enum):
    EXIF = "exif"
    ELA = "ela"
    HASH = "hash"
    AI_MODEL = "ai_model"
    C2PA = "c2pa"
    BEHAVIORAL = "behavioral"
    GEMINI = "gemini"
    NOISE = "noise"


# ── Layer Results ──────────────────────────────────────

class LayerResult(BaseModel):
    layer: LayerName
    score: float = Field(ge=0.0, le=1.0, description="Suspicion score 0-1")
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    flags: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


# ── Hash Match ─────────────────────────────────────────

class HashMatch(BaseModel):
    matched_claim_id: int
    hamming_distance: int
    hash_type: str


# ── Analysis Request ───────────────────────────────────

class AnalysisContext(BaseModel):
    """Optional contextual data sent alongside the image."""
    account_id: Optional[str] = None
    device_fingerprint: Optional[str] = None
    delivery_lat: Optional[float] = None
    delivery_lon: Optional[float] = None
    order_value: Optional[float] = None
    claim_description: Optional[str] = None


# ── Analysis Response ──────────────────────────────────

class AnalysisResponse(BaseModel):
    id: int
    filename: str
    risk_score: float = Field(ge=0.0, le=1.0)
    risk_tier: RiskTier
    layer_results: list[LayerResult]
    hash_matches: list[HashMatch] = Field(default_factory=list)
    ela_heatmap_b64: Optional[str] = None
    gemini_reasoning: Optional[str] = None
    processing_time_ms: int
    created_at: datetime


# ── History ────────────────────────────────────────────

class AnalysisHistoryItem(BaseModel):
    id: int
    filename: str
    risk_score: float
    risk_tier: RiskTier
    created_at: datetime


class StatsResponse(BaseModel):
    total_scans: int
    flagged_count: int
    avg_risk_score: float
    layer_trigger_counts: dict[str, int]
