"""
license_server/app/services/license_service.py — Core business logic.

Activation, verification, fuzzy hardware matching.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import License, LicenseLog

logger = logging.getLogger(__name__)

# ── Fuzzy matching constants ──────────────────────────────────────
_UNAVAILABLE = "UNAVAILABLE"
FUZZY_MATCH_THRESHOLD = 4  # out of 6 components


def _fuzzy_match(
    current_components: dict, stored_components: dict
) -> Tuple[bool, int, int]:
    """
    Compare two component dicts.
    Returns (is_match, matches, comparable).
    """
    matches = 0
    comparable = 0
    for key in ("cpu", "bios", "motherboard", "disk", "product_id", "machine_guid"):
        cur = current_components.get(key)
        sto = stored_components.get(key)
        if cur == _UNAVAILABLE or sto == _UNAVAILABLE or not cur or not sto:
            continue
        comparable += 1
        if cur == sto:
            matches += 1

    # If very few are comparable, require all to match
    if comparable <= 3:
        return (matches == comparable, matches, comparable)

    return (matches >= FUZZY_MATCH_THRESHOLD, matches, comparable)


async def find_license(
    db: AsyncSession, license_key: str, email: str
) -> Optional[License]:
    """Look up a license by key + email (case-insensitive email)."""
    stmt = select(License).where(
        License.license_key == license_key.strip().upper(),
        License.email == email.strip().lower(),
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def find_license_by_key(
    db: AsyncSession, license_key: str
) -> Optional[License]:
    """Look up a license by key only."""
    stmt = select(License).where(
        License.license_key == license_key.strip().upper()
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def log_action(
    db: AsyncSession,
    license_obj: Optional[License],
    action: str,
    hw_fingerprint: str = "",
    ip_address: str = "",
    details: Optional[dict] = None,
) -> None:
    """Append to the license_logs table."""
    entry = LicenseLog(
        license_id=license_obj.id if license_obj else None,
        action=action,
        hw_fingerprint=hw_fingerprint,
        ip_address=ip_address,
        details=details or {},
    )
    db.add(entry)
    await db.flush()


async def activate_license(
    db: AsyncSession,
    lic: License,
    hw_fingerprint: str,
    hw_components: dict,
    machine_name: str,
    ip_address: str,
) -> Tuple[bool, str]:
    """
    Attempt to activate.
    Returns (success, error_message). On success error_message is empty.
    """
    now = datetime.now(timezone.utc)

    # Check active
    if not lic.is_active:
        await log_action(db, lic, "reject", hw_fingerprint, ip_address,
                         {"reason": "license disabled"})
        return False, "This license has been disabled. Contact support."

    # Check expiry
    if lic.expires_at and lic.expires_at < now:
        await log_action(db, lic, "reject", hw_fingerprint, ip_address,
                         {"reason": "expired"})
        return False, "This license has expired."

    # First activation — no hardware bound yet
    if lic.hw_fingerprint is None:
        lic.hw_fingerprint = hw_fingerprint
        lic.hw_components = hw_components
        lic.machine_name = machine_name
        lic.activated_at = now
        lic.last_verified = now
        await log_action(db, lic, "activate", hw_fingerprint, ip_address,
                         {"type": "first_activation"})
        await db.flush()
        return True, ""

    # Re-activation on same machine (exact match)
    if lic.hw_fingerprint == hw_fingerprint:
        lic.last_verified = now
        lic.machine_name = machine_name  # update in case name changed
        await log_action(db, lic, "activate", hw_fingerprint, ip_address,
                         {"type": "re_activation_exact"})
        await db.flush()
        return True, ""

    # Fuzzy match (hardware upgrade)
    stored = lic.hw_components or {}
    is_match, matches, comparable = _fuzzy_match(hw_components, stored)
    if is_match:
        lic.hw_fingerprint = hw_fingerprint
        lic.hw_components = hw_components
        lic.machine_name = machine_name
        lic.last_verified = now
        await log_action(db, lic, "activate", hw_fingerprint, ip_address, {
            "type": "re_activation_fuzzy",
            "matches": matches,
            "comparable": comparable,
        })
        await db.flush()
        logger.info("Fuzzy match OK (%d/%d) for %s", matches, comparable, lic.license_key)
        return True, ""

    # Different machine — reject
    await log_action(db, lic, "reject", hw_fingerprint, ip_address, {
        "reason": "different_machine",
        "matches": matches,
        "comparable": comparable,
    })
    return False, (
        "This license is already activated on another machine. "
        "Contact support to transfer your license."
    )


async def verify_license(
    db: AsyncSession,
    lic: License,
    hw_fingerprint: str,
    hw_components: dict,
    ip_address: str,
) -> Tuple[bool, str]:
    """
    Verify an already-activated license.
    Returns (is_valid, reason).
    """
    now = datetime.now(timezone.utc)

    if not lic.is_active:
        await log_action(db, lic, "verify_reject", hw_fingerprint, ip_address,
                         {"reason": "disabled"})
        return False, "License has been disabled."

    if lic.expires_at and lic.expires_at < now:
        await log_action(db, lic, "verify_reject", hw_fingerprint, ip_address,
                         {"reason": "expired"})
        return False, "License has expired."

    if lic.hw_fingerprint is None:
        await log_action(db, lic, "verify_reject", hw_fingerprint, ip_address,
                         {"reason": "not_activated"})
        return False, "License has not been activated yet."

    # Exact match
    if lic.hw_fingerprint == hw_fingerprint:
        lic.last_verified = now
        await log_action(db, lic, "verify", hw_fingerprint, ip_address,
                         {"type": "exact"})
        await db.flush()
        return True, ""

    # Fuzzy match
    stored = lic.hw_components or {}
    is_match, matches, comparable = _fuzzy_match(hw_components, stored)
    if is_match:
        lic.hw_fingerprint = hw_fingerprint
        lic.hw_components = hw_components
        lic.last_verified = now
        await log_action(db, lic, "verify", hw_fingerprint, ip_address, {
            "type": "fuzzy",
            "matches": matches,
            "comparable": comparable,
        })
        await db.flush()
        return True, ""

    await log_action(db, lic, "verify_reject", hw_fingerprint, ip_address, {
        "reason": "hw_mismatch",
        "matches": matches,
        "comparable": comparable,
    })
    return False, "Hardware fingerprint does not match. License is bound to another machine."
