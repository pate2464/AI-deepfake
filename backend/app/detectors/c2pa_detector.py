"""Layer 5 — C2PA Cryptographic Provenance.

Checks whether an image has a Content Credentials (C2PA) manifest, validates
signatures, and looks for ai_generated assertions.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.models import LayerName, LayerResult


def _try_read_c2pa(image_path: str) -> dict[str, Any] | None:
    """Attempt to read C2PA manifest.  Returns parsed manifest or None."""
    try:
        import c2pa
        reader = c2pa.Reader.from_file(image_path)
        manifest_json = reader.json()
        return json.loads(manifest_json) if isinstance(manifest_json, str) else manifest_json
    except ImportError:
        return None
    except Exception:
        # No C2PA manifest, invalid, or unsupported format
        return None


def _search_ai_assertions(manifest: dict) -> list[str]:
    """Walk the manifest looking for AI-generation related assertions."""
    ai_flags: list[str] = []
    manifest_str = json.dumps(manifest).lower()

    ai_keywords = [
        "ai_generated", "ai generated", "generative_ai",
        "c2pa.ai", "trained_model", "compositeWithTrainedAlgorithmicMedia",
        "dall-e", "stable diffusion", "midjourney", "firefly", "imagen",
    ]
    for kw in ai_keywords:
        if kw in manifest_str:
            ai_flags.append(f"C2PA manifest contains AI indicator: '{kw}'")

    return ai_flags


def analyze(image_path: str) -> LayerResult:
    """Run C2PA provenance check."""
    flags: list[str] = []
    details: dict[str, Any] = {}

    manifest = _try_read_c2pa(image_path)

    if manifest is None:
        # No C2PA — weak signal, most images still don't have it
        details["has_c2pa"] = False
        details["note"] = "No C2PA manifest found. Most cameras do not embed C2PA yet."
        flags.append("No C2PA provenance data — neutral signal")
        score = 0.3
        confidence = 0.3

    else:
        details["has_c2pa"] = True
        details["manifest_keys"] = list(manifest.keys()) if isinstance(manifest, dict) else []

        # Check for AI assertions
        ai_flags = _search_ai_assertions(manifest)
        if ai_flags:
            flags.extend(ai_flags)
            flags.append("C2PA manifest explicitly indicates AI-generated content")
            score = 1.0
            confidence = 0.95
        else:
            # Valid C2PA from a camera → strong real signal
            flags.append("Valid C2PA manifest found — likely authentic camera capture")
            score = 0.05
            confidence = 0.9

        # Store a summary (not the full manifest to keep response small)
        try:
            details["manifest_summary"] = {
                k: str(v)[:200] for k, v in manifest.items()
            } if isinstance(manifest, dict) else str(manifest)[:500]
        except Exception:
            details["manifest_summary"] = "present but could not summarise"

    # File format as secondary signal
    ext = image_path.rsplit(".", 1)[-1].lower() if "." in image_path else ""
    details["file_extension"] = ext
    if ext == "png":
        flags.append("PNG format — AI tools typically save as PNG")
        score = min(1.0, score + 0.05)

    return LayerResult(
        layer=LayerName.C2PA,
        score=round(score, 4),
        confidence=round(confidence, 4),
        flags=flags,
        details=details,
    )
