"""Layer 10 — CNN-based AI Image Detection (Wang et al.).

Uses a ResNet-50 fine-tuned to detect CNN-generated images.  The model was
trained on ProGAN with blur + JPEG augmentation and generalises well to other
generators (~90 % cross-generator accuracy).

Reference: Wang et al., "CNN-generated images are surprisingly easy to
           spot…for now" (CVPR 2020)
Repo: https://github.com/PeterWang512/CNNDetection  (CC-BY-NC-SA)
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from torchvision import transforms, models

from app.core.models import LayerName, LayerResult
from app.core.model_manager import get_device, get_cached, set_cached, model_path

logger = logging.getLogger(__name__)

_SUBDIR = "cnndetection"
_WEIGHTS_FILE = "blur_jpg_prob0.5.pth"

# Standard ImageNet preprocessing used by CNNDetection
_TRANSFORM = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])


def _load_model():
    """Lazy-load the ResNet-50 classifier."""
    cached = get_cached("cnn_detect")
    if cached is not None:
        return cached

    device = get_device()
    logger.info("Loading CNNDetection ResNet-50 ...")

    model = models.resnet50(weights=None)
    model.fc = nn.Linear(model.fc.in_features, 1)  # binary: real/fake logit

    weights_path = model_path(_SUBDIR, _WEIGHTS_FILE)
    if weights_path.is_file():
        state = torch.load(weights_path, map_location=device, weights_only=False)
        # Weights from the repo may be wrapped in 'model' key
        if "model" in state:
            state = state["model"]
        model.load_state_dict(state, strict=False)
        logger.info("Loaded CNNDetection weights from %s", weights_path)
        has_weights = True
    else:
        logger.warning("CNNDetection weights not found at %s — using random init (inaccurate)", weights_path)
        has_weights = False

    model = model.to(device).eval()
    bundle = (model, has_weights)
    set_cached("cnn_detect", bundle)
    return bundle


def analyze(image_path: str) -> LayerResult:
    """Run CNN-based fake image detection."""
    flags: list[str] = []
    details: dict[str, Any] = {}

    try:
        img = Image.open(image_path).convert("RGB")
    except Exception as e:
        return LayerResult(
            layer=LayerName.CNN_DETECT, score=0.5, confidence=0.0,
            flags=["Could not open image"], error=str(e),
        )

    try:
        model, has_weights = _load_model()
    except Exception as e:
        logger.error("Failed to load CNN model: %s", e)
        return LayerResult(
            layer=LayerName.CNN_DETECT, score=0.5, confidence=0.0,
            flags=["Model loading failed"], error=str(e),
        )

    device = get_device()
    img_tensor = _TRANSFORM(img).unsqueeze(0).to(device)

    with torch.no_grad(), torch.amp.autocast(device_type=device.type):
        logit = model(img_tensor)
        prob_fake = torch.sigmoid(logit).item()

    score = round(float(np.clip(prob_fake, 0.0, 1.0)), 4)
    confidence = 0.80 if has_weights else 0.15

    details["cnn_score"] = score
    details["model"] = "ResNet-50 blur+jpg"
    details["has_weights"] = has_weights

    if score >= 0.7:
        flags.append(f"CNN fake probability: {score:.0%} — HIGH")
    elif score >= 0.4:
        flags.append(f"CNN fake probability: {score:.0%} — MODERATE")
    else:
        flags.append(f"CNN fake probability: {score:.0%} — LOW")

    if not has_weights:
        flags.append("WARNING: Using untrained model — download weights for accurate results")

    return LayerResult(
        layer=LayerName.CNN_DETECT,
        score=score,
        confidence=round(confidence, 4),
        flags=flags,
        details=details,
    )
