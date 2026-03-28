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

    # ── Determine tier ─────────────────────────────────
    if risk_score >= settings.RISK_HIGH_THRESHOLD:
        tier = RiskTier.HIGH
    elif risk_score >= settings.RISK_LOW_THRESHOLD:
        tier = RiskTier.MEDIUM
    else:
        tier = RiskTier.LOW

    return risk_score, tier
