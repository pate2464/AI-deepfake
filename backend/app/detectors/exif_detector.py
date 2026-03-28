"""Layer 1 — EXIF Metadata Forensics.

Checks for presence/absence of camera metadata fields.
AI-generated images typically have zero EXIF data, while real phone photos have 15+ fields.
"""

from __future__ import annotations

import os
from typing import Any

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

from app.core.models import LayerName, LayerResult

# Fields expected in a real smartphone photo
CRITICAL_FIELDS = {
    "Make",            # Camera manufacturer
    "Model",           # Camera model
    "DateTime",        # Capture timestamp
    "DateTimeOriginal",
    "DateTimeDigitized",
    "ExifImageWidth",
    "ExifImageHeight",
}

DESIRABLE_FIELDS = {
    "FNumber",         # Aperture
    "ExposureTime",    # Shutter speed
    "ISOSpeedRatings",
    "FocalLength",
    "LensModel",
    "LensMake",
    "Flash",
    "WhiteBalance",
    "GPSInfo",
    "Software",
    "Orientation",
    "XResolution",
    "YResolution",
}

SUSPICIOUS_SOFTWARE = [
    "dall-e", "stable diffusion", "midjourney", "firefly",
    "comfyui", "automatic1111", "invoke-ai", "novelai",
]


def _decode_exif(img: Image.Image) -> dict[str, Any]:
    """Extract human-readable EXIF dict from a PIL Image, including IFD sub-tags."""
    raw = img.getexif()
    if not raw:
        return {}

    decoded: dict[str, Any] = {}
    for tag_id, value in raw.items():
        tag_name = TAGS.get(tag_id, str(tag_id))
        if tag_name == "GPSInfo" and isinstance(value, dict):
            gps = {}
            for gps_id, gps_val in value.items():
                gps[GPSTAGS.get(gps_id, str(gps_id))] = gps_val
            decoded[tag_name] = gps
        else:
            # Convert bytes to string for JSON serialisability
            if isinstance(value, bytes):
                try:
                    value = value.decode("utf-8", errors="replace")
                except Exception:
                    value = str(value)
            decoded[tag_name] = value

    # Read IFD sub-tags (Exif IFD, GPS IFD) — these contain the detailed
    # camera settings like FNumber, ISO, LensModel that HEIC/modern formats
    # store in IFD blocks rather than top-level EXIF.
    try:
        from PIL.ExifTags import IFD
        for ifd_key in [IFD.Exif, IFD.GPSInfo]:
            ifd = raw.get_ifd(ifd_key)
            if ifd:
                tag_dict = GPSTAGS if ifd_key == IFD.GPSInfo else TAGS
                for tag_id, value in ifd.items():
                    tag_name = tag_dict.get(tag_id, TAGS.get(tag_id, str(tag_id)))
                    if isinstance(value, bytes):
                        try:
                            value = value.decode("utf-8", errors="replace")
                        except Exception:
                            value = str(value)
                    decoded[tag_name] = value
    except Exception:
        pass  # Older Pillow versions may not support IFD

    return decoded


def _check_format(filepath: str) -> tuple[str, bool]:
    """Return file extension and whether it's a suspicious format for photos."""
    ext = os.path.splitext(filepath)[1].lower()
    # AI tools typically output PNG; real phone photos are JPEG or HEIC
    # HEIC/HEIF is the default format for modern iPhones — NOT suspicious
    suspicious = ext in (".png", ".bmp", ".tiff")
    return ext, suspicious


def analyze(image_path: str) -> LayerResult:
    """Run EXIF metadata forensics on the image."""
    flags: list[str] = []
    details: dict[str, Any] = {}

    try:
        img = Image.open(image_path)
    except Exception as e:
        return LayerResult(
            layer=LayerName.EXIF,
            score=0.5,
            confidence=0.3,
            flags=["Could not open image"],
            error=str(e),
        )

    # 1. File format check
    ext, fmt_suspicious = _check_format(image_path)
    details["file_format"] = ext
    if fmt_suspicious:
        flags.append(f"Suspicious format for a photo: {ext} (AI tools default to PNG)")

    # 2. Extract EXIF
    exif = _decode_exif(img)
    details["exif_field_count"] = len(exif)
    details["exif_fields"] = {k: str(v)[:200] for k, v in exif.items()}

    # 3. Check critical fields
    present_critical = CRITICAL_FIELDS.intersection(exif.keys())
    missing_critical = CRITICAL_FIELDS - present_critical
    details["present_critical"] = list(present_critical)
    details["missing_critical"] = list(missing_critical)

    if len(exif) == 0:
        flags.append("No EXIF metadata at all — typical of AI-generated images")
    elif len(missing_critical) > 0:
        flags.append(f"Missing critical fields: {', '.join(missing_critical)}")

    # 4. Check desirable fields
    present_desirable = DESIRABLE_FIELDS.intersection(exif.keys())
    details["present_desirable"] = list(present_desirable)

    # 5. Check for suspicious software tag
    software = str(exif.get("Software", "")).lower()
    if software:
        details["software_tag"] = software
        for sus in SUSPICIOUS_SOFTWARE:
            if sus in software:
                flags.append(f"Software tag indicates AI tool: '{software}'")
                break

    # 6. GPS presence — check for GPS fields that were added from IFD sub-tags
    gps_info = exif.get("GPSInfo")
    gps_fields = {"GPSLatitude", "GPSLongitude", "GPSAltitude", "GPSDateStamp",
                  "GPSTimeStamp", "InteropIndex"}  # InteropIndex = GPSLatitudeRef in IFD
    has_gps = False
    if isinstance(gps_info, dict) and len(gps_info) > 0:
        has_gps = True
    elif any(k in exif for k in gps_fields):
        has_gps = True  # GPS fields were merged from IFD
    details["has_gps"] = has_gps
    if not has_gps and len(exif) > 0:
        flags.append("No GPS data despite having other EXIF fields")

    # 7. Thumbnail check (JPEG may have embedded thumbnail)
    has_thumbnail = hasattr(img, "applist") or img.info.get("exif_thumbnail") is not None
    details["has_thumbnail"] = has_thumbnail

    # ── Scoring ────────────────────────────────────────
    total_expected = len(CRITICAL_FIELDS) + len(DESIRABLE_FIELDS)
    total_present = len(present_critical) + len(present_desirable)
    missing_ratio = 1.0 - (total_present / total_expected) if total_expected > 0 else 1.0

    # Format penalty
    format_penalty = 0.15 if fmt_suspicious else 0.0

    # Software penalty
    software_penalty = 0.3 if any(s in software for s in SUSPICIOUS_SOFTWARE) else 0.0

    score = min(1.0, missing_ratio * 0.7 + format_penalty + software_penalty)

    # Confidence: higher when we have clear signals
    confidence = 0.8 if len(exif) == 0 else 0.6

    return LayerResult(
        layer=LayerName.EXIF,
        score=round(score, 4),
        confidence=round(confidence, 4),
        flags=flags,
        details=details,
    )
