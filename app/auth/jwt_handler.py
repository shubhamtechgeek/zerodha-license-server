"""
license_server/app/auth/jwt_handler.py — Create / verify JWT tokens for license activation.
"""

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.config import settings


def create_activation_token(license_id: str, email: str, hw_fingerprint: str) -> str:
    """Create a JWT token embedding the license info."""
    expire = datetime.now(timezone.utc) + timedelta(days=settings.license_jwt_expire_days)
    payload = {
        "sub": str(license_id),
        "email": email,
        "hw": hw_fingerprint,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.license_jwt_secret, algorithm=settings.license_jwt_algorithm)


def verify_activation_token(token: str) -> dict | None:
    """
    Verify and decode a JWT token.
    Returns the payload dict on success, None on failure.
    """
    try:
        payload = jwt.decode(
            token,
            settings.license_jwt_secret,
            algorithms=[settings.license_jwt_algorithm],
        )
        return payload
    except JWTError:
        return None
