"""
license_server/app/routes/webhook.py — Razorpay payment webhook.

POST /api/webhook/razorpay
"""

import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models import License
from app.services.email_service import send_license_email
from app.services.key_generator import generate_license_key
from app.services.license_service import log_action

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhook", tags=["webhook"])

# Plan mapping: amount in paise → plan name & duration
_PLAN_MAP = {
    49900:  ("monthly", timedelta(days=30)),
    399900: ("yearly", timedelta(days=365)),
    999900: ("lifetime", None),  # None = no expiry
}


def _verify_razorpay_signature(body: bytes, signature: str, secret: str) -> bool:
    """Verify Razorpay webhook signature (HMAC-SHA256)."""
    expected = hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/razorpay")
async def razorpay_webhook(request: Request):
    """Handle Razorpay payment.captured webhook."""
    if not settings.razorpay_webhook_secret:
        raise HTTPException(status_code=503, detail="Razorpay webhook not configured.")

    body = await request.body()
    signature = request.headers.get("x-razorpay-signature", "")

    if not _verify_razorpay_signature(body, signature, settings.razorpay_webhook_secret):
        logger.warning("Invalid Razorpay webhook signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    payload = await request.json()
    event = payload.get("event", "")

    if event != "payment.captured":
        # Acknowledge non-captured events silently
        return {"status": "ignored", "event": event}

    payment = payload.get("payload", {}).get("payment", {}).get("entity", {})
    payment_id = payment.get("id", "")
    amount = payment.get("amount", 0)
    email = (
        payment.get("notes", {}).get("email")
        or payment.get("email", "")
    ).strip().lower()
    plan_from_notes = payment.get("notes", {}).get("plan", "")

    if not email:
        logger.error("Razorpay webhook missing email: payment_id=%s", payment_id)
        raise HTTPException(status_code=400, detail="Missing email in payment notes.")

    # Determine plan from amount
    plan_name, duration = _PLAN_MAP.get(amount, (plan_from_notes or "monthly", timedelta(days=30)))

    async with async_session() as db:
        # Idempotency — check if this payment_id already created a license
        existing = await db.execute(
            select(License).where(License.payment_id == payment_id)
        )
        if existing.scalar_one_or_none():
            logger.info("Duplicate webhook for payment_id=%s — ignoring", payment_id)
            return {"status": "duplicate"}

        # Generate key and create license
        license_key = generate_license_key()
        now = datetime.now(timezone.utc)
        expires_at = (now + duration) if duration else None

        lic = License(
            email=email,
            license_key=license_key,
            plan=plan_name,
            is_active=True,
            created_at=now,
            expires_at=expires_at,
            payment_id=payment_id,
            payment_amount=amount,
            notes=f"Auto-created via Razorpay webhook",
        )
        db.add(lic)
        await db.flush()

        await log_action(db, lic, "created_via_payment", ip_address="webhook", details={
            "payment_id": payment_id,
            "amount": amount,
            "plan": plan_name,
        })
        await db.commit()

        logger.info(
            "License created: key=%s email=%s plan=%s payment=%s",
            license_key, email, plan_name, payment_id,
        )

    # Send email with license key (non-blocking, best-effort)
    await send_license_email(
        to_email=email,
        license_key=license_key,
        plan=plan_name,
        expires_at=str(expires_at) if expires_at else "Lifetime",
    )

    return {"status": "created", "license_key": license_key}
