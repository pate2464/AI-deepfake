"""Layer 14 — Pixel Gradient Distribution Analysis.

AI generators (diffusion models, GANs) produce images whose pixel-to-pixel
gradients follow a Gaussian-like distribution.  Real camera photographs have
gradients that follow a heavy-tailed Laplacian distribution caused by sensor
noise, lens aberrations, and natural texture complexity.

This detector computes horizontal and vertical Sobel gradients, fits the
empirical distribution, and measures divergence from expected camera
characteristics.  Additional metrics include gradient magnitude kurtosis,
zero-crossing density, and directional entropy.

Reference: Farid, H. (2009). "Image Forgery Detection" — IEEE SP Magazine.
"""

from __future__ import annotations

import logging
from typing import Any

import cv2
import numpy as np
from scipy import stats as sp_stats

from app.core.models import LayerName, LayerResult

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────
ANALYSIS_SIZE = 512          # Downscale to this for speed
LAPLACIAN_SCALE = 1.0        # Expected scale parameter of Laplacian distribution


def _fit_gradient_distribution(gradient: np.ndarray) -> dict[str, float]:
    """Fit gradient values to Laplacian and Gaussian, return metrics."""
    flat = gradient.ravel().astype(np.float64)
    # Remove exact zeros to avoid numerical issues
    flat = flat[flat != 0]
    if len(flat) < 100:
        return {"kl_laplacian": 0.0, "kl_gaussian": 999.0, "kurtosis": 0.0}

    # Fit Laplacian (loc, scale)
    lap_loc, lap_scale = sp_stats.laplace.fit(flat)
    # Fit Gaussian (mean, std)
    gauss_mean, gauss_std = sp_stats.norm.fit(flat)

    # Compute log-likelihood under each model
    ll_laplacian = np.mean(sp_stats.laplace.logpdf(flat, loc=lap_loc, scale=lap_scale))
    ll_gaussian = np.mean(sp_stats.norm.logpdf(flat, loc=gauss_mean, scale=gauss_std))

    # Kurtosis: Laplacian has kurtosis=3, Gaussian=0
    # Real cameras: excess kurtosis >> 0 (heavy tails)
    # AI images: excess kurtosis ≈ 0 (Gaussian-like)
    kurtosis = float(sp_stats.kurtosis(flat, fisher=True))

    return {
        "ll_laplacian": float(ll_laplacian),
        "ll_gaussian": float(ll_gaussian),
        "lap_scale": float(lap_scale),
        "gauss_std": float(gauss_std),
        "kurtosis": float(kurtosis),
        "ll_ratio": float(ll_laplacian - ll_gaussian),  # positive = Laplacian better fit
    }


def _gradient_zero_crossings(gray: np.ndarray) -> float:
    """Fraction of pixels where the Laplacian changes sign.

    Real images have higher zero-crossing density due to texture edges.
    AI images tend to have smoother regions with fewer crossings.
    """
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    # Count sign changes in horizontal direction
    signs = np.sign(lap)
    h_crossings = np.sum(np.abs(np.diff(signs, axis=1)) > 0)
    v_crossings = np.sum(np.abs(np.diff(signs, axis=0)) > 0)
    total_pixels = (gray.shape[0] - 1) * gray.shape[1] + gray.shape[0] * (gray.shape[1] - 1)
    return float((h_crossings + v_crossings) / max(total_pixels, 1))


def _directional_entropy(grad_x: np.ndarray, grad_y: np.ndarray) -> float:
    """Entropy of gradient direction distribution.

    Real photos have diverse gradient directions (high entropy).
    AI images often show directional bias from upsampling layers (lower entropy).
    """
    # Compute gradient angle at each pixel
    angles = np.arctan2(grad_y.ravel(), grad_x.ravel())
    # Quantise into 72 bins (5-degree resolution)
    hist, _ = np.histogram(angles, bins=72, range=(-np.pi, np.pi))
    hist = hist / hist.sum()
    hist = hist[hist > 0]
    entropy = -np.sum(hist * np.log2(hist))
    # Max entropy for 72 bins = log2(72) ≈ 6.17
    return float(entropy)


def _gradient_magnitude_stats(mag: np.ndarray) -> dict[str, float]:
    """Statistics of gradient magnitudes."""
    flat = mag.ravel()
    return {
        "mag_mean": float(np.mean(flat)),
        "mag_std": float(np.std(flat)),
        "mag_p95": float(np.percentile(flat, 95)),
        "mag_p99": float(np.percentile(flat, 99)),
        "mag_sparsity": float(np.mean(flat < 2.0)),  # fraction of near-zero gradients
    }


def analyze(image_path: str) -> LayerResult:
    """Analyse pixel gradient distributions for AI generation signatures."""
    flags: list[str] = []
    details: dict[str, Any] = {}

    try:
        img = cv2.imread(image_path, cv2.IMREAD_COLOR)
        if img is None:
            return LayerResult(
                layer=LayerName.GRADIENT, score=0.5, confidence=0.0,
                flags=["Could not open image"], error="cv2.imread returned None",
            )

        # Resize for consistent analysis
        h, w = img.shape[:2]
        if max(h, w) > ANALYSIS_SIZE:
            scale = ANALYSIS_SIZE / max(h, w)
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float64)

        # ── Sobel gradients ────────────────────────────
        grad_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        grad_mag = np.sqrt(grad_x**2 + grad_y**2)

        # ── 1. Gradient distribution fitting ───────────
        h_fit = _fit_gradient_distribution(grad_x)
        v_fit = _fit_gradient_distribution(grad_y)
        details["horizontal_fit"] = h_fit
        details["vertical_fit"] = v_fit

        # Average the LL ratio across both directions
        avg_ll_ratio = (h_fit["ll_ratio"] + v_fit["ll_ratio"]) / 2.0
        avg_kurtosis = (h_fit["kurtosis"] + v_fit["kurtosis"]) / 2.0
        details["avg_ll_ratio"] = round(avg_ll_ratio, 4)
        details["avg_kurtosis"] = round(avg_kurtosis, 4)

        # ── 2. Zero-crossing density ───────────────────
        zc_density = _gradient_zero_crossings(gray.astype(np.uint8))
        details["zero_crossing_density"] = round(zc_density, 4)

        # ── 3. Directional entropy ─────────────────────
        dir_entropy = _directional_entropy(grad_x, grad_y)
        details["directional_entropy"] = round(dir_entropy, 4)

        # ── 4. Gradient magnitude statistics ───────────
        mag_stats = _gradient_magnitude_stats(grad_mag)
        details.update({k: round(v, 4) for k, v in mag_stats.items()})

        # ── Scoring ────────────────────────────────────
        # AI signatures: Gaussian-like gradients (ll_ratio ≤ 0), low kurtosis,
        # low zero-crossing density, smooth texture (high sparsity)
        score = 0.0

        # LL ratio: positive = Laplacian fits better (real camera)
        #           negative or zero = Gaussian fits as well or better (AI)
        if avg_ll_ratio < -0.05:
            score += 0.25
            flags.append(f"Gradient distribution is Gaussian-like (LL ratio={avg_ll_ratio:.3f})")
        elif avg_ll_ratio < 0.05:
            score += 0.10
            flags.append(f"Gradient distribution is borderline (LL ratio={avg_ll_ratio:.3f})")
        else:
            score -= 0.10
            flags.append(f"Heavy-tailed gradients — natural camera signature (LL ratio={avg_ll_ratio:.3f})")

        # Kurtosis: Real = high (>2), AI = low (<1)
        if avg_kurtosis < 0.5:
            score += 0.20
            flags.append(f"Very low gradient kurtosis ({avg_kurtosis:.2f}) — Gaussian tails")
        elif avg_kurtosis < 1.5:
            score += 0.10
            flags.append(f"Low gradient kurtosis ({avg_kurtosis:.2f})")
        elif avg_kurtosis > 3.0:
            score -= 0.10
            flags.append(f"High gradient kurtosis ({avg_kurtosis:.2f}) — heavy tails (natural)")

        # Zero-crossing density: Real > 0.25, AI < 0.20
        if zc_density < 0.15:
            score += 0.15
            flags.append(f"Low zero-crossing density ({zc_density:.3f}) — overly smooth")
        elif zc_density > 0.30:
            score -= 0.05
            flags.append(f"High zero-crossing density ({zc_density:.3f}) — rich texture")

        # Directional entropy: Real ≈ 5.5-6.1, AI with upsampling bias < 5.0
        if dir_entropy < 4.5:
            score += 0.15
            flags.append(f"Low directional entropy ({dir_entropy:.2f}) — directional bias")
        elif dir_entropy < 5.2:
            score += 0.05

        # Gradient sparsity: AI images have more flat (near-zero gradient) regions
        if mag_stats["mag_sparsity"] > 0.70:
            score += 0.15
            flags.append(f"High gradient sparsity ({mag_stats['mag_sparsity']:.2f}) — AI smoothness")
        elif mag_stats["mag_sparsity"] < 0.40:
            score -= 0.05
            flags.append(f"Low gradient sparsity ({mag_stats['mag_sparsity']:.2f}) — textured (natural)")

        score = round(max(0.0, min(1.0, score)), 4)
        confidence = 0.65  # Signal processing based — solid but not model-backed

        return LayerResult(
            layer=LayerName.GRADIENT,
            score=score,
            confidence=confidence,
            flags=flags,
            details=details,
        )

    except Exception as e:
        logger.exception("Gradient analysis failed")
        return LayerResult(
            layer=LayerName.GRADIENT, score=0.5, confidence=0.0,
            flags=["Gradient analysis failed"], error=str(e),
        )
