"""
license_server/app/routes/updates.py — Update distribution endpoints.

GET  /api/updates/check?current_version=1.0.0   →  check if an update is available
GET  /api/updates/latest-installer-url           →  get the direct download URL
GET  /api/updates/download                       →  proxy-stream the installer .exe

The installer binary lives on GitHub Releases.  Because the repo may be
private, the /download endpoint streams it through this server using an
authenticated GitHub API request so the desktop client never needs a
GitHub token.
"""

import logging

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse, StreamingResponse

from app.services.update_service import (
    check_update_available,
    get_api_download_url,
    get_latest_download_info,
    _github_headers,
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


@router.get("/download")
async def download_installer():
    """
    Stream the latest installer through the license server.

    The installer binary lives on a **private** GitHub repo, so direct
    ``browser_download_url`` links return 404 for unauthenticated callers.
    This endpoint authenticates with the GitHub API on behalf of the
    desktop client and streams the .exe back as an
    ``application/octet-stream`` response.
    """
    asset = await get_api_download_url()
    if not asset or not asset.get("api_download_url"):
        raise HTTPException(status_code=404, detail="No installer found in latest release.")

    api_url = asset["api_download_url"]
    filename = asset.get("asset_name") or f"ZerodhaPortfolio_Setup_{asset['version']}.exe"
    file_size = asset.get("file_size", 0)

    # Build headers for the GitHub Assets API (requires Accept: application/octet-stream)
    headers = _github_headers()
    headers["Accept"] = "application/octet-stream"

    logger.info("Proxying installer download: %s (%d bytes)", filename, file_size)

    async def _stream():
        async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
            async with client.stream("GET", api_url, headers=headers) as resp:
                if resp.status_code != 200:
                    logger.error("GitHub asset download failed: %s", resp.status_code)
                    return
                async for chunk in resp.aiter_bytes(chunk_size=128 * 1024):
                    yield chunk

    resp_headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
    }
    if file_size:
        resp_headers["Content-Length"] = str(file_size)

    return StreamingResponse(
        _stream(),
        media_type="application/octet-stream",
        headers=resp_headers,
    )
