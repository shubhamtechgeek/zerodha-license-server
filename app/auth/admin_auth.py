"""
license_server/app/auth/admin_auth.py — Simple API-key auth for admin endpoints.
"""

from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader

from app.config import settings

_api_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)


async def require_admin_key(api_key: str = Security(_api_key_header)) -> str:
    """FastAPI dependency — reject requests without a valid admin API key."""
    if not api_key or api_key != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="Invalid or missing admin API key")
    return api_key
