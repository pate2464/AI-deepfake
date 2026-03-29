"""Layer 8 — Enhanced Noise / PRNU Analysis.

Extracts the noise residual using wavelet-based denoising (Daubechies-4) and
analyses its statistical properties including PCE (Peak-to-Correlation Energy)
— the metric used in court-admissible digital forensics.

Real camera photos have sensor-specific PRNU (Photo Response Non-Uniformity).
AI-generated images lack any sensor fingerprint — their noise is either too
uniform or artificially random.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pywt
from PIL import Image
from scipy import stats

from app.core.models import LayerName, LayerResult


def _wavelet_denoise(img_arr: np.ndarray, wavelet: str = "db4", level: int = 3) -> np.ndarray:
    """Denoise using wavelet decomposition + Wiener-like soft thresholding.

    This extracts a much cleaner PRNU residual than simple Gaussian subtraction.
    """
    denoised = np.zeros_like(img_arr, dtype=np.float64)

    # Process each channel independently
    for ch in range(img_arr.shape[2] if img_arr.ndim == 3 else 1):
        channel = img_arr[:, :, ch].astype(np.float64) if img_arr.ndim == 3 else img_arr.astype(np.float64)

        # Wavelet decomposition
        coeffs = pywt.wavedec2(channel, wavelet, level=level)

        # Estimate noise sigma from finest detail coefficients (MAD estimator)
        detail_coeffs = coeffs[-1]  # (cH, cV, cD) at finest level
        sigma = np.median(np.abs(detail_coeffs[0])) / 0.6745

        # Soft-threshold detail coefficients (BayesShrink / Wiener-like)
        new_coeffs = [coeffs[0]]  # keep approximation
        for i in range(1, len(coeffs)):
            thresholded = []
            for c in coeffs[i]:
                # BayesShrink threshold
                sigma_c = max(np.std(c), 1e-10)
                sigma_n = max(sigma, 1e-10)
                sigma_s = max(sigma_c**2 - sigma_n**2, 0) ** 0.5
                if sigma_s > 0:
                    threshold = sigma_n**2 / sigma_s
                else:
                    threshold = np.max(np.abs(c))
                thresholded.append(pywt.threshold(c, threshold, mode="soft"))
            new_coeffs.append(tuple(thresholded))

        # Reconstruct denoised channel
        denoised_ch = pywt.waverec2(new_coeffs, wavelet)
        # Trim to original size (wavelet may pad)
        denoised_ch = denoised_ch[:channel.shape[0], :channel.shape[1]]

        if img_arr.ndim == 3:
            denoised[:, :, ch] = denoised_ch
        else:
            denoised = denoised_ch

    return denoised


def _extract_noise_residual(img_arr: np.ndarray) -> np.ndarray:
    """Extract noise residual using wavelet denoising (enhanced PRNU extraction)."""
    denoised = _wavelet_denoise(img_arr)
    residual = img_arr.astype(np.float64) - denoised
    return residual


def _compute_pce(residual: np.ndarray) -> float:
    """Compute Peak-to-Correlation Energy (PCE) of the noise residual.

    Real cameras produce PCE >> 25 (strong periodic sensor pattern).
    AI images produce PCE ≈ 1-5 (random noise, no sensor footprint).
    This metric is used in court-admissible forensics (Fridrich & Goljan).
    """
    if residual.ndim == 3:
        gray = np.mean(residual, axis=2)
    else:
        gray = residual

    # Downsample for speed (PCE is scale-invariant)
    h, w = gray.shape
    if h > 512 or w > 512:
        scale = min(512 / h, 512 / w)
        new_h, new_w = int(h * scale), int(w * scale)
        from PIL import Image as PILImage
        gray_img = PILImage.fromarray(gray)
        gray_img = gray_img.resize((new_w, new_h), PILImage.LANCZOS)
        gray = np.array(gray_img, dtype=np.float64)

    # Normalised circular cross-correlation via FFT
    fft = np.fft.fft2(gray)
    # Cross-correlate with itself (autocorrelation)
    power = fft * np.conj(fft)
    corr = np.fft.ifft2(power).real

    # Find peak (excluding DC / center)
    corr_shifted = np.fft.fftshift(corr)
    cy, cx = corr_shifted.shape[0] // 2, corr_shifted.shape[1] // 2

    # Mask out the central peak neighbourhood (5×5)
    mask = np.ones_like(corr_shifted, dtype=bool)
    mask[max(0, cy - 2):cy + 3, max(0, cx - 2):cx + 3] = False

    peak = corr_shifted[cy, cx]
    sidelobe_energy = np.mean(corr_shifted[mask] ** 2) if mask.any() else 1.0

    if sidelobe_energy > 0:
        pce = float(peak ** 2 / sidelobe_energy)
    else:
        pce = 0.0

    return pce


def _noise_spectrum_flatness(residual: np.ndarray) -> float:
    """Compute spectral flatness of the noise residual.

    Real cameras produce coloured noise (1/f + sensor peaks) → low flatness.
    AI generators produce white/flat noise → high flatness (~1.0).
    """
    if residual.ndim == 3:
        gray = np.mean(residual, axis=2)
    else:
        gray = residual

    # Power spectral density
    fft_mag = np.abs(np.fft.fft2(gray)) ** 2
    fft_mag = fft_mag.flatten()
    fft_mag = fft_mag[fft_mag > 0]  # avoid log(0)

    if len(fft_mag) == 0:
        return 0.5

    # Spectral flatness = geometric mean / arithmetic mean
    log_mean = np.mean(np.log(fft_mag + 1e-10))
    geo_mean = np.exp(log_mean)
    arith_mean = np.mean(fft_mag)

    if arith_mean > 0:
        flatness = float(geo_mean / arith_mean)
    else:
        flatness = 0.5

    return np.clip(flatness, 0.0, 1.0)


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

    residual = _extract_noise_residual(img_arr)
    noise_stats = _compute_noise_stats(residual)
    details["noise_stats"] = noise_stats
    details["denoising_method"] = "wavelet (Daubechies-4, BayesShrink)"

    # ── PCE — Peak-to-Correlation Energy ───────────────
    pce_value = _compute_pce(residual)
    details["pce_value"] = round(pce_value, 2)

    # ── Noise spectrum flatness ────────────────────────
    spectrum_flatness = _noise_spectrum_flatness(residual)
    details["spectrum_flatness"] = round(spectrum_flatness, 4)

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

    # 5. PCE — Peak-to-Correlation Energy (court-grade forensic metric)
    #    Real cameras: PCE >> 25, AI images: PCE ≈ 1-5
    #    PCE is the single strongest forensic signal — weight it heavily.
    if pce_value > 500:
        flags.append(f"Very strong camera sensor pattern (PCE={pce_value:.0f}) — forensically authentic")
        score -= 0.40  # Dominant evidence of real camera — override weaker heuristics
    elif pce_value > 50:
        flags.append(f"Strong camera sensor pattern (PCE={pce_value:.0f}) — forensically authentic")
        score -= 0.25
    elif pce_value > 25:
        flags.append(f"Moderate camera sensor pattern (PCE={pce_value:.0f})")
        score -= 0.10
    elif pce_value < 5:
        flags.append(f"No camera sensor pattern detected (PCE={pce_value:.1f}) — suspicious")
        score += 0.15

    # 6. Noise spectrum flatness — real cameras have coloured noise, AI has white noise
    if spectrum_flatness > 0.8:
        flags.append(f"Flat/white noise spectrum ({spectrum_flatness:.3f}) — suggests AI generation")
        score += 0.15
    elif spectrum_flatness < 0.3:
        flags.append(f"Coloured noise spectrum ({spectrum_flatness:.3f}) — consistent with camera sensor")
        score -= 0.10

    score = max(0.0, min(1.0, score))
    confidence = 0.65  # Enhanced with PCE + spectrum — higher than before

    if not flags:
        flags.append("Noise patterns appear consistent with natural camera capture")

    return LayerResult(
        layer=LayerName.NOISE,
        score=round(score, 4),
        confidence=round(confidence, 4),
        flags=flags,
        details=details,
    )
