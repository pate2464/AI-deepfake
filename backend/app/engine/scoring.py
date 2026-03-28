"""Weighted ensemble scoring engine.

Combines per-layer scores using configurable weights into a final risk score
and risk tier.  Includes override rules for high-confidence signals.
"""

from __future__ import annotations

from app.core.config import settings
from app.core.models import HashMatch, LayerName, LayerResult, RiskTier


# Weight mapping
WEIGHTS: dict[LayerName, str] = {
    LayerName.EXIF: "WEIGHT_EXIF",
    LayerName.ELA: "WEIGHT_ELA",
    LayerName.HASH: "WEIGHT_HASH",
    LayerName.AI_MODEL: "WEIGHT_AI_MODEL",
    LayerName.C2PA: "WEIGHT_C2PA",
    LayerName.BEHAVIORAL: "WEIGHT_BEHAVIORAL",
    LayerName.GEMINI: "WEIGHT_GEMINI",
    LayerName.NOISE: "WEIGHT_NOISE",
    LayerName.CLIP_DETECT: "WEIGHT_CLIP_DETECT",
    LayerName.CNN_DETECT: "WEIGHT_CNN_DETECT",
    LayerName.WATERMARK: "WEIGHT_WATERMARK",
    LayerName.TRUFOR: "WEIGHT_TRUFOR",
    LayerName.DIRE: "WEIGHT_DIRE",
    LayerName.GRADIENT: "WEIGHT_GRADIENT",
    LayerName.LSB: "WEIGHT_LSB",
    LayerName.DCT_HIST: "WEIGHT_DCT_HIST",
    LayerName.GAN_FINGERPRINT: "WEIGHT_GAN_FINGERPRINT",
    LayerName.ATTENTION_PATTERN: "WEIGHT_ATTENTION_PATTERN",
    LayerName.TEXTURE: "WEIGHT_TEXTURE",
    LayerName.NPR: "WEIGHT_NPR",
    LayerName.MLEP: "WEIGHT_MLEP",
}


def compute_risk_score(
    layer_results: list[LayerResult],
    hash_matches: list[HashMatch] | None = None,
) -> tuple[float, RiskTier]:
    """Compute weighted ensemble risk score with override rules.

    Returns (risk_score, risk_tier).
    """
    # ── Override rules (checked first) ─────────────────

    # Override 1: Exact hash match → force HIGH
    if hash_matches:
        min_dist = min(m.hamming_distance for m in hash_matches)
        if min_dist <= 3:
            return 0.95, RiskTier.HIGH

    # Override 2: Valid camera C2PA → force LOW
    for lr in layer_results:
        if lr.layer == LayerName.C2PA and lr.score <= 0.1 and lr.confidence >= 0.8:
            return 0.05, RiskTier.LOW

    # ── Weighted ensemble ──────────────────────────────
    weighted_sum = 0.0
    total_weight = 0.0

    for lr in layer_results:
        attr_name = WEIGHTS.get(lr.layer)
        if attr_name is None:
            continue
        weight = getattr(settings, attr_name, 0.0)

        # Layers that errored or have zero confidence contribute nothing
        if lr.error or lr.confidence == 0.0:
            continue

        # Weight by both configured weight and layer confidence
        effective_weight = weight * lr.confidence
        weighted_sum += lr.score * effective_weight
        total_weight += effective_weight

    if total_weight > 0:
        risk_score = weighted_sum / total_weight
    else:
        risk_score = 0.5  # Fallback

    risk_score = round(min(1.0, max(0.0, risk_score)), 4)

    # ── Consensus boost ────────────────────────────────
    # When multiple independent AI-detection layers agree that the
    # image is suspicious, their consensus should override "blind"
    # layers (e.g. GAN-specific detectors that can't see diffusion
    # artifacts).  This prevents confident false-negatives from
    # drowning out confident true-positives in the weighted average.
    _AI_DETECTION_LAYERS = {
        LayerName.GEMINI,       # VLM semantic analysis
        LayerName.TRUFOR,       # Learned manipulation detector
        LayerName.CLIP_DETECT,  # CLIP-based AI classifier
        LayerName.ATTENTION_PATTERN,  # Patch self-similarity
        LayerName.EXIF,         # Metadata / format signals
        LayerName.NPR,          # Neighboring pixel residuals
    }
    ai_signals = [
        lr for lr in layer_results
        if lr.layer in _AI_DETECTION_LAYERS
        and lr.score >= 0.5 and lr.confidence >= 0.5
        and not lr.error
    ]
    if len(ai_signals) >= 3:
        # Strong consensus (3+ independent detectors agree) — use their
        # confidence-weighted average as a floor for the risk score.
        s_sum = sum(s.score * s.confidence for s in ai_signals)
        c_sum = sum(s.confidence for s in ai_signals)
        consensus = s_sum / c_sum
        risk_score = max(risk_score, round(consensus, 4))

    # ── Determine tier ─────────────────────────────────
    if risk_score >= settings.RISK_HIGH_THRESHOLD:
        tier = RiskTier.HIGH
    elif risk_score >= settings.RISK_LOW_THRESHOLD:
        tier = RiskTier.MEDIUM
    else:
        tier = RiskTier.LOW

    return risk_score, tier
