"""Layer 12 — TruFor: Trustworthy Image Forgery Detection & Localisation.

Uses a Noiseprint++ feature extractor combined with a CMX segmentation head to
produce both a global detection score and a per-pixel manipulation heatmap.

Reference: Guillaro et al., "TruFor: Leveraging all-round clues for
           trustworthy image forgery detection and localization" (CVPR 2023)
Repo: https://github.com/grip-unina/TruFor  (Research licence)

Weights: Downloaded from https://www.grip.unina.it/download/prog/TruFor/TruFor_weights.zip
"""

from __future__ import annotations

import base64
import logging
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

from app.core.models import LayerName, LayerResult
from app.core.model_manager import get_device, get_cached, set_cached, model_path

logger = logging.getLogger(__name__)

_SUBDIR = "trufor"
_WEIGHTS_FILE = "trufor.pth.tar"

# Add the TruFor source directory to the Python path so model code can be imported
_TRUFOR_SRC = Path(__file__).resolve().parent.parent.parent / "trufor_src"
if str(_TRUFOR_SRC) not in sys.path:
    sys.path.insert(0, str(_TRUFOR_SRC))


def _build_model(device: torch.device):
    """Build the TruFor model architecture and load checkpoint weights."""
    from trufor_config import get_trufor_config
    from models.cmx.builder_np_conf import myEncoderDecoder

    cfg = get_trufor_config()
    model = myEncoderDecoder(cfg=cfg)

    weights_path = model_path(_SUBDIR, _WEIGHTS_FILE)
    if not weights_path.is_file():
        return None, False

    logger.info("Loading TruFor checkpoint from %s ...", weights_path)
    checkpoint = torch.load(weights_path, map_location=device, weights_only=False)

    # The checkpoint has a 'state_dict' key with all model weights
    if "state_dict" in checkpoint:
        state = checkpoint["state_dict"]
    else:
        state = checkpoint

    model.load_state_dict(state)
    model = model.to(device).eval()
    logger.info("TruFor model loaded successfully (%d parameters)",
                sum(p.numel() for p in model.parameters()))
    return model, True


def _load_model():
    cached = get_cached("trufor")
    if cached is not None:
        return cached

    device = get_device()

    try:
        model, has_weights = _build_model(device)
    except Exception as e:
        logger.error("Failed to build TruFor model: %s", e, exc_info=True)
        result = (None, False)
        set_cached("trufor", result)
        return result

    if model is None:
        logger.warning("TruFor weights not found at %s — layer will be skipped",
                        model_path(_SUBDIR, _WEIGHTS_FILE))
        result = (None, False)
    else:
        result = (model, True)

    set_cached("trufor", result)
    return result


def _to_heatmap_b64(conf_map: np.ndarray) -> str:
    """Convert a [0,1] confidence map to a coloured heatmap PNG (base64)."""
    scaled = (np.clip(conf_map, 0, 1) * 255).astype(np.uint8)
    coloured = cv2.applyColorMap(scaled, cv2.COLORMAP_JET)
    _, buf = cv2.imencode(".png", coloured)
    return base64.b64encode(buf.tobytes()).decode("ascii")


# ── Public API ─────────────────────────────────────────

def analyze(image_path: str) -> tuple[LayerResult, str | None]:
    """Run TruFor detection + localisation.

    Returns ``(LayerResult, heatmap_base64_or_None)``.
    """
    flags: list[str] = []
    details: dict[str, Any] = {}
    heatmap_b64: str | None = None

    try:
        img = Image.open(image_path).convert("RGB")
    except Exception as e:
        return LayerResult(
            layer=LayerName.TRUFOR, score=0.5, confidence=0.0,
            flags=["Could not open image"], error=str(e),
        ), None

    model, has_weights = _load_model()

    if not has_weights or model is None:
        return LayerResult(
            layer=LayerName.TRUFOR,
            score=0.0,
            confidence=0.0,
            flags=["TruFor weights not downloaded — run download_models.py"],
            details={"has_trained_weights": False},
        ), None

    device = get_device()

    # ── Resize to fit VRAM ──
    # TruFor supports arbitrary sizes but attention is O(N²).
    # Limit max dimension to 1024 for 16GB GPUs.
    MAX_DIM = 1024
    w, h = img.size
    if max(w, h) > MAX_DIM:
        scale = MAX_DIM / max(w, h)
        new_w, new_h = int(w * scale), int(h * scale)
        # Ensure dimensions are divisible by 4 (patch embedding stride)
        new_w = (new_w // 4) * 4
        new_h = (new_h // 4) * 4
        img = img.resize((new_w, new_h), Image.LANCZOS)
        logger.info("Resized image from %dx%d to %dx%d for TruFor", w, h, new_w, new_h)

    # ── Prepare image tensor ──
    # TruFor expects float32 [B, 3, H, W] in [0, 1] range (divided by 256)
    # The model handles ImageNet normalization internally for the RGB branch
    img_arr = np.array(img, dtype=np.float32)
    tensor = torch.tensor(img_arr.transpose(2, 0, 1), dtype=torch.float32).unsqueeze(0) / 256.0
    tensor = tensor.to(device)

    with torch.no_grad():
        pred, conf, det, npp = model(tensor)

    # ── Process outputs ──
    # pred: [1, 2, H, W] → softmax → channel 1 = manipulation probability map
    pred = torch.squeeze(pred, 0)
    loc_map = F.softmax(pred, dim=0)[1].cpu().numpy()

    # conf: [1, 1, H, W] → sigmoid → confidence map
    conf_map = None
    if conf is not None:
        conf = torch.squeeze(conf, 0)
        conf_map = torch.sigmoid(conf)[0].cpu().numpy()

    # det: scalar → sigmoid → detection score (0=authentic, 1=manipulated)
    det_score = 0.5
    if det is not None:
        det_score = torch.sigmoid(det).item()

    details["has_trained_weights"] = True
    details["trufor_det_score"] = round(det_score, 4)

    # Score from detection head
    score = round(float(np.clip(det_score, 0.0, 1.0)), 4)

    # Manipulation area from localization map
    manip_pct = float((loc_map > 0.5).sum() / loc_map.size * 100)
    details["manipulation_area_pct"] = round(manip_pct, 1)
    details["has_localization_map"] = True

    confidence = 0.80

    # Generate heatmap from localization map
    try:
        heatmap_b64 = _to_heatmap_b64(loc_map)
    except Exception:
        heatmap_b64 = None
        details["has_localization_map"] = False

    # Flag interpretation
    if score >= 0.7:
        flags.append(f"TruFor detection score: {score:.0%} — LIKELY MANIPULATED")
    elif score >= 0.4:
        flags.append(f"TruFor detection score: {score:.0%} — UNCERTAIN")
    else:
        flags.append(f"TruFor detection score: {score:.0%} — LIKELY AUTHENTIC")

    if manip_pct > 30:
        flags.append(f"{manip_pct:.0f}% of image flagged as potentially manipulated")
    elif manip_pct > 5:
        flags.append(f"{manip_pct:.0f}% of image shows manipulation signatures")

    return LayerResult(
        layer=LayerName.TRUFOR,
        score=score,
        confidence=round(confidence, 4),
        flags=flags,
        details=details,
    ), heatmap_b64
