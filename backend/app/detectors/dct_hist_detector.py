"""Layer 16 — DCT Coefficient Histogram Analysis (Double-JPEG Forensics).

When an image undergoes double JPEG compression (save → edit → re-save), the
DCT coefficient histograms develop a characteristic "comb" pattern caused by
the interaction of two different quantisation tables.  AI-generated images
show different DCT coefficient distributions than camera-original JPEGs:

  1. First-digit distribution follows Benford's Law in natural images but not in AI
  2. Double quantisation "comb" pattern in coefficient histograms
  3. Block artifact grid (BAG) misalignment (shift from 8×8 origin)
  4. Quantisation table analysis (standard vs non-standard tables)
  5. AC/DC coefficient ratio anomalies

Reference:
  Bianchi, T. & Piva, A. (2012). "Image Forgery Localization via Block-Grained
  Analysis of JPEG Artifacts" — IEEE TIFS.
  Fu, D. et al. (2007). "JPEG Double Compression Detection" — ICM.
"""

from __future__ import annotations

import io
import logging
import struct
from typing import Any

import cv2
import numpy as np
from scipy.fftpack import dctn

from app.core.models import LayerName, LayerResult

logger = logging.getLogger(__name__)

ANALYSIS_SIZE = 512
BENFORD_EXPECTED = np.array([
    np.log10(1 + 1 / d) for d in range(1, 10)
])  # Benford's Law first-digit probabilities


def _extract_dct_coefficients(gray: np.ndarray) -> np.ndarray:
    """Compute 8×8 block DCT coefficients (mimics JPEG encoding)."""
    h, w = gray.shape
    # Crop to multiple of 8
    h8, w8 = (h // 8) * 8, (w // 8) * 8
    gray = gray[:h8, :w8].astype(np.float64)

    coeffs = []
    for y in range(0, h8, 8):
        for x in range(0, w8, 8):
            block = gray[y:y + 8, x:x + 8]
            dct_block = dctn(block, type=2, norm='ortho')
            coeffs.append(dct_block.ravel())
    return np.array(coeffs)  # shape (num_blocks, 64)


def _benford_law_test(coefficients: np.ndarray) -> float:
    """Test if AC coefficient first digits follow Benford's Law.

    Natural images' DCT coefficients follow Benford's Law.
    Manipulated/AI images deviate.  Returns chi-squared statistic.
    """
    # Take absolute values of non-zero AC coefficients
    ac = coefficients[:, 1:]  # skip DC (index 0)
    flat = np.abs(ac.ravel())
    flat = flat[flat >= 1.0]  # Only consider values ≥ 1

    if len(flat) < 100:
        return 0.0

    # Extract first digit
    first_digits = np.floor(flat / 10 ** np.floor(np.log10(flat))).astype(int)
    first_digits = first_digits[(first_digits >= 1) & (first_digits <= 9)]

    if len(first_digits) < 100:
        return 0.0

    observed = np.array([np.sum(first_digits == d) for d in range(1, 10)], dtype=np.float64)
    observed /= observed.sum()

    # Chi-squared distance from Benford distribution
    chi2 = np.sum((observed - BENFORD_EXPECTED) ** 2 / BENFORD_EXPECTED)
    return float(chi2)


def _double_compression_comb(coefficients: np.ndarray) -> float:
    """Detect periodic "comb" patterns in DCT coefficient histograms.

    Double JPEG compression creates periodic gaps/peaks in coefficient
    histograms.  Measures the autocorrelation periodicity.
    """
    # Use a representative AC coefficient (position 1 = DC, use 2-10)
    scores = []
    for coeff_idx in [1, 2, 3, 8, 9, 10]:
        vals = coefficients[:, coeff_idx]
        hist_range = 50
        hist, _ = np.histogram(vals, bins=2 * hist_range + 1,
                               range=(-hist_range - 0.5, hist_range + 0.5))
        hist = hist.astype(np.float64)
        if hist.sum() < 100:
            continue

        hist /= hist.sum()

        # Compute autocorrelation — look for periodicity (peaks at multiples of Q)
        ac = np.correlate(hist - hist.mean(), hist - hist.mean(), mode='full')
        ac = ac[len(ac) // 2:]  # Take positive lags
        if ac[0] > 0:
            ac = ac / ac[0]  # Normalise

        # Check for secondary peak (indicates double quantisation)
        # Look at lags 2-15 (quantisation step sizes)
        if len(ac) > 15:
            secondary_peak = np.max(ac[2:15])
            scores.append(float(secondary_peak))

    return float(np.mean(scores)) if scores else 0.0


def _block_artifact_grid_analysis(gray: np.ndarray) -> dict[str, float]:
    """Detect 8×8 block artifact grid (BAG) and check alignment.

    Camera-original JPEGs have BAG aligned at (0,0).
    Manipulated images may have shifted BAG or missing block artifacts.
    """
    h, w = gray.shape

    # Compute horizontal and vertical pixel differences
    h_diff = np.abs(np.diff(gray.astype(np.float64), axis=1))
    v_diff = np.abs(np.diff(gray.astype(np.float64), axis=0))

    # Average difference at each column/row modulo 8
    h_periodic = np.zeros(8)
    for offset in range(8):
        cols = np.arange(offset, w - 1, 8)
        if len(cols) > 0:
            h_periodic[offset] = np.mean(h_diff[:, cols])

    v_periodic = np.zeros(8)
    for offset in range(8):
        rows = np.arange(offset, h - 1, 8)
        if len(rows) > 0:
            v_periodic[offset] = np.mean(v_diff[rows, :])

    # BAG strength: ratio of max periodic difference to mean
    h_bag_strength = float(np.max(h_periodic) / np.mean(h_periodic)) if np.mean(h_periodic) > 0 else 1.0
    v_bag_strength = float(np.max(v_periodic) / np.mean(v_periodic)) if np.mean(v_periodic) > 0 else 1.0

    # Grid alignment: peak should be at offset 7 (boundary between blocks)
    h_peak_offset = int(np.argmax(h_periodic))
    v_peak_offset = int(np.argmax(v_periodic))

    # Misalignment from standard (0,0) origin — indicates crop/manipulation
    is_aligned = (h_peak_offset == 7 and v_peak_offset == 7) or \
                 (h_peak_offset == 0 and v_peak_offset == 0)

    return {
        "h_bag_strength": round(h_bag_strength, 4),
        "v_bag_strength": round(v_bag_strength, 4),
        "h_peak_offset": h_peak_offset,
        "v_peak_offset": v_peak_offset,
        "grid_aligned": is_aligned,
        "avg_bag_strength": round((h_bag_strength + v_bag_strength) / 2, 4),
    }


def _quantisation_table_analysis(image_path: str) -> dict[str, Any]:
    """Attempt to extract JPEG quantisation tables from file header.

    Standard tables (e.g., IJG/libjpeg) indicate basic tool processing.
    Camera-specific tables indicate genuine camera output.
    """
    result = {"has_qtable": False, "tables_found": 0, "is_standard": False}
    try:
        with open(image_path, "rb") as f:
            data = f.read(65536)  # Read first 64KB of header

        # Look for DQT marker (0xFF, 0xDB) in JPEG
        pos = 0
        tables = []
        while pos < len(data) - 2:
            if data[pos] == 0xFF and data[pos + 1] == 0xDB:
                # Found DQT marker
                if pos + 4 < len(data):
                    length = struct.unpack(">H", data[pos + 2:pos + 4])[0]
                    if pos + 2 + length <= len(data):
                        table_data = data[pos + 4:pos + 2 + length]
                        tables.append(table_data)
                pos += 4
            else:
                pos += 1

        result["has_qtable"] = len(tables) > 0
        result["tables_found"] = len(tables)

        # Check if first table matches standard JPEG quality tables
        # Standard IJG luminance table at quality 75
        standard_luma_75 = bytes([
            8, 6, 6, 7, 6, 5, 8, 7, 7, 7, 9, 9, 8, 10, 12, 20,
            13, 12, 11, 11, 12, 25, 18, 19, 15, 20, 29, 26, 31, 30, 29,
            26, 28, 28, 32, 36, 46, 39, 32, 34, 44, 35, 28, 28, 40, 55,
            41, 44, 48, 49, 52, 52, 52, 31, 39, 57, 61, 56, 50, 60, 46,
            51, 52, 50,
        ])
        if tables and len(tables[0]) >= 64:
            # Skip precision/id byte
            actual = tables[0][1:65] if len(tables[0]) >= 65 else tables[0][:64]
            if actual == standard_luma_75:
                result["is_standard"] = True

    except Exception:
        pass
    return result


def _dc_ac_ratio_analysis(coefficients: np.ndarray) -> dict[str, float]:
    """Analyse ratio of DC to AC energy across blocks.

    Natural images have consistent DC/AC ratio patterns.
    AI images may have anomalous ratios (e.g., too-uniform DC component).
    """
    dc = coefficients[:, 0]
    ac_energy = np.sum(coefficients[:, 1:] ** 2, axis=1)

    dc_variance = float(np.var(dc))
    ac_mean_energy = float(np.mean(ac_energy))
    dc_ac_ratio = dc_variance / max(ac_mean_energy, 1e-10)

    # Coefficient of variation of AC energy across blocks
    ac_cv = float(np.std(ac_energy) / max(np.mean(ac_energy), 1e-10))

    return {
        "dc_variance": round(dc_variance, 2),
        "ac_mean_energy": round(ac_mean_energy, 2),
        "dc_ac_ratio": round(dc_ac_ratio, 4),
        "ac_energy_cv": round(ac_cv, 4),
    }


def analyze(image_path: str) -> LayerResult:
    """Analyse DCT coefficient histograms for forgery/AI signatures."""
    flags: list[str] = []
    details: dict[str, Any] = {}

    try:
        img = cv2.imread(image_path, cv2.IMREAD_COLOR)
        if img is None:
            return LayerResult(
                layer=LayerName.DCT_HIST, score=0.5, confidence=0.0,
                flags=["Could not open image"], error="cv2.imread returned None",
            )

        h, w = img.shape[:2]
        if max(h, w) > ANALYSIS_SIZE:
            scale = ANALYSIS_SIZE / max(h, w)
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # ── 1. Extract DCT coefficients ────────────────
        coefficients = _extract_dct_coefficients(gray)
        details["num_blocks"] = len(coefficients)

        # ── 2. Benford's Law test ──────────────────────
        benford_chi2 = _benford_law_test(coefficients)
        details["benford_chi2"] = round(benford_chi2, 4)

        # ── 3. Double compression comb detection ───────
        comb_score = _double_compression_comb(coefficients)
        details["double_compress_comb"] = round(comb_score, 4)

        # ── 4. Block artifact grid analysis ────────────
        bag = _block_artifact_grid_analysis(gray.astype(np.float64))
        details.update(bag)

        # ── 5. Quantisation table analysis ─────────────
        qtable = _quantisation_table_analysis(image_path)
        details.update(qtable)

        # ── 6. DC/AC ratio analysis ────────────────────
        dc_ac = _dc_ac_ratio_analysis(coefficients)
        details.update(dc_ac)

        # ── Scoring ────────────────────────────────────
        score = 0.0

        # Benford's Law: low chi2 = good fit (natural), high chi2 = deviation (AI/edited)
        if benford_chi2 > 0.1:
            score += 0.20
            flags.append(f"DCT coefficients deviate from Benford's Law (χ²={benford_chi2:.4f})")
        elif benford_chi2 > 0.05:
            score += 0.10
            flags.append(f"Moderate Benford deviation (χ²={benford_chi2:.4f})")
        else:
            score -= 0.05
            flags.append(f"DCT first digits follow Benford's Law — natural image")

        # Double compression: high comb score = double JPEG
        if comb_score > 0.5:
            score += 0.25
            flags.append(f"Strong double-JPEG comb pattern ({comb_score:.3f})")
        elif comb_score > 0.3:
            score += 0.10
            flags.append(f"Possible double compression ({comb_score:.3f})")

        # BAG analysis: very low = no JPEG artifacts = AI (never compressed)
        #               misaligned = cropped/edited
        avg_bag = bag["avg_bag_strength"]
        if avg_bag < 1.05:
            score += 0.15
            flags.append(f"No block artifact grid detected (BAG={avg_bag:.3f}) — non-JPEG origin")
        elif not bag["grid_aligned"]:
            score += 0.10
            flags.append(f"BAG grid misaligned (offsets: h={bag['h_peak_offset']}, v={bag['v_peak_offset']})")

        # AC energy coefficient of variation: very uniform = synthetic
        if dc_ac["ac_energy_cv"] < 0.5:
            score += 0.15
            flags.append(f"Uniform AC energy across blocks (CV={dc_ac['ac_energy_cv']:.3f}) — synthetic")
        elif dc_ac["ac_energy_cv"] > 2.0:
            score -= 0.05
            flags.append(f"Varied AC energy (CV={dc_ac['ac_energy_cv']:.3f}) — natural complexity")

        # Standard quantisation table = processed by standard tool (not camera)
        if qtable.get("has_qtable") and qtable.get("is_standard"):
            score += 0.05
            flags.append("Standard JPEG quantisation table — tool-processed (not camera-native)")

        score = round(max(0.0, min(1.0, score)), 4)
        confidence = 0.60

        return LayerResult(
            layer=LayerName.DCT_HIST,
            score=score,
            confidence=confidence,
            flags=flags,
            details=details,
        )

    except Exception as e:
        logger.exception("DCT histogram analysis failed")
        return LayerResult(
            layer=LayerName.DCT_HIST, score=0.5, confidence=0.0,
            flags=["DCT histogram analysis failed"], error=str(e),
        )
