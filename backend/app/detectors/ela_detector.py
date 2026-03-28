"""Layer 2 — Error Level Analysis (ELA).

Re-saves the image at a known JPEG quality, then computes the pixel-by-pixel
difference.  AI-generated images show suspiciously *uniform* error levels
while real photos have non-uniform compression artifacts.
"""

from __future__ import annotations

import base64
import io
import tempfile
from typing import Any

import numpy as np
from PIL import Image

from app.core.config import settings
from app.core.models import LayerName, LayerResult


def _compute_ela(img: Image.Image, quality: int = 90, scale: int = 15) -> tuple[np.ndarray, np.ndarray]:
    """Return (ela_image_array, raw_diff_array)."""
    # Re-save at known quality
    buf = io.BytesIO()
    img_rgb = img.convert("RGB")
    img_rgb.save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    resaved = Image.open(buf).convert("RGB")

    original_arr = np.array(img_rgb, dtype=np.float64)
    resaved_arr = np.array(resaved, dtype=np.float64)

    # Absolute difference
    diff = np.abs(original_arr - resaved_arr)

    # Scale for visibility
    ela_scaled = np.clip(diff * scale, 0, 255).astype(np.uint8)

    return ela_scaled, diff


def _array_to_b64(arr: np.ndarray) -> str:
    """Convert numpy array to base64-encoded PNG."""
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _compute_stats(diff: np.ndarray) -> dict[str, float]:
    """Compute statistical metrics on the raw difference array."""
    flat = diff.mean(axis=2)  # average across RGB channels
    return {
        "mean": float(np.mean(flat)),
        "std_dev": float(np.std(flat)),
        "median": float(np.median(flat)),
        "max": float(np.max(flat)),
        "min": float(np.min(flat)),
        "uniformity": float(np.std(flat) / (np.mean(flat) + 1e-8)),  # low = suspicious
    }


def analyze(image_path: str) -> tuple[LayerResult, str | None]:
    """Run ELA on the image.

    Returns (LayerResult, base64_heatmap_or_None).
    """
    flags: list[str] = []
    details: dict[str, Any] = {}

    try:
        img = Image.open(image_path)
    except Exception as e:
        return LayerResult(
            layer=LayerName.ELA, score=0.5, confidence=0.3,
            flags=["Could not open image"], error=str(e),
        ), None

    quality = settings.ELA_QUALITY
    scale = settings.ELA_SCALE_FACTOR

    # Detect source format — ELA is most meaningful for JPEG→JPEG comparisons
    is_jpeg = image_path.lower().endswith((".jpg", ".jpeg"))
    is_non_jpeg = image_path.lower().endswith(
        (".png", ".heic", ".heif", ".webp", ".bmp", ".tiff", ".tif", ".avif")
    )
    details["source_format"] = img.format or "unknown"
    details["is_native_jpeg"] = is_jpeg

    ela_arr, raw_diff = _compute_ela(img, quality=quality, scale=scale)
    stats = _compute_stats(raw_diff)
    details["stats"] = stats
    details["quality_used"] = quality

    # ── Interpret stats ────────────────────────────────

    uniformity = stats["uniformity"]
    std_dev = stats["std_dev"]
    mean_err = stats["mean"]

    # For non-JPEG sources (HEIC, PNG, WebP, etc.), the ELA baseline is
    # fundamentally different because we're comparing cross-codec artifacts,
    # not double-JPEG artifacts. Low error in these cases is EXPECTED for
    # any well-compressed source, real or AI-generated.
    if is_non_jpeg:
        # Non-JPEG: the codec difference dominates, so raise thresholds significantly
        # A real HEIC photo will have very low, uniform JPEG re-save error
        # because HEVC is excellent at compression — this is NOT an AI signal.
        if std_dev < 0.5 and mean_err < 0.5:
            flags.append("Extremely low ELA error — possibly synthetic or heavily processed")
            score = 0.5
        elif uniformity < 0.3:
            flags.append("Low error-level variance for non-JPEG source")
            score = 0.4
        elif uniformity < 0.8:
            flags.append("Moderate ELA patterns — inconclusive for non-JPEG format")
            score = 0.3
        else:
            flags.append("Non-uniform error levels — consistent with real photograph")
            score = 0.15

        flags.append(f"Source format: {img.format or 'non-JPEG'} — ELA confidence reduced")
        details["note"] = (
            f"ELA is designed for JPEG→JPEG analysis. "
            f"This {img.format or 'non-JPEG'} file uses a different codec, "
            f"so low/uniform errors are expected and do not indicate AI generation."
        )
        confidence = 0.3  # Low confidence for non-JPEG
    else:
        # Native JPEG: original ELA logic is appropriate
        if std_dev < 1.5 and mean_err < 2.0:
            flags.append("Extremely uniform error levels — strong AI generation signal")
            score = 0.85
        elif uniformity < 0.5:
            flags.append("Low error-level variance — consistent with AI-generated image")
            score = 0.7
        elif uniformity < 1.0:
            flags.append("Moderate uniformity in compression errors")
            score = 0.45
        else:
            flags.append("Non-uniform error levels — consistent with real photograph")
            score = 0.15
        confidence = 0.7

    heatmap_b64 = _array_to_b64(ela_arr)

    return LayerResult(
        layer=LayerName.ELA,
        score=round(score, 4),
        confidence=round(confidence, 4),
        flags=flags,
        details=details,
    ), heatmap_b64
