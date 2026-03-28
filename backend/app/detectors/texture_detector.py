"""Layer 19 — Texture Analysis (LBP + Gabor Filter Bank).

AI generators struggle with specific texture types — hair strands merge
unnaturally, fabric weave breaks, skin pores are randomly placed, and
text characters have inconsistent stroke widths.  This detector uses:

  1. Local Binary Patterns (LBP) — captures micro-texture structure
  2. Gabor filter bank — multi-scale, multi-orientation texture analysis
  3. LBP histogram uniformity — AI textures are less diverse
  4. Gabor energy distribution — AI lacks natural texture complexity
  5. Co-occurrence texture features (GLCM-like) — inter-pixel relationships
  6. Texture regularity index — AI textures are artificially regular

Reference:
  Ojala, T. et al. (2002). "Multiresolution Gray-Scale and Rotation Invariant
  Texture Classification with Local Binary Patterns" — IEEE TPAMI.
  Liu, Z. et al. (2020). "Global Texture Enhancement for Fake Face Detection
  in the Wild" — CVPR.
"""

from __future__ import annotations

import logging
from typing import Any

import cv2
import numpy as np

from app.core.models import LayerName, LayerResult

logger = logging.getLogger(__name__)

ANALYSIS_SIZE = 256


def _compute_lbp(gray: np.ndarray, radius: int = 1, neighbors: int = 8) -> np.ndarray:
    """Compute rotation-invariant Local Binary Pattern.

    For each pixel, compare it to `neighbors` equally spaced points on a
    circle of `radius`.  The binary comparison pattern encodes local texture.
    """
    h, w = gray.shape
    lbp = np.zeros((h, w), dtype=np.uint8)

    for n in range(neighbors):
        # Compute offset for this neighbour
        angle = 2 * np.pi * n / neighbors
        dy = -radius * np.cos(angle)
        dx = radius * np.sin(angle)

        # Bilinear interpolation coordinates
        y1, x1 = int(np.floor(dy)), int(np.floor(dx))
        y2, x2 = y1 + 1, x1 + 1
        fy, fx = dy - y1, dx - x1

        # Boundary-safe slicing
        cy1 = max(0, -y1)
        cy2 = min(h, h - y2)
        cx1 = max(0, -x1)
        cx2 = min(w, w - x2)

        if cy1 >= cy2 or cx1 >= cx2:
            continue

        # Bilinear interpolated neighbour value
        center = gray[cy1:cy2, cx1:cx2].astype(np.float64)
        val = np.zeros_like(center)

        for oy, wy in [(y1, 1 - fy), (y2, fy)]:
            for ox, wx in [(x1, 1 - fx), (x2, fx)]:
                sy = max(0, cy1 + oy)
                ey = min(h, cy2 + oy)
                sx = max(0, cx1 + ox)
                ex = min(w, cx2 + ox)
                if sy < ey and sx < ex:
                    # Align shape
                    rh = min(ey - sy, cy2 - cy1)
                    rw = min(ex - sx, cx2 - cx1)
                    val[:rh, :rw] += wy * wx * gray[sy:sy + rh, sx:sx + rw].astype(np.float64)

        # Binary comparison: neighbour >= center → 1
        bits = (val >= center).astype(np.uint8)
        lbp[cy1:cy2, cx1:cx2] |= bits << n

    return lbp


def _lbp_histogram_analysis(lbp: np.ndarray) -> dict[str, float]:
    """Analyse LBP histogram for texture characteristics.

    Natural images have rich, diverse LBP histograms.
    AI images show concentrated LBP patterns (less texture diversity).
    """
    hist, _ = np.histogram(lbp.ravel(), bins=256, range=(0, 256))
    hist = hist.astype(np.float64)
    hist /= max(hist.sum(), 1)

    # Shannon entropy of LBP histogram (max = log2(256) = 8)
    nonzero = hist[hist > 0]
    entropy = float(-np.sum(nonzero * np.log2(nonzero)))

    # Number of "dominant" patterns (bins with >1% of mass)
    dominant = int(np.sum(hist > 0.01))

    # Uniformity: sum of squared probabilities (high = concentrated = AI)
    uniformity = float(np.sum(hist ** 2))

    # Ratio of "uniform" LBP patterns (patterns with ≤2 bit transitions)
    # These are the structurally meaningful patterns
    uniform_count = 0
    for val in range(256):
        byte_str = format(val, '08b')
        transitions = sum(1 for i in range(7) if byte_str[i] != byte_str[i + 1])
        # Also check wrap-around
        transitions += (1 if byte_str[0] != byte_str[7] else 0)
        if transitions <= 2:
            uniform_count += hist[val]
    uniform_ratio = float(uniform_count)

    return {
        "lbp_entropy": round(entropy, 4),
        "lbp_dominant_bins": dominant,
        "lbp_uniformity": round(uniformity, 6),
        "lbp_uniform_ratio": round(uniform_ratio, 4),
    }


def _gabor_filter_bank(gray: np.ndarray) -> dict[str, float]:
    """Apply Gabor filter bank at multiple scales and orientations.

    Returns energy distribution statistics across the filter bank.
    Natural images activate diverse Gabor responses.
    AI images show more uniform or missing responses at certain scales.
    """
    img = gray.astype(np.float64) / 255.0

    # Filter bank: 4 scales × 6 orientations = 24 filters
    scales = [3, 5, 7, 11]        # Kernel sizes
    freqs = [0.1, 0.2, 0.3, 0.4]  # Spatial frequencies
    orientations = np.arange(0, np.pi, np.pi / 6)  # 6 orientations

    energies = []
    for ksize, freq in zip(scales, freqs):
        for theta in orientations:
            kernel = cv2.getGaborKernel(
                (ksize, ksize), sigma=ksize / 3, theta=theta,
                lambd=1.0 / freq, gamma=0.5, psi=0,
            )
            response = cv2.filter2D(img, cv2.CV_64F, kernel)
            energy = float(np.mean(response ** 2))
            energies.append(energy)

    energies = np.array(energies)

    # Statistics of Gabor energy distribution
    mean_energy = float(np.mean(energies))
    std_energy = float(np.std(energies))
    cv_energy = std_energy / max(mean_energy, 1e-10)

    # Energy distribution across scales
    per_scale = []
    for i in range(4):
        scale_energies = energies[i * 6:(i + 1) * 6]
        per_scale.append(float(np.mean(scale_energies)))

    # Scale ratio: fine/coarse texture balance
    # Natural images: fine textures present (high ratio)
    # AI images: fine textures suppressed (low ratio)
    fine_coarse_ratio = per_scale[-1] / max(per_scale[0], 1e-10)

    # Orientation uniformity per scale (should be high for natural textures)
    orient_cvs = []
    for i in range(4):
        scale_energies = energies[i * 6:(i + 1) * 6]
        if np.mean(scale_energies) > 0:
            orient_cvs.append(float(np.std(scale_energies) / np.mean(scale_energies)))
    avg_orient_cv = float(np.mean(orient_cvs)) if orient_cvs else 0.0

    return {
        "gabor_mean_energy": round(mean_energy, 6),
        "gabor_energy_cv": round(cv_energy, 4),
        "gabor_fine_coarse_ratio": round(fine_coarse_ratio, 4),
        "gabor_orient_cv": round(avg_orient_cv, 4),
        "gabor_per_scale": [round(s, 6) for s in per_scale],
    }


def _cooccurrence_features(gray: np.ndarray) -> dict[str, float]:
    """Simplified GLCM-like co-occurrence texture features.

    Compute pixel pair statistics for adjacent pixels (horizontal).
    """
    # Quantise to 16 levels for tractable computation
    quantised = (gray.astype(np.float64) / 256.0 * 16).astype(int)
    quantised = np.clip(quantised, 0, 15)

    h, w = quantised.shape
    # Horizontal co-occurrence matrix
    glcm = np.zeros((16, 16), dtype=np.float64)
    for y in range(h):
        for x in range(w - 1):
            i, j = quantised[y, x], quantised[y, x + 1]
            glcm[i, j] += 1

    total = glcm.sum()
    if total > 0:
        glcm /= total

    # GLCM features
    # 1. Contrast: sum of (i-j)^2 * P(i,j) — measures local variation
    i_idx, j_idx = np.meshgrid(range(16), range(16), indexing='ij')
    contrast = float(np.sum((i_idx - j_idx) ** 2 * glcm))

    # 2. Homogeneity (IDM): sum of P(i,j) / (1 + |i-j|)
    homogeneity = float(np.sum(glcm / (1 + np.abs(i_idx - j_idx))))

    # 3. Energy (ASM): sum of P(i,j)^2 — measures texture regularity
    energy = float(np.sum(glcm ** 2))

    # 4. Entropy
    nonzero = glcm[glcm > 0]
    entropy = float(-np.sum(nonzero * np.log2(nonzero)))

    # 5. Correlation
    mu_i = np.sum(i_idx * glcm)
    mu_j = np.sum(j_idx * glcm)
    std_i = np.sqrt(np.sum((i_idx - mu_i) ** 2 * glcm))
    std_j = np.sqrt(np.sum((j_idx - mu_j) ** 2 * glcm))
    if std_i > 0 and std_j > 0:
        correlation = float(np.sum((i_idx - mu_i) * (j_idx - mu_j) * glcm) / (std_i * std_j))
    else:
        correlation = 0.0

    return {
        "glcm_contrast": round(contrast, 4),
        "glcm_homogeneity": round(homogeneity, 4),
        "glcm_energy": round(energy, 6),
        "glcm_entropy": round(entropy, 4),
        "glcm_correlation": round(correlation, 4),
    }


def _texture_regularity_index(gray: np.ndarray, block_size: int = 32) -> float:
    """Compute texture regularity index.

    Divide image into blocks, compute texture descriptor per block, measure
    how similar blocks are to each other.  AI textures are more regular.
    """
    h, w = gray.shape
    descriptors = []

    for y in range(0, h - block_size + 1, block_size):
        for x in range(0, w - block_size + 1, block_size):
            block = gray[y:y + block_size, x:x + block_size].astype(np.float64)
            # Simple texture descriptor: [mean, std, gradient_mean, gradient_std]
            grad = np.abs(np.diff(block, axis=1))
            desc = np.array([
                np.mean(block), np.std(block),
                np.mean(grad), np.std(grad),
            ])
            norm = np.linalg.norm(desc)
            if norm > 0:
                descriptors.append(desc / norm)

    if len(descriptors) < 4:
        return 0.0

    descriptors = np.array(descriptors)
    # Pairwise cosine similarity
    sim = descriptors @ descriptors.T
    mask = ~np.eye(len(sim), dtype=bool)
    regularity = float(np.mean(sim[mask]))

    return regularity


def analyze(image_path: str) -> LayerResult:
    """Analyse texture patterns for AI generation signatures."""
    flags: list[str] = []
    details: dict[str, Any] = {}

    try:
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return LayerResult(
                layer=LayerName.TEXTURE, score=0.5, confidence=0.0,
                flags=["Could not open image"], error="cv2.imread returned None",
            )

        gray = cv2.resize(img, (ANALYSIS_SIZE, ANALYSIS_SIZE), interpolation=cv2.INTER_AREA)

        # ── 1. LBP analysis ───────────────────────────
        lbp_map = _compute_lbp(gray, radius=1, neighbors=8)
        lbp_stats = _lbp_histogram_analysis(lbp_map)
        details.update(lbp_stats)

        # ── 2. Gabor filter bank ───────────────────────
        gabor = _gabor_filter_bank(gray)
        details.update(gabor)

        # ── 3. Co-occurrence features ──────────────────
        glcm = _cooccurrence_features(gray)
        details.update(glcm)

        # ── 4. Texture regularity index ────────────────
        regularity = _texture_regularity_index(gray)
        details["texture_regularity"] = round(regularity, 4)

        # ── Scoring ────────────────────────────────────
        score = 0.0

        # LBP entropy: natural > 6.5, AI < 5.5
        if lbp_stats["lbp_entropy"] < 5.0:
            score += 0.20
            flags.append(f"Low LBP entropy ({lbp_stats['lbp_entropy']:.2f}) — limited texture diversity")
        elif lbp_stats["lbp_entropy"] < 6.0:
            score += 0.10
            flags.append(f"Moderate LBP entropy ({lbp_stats['lbp_entropy']:.2f})")
        elif lbp_stats["lbp_entropy"] > 7.0:
            score -= 0.05
            flags.append(f"High LBP entropy ({lbp_stats['lbp_entropy']:.2f}) — rich natural texture")

        # LBP uniformity (sum of squared probs): high = concentrated = AI
        if lbp_stats["lbp_uniformity"] > 0.05:
            score += 0.10
            flags.append(f"Concentrated LBP histogram ({lbp_stats['lbp_uniformity']:.4f})")

        # Gabor fine/coarse ratio: AI suppresses fine textures
        if gabor["gabor_fine_coarse_ratio"] < 0.1:
            score += 0.15
            flags.append(f"Suppressed fine-scale textures (ratio={gabor['gabor_fine_coarse_ratio']:.3f})")
        elif gabor["gabor_fine_coarse_ratio"] > 0.5:
            score -= 0.05
            flags.append(f"Rich fine-scale textures (ratio={gabor['gabor_fine_coarse_ratio']:.3f})")

        # Gabor energy CV: Low = uniform energy across scales (AI)
        if gabor["gabor_energy_cv"] < 0.5:
            score += 0.10
            flags.append(f"Uniform Gabor energy (CV={gabor['gabor_energy_cv']:.3f})")
        elif gabor["gabor_energy_cv"] > 1.5:
            score -= 0.05

        # GLCM energy: high = regular texture (AI), low = complex (natural)
        if glcm["glcm_energy"] > 0.1:
            score += 0.15
            flags.append(f"High GLCM energy ({glcm['glcm_energy']:.4f}) — regular texture (AI)")
        elif glcm["glcm_energy"] < 0.02:
            score -= 0.05
            flags.append(f"Low GLCM energy ({glcm['glcm_energy']:.4f}) — complex natural texture")

        # GLCM contrast: AI tends to have lower contrast
        if glcm["glcm_contrast"] < 1.0:
            score += 0.10
            flags.append(f"Low texture contrast ({glcm['glcm_contrast']:.3f})")

        # Texture regularity: AI > 0.8, natural < 0.6
        if regularity > 0.85:
            score += 0.15
            flags.append(f"Very regular texture (regularity={regularity:.3f}) — AI uniformity")
        elif regularity > 0.7:
            score += 0.05
        elif regularity < 0.5:
            score -= 0.05
            flags.append(f"Irregular texture (regularity={regularity:.3f}) — natural variation")

        score = round(max(0.0, min(1.0, score)), 4)
        confidence = 0.60

        return LayerResult(
            layer=LayerName.TEXTURE,
            score=score,
            confidence=confidence,
            flags=flags,
            details=details,
        )

    except Exception as e:
        logger.exception("Texture analysis failed")
        return LayerResult(
            layer=LayerName.TEXTURE, score=0.5, confidence=0.0,
            flags=["Texture analysis failed"], error=str(e),
        )
