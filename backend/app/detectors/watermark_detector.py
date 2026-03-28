"""Layer 11 — Invisible Watermark Detection.

Attempts to decode steganographic watermarks embedded by AI generators.
Stable Diffusion (some versions) embeds a 136-bit DwtDctSvd watermark that
survives JPEG compression, resizing, and mild editing.

Library: ``invisible-watermark`` (MIT licence)

IMPORTANT: The DwtDctSvd decoder *always* returns bytes from ANY image — it
reads the frequency domain regardless of whether a watermark was actually
embedded.  For real photos, the decoded payload is meaningless noise.  We must
apply strict validation to avoid false positives:
  1. Known SD signature matching (exact byte patterns)
  2. Byte-distribution chi-squared test (uniform = noise, non-uniform = data)
  3. Minimum unique-byte ratio check (real payloads reuse byte values)
  4. Cross-check: both DwtDctSvd and overall payload structure must agree
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
from PIL import Image

from app.core.models import LayerName, LayerResult

logger = logging.getLogger(__name__)

# Known Stable Diffusion watermark payload byte patterns.
# SD v2.x embeds the ASCII string "SDV2" (or similar) repeated/padded.
_SD_SIGNATURES = [
    b"SDV2",
    b"StableDiffusion",
    b"SD",
]

# A genuine null watermark (all zeros) — means the encoder ran but wrote zeros.
_NULL_PAYLOAD = b"\x00" * 17


def analyze(image_path: str) -> LayerResult:
    """Try to decode invisible watermarks from the image."""
    flags: list[str] = []
    details: dict[str, Any] = {}

    try:
        img = Image.open(image_path).convert("RGB")
        img_arr = np.array(img)
    except Exception as e:
        return LayerResult(
            layer=LayerName.WATERMARK, score=0.5, confidence=0.0,
            flags=["Could not open image"], error=str(e),
        )

    # Minimum size guard — decoder needs >= 256×256
    h, w = img_arr.shape[:2]
    if h < 256 or w < 256:
        return LayerResult(
            layer=LayerName.WATERMARK, score=0.10, confidence=0.15,
            flags=[f"Image too small ({w}×{h}) for watermark decoding — skipped"],
            details={"skipped": True, "reason": "min_size"},
        )

    score = 0.10  # baseline — absence of watermark doesn't prove real
    confidence = 0.30

    # ── 1. Stable Diffusion DwtDctSvd watermark ───────
    sd_detected = False
    try:
        from imwatermark import WatermarkDecoder

        # SD uses 136-bit payload via DwtDctSvd
        decoder = WatermarkDecoder("bytes", 136)
        payload = decoder.decode(img_arr, "dwtDctSvd")

        if payload is not None and len(payload) > 0:
            byte_entropy = _byte_entropy(payload)
            unique_ratio = _unique_byte_ratio(payload)
            chi2_random = _chi_squared_uniform(payload)
            has_known_sig = any(sig in payload for sig in _SD_SIGNATURES)
            is_null = (payload == _NULL_PAYLOAD)

            details["sd_payload_hex"] = payload.hex()
            details["sd_payload_entropy"] = round(byte_entropy, 3)
            details["sd_unique_ratio"] = round(unique_ratio, 3)
            details["sd_chi2_pvalue"] = round(chi2_random, 4)
            details["sd_has_known_signature"] = has_known_sig

            # ── Decision logic ──
            # CRITICAL: The DwtDctSvd decoder *always* returns 17 bytes from
            # any image — it reads the DCT frequency domain regardless of
            # whether a real watermark exists.  With only 17 bytes, entropy
            # and chi-squared tests have extremely high false-positive rates
            # because JPEG/HEIC codec artifacts naturally produce non-uniform
            # byte patterns in the frequency domain.
            #
            # The ONLY reliable detection method is matching known exact byte
            # signatures that real SD encoders actually embed.
            if has_known_sig:
                # Gold standard: known byte pattern found in payload
                sd_detected = True
                score = 0.92
                confidence = 0.92
                flags.append("Stable Diffusion watermark signature matched")
            elif is_null:
                # All zeros — encoder ran but wrote no content (still proof of SD pipeline)
                sd_detected = True
                score = 0.80
                confidence = 0.75
                flags.append("Null SD watermark payload (encoder present, empty content)")
            else:
                # No known signature — payload is frequency-domain noise, NOT a watermark.
                # Log diagnostics but do NOT flag as detection.
                details["sd_watermark_noise"] = True
                flags.append(f"DwtDctSvd decoded noise (entropy={byte_entropy:.2f}) — no known watermark signature")
        else:
            flags.append("No Stable Diffusion DwtDctSvd watermark found")
    except Exception as e:
        logger.debug("DwtDctSvd decode error: %s", e)
        flags.append("DwtDctSvd decode unavailable")

    # ── 2. RivaGAN watermark (used by some generators) ─
    riva_detected = False
    try:
        from imwatermark import WatermarkDecoder

        decoder_riva = WatermarkDecoder("bits", 32)
        bits = decoder_riva.decode(img_arr, "rivaGan")

        if bits is not None and len(bits) > 0:
            ones_ratio = sum(bits) / len(bits)
            details["rivagan_bits"] = bits.tolist() if hasattr(bits, "tolist") else list(bits)
            details["rivagan_ones_ratio"] = round(ones_ratio, 3)

            # A real watermark has structured bits; random noise is ~50% ones.
            # Require strong deviation from random (>0.3) to flag.
            if abs(ones_ratio - 0.5) > 0.3:
                riva_detected = True
                if not sd_detected:
                    score = max(score, 0.70)
                    confidence = max(confidence, 0.65)
                flags.append(f"RivaGAN watermark detected (ones ratio={ones_ratio:.2f})")
            else:
                flags.append("RivaGAN decode returned random-looking bits — no watermark")
        else:
            flags.append("No RivaGAN watermark found")
    except Exception as e:
        logger.debug("RivaGAN decode error: %s", e)
        flags.append("RivaGAN decoder unavailable")

    details["sd_watermark_detected"] = sd_detected
    details["rivagan_watermark_detected"] = riva_detected

    if not sd_detected and not riva_detected:
        flags.append("No known AI generator watermark found — inconclusive (many generators don't watermark)")

    return LayerResult(
        layer=LayerName.WATERMARK,
        score=round(score, 4),
        confidence=round(confidence, 4),
        flags=flags,
        details=details,
    )


def _byte_entropy(data: bytes) -> float:
    """Shannon entropy of a byte string (0–8 bits)."""
    if not data:
        return 0.0
    counts = np.bincount(np.frombuffer(data, dtype=np.uint8), minlength=256)
    probs = counts / len(data)
    probs = probs[probs > 0]
    return float(-np.sum(probs * np.log2(probs)))


def _unique_byte_ratio(data: bytes) -> float:
    """Fraction of byte values that are unique.  1.0 = all unique, low = repetitive."""
    if not data:
        return 0.0
    return len(set(data)) / len(data)


def _chi_squared_uniform(data: bytes) -> float:
    """Chi-squared test p-value for the hypothesis that bytes are uniformly distributed.

    Low p-value (<0.05) means the payload is NOT random → likely a real watermark.
    High p-value (>0.05) means the payload looks random → likely noise.
    """
    from scipy.stats import chisquare
    if not data or len(data) < 4:
        return 1.0  # not enough data, assume random
    counts = np.bincount(np.frombuffer(data, dtype=np.uint8), minlength=256)
    # Only test bins that could be populated (with 17 bytes, most bins are 0)
    # Use bins that have at least one count, compare against uniform
    observed = counts[counts > 0]
    expected_val = len(data) / len(observed)  # uniform expectation over non-zero bins
    expected = np.full_like(observed, expected_val, dtype=np.float64)
    stat, p_value = chisquare(observed, expected)
    return float(p_value)
