"""
license_server/app/schemas.py — Pydantic request / response schemas.
"""

from datetime import datetime
from typing import Dict, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


# ── License activation ────────────────────────────────────────────

class ActivateRequest(BaseModel):
    email: EmailStr
    license_key: str = Field(..., min_length=10, max_length=64)
    hw_fingerprint: str = Field(..., min_length=16, max_length=128)
    hw_components: Dict[str, str] = Field(default_factory=dict)
    machine_name: Optional[str] = None


class ActivateResponse(BaseModel):
    status: str = "activated"
    token: str
    expires_at: Optional[datetime] = None
    activated_at: datetime
    plan: str


# ── License verification ─────────────────────────────────────────

class VerifyRequest(BaseModel):
    license_key: str = Field(..., min_length=10, max_length=64)
    hw_fingerprint: str = Field(..., min_length=16, max_length=128)
    hw_components: Dict[str, str] = Field(default_factory=dict)
    token: str


class VerifyResponse(BaseModel):
    status: str  # "valid" | "invalid"
    expires_at: Optional[datetime] = None
    reason: Optional[str] = None


# ── Admin ─────────────────────────────────────────────────────────

class LicenseCreate(BaseModel):
    email: EmailStr
    plan: str = "monthly"
    expires_at: Optional[datetime] = None
    notes: Optional[str] = None


class LicenseToggle(BaseModel):
    license_id: UUID
    is_active: bool


class LicenseResetHW(BaseModel):
    license_id: UUID


class LicenseOut(BaseModel):
    id: UUID
    email: str
    license_key: str
    plan: str
    is_active: bool
    hw_fingerprint: Optional[str] = None
    machine_name: Optional[str] = None
    activated_at: Optional[datetime] = None
    created_at: datetime
    expires_at: Optional[datetime] = None
    last_verified: Optional[datetime] = None
    payment_id: Optional[str] = None
    payment_amount: Optional[int] = None
    notes: Optional[str] = None
    max_machines: int = 1

    class Config:
        from_attributes = True


class LicenseLogOut(BaseModel):
    id: int
    license_id: Optional[UUID] = None
    action: str
    hw_fingerprint: Optional[str] = None
    ip_address: Optional[str] = None
    details: Optional[dict] = None
    created_at: datetime

    class Config:
        from_attributes = True
