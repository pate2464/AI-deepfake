"""Layer 6 — Behavioral Scoring.

Rule-based scoring that doesn't depend on the image at all — it looks at the
account's history.  This is the hardest layer for scammers to beat because
generating a new AI image every time doesn't reset behavioral patterns.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.models import AnalysisContext, LayerName, LayerResult
from app.db.database import Account, Claim


async def analyze(
    context: AnalysisContext,
    session: AsyncSession,
) -> LayerResult:
    """Run behavioral scoring based on account context."""
    flags: list[str] = []
    details: dict[str, Any] = {}
    score = 0.0

    if not context.account_id:
        return LayerResult(
            layer=LayerName.BEHAVIORAL,
            score=0.0,
            confidence=0.1,
            flags=["No account context provided — behavioral scoring skipped"],
            details={"note": "Submit account_id for behavioral analysis"},
        )

    # ── Lookup or create account ───────────────────────
    result = await session.execute(
        select(Account).where(Account.account_id == context.account_id)
    )
    account = result.scalar_one_or_none()

    if account is None:
        # First-time account
        account = Account(
            account_id=context.account_id,
            device_fingerprint=context.device_fingerprint,
        )
        session.add(account)
        await session.flush()
        flags.append("First-time account — limited behavioral data")
        details["account_age_days"] = 0
        details["is_new_account"] = True
    else:
        account_age = (datetime.now(timezone.utc) - account.created_at).days
        details["account_age_days"] = account_age
        details["is_new_account"] = False

        # — Rule 1: Account age —
        if account_age < settings.BEHAVIORAL_MIN_ACCOUNT_AGE_DAYS:
            flags.append(f"Account is only {account_age} days old — suspicious")
            score += 0.2

    # — Rule 2: Claim frequency (last 30 days) —
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    result = await session.execute(
        select(func.count(Claim.id))
        .where(Claim.account_db_id == account.id)
        .where(Claim.created_at >= thirty_days_ago)
    )
    claim_count = result.scalar() or 0
    details["claims_last_30d"] = claim_count

    if claim_count > settings.BEHAVIORAL_MAX_CLAIMS_30D:
        flags.append(f"High claim frequency: {claim_count} claims in 30 days")
        score += 0.25
    elif claim_count > 1:
        score += 0.1

    # — Rule 3: Device fingerprint reuse across accounts —
    if context.device_fingerprint:
        result = await session.execute(
            select(func.count(Account.id))
            .where(Account.device_fingerprint == context.device_fingerprint)
            .where(Account.account_id != context.account_id)
        )
        fp_count = result.scalar() or 0
        details["device_shared_accounts"] = fp_count

        if fp_count > 0:
            flags.append(f"Device fingerprint shared with {fp_count} other account(s)")
            score += 0.25

        # Update fingerprint if changed
        if account.device_fingerprint != context.device_fingerprint:
            account.device_fingerprint = context.device_fingerprint

    # — Rule 4: GPS mismatch —
    if context.delivery_lat is not None and context.delivery_lon is not None:
        details["delivery_coords"] = {
            "lat": context.delivery_lat,
            "lon": context.delivery_lon,
        }
        # We'd compare with image EXIF GPS if available; for now flag if no GPS
        # The pipeline can cross-reference L1 GPS with this.
        flags.append("Delivery coordinates provided — cross-reference with EXIF GPS")

    # — Rule 5: Order value —
    if context.order_value is not None:
        details["order_value"] = context.order_value
        if context.order_value > 100:
            flags.append(f"High-value order (${context.order_value:.2f}) — increased fraud incentive")
            score += 0.1

    # — Rule 6: Previously flagged account —
    if account.flagged:
        flags.append("Account has been previously flagged for fraud")
        score += 0.3

    score = min(1.0, score)
    confidence = 0.4 if claim_count <= 1 else 0.8

    return LayerResult(
        layer=LayerName.BEHAVIORAL,
        score=round(score, 4),
        confidence=round(confidence, 4),
        flags=flags,
        details=details,
    )
