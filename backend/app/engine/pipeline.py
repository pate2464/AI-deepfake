"""Detection pipeline orchestrator.

Runs all 8 detection layers (parallelising where possible), collects results,
and passes them through the ensemble scoring engine.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import (
    AnalysisContext,
    AnalysisResponse,
    HashMatch,
    LayerResult,
    RiskTier,
)
from app.db.database import Claim, ImageHash as ImageHashDB, HashMatchRecord
from app.detectors import (
    ai_model_detector,
    behavioral_detector,
    c2pa_detector,
    ela_detector,
    exif_detector,
    gemini_detector,
    hash_detector,
    noise_detector,
)
from app.engine.scoring import compute_risk_score


async def _run_sync_detector(func, *args) -> Any:
    """Run a synchronous detector in the default executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args)


async def run_pipeline(
    image_path: str,
    filename: str,
    context: AnalysisContext,
    session: AsyncSession,
) -> AnalysisResponse:
    """Execute the full 8-layer detection pipeline."""
    start = time.monotonic()

    # ── Create Claim record first (need ID for hash lookups) ──
    claim = Claim(
        filename=filename,
        image_path=image_path,
    )
    session.add(claim)
    await session.flush()  # Get claim.id

    # ── Run layers in parallel ─────────────────────────
    # Sync detectors wrapped for async execution
    exif_task = _run_sync_detector(exif_detector.analyze, image_path)
    ela_task = _run_sync_detector(ela_detector.analyze, image_path)
    ai_task = _run_sync_detector(ai_model_detector.analyze, image_path)
    c2pa_task = _run_sync_detector(c2pa_detector.analyze, image_path)
    noise_task = _run_sync_detector(noise_detector.analyze, image_path)

    # Async detectors
    hash_task = hash_detector.analyze(image_path, claim.id, session)
    behavioral_task = behavioral_detector.analyze(context, session)
    gemini_task = gemini_detector.analyze(image_path)

    # Gather all results
    results = await asyncio.gather(
        exif_task,
        ela_task,
        ai_task,
        c2pa_task,
        noise_task,
        hash_task,
        behavioral_task,
        gemini_task,
        return_exceptions=True,
    )

    # ── Unpack results ─────────────────────────────────
    layer_results: list[LayerResult] = []
    hash_matches: list[HashMatch] = []
    computed_hashes: dict[str, str] = {}
    ela_heatmap_b64: str | None = None
    gemini_reasoning: str | None = None

    # L1: EXIF
    if isinstance(results[0], LayerResult):
        layer_results.append(results[0])
    elif isinstance(results[0], Exception):
        layer_results.append(LayerResult(layer="exif", score=0.0, confidence=0.0, error=str(results[0])))

    # L2: ELA (returns tuple)
    if isinstance(results[1], tuple):
        lr, heatmap = results[1]
        layer_results.append(lr)
        ela_heatmap_b64 = heatmap
    elif isinstance(results[1], Exception):
        layer_results.append(LayerResult(layer="ela", score=0.0, confidence=0.0, error=str(results[1])))

    # L4: AI Model
    if isinstance(results[2], LayerResult):
        layer_results.append(results[2])
    elif isinstance(results[2], Exception):
        layer_results.append(LayerResult(layer="ai_model", score=0.0, confidence=0.0, error=str(results[2])))

    # L5: C2PA
    if isinstance(results[3], LayerResult):
        layer_results.append(results[3])
    elif isinstance(results[3], Exception):
        layer_results.append(LayerResult(layer="c2pa", score=0.0, confidence=0.0, error=str(results[3])))

    # L8: Noise
    if isinstance(results[4], LayerResult):
        layer_results.append(results[4])
    elif isinstance(results[4], Exception):
        layer_results.append(LayerResult(layer="noise", score=0.0, confidence=0.0, error=str(results[4])))

    # L3: Hash (returns tuple)
    if isinstance(results[5], tuple):
        lr, matches, hashes = results[5]
        layer_results.append(lr)
        hash_matches = matches
        computed_hashes = hashes
    elif isinstance(results[5], Exception):
        layer_results.append(LayerResult(layer="hash", score=0.0, confidence=0.0, error=str(results[5])))

    # L6: Behavioral
    if isinstance(results[6], LayerResult):
        layer_results.append(results[6])
    elif isinstance(results[6], Exception):
        layer_results.append(LayerResult(layer="behavioral", score=0.0, confidence=0.0, error=str(results[6])))

    # L7: Gemini (returns tuple)
    if isinstance(results[7], tuple):
        lr, reasoning = results[7]
        layer_results.append(lr)
        gemini_reasoning = reasoning
    elif isinstance(results[7], Exception):
        layer_results.append(LayerResult(layer="gemini", score=0.0, confidence=0.0, error=str(results[7])))

    # ── Ensemble scoring ───────────────────────────────
    risk_score, risk_tier = compute_risk_score(layer_results, hash_matches)

    processing_time_ms = int((time.monotonic() - start) * 1000)

    # ── Persist to DB ──────────────────────────────────
    claim.risk_score = risk_score
    claim.risk_tier = risk_tier.value
    claim.layer_scores = {lr.layer.value: lr.score for lr in layer_results}
    claim.gemini_reasoning = gemini_reasoning
    claim.processing_time_ms = processing_time_ms

    # Save hashes
    if computed_hashes:
        image_hash = ImageHashDB(
            claim_id=claim.id,
            ahash=computed_hashes.get("ahash"),
            phash=computed_hashes.get("phash"),
            dhash=computed_hashes.get("dhash"),
            whash=computed_hashes.get("whash"),
        )
        session.add(image_hash)

    # Save hash matches
    for m in hash_matches:
        session.add(HashMatchRecord(
            claim_id=claim.id,
            matched_claim_id=m.matched_claim_id,
            hamming_distance=m.hamming_distance,
            hash_type=m.hash_type,
        ))

    # Link account if provided
    if context.account_id:
        from app.db.database import Account
        from sqlalchemy import select
        result = await session.execute(
            select(Account).where(Account.account_id == context.account_id)
        )
        account = result.scalar_one_or_none()
        if account:
            claim.account_db_id = account.id

    await session.commit()

    return AnalysisResponse(
        id=claim.id,
        filename=filename,
        risk_score=risk_score,
        risk_tier=risk_tier,
        layer_results=layer_results,
        hash_matches=hash_matches,
        ela_heatmap_b64=ela_heatmap_b64,
        gemini_reasoning=gemini_reasoning,
        processing_time_ms=processing_time_ms,
        created_at=claim.created_at,
    )
