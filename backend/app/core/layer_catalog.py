"""Canonical layer metadata used for scoring introspection and evaluation."""

from __future__ import annotations

from app.core.models import LayerName


LAYER_CATALOG: dict[LayerName, dict[str, str]] = {
    LayerName.EXIF: {
        "evidence_family": "provenance",
        "implementation_kind": "metadata",
        "score_role": "core-score",
    },
    LayerName.ELA: {
        "evidence_family": "compression",
        "implementation_kind": "heuristic",
        "score_role": "supporting-score",
    },
    LayerName.HASH: {
        "evidence_family": "duplicate-fraud",
        "implementation_kind": "database",
        "score_role": "supporting-score",
    },
    LayerName.AI_MODEL: {
        "evidence_family": "frequency",
        "implementation_kind": "proxy-heuristic",
        "score_role": "supporting-score",
    },
    LayerName.C2PA: {
        "evidence_family": "provenance",
        "implementation_kind": "metadata",
        "score_role": "other-layer",
    },
    LayerName.BEHAVIORAL: {
        "evidence_family": "fraud-context",
        "implementation_kind": "database",
        "score_role": "other-layer",
    },
    LayerName.GEMINI: {
        "evidence_family": "semantic",
        "implementation_kind": "vision-language-model",
        "score_role": "supporting-score",
    },
    LayerName.NOISE: {
        "evidence_family": "sensor-noise",
        "implementation_kind": "proxy-heuristic",
        "score_role": "other-layer",
    },
    LayerName.CLIP_DETECT: {
        "evidence_family": "learned-image",
        "implementation_kind": "trained-model",
        "score_role": "core-score",
    },
    LayerName.CNN_DETECT: {
        "evidence_family": "learned-image",
        "implementation_kind": "legacy-model",
        "score_role": "other-layer",
    },
    LayerName.WATERMARK: {
        "evidence_family": "watermark",
        "implementation_kind": "heuristic",
        "score_role": "other-layer",
    },
    LayerName.TRUFOR: {
        "evidence_family": "localization",
        "implementation_kind": "trained-model",
        "score_role": "core-score",
    },
    LayerName.DIRE: {
        "evidence_family": "reconstruction",
        "implementation_kind": "proxy-heuristic",
        "score_role": "other-layer",
    },
    LayerName.GRADIENT: {
        "evidence_family": "spatial-statistics",
        "implementation_kind": "heuristic",
        "score_role": "other-layer",
    },
    LayerName.LSB: {
        "evidence_family": "bitplane",
        "implementation_kind": "heuristic",
        "score_role": "other-layer",
    },
    LayerName.DCT_HIST: {
        "evidence_family": "compression",
        "implementation_kind": "heuristic",
        "score_role": "other-layer",
    },
    LayerName.GAN_FINGERPRINT: {
        "evidence_family": "frequency",
        "implementation_kind": "heuristic",
        "score_role": "other-layer",
    },
    LayerName.ATTENTION_PATTERN: {
        "evidence_family": "spatial-statistics",
        "implementation_kind": "heuristic",
        "score_role": "supporting-score",
    },
    LayerName.TEXTURE: {
        "evidence_family": "texture",
        "implementation_kind": "heuristic",
        "score_role": "other-layer",
    },
    LayerName.NPR: {
        "evidence_family": "spatial-statistics",
        "implementation_kind": "heuristic",
        "score_role": "core-score",
    },
    LayerName.MLEP: {
        "evidence_family": "entropy",
        "implementation_kind": "heuristic",
        "score_role": "core-score",
    },
}


def get_layer_metadata(layer: LayerName | str) -> dict[str, str]:
    """Return canonical metadata for a layer or an empty mapping."""
    if isinstance(layer, str):
        try:
            layer = LayerName(layer)
        except ValueError:
            return {}
    return LAYER_CATALOG.get(layer, {})