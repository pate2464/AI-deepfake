"""Weighted ensemble scoring engine with explainable decision metadata."""

from __future__ import annotations

from app.core.config import settings
from app.core.models import HashMatch, LayerName, LayerResult, RiskTier, ScoringSummary


_EXCLUDED_SCORE_LAYERS = {
    LayerName.C2PA,
    LayerName.BEHAVIORAL,
    LayerName.WATERMARK,
    LayerName.TEXTURE,
    LayerName.NOISE,
    LayerName.CNN_DETECT,
    LayerName.DIRE,
    LayerName.GRADIENT,
    LayerName.LSB,
    LayerName.DCT_HIST,
    LayerName.GAN_FINGERPRINT,
}


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


def get_configured_weight(layer: LayerName) -> float:
    """Return the configured ensemble weight for a layer."""
    attr_name = WEIGHTS.get(layer)
    if attr_name is None:
        return 0.0
    return float(getattr(settings, attr_name, 0.0))


def _combine_signals(signals: list[tuple[float, float]]) -> tuple[float, float]:
    """Combine score/confidence pairs into a family-level signal."""
    if not signals:
        return 0.0, 0.0

    confidence_sum = sum(confidence for _, confidence in signals)
    if confidence_sum <= 0.0:
        return 0.0, 0.0

    weighted_score = sum(score * confidence for score, confidence in signals) / confidence_sum
    average_confidence = confidence_sum / len(signals)
    return round(weighted_score, 4), round(min(1.0, average_confidence), 4)


def _is_score_driving_layer(layer: LayerName) -> bool:
    """Return whether a layer currently participates in the automated score."""
    return layer not in _EXCLUDED_SCORE_LAYERS


def _has_strong_real_evidence(by_layer: dict[LayerName, LayerResult]) -> bool:
    """Check whether provenance plus image-space detectors look camera-authentic."""
    exif = by_layer.get(LayerName.EXIF)
    clip = by_layer.get(LayerName.CLIP_DETECT)
    trufor = by_layer.get(LayerName.TRUFOR)
    c2pa = by_layer.get(LayerName.C2PA)

    has_camera_metadata = bool(exif and exif.score <= 0.2 and exif.confidence >= 0.5)
    has_real_clip = bool(clip and clip.score <= 0.35 and clip.confidence >= 0.7)
    has_real_localisation = bool(trufor and trufor.score <= 0.4 and trufor.confidence >= 0.6)
    has_verified_provenance = bool(c2pa and c2pa.score <= 0.1 and c2pa.confidence >= 0.8)

    return has_verified_provenance or (has_camera_metadata and (has_real_clip or has_real_localisation))


def _resolve_effective_confidence(
    layer_result: LayerResult,
    by_layer: dict[LayerName, LayerResult],
) -> tuple[float, str | None]:
    """Guardrail brittle semantic signals without discarding useful true positives."""
    effective_confidence = layer_result.confidence
    reasons: list[str] = []

    if layer_result.layer == LayerName.GEMINI and layer_result.details.get("source") == "local_vlm":
        if layer_result.score >= 0.55 and layer_result.confidence < 0.45:
            effective_confidence = min(effective_confidence, 0.25)
            reasons.append("Local semantic VLM made a low-confidence AI call, so its scoring weight was capped.")

        if layer_result.score >= 0.55 and _has_strong_real_evidence(by_layer):
            effective_confidence = min(effective_confidence, 0.15)
            reasons.append(
                "Local semantic VLM was down-weighted because camera-style provenance and image-space detectors pointed toward a real capture."
            )

    if effective_confidence < layer_result.confidence:
        return round(effective_confidence, 4), " ".join(reasons)

    return round(effective_confidence, 4), None


def _build_family_consensus(
    layer_results: list[LayerResult],
    effective_confidences: dict[LayerName, float],
) -> tuple[float | None, list[str]]:
    """Build a floor from corroborating high-value families instead of flat layer counts."""
    by_layer = {lr.layer: lr for lr in layer_results if not lr.error}
    families: dict[str, tuple[float, float]] = {}

    exif = by_layer.get(LayerName.EXIF)
    if exif and exif.score >= 0.7 and effective_confidences.get(LayerName.EXIF, 0.0) >= 0.75:
        families["provenance"] = (exif.score, effective_confidences[LayerName.EXIF])

    gemini = by_layer.get(LayerName.GEMINI)
    gemini_effective_confidence = effective_confidences.get(LayerName.GEMINI, 0.0)
    if (
        gemini
        and not gemini.suppressed
        and gemini.score >= 0.6
        and gemini_effective_confidence >= 0.45
    ):
        families["semantic"] = (gemini.score, gemini_effective_confidence)

    learned_signals: list[tuple[float, float]] = []
    for layer_name in (LayerName.CLIP_DETECT, LayerName.TRUFOR):
        layer_result = by_layer.get(layer_name)
        effective_confidence = effective_confidences.get(layer_name, 0.0)
        if layer_result and layer_result.score >= 0.25 and effective_confidence >= 0.5:
            learned_signals.append((layer_result.score, effective_confidence))

    learned_score, learned_confidence = _combine_signals(learned_signals)
    if len(learned_signals) >= 2 and learned_confidence > 0.0:
        families["learned"] = (learned_score, learned_confidence)

    heuristic_signals: list[tuple[float, float]] = []
    for layer_name in (
        LayerName.NPR,
        LayerName.MLEP,
        LayerName.ATTENTION_PATTERN,
        LayerName.AI_MODEL,
    ):
        layer_result = by_layer.get(layer_name)
        effective_confidence = effective_confidences.get(layer_name, 0.0)
        if layer_result and layer_result.score >= 0.25 and effective_confidence >= 0.45:
            heuristic_signals.append((layer_result.score, effective_confidence))

    heuristic_score, heuristic_confidence = _combine_signals(heuristic_signals)
    if len(heuristic_signals) >= 2 and heuristic_confidence > 0.0:
        families["statistical"] = (heuristic_score, heuristic_confidence)

    if {"provenance", "learned", "statistical"}.issubset(families):
        consensus_score = (
            families["provenance"][0] * 0.55
            + families["learned"][0] * 0.25
            + families["statistical"][0] * 0.20
        )
        return round(min(0.78, consensus_score), 4), ["provenance", "learned", "statistical"]

    if {"semantic", "learned", "statistical"}.issubset(families):
        consensus_score = (
            families["semantic"][0] * 0.15
            + families["learned"][0] * 0.5
            + families["statistical"][0] * 0.35
        )
        return round(min(0.72, consensus_score), 4), ["semantic", "learned", "statistical"]

    return None, []


def _detect_conflicting_signals(layer_results: list[LayerResult]) -> list[str]:
    """Surface strong contradictions for analyst review."""
    by_layer = {lr.layer: lr for lr in layer_results if not lr.error}
    conflicts: list[str] = []

    suspicious_cluster = [
        lr for lr in layer_results
        if lr.layer in {
            LayerName.CLIP_DETECT,
            LayerName.TRUFOR,
            LayerName.NPR,
            LayerName.MLEP,
            LayerName.ATTENTION_PATTERN,
            LayerName.AI_MODEL,
        }
        and lr.score >= 0.6 and lr.confidence >= 0.6 and not lr.error and not lr.suppressed
    ]

    if len(suspicious_cluster) >= 2:
        exif = by_layer.get(LayerName.EXIF)
        if exif and exif.score <= 0.2 and exif.confidence >= 0.5:
            conflicts.append("Camera-style EXIF metadata conflicts with multiple suspicious image detectors.")

        c2pa = by_layer.get(LayerName.C2PA)
        if c2pa and c2pa.score <= 0.1 and c2pa.confidence >= 0.8:
            conflicts.append("Valid provenance-style C2PA evidence conflicts with suspicious image detectors.")

    clip = by_layer.get(LayerName.CLIP_DETECT)
    gemini = by_layer.get(LayerName.GEMINI)
    if clip and gemini and clip.confidence >= 0.6 and gemini.confidence >= 0.6:
        if abs(clip.score - gemini.score) >= 0.4:
            if gemini.suppressed:
                conflicts.append("CLIP disagrees strongly with a down-weighted local semantic VLM call.")
            else:
                conflicts.append("CLIP and semantic VLM assessments disagree strongly.")

    trufor = by_layer.get(LayerName.TRUFOR)
    if trufor and trufor.score <= 0.25 and trufor.confidence >= 0.6 and len(suspicious_cluster) >= 2:
        conflicts.append("Global suspicious signals are present while localization evidence remains weak.")

    return conflicts


def compute_risk_score(
    layer_results: list[LayerResult],
    hash_matches: list[HashMatch] | None = None,
) -> ScoringSummary:
    """Compute weighted ensemble risk score with explainable metadata."""
    weighted_sum = 0.0
    total_weight = 0.0
    by_layer = {lr.layer: lr for lr in layer_results if not lr.error}
    effective_confidences: dict[LayerName, float] = {}
    scoring_notes: list[str] = []

    for lr in layer_results:
        weight = get_configured_weight(lr.layer)
        lr.configured_weight = round(weight, 4)
        lr.effective_weight = None
        lr.weighted_contribution = None
        lr.suppressed = False
        lr.suppression_reason = None

        # Layers that errored or have zero confidence contribute nothing
        if lr.error or lr.confidence == 0.0:
            effective_confidences[lr.layer] = 0.0
            continue

        if not _is_score_driving_layer(lr.layer):
            effective_confidences[lr.layer] = 0.0
            lr.effective_weight = 0.0
            lr.weighted_contribution = 0.0
            continue

        effective_confidence, suppression_reason = _resolve_effective_confidence(lr, by_layer)
        effective_confidences[lr.layer] = effective_confidence
        if suppression_reason:
            lr.suppressed = True
            lr.suppression_reason = suppression_reason
            lr.details["effective_confidence"] = effective_confidence

        if effective_confidence == 0.0:
            continue

        # Weight by both configured weight and layer confidence
        effective_weight = weight * effective_confidence
        weighted_sum += lr.score * effective_weight
        total_weight += effective_weight
        lr.effective_weight = round(effective_weight, 4)

    if total_weight > 0:
        weighted_score = weighted_sum / total_weight
    else:
        weighted_score = 0.5  # Fallback

    weighted_score = round(min(1.0, max(0.0, weighted_score)), 4)

    if total_weight > 0:
        for lr in layer_results:
            effective_confidence = effective_confidences.get(lr.layer, 0.0)
            if lr.error or effective_confidence == 0.0:
                continue
            contribution = (lr.score * (lr.configured_weight or 0.0) * effective_confidence) / total_weight
            lr.weighted_contribution = round(contribution, 4)

    risk_score = weighted_score
    consensus_floor_score: float | None = None
    consensus_floor_applied = False
    consensus_signal_families: list[str] = []

    consensus, consensus_signal_families = _build_family_consensus(layer_results, effective_confidences)
    if consensus is not None:
        consensus_floor_score = consensus
        if consensus > risk_score:
            risk_score = consensus
            consensus_floor_applied = True

    override_applied = False
    override_reason: str | None = None

    if hash_matches:
        min_dist = min(m.hamming_distance for m in hash_matches)
        if min_dist <= 3:
            risk_score = 0.95
            override_applied = True
            override_reason = f"Exact perceptual hash match detected (minimum hamming distance {min_dist})."

    if not override_applied:
        for lr in layer_results:
            if lr.layer == LayerName.C2PA and lr.score <= 0.1 and lr.confidence >= 0.8:
                risk_score = 0.05
                override_applied = True
                override_reason = "High-confidence C2PA provenance indicates an authenticated origin."
                break

    # ── Determine tier ─────────────────────────────────
    if risk_score >= settings.RISK_HIGH_THRESHOLD:
        tier = RiskTier.HIGH
    elif risk_score >= settings.RISK_LOW_THRESHOLD:
        tier = RiskTier.MEDIUM
    else:
        tier = RiskTier.LOW

    contributing_layers = [
        lr.layer.value
        for lr in sorted(
            layer_results,
            key=lambda result: result.weighted_contribution or 0.0,
            reverse=True,
        )
        if (lr.weighted_contribution or 0.0) > 0.0
    ]

    suppressed_layers = [lr.layer.value for lr in layer_results if lr.suppressed]
    if suppressed_layers:
        scoring_notes.append(
            f"Guardrails reduced the impact of: {', '.join(suppressed_layers)}."
        )

    return ScoringSummary(
        scoring_version="research-v3",
        method="backbone_ensemble",
        weighted_score=weighted_score,
        final_score=round(risk_score, 4),
        risk_tier=tier,
        override_applied=override_applied,
        override_reason=override_reason,
        consensus_floor_applied=consensus_floor_applied,
        consensus_floor_score=consensus_floor_score,
        contributing_layers=contributing_layers,
        consensus_signal_families=consensus_signal_families,
        conflicting_signals=_detect_conflicting_signals(layer_results),
        scoring_notes=list(dict.fromkeys(scoring_notes)),
    )
