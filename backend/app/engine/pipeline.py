"""Detection pipeline orchestrator.

Runs all 21 detection layers (parallelising where possible), collects results,
and passes them through the ensemble scoring engine.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.layer_catalog import get_layer_metadata
from app.core.models import (
    AnalysisContext,
    AnalysisResponse,
    HashMatch,
    LayerResult,
)
from app.db.database import Claim, ImageHash as ImageHashDB, HashMatchRecord
from app.detectors import (
    ai_model_detector,
    attention_pattern_detector,
    behavioral_detector,
    c2pa_detector,
    clip_detector,
    cnn_detector,
    dct_hist_detector,
    dire_detector,
    ela_detector,
    exif_detector,
    gan_fingerprint_detector,
    gemini_detector,
    gradient_detector,
    hash_detector,
    lsb_detector,
    mlep_detector,
    noise_detector,
    npr_detector,
    texture_detector,
    trufor_detector,
    watermark_detector,
)
from app.engine.scoring import compute_risk_score

logger = logging.getLogger(__name__)

MAX_PREPROCESS_DIM = 2048  # Resize large images once to avoid memory pressure


def _preprocess_image(image_path: str) -> str:
    """Load image once, resize if needed, save as JPEG.

    Avoids 10+ threads simultaneously decoding a large HEIC/RAW file,
    which causes out-of-memory errors.  Returns path to a JPEG copy
    (or the original path if the image is already small enough and JPEG).
    """
    try:
        img = Image.open(image_path)
        img.load()                       # force decode once
        img = img.convert("RGB")
    except Exception:
        logger.warning("Pre-process: cannot open %s, detectors will retry", image_path)
        return image_path                # fall through – detectors handle errors

    w, h = img.size
    ext = os.path.splitext(image_path)[1].lower()

    needs_resize = max(w, h) > MAX_PREPROCESS_DIM
    needs_convert = ext not in (".jpg", ".jpeg", ".png", ".bmp", ".webp")

    if not needs_resize and not needs_convert:
        img.close()
        return image_path                # no work needed

    if needs_resize:
        scale = MAX_PREPROCESS_DIM / max(w, h)
        new_w = max(4, int(w * scale))   # keep divisible-by-4 friendly
        new_h = max(4, int(h * scale))
        new_w -= new_w % 4
        new_h -= new_h % 4
        img = img.resize((new_w, new_h), Image.LANCZOS)

    out_w, out_h = img.size
    base = os.path.splitext(image_path)[0]
    out_path = f"{base}_pp.png"
    img.save(out_path, "PNG")
    img.close()
    logger.info("Pre-processed %s → %s (%dx%d)", image_path, out_path, out_w, out_h)
    return out_path


async def _run_sync_detector(func, *args) -> Any:
    """Run a synchronous detector in the default executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args)


async def _run_timed(awaitable) -> tuple[Any, int]:
    """Run a detector and capture elapsed time even when it fails."""
    started = time.perf_counter()
    try:
        result = await awaitable
    except Exception as exc:  # pragma: no cover - defensive wrapper
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return exc, elapsed_ms
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return result, elapsed_ms


def _annotate_layer_result(layer_result: LayerResult, duration_ms: int) -> LayerResult:
    """Attach canonical metadata and timing to a layer result."""
    metadata = get_layer_metadata(layer_result.layer)
    layer_result.duration_ms = duration_ms
    layer_result.evidence_family = metadata.get("evidence_family")
    layer_result.implementation_kind = metadata.get("implementation_kind")
    layer_result.score_role = metadata.get("score_role")
    return layer_result


def _build_error_layer_result(layer: str, error: Exception | str, duration_ms: int) -> LayerResult:
    """Create a structured error result with timing and catalog metadata."""
    return _annotate_layer_result(
        LayerResult(layer=layer, score=0.0, confidence=0.0, error=str(error)),
        duration_ms,
    )


async def run_pipeline(
    image_path: str,
    filename: str,
    context: AnalysisContext,
    session: AsyncSession,
    *,
    stored_image_ref: str | None = None,
) -> AnalysisResponse:
    """Execute the full 21-layer detection pipeline."""
    start = time.monotonic()

    # ── Pre-process image once (decode HEIC, resize if huge) ──
    pp_path = await _run_sync_detector(_preprocess_image, image_path)

    # ── Create Claim record first (need ID for hash lookups) ──
    claim = Claim(
        filename=filename,
        image_path=stored_image_ref or image_path,
    )
    session.add(claim)
    await session.flush()  # Get claim.id

    # ── Run layers in parallel ─────────────────────────
    # EXIF + C2PA use ORIGINAL (need metadata / embedded manifests).
    # All pixel-analysis detectors use the pre-processed JPEG.
    exif_task = _run_timed(_run_sync_detector(exif_detector.analyze, image_path))
    ela_task = _run_timed(_run_sync_detector(ela_detector.analyze, pp_path))
    ai_task = _run_timed(_run_sync_detector(ai_model_detector.analyze, pp_path))
    c2pa_task = _run_timed(_run_sync_detector(c2pa_detector.analyze, image_path))
    noise_task = _run_timed(_run_sync_detector(noise_detector.analyze, pp_path))
    clip_task = _run_timed(_run_sync_detector(clip_detector.analyze, pp_path))
    cnn_task = _run_timed(_run_sync_detector(cnn_detector.analyze, pp_path))
    watermark_task = _run_timed(_run_sync_detector(watermark_detector.analyze, pp_path))
    trufor_task = _run_timed(_run_sync_detector(trufor_detector.analyze, pp_path))
    dire_task = _run_timed(_run_sync_detector(dire_detector.analyze, pp_path))
    gradient_task = _run_timed(_run_sync_detector(gradient_detector.analyze, pp_path))
    lsb_task = _run_timed(_run_sync_detector(lsb_detector.analyze, pp_path))
    dct_hist_task = _run_timed(_run_sync_detector(dct_hist_detector.analyze, pp_path))
    gan_fp_task = _run_timed(_run_sync_detector(gan_fingerprint_detector.analyze, pp_path))
    attn_task = _run_timed(_run_sync_detector(attention_pattern_detector.analyze, pp_path))
    texture_task = _run_timed(_run_sync_detector(texture_detector.analyze, pp_path))
    npr_task = _run_timed(_run_sync_detector(npr_detector.analyze, pp_path))
    mlep_task = _run_timed(_run_sync_detector(mlep_detector.analyze, pp_path))

    # Async detectors
    hash_task = _run_timed(hash_detector.analyze(pp_path, claim.id, session))
    behavioral_task = _run_timed(behavioral_detector.analyze(context, session))
    gemini_task = _run_timed(gemini_detector.analyze(pp_path))

    # Gather all results
    results = await asyncio.gather(
        exif_task,       # 0
        ela_task,        # 1
        ai_task,         # 2
        c2pa_task,       # 3
        noise_task,      # 4
        hash_task,       # 5
        behavioral_task, # 6
        gemini_task,     # 7
        clip_task,       # 8
        cnn_task,        # 9
        watermark_task,  # 10
        trufor_task,     # 11
        dire_task,       # 12
        gradient_task,   # 13
        lsb_task,        # 14
        dct_hist_task,   # 15
        gan_fp_task,     # 16
        attn_task,       # 17
        texture_task,    # 18
        npr_task,        # 19
        mlep_task,       # 20
    )

    # ── Unpack results ─────────────────────────────────
    layer_results: list[LayerResult] = []
    hash_matches: list[HashMatch] = []
    computed_hashes: dict[str, str] = {}
    ela_heatmap_b64: str | None = None
    trufor_heatmap_b64: str | None = None
    gemini_reasoning: str | None = None

    # L1: EXIF
    raw_result, duration_ms = results[0]
    if isinstance(raw_result, LayerResult):
        layer_results.append(_annotate_layer_result(raw_result, duration_ms))
    elif isinstance(raw_result, Exception):
        layer_results.append(_build_error_layer_result("exif", raw_result, duration_ms))

    # L2: ELA (returns tuple)
    raw_result, duration_ms = results[1]
    if isinstance(raw_result, tuple):
        lr, heatmap = raw_result
        layer_results.append(_annotate_layer_result(lr, duration_ms))
        ela_heatmap_b64 = heatmap
    elif isinstance(raw_result, Exception):
        layer_results.append(_build_error_layer_result("ela", raw_result, duration_ms))

    # L4: AI Model
    raw_result, duration_ms = results[2]
    if isinstance(raw_result, LayerResult):
        layer_results.append(_annotate_layer_result(raw_result, duration_ms))
    elif isinstance(raw_result, Exception):
        layer_results.append(_build_error_layer_result("ai_model", raw_result, duration_ms))

    # L5: C2PA
    raw_result, duration_ms = results[3]
    if isinstance(raw_result, LayerResult):
        layer_results.append(_annotate_layer_result(raw_result, duration_ms))
    elif isinstance(raw_result, Exception):
        layer_results.append(_build_error_layer_result("c2pa", raw_result, duration_ms))

    # L8: Noise / PRNU
    raw_result, duration_ms = results[4]
    if isinstance(raw_result, LayerResult):
        layer_results.append(_annotate_layer_result(raw_result, duration_ms))
    elif isinstance(raw_result, Exception):
        layer_results.append(_build_error_layer_result("noise", raw_result, duration_ms))

    # L3: Hash (returns tuple)
    raw_result, duration_ms = results[5]
    if isinstance(raw_result, tuple):
        lr, matches, hashes = raw_result
        layer_results.append(_annotate_layer_result(lr, duration_ms))
        hash_matches = matches
        computed_hashes = hashes
    elif isinstance(raw_result, Exception):
        layer_results.append(_build_error_layer_result("hash", raw_result, duration_ms))

    # L6: Behavioral
    raw_result, duration_ms = results[6]
    if isinstance(raw_result, LayerResult):
        layer_results.append(_annotate_layer_result(raw_result, duration_ms))
    elif isinstance(raw_result, Exception):
        layer_results.append(_build_error_layer_result("behavioral", raw_result, duration_ms))

    # L7: Gemini (returns tuple)
    raw_result, duration_ms = results[7]
    if isinstance(raw_result, tuple):
        lr, reasoning = raw_result
        layer_results.append(_annotate_layer_result(lr, duration_ms))
        gemini_reasoning = reasoning
    elif isinstance(raw_result, Exception):
        layer_results.append(_build_error_layer_result("gemini", raw_result, duration_ms))

    # L9: CLIP Detection
    raw_result, duration_ms = results[8]
    if isinstance(raw_result, LayerResult):
        layer_results.append(_annotate_layer_result(raw_result, duration_ms))
    elif isinstance(raw_result, Exception):
        layer_results.append(_build_error_layer_result("clip_detect", raw_result, duration_ms))

    # L10: CNN Detection
    raw_result, duration_ms = results[9]
    if isinstance(raw_result, LayerResult):
        layer_results.append(_annotate_layer_result(raw_result, duration_ms))
    elif isinstance(raw_result, Exception):
        layer_results.append(_build_error_layer_result("cnn_detect", raw_result, duration_ms))

    # L11: Watermark
    raw_result, duration_ms = results[10]
    if isinstance(raw_result, LayerResult):
        layer_results.append(_annotate_layer_result(raw_result, duration_ms))
    elif isinstance(raw_result, Exception):
        layer_results.append(_build_error_layer_result("watermark", raw_result, duration_ms))

    # L12: TruFor (returns tuple)
    raw_result, duration_ms = results[11]
    if isinstance(raw_result, tuple):
        lr, heatmap = raw_result
        layer_results.append(_annotate_layer_result(lr, duration_ms))
        trufor_heatmap_b64 = heatmap
    elif isinstance(raw_result, LayerResult):
        layer_results.append(_annotate_layer_result(raw_result, duration_ms))
    elif isinstance(raw_result, Exception):
        layer_results.append(_build_error_layer_result("trufor", raw_result, duration_ms))

    # L13: DIRE
    raw_result, duration_ms = results[12]
    if isinstance(raw_result, LayerResult):
        layer_results.append(_annotate_layer_result(raw_result, duration_ms))
    elif isinstance(raw_result, Exception):
        layer_results.append(_build_error_layer_result("dire", raw_result, duration_ms))

    # L14: Gradient Distribution
    raw_result, duration_ms = results[13]
    if isinstance(raw_result, LayerResult):
        layer_results.append(_annotate_layer_result(raw_result, duration_ms))
    elif isinstance(raw_result, Exception):
        layer_results.append(_build_error_layer_result("gradient", raw_result, duration_ms))

    # L15: LSB Forensics
    raw_result, duration_ms = results[14]
    if isinstance(raw_result, LayerResult):
        layer_results.append(_annotate_layer_result(raw_result, duration_ms))
    elif isinstance(raw_result, Exception):
        layer_results.append(_build_error_layer_result("lsb", raw_result, duration_ms))

    # L16: DCT Histogram Analysis
    raw_result, duration_ms = results[15]
    if isinstance(raw_result, LayerResult):
        layer_results.append(_annotate_layer_result(raw_result, duration_ms))
    elif isinstance(raw_result, Exception):
        layer_results.append(_build_error_layer_result("dct_hist", raw_result, duration_ms))

    # L17: GAN Spectral Fingerprint
    raw_result, duration_ms = results[16]
    if isinstance(raw_result, LayerResult):
        layer_results.append(_annotate_layer_result(raw_result, duration_ms))
    elif isinstance(raw_result, Exception):
        layer_results.append(_build_error_layer_result("gan_fingerprint", raw_result, duration_ms))

    # L18: Attention Pattern Detection
    raw_result, duration_ms = results[17]
    if isinstance(raw_result, LayerResult):
        layer_results.append(_annotate_layer_result(raw_result, duration_ms))
    elif isinstance(raw_result, Exception):
        layer_results.append(_build_error_layer_result("attention_pattern", raw_result, duration_ms))

    # L19: Texture Analysis
    raw_result, duration_ms = results[18]
    if isinstance(raw_result, LayerResult):
        layer_results.append(_annotate_layer_result(raw_result, duration_ms))
    elif isinstance(raw_result, Exception):
        layer_results.append(_build_error_layer_result("texture", raw_result, duration_ms))

    # L20: NPR Pixel Residuals
    raw_result, duration_ms = results[19]
    if isinstance(raw_result, LayerResult):
        layer_results.append(_annotate_layer_result(raw_result, duration_ms))
    elif isinstance(raw_result, Exception):
        layer_results.append(_build_error_layer_result("npr", raw_result, duration_ms))

    # L21: MLEP Entropy Patterns
    raw_result, duration_ms = results[20]
    if isinstance(raw_result, LayerResult):
        layer_results.append(_annotate_layer_result(raw_result, duration_ms))
    elif isinstance(raw_result, Exception):
        layer_results.append(_build_error_layer_result("mlep", raw_result, duration_ms))

    # ── Ensemble scoring ───────────────────────────────
    scoring_summary = compute_risk_score(layer_results, hash_matches)
    risk_score = scoring_summary.final_score
    risk_tier = scoring_summary.risk_tier

    processing_time_ms = int((time.monotonic() - start) * 1000)

    # ── Persist to DB ──────────────────────────────────
    claim.risk_score = risk_score
    claim.risk_tier = risk_tier.value
    claim.layer_scores = {lr.layer.value: lr.score for lr in layer_results}
    claim.layer_results_detail = [lr.model_dump(mode="json") for lr in layer_results]
    claim.scoring_summary = scoring_summary.model_dump(mode="json")
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

    # ── Cleanup preprocessed temp file ─────────────────
    if pp_path != image_path and os.path.exists(pp_path):
        try:
            os.remove(pp_path)
        except OSError:
            pass

    return AnalysisResponse(
        id=claim.id,
        filename=filename,
        risk_score=risk_score,
        risk_tier=risk_tier,
        scoring_summary=scoring_summary,
        layer_results=layer_results,
        hash_matches=hash_matches,
        ela_heatmap_b64=ela_heatmap_b64,
        trufor_heatmap_b64=trufor_heatmap_b64,
        gemini_reasoning=gemini_reasoning,
        processing_time_ms=processing_time_ms,
        created_at=claim.created_at,
    )
