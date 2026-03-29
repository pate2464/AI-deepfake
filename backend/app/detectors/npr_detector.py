"""Layer 20 — Neighboring Pixel Relationships (NPR) Detection.

Implements the core insight from Tan et al. (arXiv:2312.10461):
Every image generator uses upsampling (ConvTranspose2d, bilinear interpolation,
pixel shuffle), creating local pixel interdependence where adjacent pixels are
computed from shared operations rather than independently sampled.

The NPR residual — the difference between each pixel and the mean of its
8-connected neighbors — follows distinctly different distributions for real
vs. AI-generated images:
  - Real: high-entropy, heavy-tailed residuals (sensor noise, natural textures)
  - AI:   low-entropy, regular residuals (upsampling math, checkerboard artifacts)

This is an *architectural invariant* — it works across GANs, diffusion models,
and any future generator that uses upsampling.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np
from PIL import Image
from scipy import stats

from app.core.models import LayerName, LayerResult

logger = logging.getLogger(__name__)

# 8-connected neighbor mean kernel (excludes center pixel)
_NEIGHBOR_KERNEL = np.array(
    [[1, 1, 1],
     [1, 0, 1],
     [1, 1, 1]], dtype=np.float64,
) / 8.0

_ANALYSIS_SIZE = 512


# ── Feature extraction ──────────────────────────────────

def _compute_npr_residual(gray: np.ndarray) -> np.ndarray:
    """Compute the NPR residual map: I(i,j) - mean(8-neighbors)."""
    neighbor_mean = cv2.filter2D(gray, cv2.CV_64F, _NEIGHBOR_KERNEL)
    residual = gray.astype(np.float64) - neighbor_mean
    return residual


def _residual_kurtosis(residual: np.ndarray) -> float:
    """Excess kurtosis of the residual distribution.

    Real images have heavy-tailed residuals (high kurtosis) from sensor noise
    and natural texture edges.  AI images have lighter tails (lower kurtosis)
    because upsampling creates smoother, more predictable neighbor relationships.
    """
    flat = residual.ravel()
    return float(stats.kurtosis(flat, fisher=True))


def _residual_entropy(residual: np.ndarray) -> float:
    """Shannon entropy of the NPR residual histogram.

    Quantise residuals to 256 bins and compute H = -Σ p log₂(p).
    Real → high entropy (diverse residuals); AI → lower entropy (patterned).
    """
    flat = residual.ravel()
    # Clip extreme outliers and bin into 256 levels
    vmin, vmax = np.percentile(flat, [0.5, 99.5])
    clipped = np.clip(flat, vmin, vmax)
    counts, _ = np.histogram(clipped, bins=256)
    probs = counts / counts.sum()
    probs = probs[probs > 0]
    return float(-np.sum(probs * np.log2(probs)))


def _checkerboard_energy(residual: np.ndarray) -> float:
    """Energy at Nyquist frequencies in the residual's FFT.

    Upsampling operations (ConvTranspose2d, pixel shuffle) create periodic
    artifacts at spatial frequencies (π, 0), (0, π), and (π, π) — the
    "checkerboard" pattern.  We measure the fraction of total FFT energy
    concentrated at these frequencies.
    """
    # Use center crop for efficiency
    h, w = residual.shape
    crop = min(h, w, 256)
    cy, cx = h // 2, w // 2
    patch = residual[cy - crop // 2:cy + crop // 2, cx - crop // 2:cx + crop // 2]

    fft_mag = np.abs(np.fft.fft2(patch))
    total_energy = np.sum(fft_mag ** 2) + 1e-10

    ph, pw = patch.shape
    # Nyquist corners: (0, N/2), (N/2, 0), (N/2, N/2) ± small region
    margin = 3
    nyquist_energy = 0.0
    for (fy, fx) in [(0, pw // 2), (ph // 2, 0), (ph // 2, pw // 2)]:
        y_lo = max(0, fy - margin)
        y_hi = min(ph, fy + margin + 1)
        x_lo = max(0, fx - margin)
        x_hi = min(pw, fx + margin + 1)
        nyquist_energy += np.sum(fft_mag[y_lo:y_hi, x_lo:x_hi] ** 2)

    return float(nyquist_energy / total_energy)


def _directional_asymmetry(gray: np.ndarray) -> float:
    """Asymmetry between horizontal and vertical neighbor residuals.

    Upsampling often introduces directional bias (e.g., bilinear interpolation
    treats x/y axes differently from diagonal).  We compare:
      residual_h[i,j] = I[i,j] - I[i, j+1]
      residual_v[i,j] = I[i,j] - I[i+1, j]
    and measure asymmetry as |var(h) - var(v)| / (var(h) + var(v)).

    Real images → low asymmetry (isotropic noise); AI → higher asymmetry.
    """
    h_diff = np.diff(gray.astype(np.float64), axis=1)
    v_diff = np.diff(gray.astype(np.float64), axis=0)

    var_h = np.var(h_diff) + 1e-10
    var_v = np.var(v_diff) + 1e-10
    return float(abs(var_h - var_v) / (var_h + var_v))


def _local_variance_uniformity(residual: np.ndarray, block_size: int = 16) -> float:
    """Coefficient of variation of local residual variances.

    Divide the residual map into non-overlapping blocks, compute variance
    per block, then measure coefficient of variation (std/mean) of those
    variances.

    Real → high CoV (heterogeneous — some blocks smooth, others textured)
    AI → low CoV (uniformly regular residual structure)
    """
    h, w = residual.shape
    variances = []
    for i in range(0, h - block_size + 1, block_size):
        for j in range(0, w - block_size + 1, block_size):
            block = residual[i:i + block_size, j:j + block_size]
            variances.append(np.var(block))

    variances = np.array(variances)
    mean_var = np.mean(variances) + 1e-10
    std_var = np.std(variances)
    return float(std_var / mean_var)


# ── Scoring ─────────────────────────────────────────────

def _score_from_features(features: dict[str, float]) -> tuple[float, float, list[str]]:
    """Convert NPR features to (score, confidence, flags).

    Score: 0.0 = definitely real, 1.0 = definitely AI.
    """
    score = 0.0
    flags: list[str] = []

    kurtosis = features["residual_kurtosis"]
    entropy = features["residual_entropy"]
    checker = features["checkerboard_energy"]
    asymmetry = features["directional_asymmetry"]
    cov = features["local_variance_cov"]

    # 1. Residual kurtosis — most discriminative single feature
    #    Real: kurtosis > 10 (heavy tails from sensor noise)
    #    AI:   kurtosis < 5  (lighter tails from upsampling)
    if kurtosis < 3.0:
        score += 0.25
        flags.append(f"Low NPR kurtosis ({kurtosis:.1f}) — AI-like residual distribution")
    elif kurtosis < 6.0:
        score += 0.12
        flags.append(f"Moderate NPR kurtosis ({kurtosis:.1f})")
    elif kurtosis > 20.0:
        score -= 0.05

    # 2. Residual entropy — low entropy = patterned residuals
    if entropy < 4.0:
        score += 0.20
        flags.append(f"Low residual entropy ({entropy:.2f}) — patterned pixel relationships")
    elif entropy < 5.5:
        score += 0.10
    elif entropy > 7.5:
        score -= 0.05

    # 3. Checkerboard energy at Nyquist frequencies
    if checker > 0.05:
        score += 0.25
        flags.append(f"Strong checkerboard artifacts ({checker:.4f}) — upsampling signature")
    elif checker > 0.02:
        score += 0.10
        flags.append(f"Moderate Nyquist energy ({checker:.4f})")

    # 4. Directional asymmetry — strong diffusion-model signal
    if asymmetry > 0.15:
        score += 0.20
        flags.append(f"Directional residual asymmetry ({asymmetry:.4f}) — non-isotropic generation")
    elif asymmetry > 0.08:
        score += 0.12
        flags.append(f"Moderate directional asymmetry ({asymmetry:.4f})")
    elif asymmetry > 0.04:
        score += 0.05

    # 5. Local variance uniformity — low CoV = AI-like uniform structure
    if cov < 0.5:
        score += 0.15
        flags.append(f"Uniform local residual variance (CoV={cov:.3f}) — AI generation pattern")
    elif cov < 1.0:
        score += 0.08
    elif cov > 2.5:
        score -= 0.05

    score = max(0.0, min(1.0, score))

    # Confidence: NPR is a strong technique — high baseline
    confidence = 0.70
    if score > 0.5:
        confidence = 0.80
    elif score < 0.15:
        confidence = 0.75  # confident it's real

    return score, confidence, flags


# ── Public entry point ──────────────────────────────────

def analyze(image_path: str) -> LayerResult:
    """Run NPR pixel-relationship analysis on an image."""
    try:
        img = Image.open(image_path).convert("L")
        gray = np.array(img, dtype=np.float64)
    except Exception as e:
        return LayerResult(
            layer=LayerName.NPR, score=0.0, confidence=0.0,
            flags=["Could not open image"], error=str(e),
        )

    # Resize to standard analysis size
    if max(gray.shape) != _ANALYSIS_SIZE:
        gray = cv2.resize(gray, (_ANALYSIS_SIZE, _ANALYSIS_SIZE))

    # Compute NPR residual map
    residual = _compute_npr_residual(gray)

    # Extract features
    features: dict[str, float] = {
        "residual_kurtosis": _residual_kurtosis(residual),
        "residual_entropy": _residual_entropy(residual),
        "checkerboard_energy": _checkerboard_energy(residual),
        "directional_asymmetry": _directional_asymmetry(gray),
        "local_variance_cov": _local_variance_uniformity(residual),
    }

    score, confidence, flags = _score_from_features(features)

    # Summary flag
    if score >= 0.5:
        flags.insert(0, f"NPR score: {score:.0%} — AI-like pixel neighbor patterns detected")
    elif score >= 0.25:
        flags.insert(0, f"NPR score: {score:.0%} — some AI-like neighbor patterns")
    else:
        flags.insert(0, f"NPR score: {score:.0%} — natural pixel relationships")

    return LayerResult(
        layer=LayerName.NPR,
        score=round(score, 4),
        confidence=round(confidence, 4),
        flags=flags,
        details={k: round(v, 6) for k, v in features.items()},
    )
