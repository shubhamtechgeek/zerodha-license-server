"""
license_server/app/routes/admin.py — Admin API + dashboard page.

All API endpoints require X-Admin-Key header.
The HTML dashboard uses session cookie auth (admin password).
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.admin_auth import require_admin_key
from app.config import settings
from app.database import get_db
from app.models import License, LicenseLog
from app.schemas import LicenseCreate, LicenseLogOut, LicenseOut, LicenseResetHW, LicenseToggle
from app.services.key_generator import generate_license_key
from app.services.license_service import log_action

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


# ── Admin HTML Dashboard ──────────────────────────────────────────

@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard():
    """Serve the admin panel HTML."""
    import os
    template_path = os.path.join(os.path.dirname(__file__), "..", "templates", "admin.html")
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>Admin template not found</h1><p>Place admin.html in app/templates/</p>",
            status_code=500,
        )


# ── Admin API Endpoints ───────────────────────────────────────────

@router.get("/api/licenses", response_model=list[LicenseOut])
async def list_licenses(
    search: Optional[str] = Query(None, description="Search by email or key"),
    status: Optional[str] = Query(None, description="Filter: active, inactive, expired, unactivated"),
    _key: str = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
):
    """List all licenses with optional search/filter."""
    stmt = select(License).order_by(License.created_at.desc())

    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            or_(
                License.email.ilike(pattern),
                License.license_key.ilike(pattern),
            )
        )

    now = datetime.now(timezone.utc)
    if status == "active":
        stmt = stmt.where(License.is_active == True, License.hw_fingerprint.isnot(None))
    elif status == "inactive":
        stmt = stmt.where(License.is_active == False)
    elif status == "expired":
        stmt = stmt.where(License.expires_at < now)
    elif status == "unactivated":
        stmt = stmt.where(License.hw_fingerprint.is_(None))

    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/api/licenses/{license_id}", response_model=LicenseOut)
async def get_license(
    license_id: UUID,
    _key: str = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
):
    """Get a single license by ID."""
    lic = await db.get(License, license_id)
    if not lic:
        raise HTTPException(status_code=404, detail="License not found")
    return lic


@router.get("/api/licenses/{license_id}/logs", response_model=list[LicenseLogOut])
async def get_license_logs(
    license_id: UUID,
    _key: str = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
):
    """Get logs for a specific license."""
    stmt = (
        select(LicenseLog)
        .where(LicenseLog.license_id == license_id)
        .order_by(LicenseLog.created_at.desc())
        .limit(100)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/api/license/create", response_model=LicenseOut)
async def create_license(
    body: LicenseCreate,
    _key: str = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
):
    """Manually create a new license."""
    now = datetime.now(timezone.utc)
    license_key = generate_license_key()

    # Default expiry based on plan
    expires_at = body.expires_at
    if not expires_at:
        if body.plan == "monthly":
            expires_at = now + timedelta(days=30)
        elif body.plan == "yearly":
            expires_at = now + timedelta(days=365)
        # lifetime → None

    lic = License(
        email=body.email.strip().lower(),
        license_key=license_key,
        plan=body.plan,
        is_active=True,
        created_at=now,
        expires_at=expires_at,
        notes=body.notes,
    )
    db.add(lic)
    await db.flush()

    await log_action(db, lic, "created_manually", details={"plan": body.plan})
    await db.commit()
    await db.refresh(lic)

    logger.info("Admin created license: %s for %s", license_key, body.email)
    return lic


@router.post("/api/license/toggle", response_model=LicenseOut)
async def toggle_license(
    body: LicenseToggle,
    _key: str = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
):
    """Enable or disable a license."""
    lic = await db.get(License, body.license_id)
    if not lic:
        raise HTTPException(status_code=404, detail="License not found")

    lic.is_active = body.is_active
    await log_action(db, lic, "toggled", details={"is_active": body.is_active})
    await db.commit()
    await db.refresh(lic)

    logger.info("License %s %s", lic.license_key, "enabled" if body.is_active else "disabled")
    return lic


@router.post("/api/license/reset-hw", response_model=LicenseOut)
async def reset_hardware(
    body: LicenseResetHW,
    _key: str = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
):
    """Clear hardware binding so the user can re-activate on a new machine."""
    lic = await db.get(License, body.license_id)
    if not lic:
        raise HTTPException(status_code=404, detail="License not found")

    lic.hw_fingerprint = None
    lic.hw_components = None
    lic.machine_name = None
    lic.activated_at = None
    await log_action(db, lic, "hw_reset", details={"reason": "admin_reset"})
    await db.commit()
    await db.refresh(lic)

    logger.info("Hardware binding reset for %s", lic.license_key)
    return lic


@router.get("/api/stats")
async def admin_stats(
    _key: str = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
):
    """Return dashboard statistics."""
    now = datetime.now(timezone.utc)

    total = await db.scalar(select(func.count(License.id)))
    active = await db.scalar(
        select(func.count(License.id)).where(
            License.is_active == True, License.hw_fingerprint.isnot(None)
        )
    )
    expired = await db.scalar(
        select(func.count(License.id)).where(License.expires_at < now)
    )
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    activations_today = await db.scalar(
        select(func.count(LicenseLog.id)).where(
            LicenseLog.action == "activate",
            LicenseLog.created_at >= today_start,
        )
    )

    # Revenue this month
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    revenue = await db.scalar(
        select(func.coalesce(func.sum(License.payment_amount), 0)).where(
            License.created_at >= month_start,
            License.payment_amount.isnot(None),
        )
    )

    return {
        "total_licenses": total or 0,
        "active_licenses": active or 0,
        "expired_licenses": expired or 0,
        "activations_today": activations_today or 0,
        "revenue_this_month_paise": revenue or 0,
    }
