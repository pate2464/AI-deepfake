"""Layer 21 — Multi-granularity Local Entropy Patterns (MLEP).

Implements the core insight from Yuan et al. (arXiv:2504.13726):
Compute local Shannon entropy of image patches at multiple scales, after
random shuffling of sub-patches to destroy semantic content while preserving
pixel-level statistical structure.

Real images have highly variable local entropy (sensor noise, natural textures,
depth variation).  AI images have smoother, more uniform local entropy because
generators produce statistically regular microstructure at all scales.

Model-agnostic, training-free feature extraction — tested on 32 generators.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np
from PIL import Image

from app.core.models import LayerName, LayerResult

logger = logging.getLogger(__name__)

_ANALYSIS_SIZE = 512  # Must be divisible by 64
_SCALES = [8, 16, 32, 64]
_SUBSHUFFLE_GRID = 4  # Divide each patch into 4×4 sub-patches for shuffling
_RNG_SEED = 42  # Fixed seed for reproducibility


# ── Feature extraction ──────────────────────────────────

def _shannon_entropy(patch: np.ndarray) -> float:
    """Compute Shannon entropy of a grayscale patch (256-bin histogram)."""
    counts, _ = np.histogram(patch.ravel(), bins=256, range=(0, 255))
    probs = counts / (counts.sum() + 1e-10)
    probs = probs[probs > 0]
    return float(-np.sum(probs * np.log2(probs)))


def _shuffle_subpatches(patch: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Shuffle sub-patches within a patch to destroy semantic content.

    Divides the patch into a _SUBSHUFFLE_GRID×_SUBSHUFFLE_GRID grid of
    sub-patches and randomly permutes their positions.  This preserves
    pixel-level statistical structure while removing content bias.
    """
    ph, pw = patch.shape
    gh = ph // _SUBSHUFFLE_GRID
    gw = pw // _SUBSHUFFLE_GRID
    if gh < 2 or gw < 2:
        return patch  # Patch too small to shuffle meaningfully

    # Extract sub-patches
    subpatches = []
    for i in range(_SUBSHUFFLE_GRID):
        for j in range(_SUBSHUFFLE_GRID):
            subpatches.append(patch[i * gh:(i + 1) * gh, j * gw:(j + 1) * gw].copy())

    # Shuffle
    rng.shuffle(subpatches)

    # Rebuild patch
    shuffled = np.zeros_like(patch)
    idx = 0
    for i in range(_SUBSHUFFLE_GRID):
        for j in range(_SUBSHUFFLE_GRID):
            shuffled[i * gh:(i + 1) * gh, j * gw:(j + 1) * gw] = subpatches[idx]
            idx += 1

    return shuffled


def _compute_entropy_map(gray: np.ndarray, scale: int, rng: np.random.Generator) -> np.ndarray:
    """Compute local entropy map at a given patch scale.

    Each value = Shannon entropy of the shuffled patch at that position.
    """
    h, w = gray.shape
    ny = h // scale
    nx = w // scale
    entropy_map = np.zeros((ny, nx), dtype=np.float64)

    for i in range(ny):
        for j in range(nx):
            patch = gray[i * scale:(i + 1) * scale, j * scale:(j + 1) * scale]
            shuffled = _shuffle_subpatches(patch, rng)
            entropy_map[i, j] = _shannon_entropy(shuffled)

    return entropy_map


def _extract_mlep_features(gray: np.ndarray) -> dict[str, float]:
    """Extract multi-granularity local entropy pattern features.

    Returns a dict with features computed across multiple scales.
    """
    rng = np.random.default_rng(_RNG_SEED)

    entropy_maps: dict[int, np.ndarray] = {}
    per_scale_variance: list[float] = []
    per_scale_range: list[float] = []
    per_scale_mean: list[float] = []

    for scale in _SCALES:
        emap = _compute_entropy_map(gray, scale, rng)
        entropy_maps[scale] = emap

        per_scale_variance.append(float(np.var(emap)))
        per_scale_range.append(float(np.ptp(emap)))  # max - min
        per_scale_mean.append(float(np.mean(emap)))

    # ── Feature 1: Entropy variance at finest scale (8×8) ──
    # Real → high variance; AI → low variance
    fine_variance = per_scale_variance[0]  # scale=8

    # ── Feature 2: Cross-scale entropy correlation ──
    # Pearson correlation between adjacent scale entropy maps (resampled)
    # AI → higher correlation (self-similar generation artifacts at all scales)
    cross_corrs = []
    for k in range(len(_SCALES) - 1):
        s1, s2 = _SCALES[k], _SCALES[k + 1]
        map1 = entropy_maps[s1]
        map2 = entropy_maps[s2]
        # Downsample map1 to match map2 dimensions
        target_h, target_w = map2.shape
        map1_resized = cv2.resize(map1, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
        flat1 = map1_resized.ravel()
        flat2 = map2.ravel()
        if np.std(flat1) > 1e-10 and np.std(flat2) > 1e-10:
            corr = float(np.corrcoef(flat1, flat2)[0, 1])
        else:
            corr = 1.0  # Perfectly uniform → treat as max correlation
        cross_corrs.append(corr)
    mean_cross_corr = float(np.mean(cross_corrs))

    # ── Feature 3: Entropy range at finest scale ──
    # Real → wide range; AI → narrow range
    fine_range = per_scale_range[0]

    # ── Feature 4: Global entropy uniformity (CoV at 8×8) ──
    # Coefficient of variation of entropy values across all 8×8 patches
    fine_map = entropy_maps[_SCALES[0]]
    fine_mean = np.mean(fine_map) + 1e-10
    fine_cov = float(np.std(fine_map) / fine_mean)

    # ── Feature 5: Entropy gradient (spatial smoothness) ──
    # Mean absolute difference between spatially adjacent entropy values
    # Real → steep gradients (entropy changes sharply); AI → smooth
    fine_grad_h = np.abs(np.diff(fine_map, axis=1))
    fine_grad_v = np.abs(np.diff(fine_map, axis=0))
    entropy_gradient = float(
        (np.mean(fine_grad_h) + np.mean(fine_grad_v)) / 2.0
    )

    return {
        "fine_entropy_variance": fine_variance,
        "cross_scale_correlation": mean_cross_corr,
        "fine_entropy_range": fine_range,
        "fine_entropy_cov": fine_cov,
        "entropy_gradient": entropy_gradient,
        "fine_entropy_mean": per_scale_mean[0],
    }


# ── Scoring ─────────────────────────────────────────────

def _score_from_features(features: dict[str, float]) -> tuple[float, float, list[str]]:
    """Convert MLEP features to (score, confidence, flags)."""
    score = 0.0
    flags: list[str] = []

    variance = features["fine_entropy_variance"]
    cross_corr = features["cross_scale_correlation"]
    ent_range = features["fine_entropy_range"]
    cov = features["fine_entropy_cov"]
    gradient = features["entropy_gradient"]

    # 1. Fine-scale entropy variance — most discriminative
    #    Real: variance > 0.5 (heterogeneous textures)
    #    AI: variance < 0.2 (uniform microstructure)
    if variance < 0.10:
        score += 0.25
        flags.append(f"Very uniform local entropy (var={variance:.4f}) — AI-generated pattern")
    elif variance < 0.25:
        score += 0.12
        flags.append(f"Low entropy variance ({variance:.4f})")

    # 2. Cross-scale correlation — strongest diffusion-model signal
    #    AI → higher correlation (self-similar at all scales)
    if cross_corr > 0.95:
        score += 0.30
        flags.append(f"Very high cross-scale entropy correlation ({cross_corr:.3f}) — hallmark of AI generation")
    elif cross_corr > 0.85:
        score += 0.18
        flags.append(f"High cross-scale entropy correlation ({cross_corr:.3f}) — self-similar generation")
    elif cross_corr > 0.75:
        score += 0.08
    elif cross_corr < 0.50:
        score -= 0.05

    # 3. Entropy range at finest scale
    if ent_range < 1.5:
        score += 0.15
        flags.append(f"Narrow entropy range ({ent_range:.2f}) — uniform microstructure")
    elif ent_range < 3.0:
        score += 0.08
    elif ent_range > 6.0:
        score -= 0.05

    # 4. Coefficient of variation
    if cov < 0.05:
        score += 0.15
        flags.append(f"Very low entropy CoV ({cov:.4f}) — AI-generated uniformity")
    elif cov < 0.10:
        score += 0.08

    # 5. Entropy gradient (spatial smoothness)
    if gradient < 0.10:
        score += 0.15
        flags.append(f"Smooth entropy gradients ({gradient:.4f}) — no natural texture transitions")
    elif gradient < 0.25:
        score += 0.08

    score = max(0.0, min(1.0, score))

    # Confidence: MLEP is model-agnostic and well-founded
    confidence = 0.65
    if score > 0.5:
        confidence = 0.75
    elif score < 0.15:
        confidence = 0.70

    return score, confidence, flags


# ── Public entry point ──────────────────────────────────

def analyze(image_path: str) -> LayerResult:
    """Run MLEP multi-scale entropy analysis on an image."""
    try:
        img = Image.open(image_path).convert("L")
        gray = np.array(img, dtype=np.float64)
    except Exception as e:
        return LayerResult(
            layer=LayerName.MLEP, score=0.0, confidence=0.0,
            flags=["Could not open image"], error=str(e),
        )

    # Resize to standard analysis size (must be divisible by 64)
    if gray.shape[0] != _ANALYSIS_SIZE or gray.shape[1] != _ANALYSIS_SIZE:
        gray = cv2.resize(gray, (_ANALYSIS_SIZE, _ANALYSIS_SIZE))

    features = _extract_mlep_features(gray)
    score, confidence, flags = _score_from_features(features)

    if score >= 0.5:
        flags.insert(0, f"MLEP score: {score:.0%} — AI-like entropy patterns across scales")
    elif score >= 0.25:
        flags.insert(0, f"MLEP score: {score:.0%} — some AI-like entropy patterns")
    else:
        flags.insert(0, f"MLEP score: {score:.0%} — natural multi-scale entropy")

    return LayerResult(
        layer=LayerName.MLEP,
        score=round(score, 4),
        confidence=round(confidence, 4),
        flags=flags,
        details={k: round(v, 6) for k, v in features.items()},
    )
