"""Layer 15 — Least Significant Bit (LSB) Forensics.

Real camera photos have LSBs dominated by random sensor ADC noise, producing
near-uniform 0/1 distributions with no spatial structure.  AI generators
produce pixel values through floating-point computation then quantise to 8-bit,
creating subtle statistical biases:

  1. Non-uniform LSB histogram (chi-squared deviation from uniform)
  2. Spatial correlation between adjacent LSBs (should be zero for cameras)
  3. Bit-plane entropy loss in lower bits (AI quantisation artifacts)
  4. Even/odd pixel value bias (generator-specific quantisation patterns)
  5. Multi-bit-plane structural analysis (bit 0-2 correlation)

This is a pure mathematical/statistical detector — no ML model required.

Reference: Fridrich, J. et al. (2003). "Steganalysis of LSB Embedding in
Color Images" — adapted for AI generation detection.
"""

from __future__ import annotations

import logging
from typing import Any

import cv2
import numpy as np
from scipy import stats as sp_stats

from app.core.models import LayerName, LayerResult

logger = logging.getLogger(__name__)

ANALYSIS_SIZE = 512


def _chi_squared_lsb(channel: np.ndarray) -> float:
    """Chi-squared test of LSB against uniform distribution.

    For true random LSBs (camera ADC noise), the distribution of 0s and 1s
    should be very close to 50/50.  AI generators often show bias.

    Returns the chi-squared p-value (low = suspicious deviation from uniform).
    """
    lsb = channel.ravel() & 1
    n_zeros = np.sum(lsb == 0)
    n_ones = np.sum(lsb == 1)
    n = len(lsb)
    expected = n / 2
    chi2_stat = (n_zeros - expected) ** 2 / expected + (n_ones - expected) ** 2 / expected
    # 1 degree of freedom
    p_value = float(sp_stats.chi2.sf(chi2_stat, df=1))
    return p_value


def _lsb_spatial_correlation(channel: np.ndarray) -> float:
    """Measure spatial autocorrelation of the LSB plane.

    Real camera LSB planes have near-zero autocorrelation (random noise).
    AI images have structured LSB planes with positive autocorrelation.
    """
    lsb = (channel & 1).astype(np.float64)
    # Horizontal and vertical neighbour correlation
    h_corr = np.corrcoef(lsb[:, :-1].ravel(), lsb[:, 1:].ravel())[0, 1]
    v_corr = np.corrcoef(lsb[:-1, :].ravel(), lsb[1:, :].ravel())[0, 1]
    if np.isnan(h_corr):
        h_corr = 0.0
    if np.isnan(v_corr):
        v_corr = 0.0
    return float((abs(h_corr) + abs(v_corr)) / 2.0)


def _bit_plane_entropy(channel: np.ndarray, bit: int) -> float:
    """Shannon entropy of a single bit plane (0 = LSB, 7 = MSB).

    Maximum entropy = 1.0 bit (perfect 50/50 distribution).
    Lower bits in real photos have entropy ≈ 1.0.
    AI images show entropy drop in lower bit planes.
    """
    plane = (channel >> bit) & 1
    p1 = np.mean(plane)
    p0 = 1.0 - p1
    if p0 <= 0 or p1 <= 0:
        return 0.0
    return float(-(p0 * np.log2(p0) + p1 * np.log2(p1)))


def _even_odd_pair_analysis(channel: np.ndarray) -> float:
    """Analyse histogram pairs of adjacent values (2k, 2k+1).

    In natural images, the counts of adjacent pairs (e.g., 100 vs 101)
    are similar.  AI generators can create systematic imbalances.
    Returns the average absolute difference ratio of paired bins.
    """
    hist, _ = np.histogram(channel.ravel(), bins=256, range=(0, 256))
    pairs = hist.reshape(128, 2)
    sums = pairs.sum(axis=1)
    # Avoid division by zero for empty bins
    mask = sums > 10
    if mask.sum() < 10:
        return 0.0
    diffs = np.abs(pairs[mask, 0] - pairs[mask, 1])
    ratios = diffs / sums[mask]
    return float(np.mean(ratios))


def _multi_plane_correlation(channel: np.ndarray) -> float:
    """Correlation between bit planes 0, 1, and 2.

    In camera images, lower bit planes are essentially independent random bits.
    In AI images, the quantisation process can introduce inter-plane correlation.
    """
    b0 = ((channel >> 0) & 1).ravel().astype(np.float64)
    b1 = ((channel >> 1) & 1).ravel().astype(np.float64)
    b2 = ((channel >> 2) & 1).ravel().astype(np.float64)

    c01 = abs(float(np.corrcoef(b0, b1)[0, 1])) if not np.all(b0 == b0[0]) else 0.0
    c02 = abs(float(np.corrcoef(b0, b2)[0, 1])) if not np.all(b0 == b0[0]) else 0.0
    c12 = abs(float(np.corrcoef(b1, b2)[0, 1])) if not np.all(b1 == b1[0]) else 0.0

    for v in [c01, c02, c12]:
        if np.isnan(v):
            v = 0.0

    return float((c01 + c02 + c12) / 3.0)


def analyze(image_path: str) -> LayerResult:
    """Run LSB forensic analysis on an image."""
    flags: list[str] = []
    details: dict[str, Any] = {}

    try:
        img = cv2.imread(image_path, cv2.IMREAD_COLOR)
        if img is None:
            return LayerResult(
                layer=LayerName.LSB, score=0.5, confidence=0.0,
                flags=["Could not open image"], error="cv2.imread returned None",
            )

        h, w = img.shape[:2]
        if max(h, w) > ANALYSIS_SIZE:
            scale = ANALYSIS_SIZE / max(h, w)
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

        # Work on all 3 channels (BGR)
        channels = cv2.split(img)
        channel_names = ["B", "G", "R"]

        # ── Per-channel analysis ───────────────────────
        chi2_pvalues = []
        spatial_corrs = []
        bp_entropies_0 = []
        bp_entropies_1 = []
        pair_diffs = []
        multi_corrs = []

        for ch, name in zip(channels, channel_names):
            # 1. Chi-squared LSB uniformity test
            pval = _chi_squared_lsb(ch)
            chi2_pvalues.append(pval)

            # 2. LSB spatial autocorrelation
            sp_corr = _lsb_spatial_correlation(ch)
            spatial_corrs.append(sp_corr)

            # 3. Bit plane entropy (bit 0 and bit 1)
            ent0 = _bit_plane_entropy(ch, 0)
            ent1 = _bit_plane_entropy(ch, 1)
            bp_entropies_0.append(ent0)
            bp_entropies_1.append(ent1)

            # 4. Even/odd pair histogram analysis
            pd = _even_odd_pair_analysis(ch)
            pair_diffs.append(pd)

            # 5. Multi-plane correlation
            mc = _multi_plane_correlation(ch)
            multi_corrs.append(mc)

        avg_chi2_p = float(np.mean(chi2_pvalues))
        avg_spatial_corr = float(np.mean(spatial_corrs))
        avg_entropy_b0 = float(np.mean(bp_entropies_0))
        avg_entropy_b1 = float(np.mean(bp_entropies_1))
        avg_pair_diff = float(np.mean(pair_diffs))
        avg_multi_corr = float(np.mean(multi_corrs))

        details["avg_chi2_pvalue"] = round(avg_chi2_p, 6)
        details["avg_lsb_spatial_corr"] = round(avg_spatial_corr, 6)
        details["avg_bit0_entropy"] = round(avg_entropy_b0, 6)
        details["avg_bit1_entropy"] = round(avg_entropy_b1, 6)
        details["avg_pair_imbalance"] = round(avg_pair_diff, 6)
        details["avg_multi_plane_corr"] = round(avg_multi_corr, 6)

        # ── Scoring ────────────────────────────────────
        score = 0.0

        # Chi-squared: low p-value = LSBs deviate from uniform = AI signature
        if avg_chi2_p < 0.001:
            score += 0.20
            flags.append(f"LSB distribution deviates from uniform (p={avg_chi2_p:.4e})")
        elif avg_chi2_p < 0.05:
            score += 0.10
            flags.append(f"Marginal LSB uniformity deviation (p={avg_chi2_p:.4f})")
        else:
            score -= 0.05
            flags.append(f"LSB distribution is uniform — consistent with camera noise")

        # Spatial correlation: camera ≈ 0.00-0.02, AI > 0.05
        if avg_spatial_corr > 0.10:
            score += 0.25
            flags.append(f"High LSB spatial correlation ({avg_spatial_corr:.4f}) — structured (AI)")
        elif avg_spatial_corr > 0.05:
            score += 0.10
            flags.append(f"Moderate LSB spatial correlation ({avg_spatial_corr:.4f})")
        elif avg_spatial_corr < 0.02:
            score -= 0.05
            flags.append(f"Random LSB spatial structure ({avg_spatial_corr:.4f}) — camera-like")

        # Bit-plane entropy: camera ≈ 0.99-1.00, AI < 0.97
        if avg_entropy_b0 < 0.95:
            score += 0.15
            flags.append(f"Low bit-0 entropy ({avg_entropy_b0:.4f}) — quantisation artifact")
        elif avg_entropy_b0 < 0.98:
            score += 0.05

        # Even/odd pair imbalance: camera < 0.01, AI > 0.02
        if avg_pair_diff > 0.03:
            score += 0.15
            flags.append(f"Histogram pair imbalance ({avg_pair_diff:.4f}) — generation artifact")
        elif avg_pair_diff > 0.015:
            score += 0.05

        # Multi-plane correlation: camera ≈ 0.00-0.01, AI > 0.03
        if avg_multi_corr > 0.05:
            score += 0.15
            flags.append(f"Inter-plane correlation ({avg_multi_corr:.4f}) — quantisation coupling")
        elif avg_multi_corr > 0.02:
            score += 0.05

        score = round(max(0.0, min(1.0, score)), 4)
        confidence = 0.60  # Statistical analysis — reliable but not definitive

        return LayerResult(
            layer=LayerName.LSB,
            score=score,
            confidence=confidence,
            flags=flags,
            details=details,
        )

    except Exception as e:
        logger.exception("LSB analysis failed")
        return LayerResult(
            layer=LayerName.LSB, score=0.5, confidence=0.0,
            flags=["LSB analysis failed"], error=str(e),
        )
