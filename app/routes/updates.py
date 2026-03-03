"""
license_server/app/routes/updates.py — Update distribution endpoints.

GET  /api/updates/check?current_version=1.0.0   →  check if an update is available
GET  /api/updates/latest-installer-url           →  get the direct download URL

Installers are hosted on GitHub Releases (permanent, CDN-backed).
The license server never stores or proxies the .exe file.
"""

import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.services.update_service import (
    check_update_available,
    get_latest_download_info,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/updates", tags=["updates"])


@router.get("/check")
async def check_for_update(current_version: str = Query(..., description="Client's current app version")):
    """
    Check whether a newer version is available.

    Returns version info and a **direct GitHub CDN download URL**.
    The desktop client downloads from GitHub, not through this server.
    """
    result = await check_update_available(current_version)
    return result


@router.get("/latest-installer-url")
async def latest_installer_url():
    """
    Return the download URL and version of the latest release.

    Used by:
      - Legacy users who need a link to manually download the latest version.
      - The /download webpage to populate the download button.
    """
    info = await get_latest_download_info()
    if not info:
        raise HTTPException(status_code=404, detail="No releases found.")

    return {
        "version": info["version"],
        "download_url": info["download_url"],
        "file_size": info.get("file_size", 0),
        "release_notes": info.get("release_notes", ""),
        "release_date": info.get("release_date", ""),
        "html_url": info.get("html_url", ""),
    }
