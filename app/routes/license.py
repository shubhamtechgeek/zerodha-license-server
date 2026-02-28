"""
license_server/app/routes/license.py — Public license endpoints.

POST /api/license/activate
POST /api/license/verify
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt_handler import create_activation_token, verify_activation_token
from app.database import get_db
from app.schemas import ActivateRequest, ActivateResponse, VerifyRequest, VerifyResponse
from app.services.license_service import (
    activate_license,
    find_license,
    find_license_by_key,
    log_action,
    verify_license,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/license", tags=["license"])


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/activate", response_model=ActivateResponse)
async def activate(
    body: ActivateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Activate a license on this machine."""
    ip = _client_ip(request)

    lic = await find_license(db, body.license_key, body.email)
    if not lic:
        raise HTTPException(status_code=404, detail="Invalid license key or email.")

    ok, error = await activate_license(
        db,
        lic,
        hw_fingerprint=body.hw_fingerprint,
        hw_components=body.hw_components,
        machine_name=body.machine_name or "Unknown",
        ip_address=ip,
    )

    if not ok:
        raise HTTPException(status_code=403, detail=error)

    await db.commit()

    token = create_activation_token(
        license_id=str(lic.id),
        email=lic.email,
        hw_fingerprint=body.hw_fingerprint,
    )

    logger.info("License %s activated for %s from %s", lic.license_key, lic.email, ip)

    return ActivateResponse(
        status="activated",
        token=token,
        expires_at=lic.expires_at,
        activated_at=lic.activated_at,
        plan=lic.plan,
    )


@router.post("/verify", response_model=VerifyResponse)
async def verify(
    body: VerifyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Verify an already-activated license (heartbeat)."""
    ip = _client_ip(request)

    # Validate the JWT token first
    payload = verify_activation_token(body.token)
    if payload is None:
        raise HTTPException(status_code=403, detail="Invalid or expired activation token.")

    lic = await find_license_by_key(db, body.license_key)
    if not lic:
        raise HTTPException(status_code=404, detail="License not found.")

    ok, reason = await verify_license(
        db,
        lic,
        hw_fingerprint=body.hw_fingerprint,
        hw_components=body.hw_components,
        ip_address=ip,
    )

    await db.commit()

    if not ok:
        return VerifyResponse(status="invalid", reason=reason)

    return VerifyResponse(status="valid", expires_at=lic.expires_at)
