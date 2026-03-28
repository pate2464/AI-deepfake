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

logger = logging.getLogger(__name__)

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


async def run_pipeline(
    image_path: str,
    filename: str,
    context: AnalysisContext,
    session: AsyncSession,
) -> AnalysisResponse:
    """Execute the full 21-layer detection pipeline."""
    start = time.monotonic()

    # ── Pre-process image once (decode HEIC, resize if huge) ──
    pp_path = await _run_sync_detector(_preprocess_image, image_path)

    # ── Create Claim record first (need ID for hash lookups) ──
    claim = Claim(
        filename=filename,
        image_path=image_path,
    )
    session.add(claim)
    await session.flush()  # Get claim.id

    # ── Run layers in parallel ─────────────────────────
    # EXIF + C2PA use ORIGINAL (need metadata / embedded manifests).
    # All pixel-analysis detectors use the pre-processed JPEG.
    exif_task = _run_sync_detector(exif_detector.analyze, image_path)
    ela_task = _run_sync_detector(ela_detector.analyze, pp_path)
    ai_task = _run_sync_detector(ai_model_detector.analyze, pp_path)
    c2pa_task = _run_sync_detector(c2pa_detector.analyze, image_path)
    noise_task = _run_sync_detector(noise_detector.analyze, pp_path)
    clip_task = _run_sync_detector(clip_detector.analyze, pp_path)
    cnn_task = _run_sync_detector(cnn_detector.analyze, pp_path)
    watermark_task = _run_sync_detector(watermark_detector.analyze, pp_path)
    trufor_task = _run_sync_detector(trufor_detector.analyze, pp_path)
    dire_task = _run_sync_detector(dire_detector.analyze, pp_path)
    gradient_task = _run_sync_detector(gradient_detector.analyze, pp_path)
    lsb_task = _run_sync_detector(lsb_detector.analyze, pp_path)
    dct_hist_task = _run_sync_detector(dct_hist_detector.analyze, pp_path)
    gan_fp_task = _run_sync_detector(gan_fingerprint_detector.analyze, pp_path)
    attn_task = _run_sync_detector(attention_pattern_detector.analyze, pp_path)
    texture_task = _run_sync_detector(texture_detector.analyze, pp_path)
    npr_task = _run_sync_detector(npr_detector.analyze, pp_path)
    mlep_task = _run_sync_detector(mlep_detector.analyze, pp_path)

    # Async detectors
    hash_task = hash_detector.analyze(pp_path, claim.id, session)
    behavioral_task = behavioral_detector.analyze(context, session)
    gemini_task = gemini_detector.analyze(pp_path)

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
        return_exceptions=True,
    )

    # ── Unpack results ─────────────────────────────────
    layer_results: list[LayerResult] = []
    hash_matches: list[HashMatch] = []
    computed_hashes: dict[str, str] = {}
    ela_heatmap_b64: str | None = None
    trufor_heatmap_b64: str | None = None
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

    # L8: Noise / PRNU
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

    # L9: CLIP Detection
    if isinstance(results[8], LayerResult):
        layer_results.append(results[8])
    elif isinstance(results[8], Exception):
        layer_results.append(LayerResult(layer="clip_detect", score=0.0, confidence=0.0, error=str(results[8])))

    # L10: CNN Detection
    if isinstance(results[9], LayerResult):
        layer_results.append(results[9])
    elif isinstance(results[9], Exception):
        layer_results.append(LayerResult(layer="cnn_detect", score=0.0, confidence=0.0, error=str(results[9])))

    # L11: Watermark
    if isinstance(results[10], LayerResult):
        layer_results.append(results[10])
    elif isinstance(results[10], Exception):
        layer_results.append(LayerResult(layer="watermark", score=0.0, confidence=0.0, error=str(results[10])))

    # L12: TruFor (returns tuple)
    if isinstance(results[11], tuple):
        lr, heatmap = results[11]
        layer_results.append(lr)
        trufor_heatmap_b64 = heatmap
    elif isinstance(results[11], LayerResult):
        layer_results.append(results[11])
    elif isinstance(results[11], Exception):
        layer_results.append(LayerResult(layer="trufor", score=0.0, confidence=0.0, error=str(results[11])))

    # L13: DIRE
    if isinstance(results[12], LayerResult):
        layer_results.append(results[12])
    elif isinstance(results[12], Exception):
        layer_results.append(LayerResult(layer="dire", score=0.0, confidence=0.0, error=str(results[12])))

    # L14: Gradient Distribution
    if isinstance(results[13], LayerResult):
        layer_results.append(results[13])
    elif isinstance(results[13], Exception):
        layer_results.append(LayerResult(layer="gradient", score=0.0, confidence=0.0, error=str(results[13])))

    # L15: LSB Forensics
    if isinstance(results[14], LayerResult):
        layer_results.append(results[14])
    elif isinstance(results[14], Exception):
        layer_results.append(LayerResult(layer="lsb", score=0.0, confidence=0.0, error=str(results[14])))

    # L16: DCT Histogram Analysis
    if isinstance(results[15], LayerResult):
        layer_results.append(results[15])
    elif isinstance(results[15], Exception):
        layer_results.append(LayerResult(layer="dct_hist", score=0.0, confidence=0.0, error=str(results[15])))

    # L17: GAN Spectral Fingerprint
    if isinstance(results[16], LayerResult):
        layer_results.append(results[16])
    elif isinstance(results[16], Exception):
        layer_results.append(LayerResult(layer="gan_fingerprint", score=0.0, confidence=0.0, error=str(results[16])))

    # L18: Attention Pattern Detection
    if isinstance(results[17], LayerResult):
        layer_results.append(results[17])
    elif isinstance(results[17], Exception):
        layer_results.append(LayerResult(layer="attention_pattern", score=0.0, confidence=0.0, error=str(results[17])))

    # L19: Texture Analysis
    if isinstance(results[18], LayerResult):
        layer_results.append(results[18])
    elif isinstance(results[18], Exception):
        layer_results.append(LayerResult(layer="texture", score=0.0, confidence=0.0, error=str(results[18])))

    # L20: NPR Pixel Residuals
    if isinstance(results[19], LayerResult):
        layer_results.append(results[19])
    elif isinstance(results[19], Exception):
        layer_results.append(LayerResult(layer="npr", score=0.0, confidence=0.0, error=str(results[19])))

    # L21: MLEP Entropy Patterns
    if isinstance(results[20], LayerResult):
        layer_results.append(results[20])
    elif isinstance(results[20], Exception):
        layer_results.append(LayerResult(layer="mlep", score=0.0, confidence=0.0, error=str(results[20])))

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
        layer_results=layer_results,
        hash_matches=hash_matches,
        ela_heatmap_b64=ela_heatmap_b64,
        trufor_heatmap_b64=trufor_heatmap_b64,
        gemini_reasoning=gemini_reasoning,
        processing_time_ms=processing_time_ms,
        created_at=claim.created_at,
    )
