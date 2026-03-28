"""Layer 17 — GAN Spectral Fingerprint Detection.

Every GAN architecture produces a unique spectral fingerprint due to its
upsampling method (transposed convolution, pixel shuffle, bilinear+conv).
These create periodic artifacts in the 2D Fourier spectrum that are invisible
to the human eye but mathematically detectable.

Key signatures:
  1. Periodic peaks in the FFT magnitude spectrum from ConvTranspose2d
     stride patterns ("checkerboard artifacts")
  2. Radial frequency band energy ratios that differ between generators
  3. Azimuthal (angular) spectrum asymmetries from non-isotropic upsampling
  4. Cross-channel spectral correlation (RGB channels share generator artifacts)
  5. Spectral peak grid detection and periodicity scoring

References:
  Durall, R. et al. (2020). "Watch your Up-Convolution: CNN Based Generative
  Deep Neural Networks are Failing to Reproduce Spectral Distributions" — CVPR.
  Frank, J. et al. (2020). "Leveraging Frequency Analysis for Deep Fake
  Image Recognition" — ICML.
"""

from __future__ import annotations

import logging
from typing import Any

import cv2
import numpy as np

from app.core.models import LayerName, LayerResult

logger = logging.getLogger(__name__)

ANALYSIS_SIZE = 256  # Consistent FFT size (power of 2 for efficiency)


def _compute_magnitude_spectrum(channel: np.ndarray) -> np.ndarray:
    """Compute centred log-magnitude FFT spectrum of a single channel."""
    f = np.fft.fft2(channel.astype(np.float64))
    f_shift = np.fft.fftshift(f)
    magnitude = np.log1p(np.abs(f_shift))
    return magnitude


def _detect_periodic_peaks(spectrum: np.ndarray, threshold_sigma: float = 4.0) -> dict[str, Any]:
    """Detect periodic peaks in the FFT magnitude spectrum.

    GAN upsampling creates peaks at regular intervals determined by stride.
    Returns count, locations, and periodicity metrics.
    """
    h, w = spectrum.shape
    cy, cx = h // 2, w // 2

    # Subtract radial average to isolate peaks from natural spectral falloff
    Y, X = np.ogrid[:h, :w]
    R = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2).astype(int)
    max_r = min(cy, cx)

    # Compute radial average
    radial_mean = np.zeros(max_r + 1)
    radial_std = np.zeros(max_r + 1)
    for r in range(max_r + 1):
        mask = R == r
        if mask.any():
            radial_mean[r] = spectrum[mask].mean()
            radial_std[r] = spectrum[mask].std()

    # Create "expected" spectrum from radial average
    expected = np.zeros_like(spectrum)
    for r in range(max_r + 1):
        mask = R == r
        expected[mask] = radial_mean[min(r, max_r)]

    # Residual: peaks above radial average
    residual = spectrum - expected

    # Detect peaks exceeding threshold_sigma standard deviations
    global_std = np.std(residual)
    if global_std < 1e-10:
        return {"peak_count": 0, "peak_max": 0.0, "periodicity": 0.0, "grid_score": 0.0}

    peak_mask = residual > threshold_sigma * global_std
    # Exclude center (DC component) and near-center (low freq)
    center_mask = R < 5
    peak_mask &= ~center_mask

    peak_count = int(np.sum(peak_mask))
    peak_max = float(np.max(residual[~center_mask])) if np.any(~center_mask) else 0.0

    # ── Periodicity detection ──────────────────────────
    # Check if peaks form a regular grid (GAN ConvTranspose2d signature)
    peak_coords = np.argwhere(peak_mask)
    grid_score = 0.0
    if len(peak_coords) >= 4:
        # Compute distances between all peaks — GAN peaks form a grid
        # with specific spacing related to stride size
        relative = peak_coords - np.array([cy, cx])
        if len(relative) > 1:
            # Check for repeated spacings (gridness)
            diffs = []
            for i in range(min(len(relative), 50)):
                for j in range(i + 1, min(len(relative), 50)):
                    d = np.abs(relative[i] - relative[j])
                    diffs.append(tuple(d))
            if diffs:
                # Count repeated distance vectors (grid → many repeats)
                unique_diffs = set(diffs)
                repeats = len(diffs) - len(unique_diffs)
                grid_score = min(1.0, repeats / max(len(diffs), 1))

    # ── Autocorrelation periodicity ────────────────────
    # Check 1D autocorrelation of the residual along horizontal axis through center
    center_row = residual[cy, :]
    ac = np.correlate(center_row - center_row.mean(), center_row - center_row.mean(), mode='full')
    ac = ac[len(ac) // 2:]
    if ac[0] > 0:
        ac /= ac[0]
    # Look for secondary peaks (periodicity)
    secondary_peaks = []
    for i in range(3, len(ac) - 1):
        if ac[i] > ac[i - 1] and ac[i] > ac[i + 1] and ac[i] > 0.1:
            secondary_peaks.append((i, float(ac[i])))
    periodicity = max([p[1] for p in secondary_peaks], default=0.0)

    return {
        "peak_count": peak_count,
        "peak_max": round(peak_max, 4),
        "periodicity": round(periodicity, 4),
        "grid_score": round(grid_score, 4),
    }


def _azimuthal_asymmetry(spectrum: np.ndarray) -> float:
    """Measure angular asymmetry of the FFT magnitude spectrum.

    Natural images tend to have roughly isotropic spectra (equal energy
    in all directions).  GAN upsampling can create directional artifacts
    (horizontal/vertical stripes from stride patterns).
    """
    h, w = spectrum.shape
    cy, cx = h // 2, w // 2

    # Compute angle for each pixel
    Y, X = np.ogrid[:h, :w]
    angles = np.arctan2(Y - cy, X - cx)
    R = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)

    # Exclude center and edges
    valid = (R > 3) & (R < min(cy, cx) * 0.9)

    # Compute energy in angular bins (every 15 degrees = 24 bins)
    n_bins = 24
    bin_edges = np.linspace(-np.pi, np.pi, n_bins + 1)
    angular_energy = np.zeros(n_bins)

    for i in range(n_bins):
        mask = valid & (angles >= bin_edges[i]) & (angles < bin_edges[i + 1])
        if mask.any():
            angular_energy[i] = np.mean(spectrum[mask])

    if angular_energy.sum() == 0:
        return 0.0

    angular_energy /= angular_energy.sum()

    # Asymmetry: coefficient of variation of angular energy
    # Isotropic = low CV, directional artifacts = high CV
    cv = float(np.std(angular_energy) / max(np.mean(angular_energy), 1e-10))
    return cv


def _cross_channel_spectral_correlation(img: np.ndarray) -> float:
    """Measure correlation between RGB channel spectra.

    In natural images, each channel has somewhat independent spectral content.
    In GAN images, the shared generator architecture creates correlated spectra.
    """
    channels = cv2.split(img)
    spectra = [_compute_magnitude_spectrum(ch) for ch in channels]

    correlations = []
    for i in range(3):
        for j in range(i + 1, 3):
            a, b = spectra[i].ravel(), spectra[j].ravel()
            if np.std(a) > 0 and np.std(b) > 0:
                corr = float(np.corrcoef(a, b)[0, 1])
                if not np.isnan(corr):
                    correlations.append(corr)

    return float(np.mean(correlations)) if correlations else 0.0


def _spectral_rolloff(spectrum: np.ndarray, threshold: float = 0.85) -> float:
    """Frequency at which cumulative spectral energy reaches threshold.

    Real images: energy falls off gradually (high rolloff frequency).
    AI images: energy concentrated in lower frequencies (low rolloff).
    """
    h, w = spectrum.shape
    cy, cx = h // 2, w // 2
    max_r = min(cy, cx)

    R = np.sqrt((np.arange(w) - cx) ** 2 + (np.arange(h)[:, None] - cy) ** 2).astype(int)

    radial_energy = np.zeros(max_r + 1)
    for r in range(max_r + 1):
        mask = R == r
        if mask.any():
            radial_energy[r] = np.sum(spectrum[mask] ** 2)

    total = radial_energy.sum()
    if total <= 0:
        return 0.0

    cumulative = np.cumsum(radial_energy)
    rolloff_idx = np.searchsorted(cumulative, threshold * total)
    return float(rolloff_idx / max_r)  # Normalised 0-1


def analyze(image_path: str) -> LayerResult:
    """Detect GAN spectral fingerprints in the frequency domain."""
    flags: list[str] = []
    details: dict[str, Any] = {}

    try:
        img = cv2.imread(image_path, cv2.IMREAD_COLOR)
        if img is None:
            return LayerResult(
                layer=LayerName.GAN_FINGERPRINT, score=0.5, confidence=0.0,
                flags=["Could not open image"], error="cv2.imread returned None",
            )

        # Resize to fixed square for consistent FFT analysis
        img = cv2.resize(img, (ANALYSIS_SIZE, ANALYSIS_SIZE), interpolation=cv2.INTER_AREA)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        spectrum = _compute_magnitude_spectrum(gray)

        # ── 1. Periodic peak detection ─────────────────
        peaks = _detect_periodic_peaks(spectrum)
        details.update({f"peak_{k}": v for k, v in peaks.items()})

        # ── 2. Azimuthal asymmetry ─────────────────────
        azimuth = _azimuthal_asymmetry(spectrum)
        details["azimuthal_asymmetry"] = round(azimuth, 4)

        # ── 3. Cross-channel spectral correlation ──────
        cc_corr = _cross_channel_spectral_correlation(img)
        details["cross_channel_corr"] = round(cc_corr, 4)

        # ── 4. Spectral rolloff ────────────────────────
        rolloff = _spectral_rolloff(spectrum)
        details["spectral_rolloff"] = round(rolloff, 4)

        # ── Scoring ────────────────────────────────────
        score = 0.0

        # Periodic peaks: GAN signature (ConvTranspose2d checkerboard)
        if peaks["peak_count"] > 20:
            score += 0.25
            flags.append(f"Many spectral peaks detected ({peaks['peak_count']}) — GAN upsampling artifacts")
        elif peaks["peak_count"] > 8:
            score += 0.10
            flags.append(f"Moderate spectral peaks ({peaks['peak_count']})")

        # Grid pattern in peaks: strong GAN indicator
        if peaks["grid_score"] > 0.3:
            score += 0.20
            flags.append(f"Periodic grid pattern in spectrum (grid={peaks['grid_score']:.3f}) — GAN stride artifact")
        elif peaks["grid_score"] > 0.1:
            score += 0.05

        # Periodicity in autocorrelation
        if peaks["periodicity"] > 0.3:
            score += 0.15
            flags.append(f"Strong spectral periodicity ({peaks['periodicity']:.3f}) — upsampling pattern")

        # Azimuthal asymmetry: GAN > 0.3, natural < 0.2
        if azimuth > 0.4:
            score += 0.15
            flags.append(f"Directional spectral bias (asymmetry={azimuth:.3f}) — non-isotropic generation")
        elif azimuth > 0.25:
            score += 0.05
        elif azimuth < 0.15:
            score -= 0.05
            flags.append(f"Isotropic spectrum (asymmetry={azimuth:.3f}) — natural image")

        # Cross-channel correlation: GAN > 0.98, natural 0.85-0.95
        if cc_corr > 0.985:
            score += 0.15
            flags.append(f"Very high cross-channel spectral correlation ({cc_corr:.4f}) — shared generator")
        elif cc_corr < 0.90:
            score -= 0.05
            flags.append(f"Independent channel spectra ({cc_corr:.3f}) — natural image")

        # Spectral rolloff: AI < 0.3, natural > 0.4
        if rolloff < 0.25:
            score += 0.10
            flags.append(f"Low spectral rolloff ({rolloff:.3f}) — energy concentrated in low frequencies")
        elif rolloff > 0.45:
            score -= 0.05
            flags.append(f"High spectral rolloff ({rolloff:.3f}) — rich frequency content")

        score = round(max(0.0, min(1.0, score)), 4)
        confidence = 0.65

        return LayerResult(
            layer=LayerName.GAN_FINGERPRINT,
            score=score,
            confidence=confidence,
            flags=flags,
            details=details,
        )

    except Exception as e:
        logger.exception("GAN fingerprint analysis failed")
        return LayerResult(
            layer=LayerName.GAN_FINGERPRINT, score=0.5, confidence=0.0,
            flags=["GAN fingerprint analysis failed"], error=str(e),
        )
