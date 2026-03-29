"""Layer 18 — Cross-Attention & Spatial Pattern Detection.

Text-to-image diffusion models (DALL-E 3, Midjourney, SD3, Flux) use
cross-attention between text embeddings and spatial feature maps.  This creates
subtle spatial correlation patterns that don't exist in real photographs:

  1. Patch self-similarity matrix anomalies (AI patches are more self-similar)
  2. Local correlation length (how far pixel correlations extend spatially)
  3. Repetitive micro-structure detection (attention grid imprints)
  4. Spatial frequency modulation patterns (attention masking artifacts)
  5. Patch-wise variance consistency (AI images show unnaturally consistent 
     local variance across the image)

These are not visible to humans but are measurable via autocorrelation, 
local similarity analysis, and spatial statistics.

Reference:
  Corvi, R. et al. (2023). "On the Detection of Synthetic Images Generated
  by Diffusion Models" — ICASSP.
"""

from __future__ import annotations

import logging
from typing import Any

import cv2
import numpy as np

from app.core.models import LayerName, LayerResult

logger = logging.getLogger(__name__)

ANALYSIS_SIZE = 256
PATCH_SIZE = 16      # Patch size for self-similarity analysis


def _patch_self_similarity(gray: np.ndarray, patch_size: int = PATCH_SIZE) -> dict[str, float]:
    """Compute self-similarity matrix of image patches and analyse it.

    AI images show higher inter-patch correlation because the generator processes
    all patches through the same attention layers simultaneously.
    Real photos have more independent patch content.
    """
    h, w = gray.shape
    patches = []
    for y in range(0, h - patch_size + 1, patch_size):
        for x in range(0, w - patch_size + 1, patch_size):
            patch = gray[y:y + patch_size, x:x + patch_size].ravel().astype(np.float64)
            # Normalise each patch
            norm = np.linalg.norm(patch)
            if norm > 0:
                patches.append(patch / norm)

    if len(patches) < 4:
        return {"mean_similarity": 0.0, "similarity_std": 0.0, "max_offdiag": 0.0}

    patches = np.array(patches)
    # Cosine similarity matrix (patches are already normalised)
    sim_matrix = patches @ patches.T

    # Extract off-diagonal elements
    n = len(sim_matrix)
    mask = ~np.eye(n, dtype=bool)
    off_diag = sim_matrix[mask]

    return {
        "mean_similarity": float(np.mean(off_diag)),
        "similarity_std": float(np.std(off_diag)),
        "max_offdiag": float(np.max(off_diag)),
        "p90_similarity": float(np.percentile(off_diag, 90)),
    }


def _spatial_correlation_length(gray: np.ndarray) -> float:
    """Estimate how far spatial correlations extend.

    Compute 2D autocorrelation and find the half-width at half-maximum (HWHM).
    AI images have longer correlation lengths (smoother, more globally coherent).
    Camera images have shorter correlations (local texture dominates).
    """
    img = gray.astype(np.float64) - gray.mean()
    # Use FFT for fast 2D autocorrelation
    f = np.fft.fft2(img)
    ac = np.real(np.fft.ifft2(f * np.conj(f)))
    ac = np.fft.fftshift(ac)

    # Normalise so center = 1.0
    cy, cx = ac.shape[0] // 2, ac.shape[1] // 2
    if ac[cy, cx] > 0:
        ac /= ac[cy, cx]

    # Compute radial average of autocorrelation
    max_r = min(cy, cx)
    Y, X = np.ogrid[:ac.shape[0], :ac.shape[1]]
    R = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2).astype(int)

    radial_ac = np.zeros(max_r + 1)
    for r in range(max_r + 1):
        mask = R == r
        if mask.any():
            radial_ac[r] = np.mean(ac[mask])

    # Find HWHM (where autocorrelation drops to 0.5)
    half_max_idx = np.searchsorted(-radial_ac, -0.5)  # Search in descending
    hwhm = float(half_max_idx / max_r)  # Normalised 0-1

    return hwhm


def _repetitive_microstructure(gray: np.ndarray) -> dict[str, float]:
    """Detect repetitive micro-patterns via local autocorrelation peaks.

    Attention grids and upsampling patterns create periodic micro-structures
    at specific spatial intervals (e.g., every 8, 16, or 32 pixels).
    """
    h, w = gray.shape
    img = gray.astype(np.float64)

    # Compute autocorrelation of central row and column
    center_row = img[h // 2, :]
    center_col = img[:, w // 2]

    periodic_scores = []
    for signal in [center_row, center_col]:
        signal = signal - signal.mean()
        ac = np.correlate(signal, signal, mode='full')
        ac = ac[len(ac) // 2:]
        if ac[0] > 0:
            ac /= ac[0]

        # Find peaks at specific intervals (8, 16, 32, 64 — common attention grid sizes)
        peak_values = []
        for period in [8, 16, 32, 64]:
            if period < len(ac):
                # Check a small window around the expected period
                window = ac[max(0, period - 2):min(len(ac), period + 3)]
                if len(window) > 0:
                    peak_values.append(float(np.max(window)))

        if peak_values:
            periodic_scores.append(max(peak_values))

    max_periodic = max(periodic_scores, default=0.0)
    avg_periodic = float(np.mean(periodic_scores)) if periodic_scores else 0.0

    return {
        "max_periodic_peak": round(max_periodic, 4),
        "avg_periodic_peak": round(avg_periodic, 4),
    }


def _local_variance_consistency(gray: np.ndarray, block_size: int = 16) -> dict[str, float]:
    """Analyse consistency of local variance across image blocks.

    AI images have unnaturally consistent local variance across different
    regions because the generator applies the same processing pipeline
    everywhere.  Real photos have highly variable local statistics
    (sky vs texture vs edges).
    """
    h, w = gray.shape
    img = gray.astype(np.float64)

    variances = []
    means = []
    for y in range(0, h - block_size + 1, block_size):
        for x in range(0, w - block_size + 1, block_size):
            block = img[y:y + block_size, x:x + block_size]
            variances.append(float(np.var(block)))
            means.append(float(np.mean(block)))

    if len(variances) < 4:
        return {"var_cv": 0.0, "var_iqr_ratio": 0.0, "mean_var_corr": 0.0}

    variances = np.array(variances)
    means = np.array(means)

    # Coefficient of variation of local variances
    # Low CV = uniform variance = AI, High CV = natural variation
    var_cv = float(np.std(variances) / max(np.mean(variances), 1e-10))

    # IQR ratio (robust measure of spread)
    q25, q75 = np.percentile(variances, [25, 75])
    median_var = np.median(variances)
    iqr_ratio = float((q75 - q25) / max(median_var, 1e-10))

    # Correlation between local mean and local variance
    # In natural images: bright areas often have different variance than dark areas
    # In AI: more uniform handling
    if np.std(means) > 0 and np.std(variances) > 0:
        mv_corr = float(np.corrcoef(means, variances)[0, 1])
        if np.isnan(mv_corr):
            mv_corr = 0.0
    else:
        mv_corr = 0.0

    return {
        "var_cv": round(var_cv, 4),
        "var_iqr_ratio": round(iqr_ratio, 4),
        "mean_var_corr": round(mv_corr, 4),
    }


def _spatial_frequency_modulation(gray: np.ndarray) -> float:
    """Detect spatial frequency modulation patterns.

    Attention mechanisms can create visible modulation in local spatial
    frequency content.  Compute local frequency energy in sliding windows
    and measure how it varies spatially.
    """
    h, w = gray.shape

    # Compute local high-frequency energy using Laplacian
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    lap_energy = lap ** 2

    # Block-wise energy
    block = 16
    energies = []
    for y in range(0, h - block + 1, block):
        for x in range(0, w - block + 1, block):
            energies.append(float(np.mean(lap_energy[y:y + block, x:x + block])))

    if len(energies) < 4:
        return 0.0

    energies = np.array(energies)

    # Compute autocorrelation of energy pattern to detect modulation
    e_centered = energies - energies.mean()
    ac = np.correlate(e_centered, e_centered, mode='full')
    ac = ac[len(ac) // 2:]
    if ac[0] > 0:
        ac /= ac[0]

    # Check for periodic modulation in energy
    if len(ac) > 5:
        # Look for secondary peak indicating periodic attention grid
        secondary = np.max(ac[2:min(len(ac), 20)])
        return float(secondary)

    return 0.0


def analyze(image_path: str) -> LayerResult:
    """Detect cross-attention and spatial pattern artifacts from diffusion models."""
    flags: list[str] = []
    details: dict[str, Any] = {}

    try:
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return LayerResult(
                layer=LayerName.ATTENTION_PATTERN, score=0.5, confidence=0.0,
                flags=["Could not open image"], error="cv2.imread returned None",
            )

        # Also load colour for cross-channel analysis
        img_color = cv2.imread(image_path, cv2.IMREAD_COLOR)

        # Resize to analysis size
        gray = cv2.resize(img, (ANALYSIS_SIZE, ANALYSIS_SIZE), interpolation=cv2.INTER_AREA)
        if img_color is not None:
            img_color = cv2.resize(img_color, (ANALYSIS_SIZE, ANALYSIS_SIZE), interpolation=cv2.INTER_AREA)

        # ── 1. Patch self-similarity ───────────────────
        sim = _patch_self_similarity(gray)
        details.update({f"patch_{k}": round(v, 4) for k, v in sim.items()})

        # ── 2. Spatial correlation length ──────────────
        corr_length = _spatial_correlation_length(gray)
        details["correlation_length"] = round(corr_length, 4)

        # ── 3. Repetitive microstructure ───────────────
        micro = _repetitive_microstructure(gray)
        details.update(micro)

        # ── 4. Local variance consistency ──────────────
        var_stats = _local_variance_consistency(gray)
        details.update(var_stats)

        # ── 5. Spatial frequency modulation ────────────
        sfm = _spatial_frequency_modulation(gray)
        details["freq_modulation"] = round(sfm, 4)

        # ── Scoring ────────────────────────────────────
        score = 0.0

        # Patch self-similarity: AI > 0.4, natural < 0.3
        mean_sim = sim["mean_similarity"]
        if mean_sim > 0.5:
            score += 0.20
            flags.append(f"High patch self-similarity ({mean_sim:.3f}) — uniform generation")
        elif mean_sim > 0.35:
            score += 0.10
            flags.append(f"Elevated patch similarity ({mean_sim:.3f})")
        elif mean_sim < 0.2:
            score -= 0.05
            flags.append(f"Low patch similarity ({mean_sim:.3f}) — diverse content (natural)")

        # Correlation length: AI > 0.15, natural < 0.10
        if corr_length > 0.20:
            score += 0.20
            flags.append(f"Long spatial correlation ({corr_length:.3f}) — global coherence (AI)")
        elif corr_length > 0.12:
            score += 0.10
            flags.append(f"Moderate correlation length ({corr_length:.3f})")
        elif corr_length < 0.08:
            score -= 0.05
            flags.append(f"Short correlation length ({corr_length:.3f}) — local texture dominates")

        # Repetitive microstructure: attention grid
        if micro["max_periodic_peak"] > 0.3:
            score += 0.20
            flags.append(f"Periodic microstructure detected (peak={micro['max_periodic_peak']:.3f}) — attention grid")
        elif micro["max_periodic_peak"] > 0.15:
            score += 0.05

        # Local variance consistency: AI has low CV, natural has high CV
        if var_stats["var_cv"] < 0.5:
            score += 0.15
            flags.append(f"Very consistent local variance (CV={var_stats['var_cv']:.3f}) — AI uniformity")
        elif var_stats["var_cv"] < 1.0:
            score += 0.05
        elif var_stats["var_cv"] > 2.0:
            score -= 0.05
            flags.append(f"Highly variable local variance (CV={var_stats['var_cv']:.3f}) — natural complexity")

        # Spatial frequency modulation
        if sfm > 0.4:
            score += 0.15
            flags.append(f"Spatial frequency modulation ({sfm:.3f}) — attention masking artifact")
        elif sfm > 0.2:
            score += 0.05

        score = round(max(0.0, min(1.0, score)), 4)
        confidence = 0.60

        return LayerResult(
            layer=LayerName.ATTENTION_PATTERN,
            score=score,
            confidence=confidence,
            flags=flags,
            details=details,
        )

    except Exception as e:
        logger.exception("Attention pattern analysis failed")
        return LayerResult(
            layer=LayerName.ATTENTION_PATTERN, score=0.5, confidence=0.0,
            flags=["Attention pattern analysis failed"], error=str(e),
        )
