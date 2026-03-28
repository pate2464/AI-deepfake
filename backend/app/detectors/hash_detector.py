"""Layer 3 — Perceptual Hashing (Duplicate Killer).

Computes multiple perceptual hashes (pHash, dHash, aHash, wHash) and checks
against a database of previously seen claim images.  Near-duplicate detection
catches serial scammers reusing the same AI-generated image across accounts.
"""

from __future__ import annotations

from typing import Any

import imagehash
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.models import HashMatch, LayerName, LayerResult
from app.db.database import ImageHash as ImageHashDB


HASH_SIZE = 16  # 16×16 = 256-bit hashes for higher precision


def _compute_hashes(img: Image.Image) -> dict[str, str]:
    """Compute 4 perceptual hashes."""
    return {
        "ahash": str(imagehash.average_hash(img, hash_size=HASH_SIZE)),
        "phash": str(imagehash.phash(img, hash_size=HASH_SIZE)),
        "dhash": str(imagehash.dhash(img, hash_size=HASH_SIZE)),
        "whash": str(imagehash.whash(img, hash_size=HASH_SIZE)),
    }


def _hamming(hex_a: str, hex_b: str) -> int:
    """Compute hamming distance between two hex hash strings."""
    hash_a = imagehash.hex_to_hash(hex_a)
    hash_b = imagehash.hex_to_hash(hex_b)
    return int(hash_a - hash_b)


async def analyze(
    image_path: str,
    claim_id: int,
    session: AsyncSession,
) -> tuple[LayerResult, list[HashMatch], dict[str, str]]:
    """Run perceptual hashing analysis.

    Returns (LayerResult, list_of_matches, computed_hashes).
    """
    flags: list[str] = []
    details: dict[str, Any] = {}
    matches: list[HashMatch] = []

    try:
        img = Image.open(image_path)
    except Exception as e:
        return LayerResult(
            layer=LayerName.HASH, score=0.0, confidence=0.3,
            flags=["Could not open image"], error=str(e),
        ), [], {}

    hashes = _compute_hashes(img)
    details["computed_hashes"] = hashes

    # Query existing hashes
    result = await session.execute(
        select(ImageHashDB).where(ImageHashDB.claim_id != claim_id)
    )
    existing_rows = result.scalars().all()

    best_distance = float("inf")
    for row in existing_rows:
        for hash_type in ("phash", "dhash", "ahash", "whash"):
            existing_hex = getattr(row, hash_type)
            new_hex = hashes.get(hash_type)
            if not existing_hex or not new_hex:
                continue
            try:
                dist = _hamming(new_hex, existing_hex)
            except Exception:
                continue

            if dist < settings.HASH_MATCH_THRESHOLD:
                matches.append(HashMatch(
                    matched_claim_id=row.claim_id,
                    hamming_distance=dist,
                    hash_type=hash_type,
                ))
                best_distance = min(best_distance, dist)

    # Deduplicate matches (keep best per claim)
    seen_claims: dict[int, HashMatch] = {}
    for m in matches:
        if m.matched_claim_id not in seen_claims or m.hamming_distance < seen_claims[m.matched_claim_id].hamming_distance:
            seen_claims[m.matched_claim_id] = m
    matches = list(seen_claims.values())

    details["match_count"] = len(matches)
    details["best_hamming_distance"] = best_distance if matches else None

    # Scoring
    if not matches:
        score = 0.0
        flags.append("No duplicate images found in database")
    elif best_distance <= settings.HASH_IDENTICAL_THRESHOLD:
        score = 1.0
        flags.append(f"IDENTICAL image found (hamming={best_distance}) — likely reuse")
    elif best_distance <= settings.HASH_MATCH_THRESHOLD:
        score = 0.7
        flags.append(f"Near-duplicate image found (hamming={best_distance})")
    else:
        score = 0.3

    confidence = 0.95 if matches else 0.5

    return LayerResult(
        layer=LayerName.HASH,
        score=round(score, 4),
        confidence=round(confidence, 4),
        flags=flags,
        details=details,
    ), matches, hashes
