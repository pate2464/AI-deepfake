"""Layer 13 — DIRE: Diffusion Reconstruction Error (Spectral Analysis Mode).

Inspired by the DIRE paper — uses frequency-domain analysis of reconstruction
error to detect AI-generated images.  Real camera photos have rich, irregular
high-frequency content from sensor noise, lens aberrations, and natural texture.
AI-generated images have characteristic spectral fingerprints: attenuated high
frequencies and periodic patterns from the generation process.

Reference: Wang et al., "DIRE for Diffusion-Generated Image Detection"
           (ICCV 2023)

This implementation works without the original DIRE weights (which are only
available on BaiduDrive).  It uses spectral analysis + DCT-domain statistics
as a proxy for the full diffusion reconstruction pipeline.
"""

from __future__ import annotations

import logging
from typing import Any

import cv2
import numpy as np
import pywt
from PIL import Image
from scipy import fftpack

from app.core.config import settings
from app.core.models import LayerName, LayerResult

logger = logging.getLogger(__name__)


def _compute_spectral_features(img_arr: np.ndarray) -> dict[str, float]:
    """Compute frequency-domain features that distinguish real vs AI images.

    AI-generated images tend to have:
    - Less high-frequency energy (smoother textures)
    - More regular spectral patterns (grid artifacts from upsampling)
    - Lower spectral entropy (less random noise)
    - Different DCT coefficient distributions
    """
    # Convert to grayscale float
    if img_arr.ndim == 3:
        gray = cv2.cvtColor(img_arr, cv2.COLOR_RGB2GRAY).astype(np.float64)
    else:
        gray = img_arr.astype(np.float64)

    # Resize to standard size for consistent analysis
    gray = cv2.resize(gray, (512, 512))

    # 2D FFT
    f_transform = np.fft.fft2(gray)
    f_shift = np.fft.fftshift(f_transform)
    magnitude = np.abs(f_shift)
    magnitude_log = np.log1p(magnitude)

    h, w = gray.shape
    cy, cx = h // 2, w // 2

    # Radial frequency bands
    Y, X = np.ogrid[:h, :w]
    dist = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)
    max_radius = min(cy, cx)

    # Low/mid/high frequency energy ratio
    low_mask = dist < max_radius * 0.15
    mid_mask = (dist >= max_radius * 0.15) & (dist < max_radius * 0.5)
    high_mask = dist >= max_radius * 0.5

    total_energy = magnitude_log.sum() + 1e-10
    low_energy = magnitude_log[low_mask].sum() / total_energy
    mid_energy = magnitude_log[mid_mask].sum() / total_energy
    high_energy = magnitude_log[high_mask].sum() / total_energy

    # Spectral entropy (randomness of frequency distribution)
    mag_flat = magnitude_log.flatten()
    mag_flat = mag_flat / (mag_flat.sum() + 1e-10)
    mag_flat = mag_flat[mag_flat > 1e-12]
    spectral_entropy = -np.sum(mag_flat * np.log2(mag_flat + 1e-12))

    # DCT analysis on 8x8 blocks (JPEG-like)
    n_blocks = 0
    dct_high_energy_ratio = 0.0
    block_size = 8
    for i in range(0, h - block_size + 1, block_size):
        for j in range(0, w - block_size + 1, block_size):
            block = gray[i:i+block_size, j:j+block_size]
            dct_block = fftpack.dct(fftpack.dct(block, axis=0, norm='ortho'), axis=1, norm='ortho')
            block_total = np.abs(dct_block).sum() + 1e-10
            # High-frequency DCT coefficients (bottom-right quarter)
            block_high = np.abs(dct_block[4:, 4:]).sum()
            dct_high_energy_ratio += block_high / block_total
            n_blocks += 1

    dct_high_energy_ratio /= max(n_blocks, 1)

    # Laplacian variance (sharpness measure)
    laplacian = cv2.Laplacian(gray.astype(np.uint8), cv2.CV_64F)
    laplacian_var = laplacian.var()

    # Local noise estimation via median filter residual
    from scipy.ndimage import median_filter
    denoised = median_filter(gray, size=3)
    noise_residual = gray - denoised
    noise_std = noise_residual.std()

    return {
        "low_freq_ratio": float(low_energy),
        "mid_freq_ratio": float(mid_energy),
        "high_freq_ratio": float(high_energy),
        "spectral_entropy": float(spectral_entropy),
        "dct_high_energy": float(dct_high_energy_ratio),
        "laplacian_var": float(laplacian_var),
        "noise_std": float(noise_std),
    }


def _score_from_spectral(features: dict[str, float]) -> tuple[float, list[str]]:
    """Convert spectral features to a manipulation score.

    Returns (score, flags).
    Real images: high frequency energy, high noise std, high laplacian var
    AI images: low high-freq energy, low noise, smooth textures
    """
    score = 0.0
    flags = []

    high_freq = features["high_freq_ratio"]
    noise = features["noise_std"]
    lap_var = features["laplacian_var"]
    dct_high = features["dct_high_energy"]
    entropy = features["spectral_entropy"]

    # AI images have less high-frequency content
    if high_freq < 0.20:
        score += 0.25
        flags.append("Low high-frequency energy (AI signature)")
    elif high_freq < 0.25:
        score += 0.10

    # AI images have lower noise
    if noise < 2.0:
        score += 0.20
        flags.append("Very low noise floor (AI-generated patterns)")
    elif noise < 4.0:
        score += 0.10

    # AI images are smoother (lower Laplacian variance)
    if lap_var < 50:
        score += 0.15
        flags.append("Unusually smooth texture (low edge variance)")
    elif lap_var < 150:
        score += 0.05

    # AI images have less DCT high-frequency energy
    if dct_high < 0.05:
        score += 0.15
    elif dct_high < 0.08:
        score += 0.05

    # Real images: strong evidence
    if high_freq > 0.35:
        score -= 0.20
    if noise > 8.0:
        score -= 0.15
        flags.append("Rich sensor noise pattern (real camera signature)")
    if lap_var > 500:
        score -= 0.10

    score = max(0.0, min(1.0, score))
    return score, flags


# ── Snap-Back Reconstruction (Ameen & Islam, arXiv:2511.00352) ──────────

_SNAP_SIGMAS = [5.0, 10.0, 20.0, 40.0, 80.0]


def _wavelet_denoise_gray(gray: np.ndarray, wavelet: str = "db4", level: int = 3) -> np.ndarray:
    """BayesShrink wavelet denoising for a single-channel float64 image."""
    coeffs = pywt.wavedec2(gray, wavelet, level=level)
    detail = coeffs[-1]
    sigma = np.median(np.abs(detail[0])) / 0.6745

    new_coeffs = [coeffs[0]]
    for i in range(1, len(coeffs)):
        thresholded = []
        for c in coeffs[i]:
            sigma_c = max(np.std(c), 1e-10)
            sigma_n = max(sigma, 1e-10)
            sigma_s = max(sigma_c ** 2 - sigma_n ** 2, 0) ** 0.5
            threshold = sigma_n ** 2 / sigma_s if sigma_s > 0 else np.max(np.abs(c))
            thresholded.append(pywt.threshold(c, threshold, mode="soft"))
        new_coeffs.append(tuple(thresholded))

    rec = pywt.waverec2(new_coeffs, wavelet)
    return rec[:gray.shape[0], :gray.shape[1]]


def _manual_ssim(a: np.ndarray, b: np.ndarray) -> float:
    """Compute SSIM between two grayscale float64 images (simplified, no sklearn)."""
    C1 = (0.01 * 255) ** 2
    C2 = (0.03 * 255) ** 2

    mu_a = cv2.GaussianBlur(a, (11, 11), 1.5)
    mu_b = cv2.GaussianBlur(b, (11, 11), 1.5)

    mu_a_sq = mu_a ** 2
    mu_b_sq = mu_b ** 2
    mu_ab = mu_a * mu_b

    sigma_a_sq = cv2.GaussianBlur(a ** 2, (11, 11), 1.5) - mu_a_sq
    sigma_b_sq = cv2.GaussianBlur(b ** 2, (11, 11), 1.5) - mu_b_sq
    sigma_ab = cv2.GaussianBlur(a * b, (11, 11), 1.5) - mu_ab

    num = (2 * mu_ab + C1) * (2 * sigma_ab + C2)
    den = (mu_a_sq + mu_b_sq + C1) * (sigma_a_sq + sigma_b_sq + C2)

    ssim_map = num / den
    return float(np.mean(ssim_map))


def _snap_back_features(gray: np.ndarray) -> dict[str, float]:
    """Diffusion snap-back trajectory analysis.

    For each noise level σ: add Gaussian noise → denoise → measure SSIM to
    original.  AI-generated images "snap back" more readily (higher SSIM after
    heavy noise) because denoising reconstructs the learned generation manifold.
    Real images degrade permanently under heavy noise.

    Returns trajectory features that discriminate real vs AI.
    """
    rng = np.random.default_rng(42)
    ssims: list[float] = []

    for sigma in _SNAP_SIGMAS:
        noisy = gray + rng.normal(0, sigma, gray.shape)
        noisy = np.clip(noisy, 0, 255)
        denoised = _wavelet_denoise_gray(noisy)
        ssim_val = _manual_ssim(gray, denoised)
        ssims.append(ssim_val)

    ssims_arr = np.array(ssims)
    log_sigmas = np.log10(np.array(_SNAP_SIGMAS))

    # ── Snap-back ratio: SSIM at highest σ / SSIM at lowest σ ──
    # AI → higher ratio (snaps back even after heavy noise)
    snap_ratio = ssims_arr[-1] / (ssims_arr[0] + 1e-10)

    # ── Slope of SSIM vs log(σ) ──
    # Real → steeper negative slope (degrades faster)
    if len(log_sigmas) >= 2 and np.std(log_sigmas) > 1e-10:
        slope = float(np.polyfit(log_sigmas, ssims_arr, 1)[0])
    else:
        slope = 0.0

    # ── Curvature (2nd derivative proxy) ──
    # How non-linear the degradation curve is
    if len(ssims_arr) >= 3:
        d2 = np.diff(ssims_arr, n=2)
        curvature = float(np.mean(np.abs(d2)))
    else:
        curvature = 0.0

    # ── Minimum ΔSSIM between consecutive σ levels ──
    deltas = np.abs(np.diff(ssims_arr))
    min_delta = float(np.min(deltas)) if len(deltas) > 0 else 0.0

    return {
        "snap_ratio": float(snap_ratio),
        "snap_slope": slope,
        "snap_curvature": curvature,
        "snap_min_delta": min_delta,
        "snap_ssim_low": float(ssims_arr[0]),
        "snap_ssim_high": float(ssims_arr[-1]),
    }


def _score_snap_back(features: dict[str, float]) -> tuple[float, list[str]]:
    """Score the snap-back features."""
    score = 0.0
    flags: list[str] = []

    snap_ratio = features["snap_ratio"]
    slope = features["snap_slope"]
    ssim_high = features["snap_ssim_high"]

    # AI images snap back more (higher ratio at heavy noise)
    if snap_ratio > 0.85:
        score += 0.25
        flags.append(f"High snap-back ratio ({snap_ratio:.3f}) — AI manifold reconstruction")
    elif snap_ratio > 0.70:
        score += 0.10

    # Real images degrade faster (more negative slope)
    if slope > -0.05:
        score += 0.20
        flags.append(f"Flat SSIM degradation (slope={slope:.4f}) — AI resilience to noise")
    elif slope > -0.10:
        score += 0.08
    elif slope < -0.20:
        score -= 0.10

    # High SSIM even at σ=80 → AI
    if ssim_high > 0.70:
        score += 0.15
        flags.append(f"High SSIM at σ=80 ({ssim_high:.3f}) — strong manifold snap-back")
    elif ssim_high > 0.50:
        score += 0.05
    elif ssim_high < 0.30:
        score -= 0.10

    return max(0.0, min(1.0, score)), flags


def analyze(image_path: str) -> LayerResult:
    """Run DIRE spectral analysis."""

    if not settings.ENABLE_DIRE:
        return LayerResult(
            layer=LayerName.DIRE,
            score=0.0,
            confidence=0.0,
            flags=["DIRE layer disabled — enable with ENABLE_DIRE=true"],
            details={"enabled": False},
        )

    flags: list[str] = []
    details: dict[str, Any] = {}

    try:
        img = Image.open(image_path).convert("RGB")
    except Exception as e:
        return LayerResult(
            layer=LayerName.DIRE, score=0.5, confidence=0.0,
            flags=["Could not open image"], error=str(e),
        )

    img_arr = np.array(img)
    features = _compute_spectral_features(img_arr)
    spectral_score, spec_flags = _score_from_spectral(features)
    flags.extend(spec_flags)

    details["enabled"] = True
    details["spectral_features"] = {k: round(v, 6) for k, v in features.items()}

    # Snap-back trajectory analysis
    gray = cv2.cvtColor(img_arr, cv2.COLOR_RGB2GRAY).astype(np.float64)
    gray = cv2.resize(gray, (512, 512))
    snap_features = _snap_back_features(gray)
    snap_score, snap_flags = _score_snap_back(snap_features)
    flags.extend(snap_flags)
    details["snap_back_features"] = {k: round(v, 6) for k, v in snap_features.items()}

    # Blend spectral + snap-back (60/40 — snap-back is newer/complementary)
    score = 0.60 * spectral_score + 0.40 * snap_score
    details["spectral_score"] = round(spectral_score, 4)
    details["snap_back_score"] = round(snap_score, 4)
    details["dire_score"] = round(score, 4)

    # Boost confidence when both sub-scores agree
    confidence = 0.35
    if spectral_score >= 0.4 and snap_score >= 0.3:
        confidence = 0.50
    elif spectral_score < 0.2 and snap_score < 0.2:
        confidence = 0.45

    if score >= 0.5:
        flags.insert(0, f"DIRE spectral score: {score:.0%} — frequency patterns suggest AI generation")
    elif score >= 0.25:
        flags.insert(0, f"DIRE spectral score: {score:.0%} — some AI-like spectral characteristics")
    else:
        flags.insert(0, f"DIRE spectral score: {score:.0%} — natural frequency distribution")

    return LayerResult(
        layer=LayerName.DIRE,
        score=round(score, 4),
        confidence=round(confidence, 4),
        flags=flags,
        details=details,
    )
