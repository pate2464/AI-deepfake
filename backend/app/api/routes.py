"""API routes for the fraud detection service."""

from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.models import (
    AnalysisContext,
    AnalysisHistoryItem,
    AnalysisResponse,
    RiskTier,
    StatsResponse,
)
from app.db.database import Claim, get_session
from app.engine.pipeline import run_pipeline
from app.storage.object_storage import put_bytes

router = APIRouter()


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_image(
    file: UploadFile = File(...),
    account_id: str | None = Form(None),
    device_fingerprint: str | None = Form(None),
    delivery_lat: float | None = Form(None),
    delivery_lon: float | None = Form(None),
    order_value: float | None = Form(None),
    claim_description: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
):
    """Upload an image for full-ensemble analysis with scoring metadata."""
    # Validate file type
    allowed_types = {
        "image/jpeg", "image/png", "image/webp", "image/tiff",
        "image/heic", "image/heif",
        "image/bmp", "image/gif",
        "application/octet-stream",  # Some browsers send HEIC as octet-stream
    }
    # Also allow by file extension for formats browsers don't always detect
    ext_lower = os.path.splitext(file.filename or "")[1].lower()
    allowed_exts = {".jpg", ".jpeg", ".png", ".webp", ".tiff", ".tif",
                    ".heic", ".heif", ".bmp", ".gif", ".avif"}

    if file.content_type not in allowed_types and ext_lower not in allowed_exts:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image format '{ext_lower}'. "
                   f"Use JPEG, PNG, WebP, HEIC, TIFF, or BMP.",
        )

    # Validate file size
    contents = await file.read()
    if len(contents) > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"File exceeds {settings.MAX_FILE_SIZE_MB}MB limit.")

    # Save to disk
    ext = os.path.splitext(file.filename or "image.jpg")[1] or ".jpg"
    safe_filename = f"{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(settings.UPLOAD_DIR, safe_filename)
    with open(save_path, "wb") as f:
        f.write(contents)

    stored_ref: str | None = None
    if settings.OBJECT_STORAGE_ENABLED:
        key = f"{settings.OBJECT_STORAGE_PREFIX.strip('/')}/{safe_filename}"
        try:
            stored_ref = await put_bytes(key=key, data=contents, filename=file.filename or safe_filename)
        except Exception:
            # Object storage should not block the analysis path.
            stored_ref = None

    # Build context
    context = AnalysisContext(
        account_id=account_id,
        device_fingerprint=device_fingerprint,
        delivery_lat=delivery_lat,
        delivery_lon=delivery_lon,
        order_value=order_value,
        claim_description=claim_description,
    )

    # Run pipeline
    result = await run_pipeline(
        save_path,
        file.filename or safe_filename,
        context,
        session,
        stored_image_ref=stored_ref,
    )
    return result


@router.get("/history", response_model=list[AnalysisHistoryItem])
async def get_history(
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
):
    """Get analysis history, newest first."""
    result = await session.execute(
        select(Claim)
        .order_by(desc(Claim.created_at))
        .offset(offset)
        .limit(min(limit, 200))
    )
    claims = result.scalars().all()
    return [
        AnalysisHistoryItem(
            id=c.id,
            filename=c.filename,
            risk_score=c.risk_score,
            risk_tier=RiskTier(c.risk_tier),
            created_at=c.created_at,
        )
        for c in claims
    ]


@router.get("/analysis/{claim_id}", response_model=dict)
async def get_analysis(
    claim_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get detailed analysis result by ID."""
    result = await session.execute(
        select(Claim).where(Claim.id == claim_id)
    )
    claim = result.scalar_one_or_none()
    if not claim:
        raise HTTPException(status_code=404, detail="Analysis not found")

    return {
        "id": claim.id,
        "filename": claim.filename,
        "risk_score": claim.risk_score,
        "risk_tier": claim.risk_tier,
        "layer_scores": claim.layer_scores,
        "layer_results": claim.layer_results_detail or [],
        "scoring_summary": claim.scoring_summary or {},
        "gemini_reasoning": claim.gemini_reasoning,
        "processing_time_ms": claim.processing_time_ms,
        "created_at": claim.created_at.isoformat(),
    }


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    session: AsyncSession = Depends(get_session),
):
    """Get aggregate statistics."""
    total = (await session.execute(select(func.count(Claim.id)))).scalar() or 0
    flagged = (await session.execute(
        select(func.count(Claim.id)).where(Claim.risk_tier == "high")
    )).scalar() or 0
    avg_score = (await session.execute(
        select(func.avg(Claim.risk_score))
    )).scalar() or 0.0

    # Count triggers per layer (score > 0.5)
    all_claims = (await session.execute(select(Claim.layer_scores))).scalars().all()
    layer_triggers: dict[str, int] = {}
    for scores in all_claims:
        if isinstance(scores, dict):
            for layer_name, score in scores.items():
                if score > 0.5:
                    layer_triggers[layer_name] = layer_triggers.get(layer_name, 0) + 1

    return StatsResponse(
        total_scans=total,
        flagged_count=flagged,
        avg_risk_score=round(float(avg_score), 4),
        layer_trigger_counts=layer_triggers,
    )


@router.get("/health")
async def health():
    """Health check."""
    return {"status": "ok", "service": settings.APP_NAME}
