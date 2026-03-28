"""Layer 4 — AI Model Detection (FFT Frequency Analysis).

Analyses the image in the frequency domain using Fast Fourier Transform.
AI-generated images (from diffusion models and GANs) introduce periodic
artifacts in high-frequency components that don't exist in real camera photos.

Note: For a hackathon build, we use FFT spectral analysis rather than the
full CLIP-based UniversalFakeDetect model to avoid large model downloads.
The CLIP layer can be added as a stretch goal.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from PIL import Image

from app.core.models import LayerName, LayerResult


def _compute_fft_features(img_array: np.ndarray) -> dict[str, float]:
    """Compute frequency-domain features from a grayscale image."""
    # 2D FFT
    f_transform = np.fft.fft2(img_array)
    f_shift = np.fft.fftshift(f_transform)
    magnitude = np.abs(f_shift)

    # Log magnitude spectrum (avoid log(0))
    log_mag = np.log1p(magnitude)

    h, w = img_array.shape
    cy, cx = h // 2, w // 2

    # Define regions: low-freq (center 25%), mid (25-50%), high (50-100%)
    radius_low = min(h, w) // 8
    radius_mid = min(h, w) // 4

    y, x = np.ogrid[:h, :w]
    dist = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)

    mask_low = dist <= radius_low
    mask_mid = (dist > radius_low) & (dist <= radius_mid)
    mask_high = dist > radius_mid

    total_energy = np.sum(magnitude ** 2)
    low_energy = np.sum(magnitude[mask_low] ** 2) / (total_energy + 1e-10)
    mid_energy = np.sum(magnitude[mask_mid] ** 2) / (total_energy + 1e-10)
    high_energy = np.sum(magnitude[mask_high] ** 2) / (total_energy + 1e-10)

    # Spectral flatness — AI images tend to have more structured (less flat) spectra
    geo_mean = np.exp(np.mean(np.log(magnitude + 1e-10)))
    arith_mean = np.mean(magnitude)
    spectral_flatness = geo_mean / (arith_mean + 1e-10)

    # Peak detection in high-frequency region
    high_freq_vals = magnitude[mask_high]
    if len(high_freq_vals) > 0:
        hf_mean = np.mean(high_freq_vals)
        hf_std = np.std(high_freq_vals)
        hf_max = np.max(high_freq_vals)
        # Peaks = values more than 3 std above mean
        peak_count = int(np.sum(high_freq_vals > hf_mean + 3 * hf_std))
        peak_ratio = peak_count / (len(high_freq_vals) + 1e-10)
    else:
        hf_mean = hf_std = hf_max = 0.0
        peak_count = 0
        peak_ratio = 0.0

    return {
        "low_freq_energy_ratio": float(low_energy),
        "mid_freq_energy_ratio": float(mid_energy),
        "high_freq_energy_ratio": float(high_energy),
        "spectral_flatness": float(spectral_flatness),
        "hf_peak_count": peak_count,
        "hf_peak_ratio": float(peak_ratio),
        "hf_mean": float(hf_mean),
        "hf_std": float(hf_std),
        "hf_max": float(hf_max),
    }


def _compute_dct_features(img_array: np.ndarray) -> dict[str, float]:
    """Compute DCT-based features (complementary to FFT)."""
    from scipy.fft import dctn

    dct = dctn(img_array.astype(np.float64), norm="ortho")
    abs_dct = np.abs(dct)

    h, w = img_array.shape
    # Block-based DCT analysis (8x8 blocks like JPEG)
    block_size = 8
    block_energies = []
    for i in range(0, h - block_size + 1, block_size):
        for j in range(0, w - block_size + 1, block_size):
            block = abs_dct[i:i + block_size, j:j + block_size]
            # Ratio of AC to DC component
            dc = block[0, 0] + 1e-10
            ac = np.sum(block) - block[0, 0]
            block_energies.append(ac / dc)

    if block_energies:
        return {
            "dct_ac_dc_mean": float(np.mean(block_energies)),
            "dct_ac_dc_std": float(np.std(block_energies)),
        }
    return {"dct_ac_dc_mean": 0.0, "dct_ac_dc_std": 0.0}


def _compute_power_law_features(img_array: np.ndarray) -> dict[str, float]:
    """Compute 1/f^β power-law spectral features (Doloriel et al., arXiv:2512.08042).

    Natural images follow a 1/f^β power spectral density with β ≈ 1.8–2.2.
    AI-generated images deviate from this — often β < 1.5 or > 2.5, and the
    residual energy from the power-law fit is higher.
    """
    f_transform = np.fft.fft2(img_array)
    f_shift = np.fft.fftshift(f_transform)
    power = np.abs(f_shift) ** 2

    h, w = img_array.shape
    cy, cx = h // 2, w // 2
    Y, X = np.ogrid[:h, :w]
    dist = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)

    max_radius = min(cy, cx)

    # Radial PSD in log-spaced bins (avoid DC component)
    n_bins = 30
    bin_edges = np.logspace(np.log10(2), np.log10(max_radius), n_bins + 1)
    radial_freq = []
    radial_psd = []

    for k in range(n_bins):
        mask = (dist >= bin_edges[k]) & (dist < bin_edges[k + 1])
        if np.sum(mask) > 0:
            mean_psd = float(np.mean(power[mask]))
            if mean_psd > 0:
                radial_freq.append((bin_edges[k] + bin_edges[k + 1]) / 2.0)
                radial_psd.append(mean_psd)

    if len(radial_freq) < 5:
        return {
            "beta_exponent": 0.0,
            "beta_deviation": 2.0,
            "power_law_residual": 1.0,
            "n_spectral_bumps": 0,
        }

    log_freq = np.log10(np.array(radial_freq))
    log_psd = np.log10(np.array(radial_psd))

    # Linear fit: log(PSD) = -β * log(freq) + c
    coeffs = np.polyfit(log_freq, log_psd, 1)
    beta_exponent = -coeffs[0]  # Negate because slope is negative for 1/f^β

    # Deviation from natural β ≈ 2.0
    beta_deviation = abs(beta_exponent - 2.0)

    # Residual energy from fit (how well it follows power law)
    fitted = np.polyval(coeffs, log_freq)
    residuals = log_psd - fitted
    residual_energy = float(np.mean(residuals ** 2))

    # Count spectral "bumps" — local maxima in residuals that exceed 1 std
    # AI images often have characteristic bumps at specific frequencies
    res_std = np.std(residuals)
    n_bumps = 0
    for i in range(1, len(residuals) - 1):
        if residuals[i] > residuals[i - 1] and residuals[i] > residuals[i + 1]:
            if residuals[i] > res_std:
                n_bumps += 1

    return {
        "beta_exponent": float(beta_exponent),
        "beta_deviation": float(beta_deviation),
        "power_law_residual": float(residual_energy),
        "n_spectral_bumps": n_bumps,
    }


def analyze(image_path: str) -> LayerResult:
    """Run frequency-domain AI detection analysis."""
    flags: list[str] = []
    details: dict[str, Any] = {}

    try:
        img = Image.open(image_path).convert("L")  # Convert to grayscale
        img_arr = np.array(img, dtype=np.float64)
    except Exception as e:
        return LayerResult(
            layer=LayerName.AI_MODEL, score=0.5, confidence=0.3,
            flags=["Could not open image"], error=str(e),
        )

    # Detect if source is a lossy-compressed format (HEIC, WebP, etc.)
    # These codecs naturally suppress high-frequency energy during compression,
    # which is NOT an AI artifact — it's just how modern codecs work.
    ext_lower = image_path.rsplit(".", 1)[-1].lower() if "." in image_path else ""
    is_lossy_non_jpeg = ext_lower in ("heic", "heif", "webp", "avif")
    details["source_format"] = ext_lower
    details["is_lossy_non_jpeg"] = is_lossy_non_jpeg

    # FFT analysis
    fft_feats = _compute_fft_features(img_arr)
    details["fft"] = fft_feats

    # DCT analysis
    dct_feats = _compute_dct_features(img_arr)
    details["dct"] = dct_feats

    # Power-law 1/f^β analysis
    power_law_feats = _compute_power_law_features(img_arr)
    details["power_law"] = power_law_feats

    # ── Scoring heuristics ─────────────────────────────

    score = 0.0
    confidence = 0.5  # Frequency analysis alone has moderate confidence

    # AI images often have unusually high energy in specific high-freq bands
    # and more periodic peaks than natural images
    hf_peak_ratio = fft_feats["hf_peak_ratio"]
    spectral_flatness = fft_feats["spectral_flatness"]
    high_energy = fft_feats["high_freq_energy_ratio"]

    # 1. Peak ratio — AI images have periodic peaks, but natural high-detail
    #    photos can also have many peaks. Need higher threshold.
    #    Real photos with rich texture (food, nature) commonly have peak_ratio > 0.01
    if hf_peak_ratio > 0.05:
        flags.append(f"Excessive high-frequency spectral peaks (ratio={hf_peak_ratio:.6f})")
        score += 0.3
    elif hf_peak_ratio > 0.02:
        flags.append(f"Elevated high-frequency peaks (ratio={hf_peak_ratio:.6f})")
        score += 0.15
    elif hf_peak_ratio > 0.005:
        # Normal range for detailed real photos — not suspicious
        pass

    # 2. Spectral flatness — AI images often show less flat spectra
    if spectral_flatness < 0.001:
        flags.append("Very structured frequency spectrum — possible GAN/diffusion artifacts")
        score += 0.2
    elif spectral_flatness < 0.01:
        score += 0.1

    # 3. High-frequency energy distribution
    if high_energy > 0.3:
        flags.append("Unusually high energy in high-frequency bands")
        score += 0.2
    elif high_energy < 0.005:
        if is_lossy_non_jpeg:
            # HEIC/WebP/AVIF codecs naturally suppress HF energy — not suspicious
            flags.append(f"Low HF energy expected for {ext_lower.upper()} codec — not indicative of AI")
        else:
            flags.append("Very low high-frequency energy — possible over-smoothed AI image")
            score += 0.2
    elif high_energy < 0.01:
        if not is_lossy_non_jpeg:
            flags.append("Low high-frequency energy — possible smoothing")
            score += 0.1

    # 4. DCT block uniformity
    dct_std = dct_feats["dct_ac_dc_std"]
    if dct_std < 0.3:
        flags.append("Uniform DCT block patterns — suggests synthetic generation")
        score += 0.15
    elif dct_std < 0.5:
        score += 0.05

    # 5. Power-law β exponent (Doloriel et al.)
    #    Natural images: β ≈ 1.8–2.2; AI-generated: β deviates
    beta_dev = power_law_feats["beta_deviation"]
    beta_exp = power_law_feats["beta_exponent"]
    pl_residual = power_law_feats["power_law_residual"]
    n_bumps = power_law_feats["n_spectral_bumps"]

    if beta_dev > 0.8:
        flags.append(f"Power-law β={beta_exp:.2f} deviates strongly from natural (β≈2.0)")
        score += 0.20
    elif beta_dev > 0.4:
        flags.append(f"Power-law β={beta_exp:.2f} — moderate deviation")
        score += 0.10
    elif beta_dev < 0.15:
        # Very close to natural β — slightly reduce score
        score -= 0.05

    # 6. Power-law fit residual — poor fit means non-natural frequency distribution
    if pl_residual > 0.3:
        flags.append(f"High spectral power-law residual ({pl_residual:.3f}) — non-natural PSD")
        score += 0.10
    elif pl_residual > 0.15:
        score += 0.05

    # 7. Spectral bumps at specific frequencies (generation artifacts)
    if n_bumps >= 4:
        flags.append(f"Multiple spectral bumps ({n_bumps}) — periodic generation artifacts")
        score += 0.10
    elif n_bumps >= 2:
        score += 0.05

    score = min(1.0, score)

    if not flags:
        flags.append("Frequency analysis did not detect clear AI artifacts")
        confidence = 0.4

    return LayerResult(
        layer=LayerName.AI_MODEL,
        score=round(score, 4),
        confidence=round(confidence, 4),
        flags=flags,
        details=details,
    )
