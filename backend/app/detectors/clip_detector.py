"""Layer 9 — CLIP-based Universal Fake Image Detection.

Uses a frozen CLIP ViT-L/14 backbone with a trained linear probe to classify
images as real or AI-generated.  Generalises across unseen generators.

Reference: Ojha et al., "Towards Universal Fake Image Detectors" (CVPR 2023)
Repo: https://github.com/Yuheng-Li/UniversalFakeDetect  (MIT License)
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import torch
import torch.nn as nn
from PIL import Image

from app.core.models import LayerName, LayerResult
from app.core.model_manager import get_device, get_cached, set_cached, model_path, is_downloaded

logger = logging.getLogger(__name__)

# ── Model helpers ──────────────────────────────────────

_SUBDIR = "clip_universalfakedetect"
_WEIGHTS_FILE = "fc_weights.pth"


def _load_model():
    """Lazy-load the CLIP backbone + linear probe."""
    cached = get_cached("clip_detect")
    if cached is not None:
        return cached

    import open_clip

    device = get_device()
    logger.info("Loading CLIP ViT-L/14 for fake detection ...")

    # Load CLIP backbone (auto-downloads ~900MB to HuggingFace cache)
    clip_model, _, preprocess = open_clip.create_model_and_transforms(
        "ViT-L-14", pretrained="openai",
    )
    clip_model = clip_model.to(device).eval()

    # Load trained linear probe
    weights_path = model_path(_SUBDIR, _WEIGHTS_FILE)
    if weights_path.is_file():
        state = torch.load(weights_path, map_location=device, weights_only=True)
        # The probe is a single Linear layer: 768 → 1
        probe = nn.Linear(768, 1).to(device)
        probe.load_state_dict(state)
        probe.eval()
        logger.info("Loaded linear probe from %s", weights_path)
    else:
        # No weights — fall back to feature-distance heuristic
        probe = None
        logger.warning("Linear probe weights not found at %s — using heuristic", weights_path)

    bundle = (clip_model, preprocess, probe)
    set_cached("clip_detect", bundle)
    return bundle


# ── Public API ─────────────────────────────────────────

def analyze(image_path: str) -> LayerResult:
    """Run CLIP-based fake image detection."""
    flags: list[str] = []
    details: dict[str, Any] = {}

    try:
        img = Image.open(image_path).convert("RGB")
    except Exception as e:
        return LayerResult(
            layer=LayerName.CLIP_DETECT, score=0.5, confidence=0.0,
            flags=["Could not open image"], error=str(e),
        )

    try:
        clip_model, preprocess, probe = _load_model()
    except Exception as e:
        logger.error("Failed to load CLIP model: %s", e)
        return LayerResult(
            layer=LayerName.CLIP_DETECT, score=0.5, confidence=0.0,
            flags=["Model loading failed"], error=str(e),
        )

    device = get_device()

    # Preprocess
    img_tensor = preprocess(img).unsqueeze(0).to(device)

    with torch.no_grad(), torch.amp.autocast(device_type=device.type):
        features = clip_model.encode_image(img_tensor)
        features = features / features.norm(dim=-1, keepdim=True)  # L2-normalise

    if probe is not None:
        with torch.no_grad():
            logit = probe(features.float())
            prob_fake = torch.sigmoid(logit).item()
    else:
        # Fallback heuristic: use feature norm spread (less reliable)
        feature_std = features.float().std().item()
        prob_fake = min(1.0, max(0.0, 0.5 + (feature_std - 0.035) * 10))
        flags.append("Using heuristic fallback — download probe weights for best accuracy")

    score = round(float(np.clip(prob_fake, 0.0, 1.0)), 4)
    confidence = 0.85 if probe is not None else 0.30

    details["clip_score"] = score
    details["model"] = "ViT-L-14 (OpenAI CLIP)"
    details["has_probe_weights"] = probe is not None

    if score >= 0.7:
        flags.append(f"CLIP probability of AI generation: {score:.0%} — HIGH")
    elif score >= 0.4:
        flags.append(f"CLIP probability of AI generation: {score:.0%} — MODERATE")
    else:
        flags.append(f"CLIP probability of AI generation: {score:.0%} — LOW")

    return LayerResult(
        layer=LayerName.CLIP_DETECT,
        score=score,
        confidence=round(confidence, 4),
        flags=flags,
        details=details,
    )
