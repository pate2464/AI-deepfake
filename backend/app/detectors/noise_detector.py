"""Layer 8 — Noise / PRNU Analysis.

Extracts the noise residual of an image and analyses its statistical properties.
Real camera photos have sensor-specific PRNU (Photo Response Non-Uniformity).
AI-generated images lack any sensor fingerprint — their noise is either too
uniform or artificially random.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from PIL import Image
from scipy import ndimage, stats

from app.core.models import LayerName, LayerResult


def _extract_noise_residual(img_arr: np.ndarray, sigma: float = 3.0) -> np.ndarray:
    """Extract noise by subtracting a denoised version (Gaussian filter)."""
    denoised = ndimage.gaussian_filter(img_arr.astype(np.float64), sigma=sigma)
    residual = img_arr.astype(np.float64) - denoised
    return residual


def _compute_noise_stats(residual: np.ndarray) -> dict[str, float]:
    """Compute statistical features of the noise residual."""
    flat = residual.flatten()

    variance = float(np.var(flat))
    kurtosis = float(stats.kurtosis(flat, fisher=True))
    skewness = float(stats.skew(flat))
    std = float(np.std(flat))

    # Spatial autocorrelation (1-pixel lag in horizontal direction)
    rows, cols = residual.shape[:2]
    if residual.ndim == 3:
        gray_residual = np.mean(residual, axis=2)
    else:
        gray_residual = residual

    # Autocorrelation at lag 1 (horizontal)
    if cols > 1:
        left = gray_residual[:, :-1].flatten()
        right = gray_residual[:, 1:].flatten()
        if np.std(left) > 1e-10 and np.std(right) > 1e-10:
            autocorr = float(np.corrcoef(left, right)[0, 1])
        else:
            autocorr = 0.0
    else:
        autocorr = 0.0

    # Local variance map (8x8 blocks)
    block_size = 8
    local_vars = []
    for i in range(0, rows - block_size + 1, block_size):
        for j in range(0, cols - block_size + 1, block_size):
            block = gray_residual[i:i + block_size, j:j + block_size]
            local_vars.append(np.var(block))

    local_var_std = float(np.std(local_vars)) if local_vars else 0.0
    local_var_mean = float(np.mean(local_vars)) if local_vars else 0.0

    return {
        "noise_variance": variance,
        "noise_std": std,
        "kurtosis": kurtosis,
        "skewness": skewness,
        "spatial_autocorrelation": autocorr,
        "local_variance_std": local_var_std,
        "local_variance_mean": local_var_mean,
    }


def analyze(image_path: str) -> LayerResult:
    """Run noise/PRNU analysis."""
    flags: list[str] = []
    details: dict[str, Any] = {}

    try:
        img = Image.open(image_path).convert("RGB")
        img_arr = np.array(img, dtype=np.float64)
    except Exception as e:
        return LayerResult(
            layer=LayerName.NOISE, score=0.5, confidence=0.3,
            flags=["Could not open image"], error=str(e),
        )

    residual = _extract_noise_residual(img_arr, sigma=3.0)
    noise_stats = _compute_noise_stats(residual)
    details["noise_stats"] = noise_stats

    # ── Scoring heuristics ─────────────────────────────
    score = 0.0

    kurtosis = noise_stats["kurtosis"]
    autocorr = noise_stats["spatial_autocorrelation"]
    local_var_std = noise_stats["local_variance_std"]
    noise_std = noise_stats["noise_std"]

    # 1. Kurtosis — real camera noise tends towards Gaussian (kurtosis ≈ 0).
    #    AI noise can be super-Gaussian (high kurtosis) or sub-Gaussian (negative).
    if abs(kurtosis) > 5:
        flags.append(f"Abnormal noise kurtosis ({kurtosis:.2f}) — inconsistent with camera sensor")
        score += 0.25
    elif abs(kurtosis) > 2:
        score += 0.1

    # 2. Spatial autocorrelation — real sensor noise has moderate-to-high spatial
    #    correlation from the sensor's readout pattern (PRNU).
    #    AI noise has near-zero or very low correlation.
    #    High correlation (0.3-0.95) is NORMAL for real cameras — that's the PRNU fingerprint.
    if abs(autocorr) < 0.05:
        flags.append("Very low spatial noise correlation — no camera sensor fingerprint detected")
        score += 0.3
    elif abs(autocorr) < 0.15:
        flags.append("Low spatial noise correlation — weak sensor fingerprint")
        score += 0.15
    elif autocorr > 0.3:
        # Moderate-to-high correlation = real camera PRNU fingerprint — GOOD sign
        flags.append(f"Camera sensor fingerprint detected (PRNU autocorrelation={autocorr:.3f})")
        score -= 0.1  # Reduce suspicion — this is evidence of a real camera

    # 3. Local variance consistency — real photos have varying noise across the image
    #    (darker areas = less noise). AI images tend to have uniform noise.
    if local_var_std < 0.5 and noise_std > 1:
        flags.append("Extremely uniform noise distribution — suggests synthetic origin")
        score += 0.2

    # 4. Overall noise level — real photos from high-ISO shots have noise
    if noise_std < 0.5:
        flags.append("Very low noise — possibly over-processed or AI-generated")
        score += 0.15
    elif noise_std > 60:
        flags.append("Extremely high noise level — unusual")
        score += 0.1
    elif noise_std > 10:
        # Normal camera noise range — not suspicious
        flags.append(f"Normal noise level (std={noise_std:.1f}) — consistent with camera capture")

    score = max(0.0, min(1.0, score))
    confidence = 0.5  # Noise analysis alone has moderate confidence

    if not flags:
        flags.append("Noise patterns appear consistent with natural camera capture")

    return LayerResult(
        layer=LayerName.NOISE,
        score=round(score, 4),
        confidence=round(confidence, 4),
        flags=flags,
        details=details,
    )
