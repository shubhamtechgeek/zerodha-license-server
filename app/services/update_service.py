"""
license_server/app/services/update_service.py — Application update service.

Uses **GitHub Releases** as the permanent storage layer for installer files.
The license server never stores the .exe — it reads the GitHub Releases API
to discover the latest version and returns a direct GitHub CDN download URL
to the desktop client.

Expected GitHub Release structure (created by publish_update.ps1):
    Tag:    v1.1.0
    Assets: ZerodhaPortfolio_Setup_1.1.0.exe   (the Inno Setup installer)
            ZerodhaPortfolio_Setup_1.1.0.exe.sha256   (plain-text SHA-256 hash)

The release body may contain a YAML-like metadata block:
    mandatory: true
    min_version: 1.0.0
    ---
    Release notes here...
"""

import logging
import re
import time
from typing import Optional

import httpx
from packaging.version import Version, InvalidVersion

from app.config import settings

logger = logging.getLogger(__name__)

# ── In-memory cache for GitHub API responses ──────────────────────────────
# Avoids hitting the GitHub API rate limit (60/hr unauthenticated, 5000/hr with token)
_cache: dict = {}
_CACHE_TTL = 300  # 5 minutes


def _parse_version(v: str) -> Optional[Version]:
    """Safely parse a PEP 440 version string."""
    try:
        return Version(v)
    except InvalidVersion:
        return None


def _github_headers() -> dict:
    """Build headers for the GitHub API. Adds auth token if configured."""
    headers = {"Accept": "application/vnd.github+json"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    return headers


def _parse_release_body(body: str) -> dict:
    """
    Parse the release body for optional metadata and release notes.

    Format:
        mandatory: true
        min_version: 1.0.0
        ---
        Actual release notes here...

    If there is no --- separator, the entire body is treated as release notes.
    """
    metadata = {"mandatory": False, "min_version": "", "release_notes": ""}
    if not body:
        return metadata

    # Check for a --- separator
    if "---" in body:
        parts = body.split("---", 1)
        meta_section = parts[0].strip()
        metadata["release_notes"] = parts[1].strip()

        # Parse key: value lines from the metadata section
        for line in meta_section.splitlines():
            line = line.strip()
            if line.lower().startswith("mandatory:"):
                val = line.split(":", 1)[1].strip().lower()
                metadata["mandatory"] = val in ("true", "yes", "1")
            elif line.lower().startswith("min_version:"):
                metadata["min_version"] = line.split(":", 1)[1].strip()
    else:
        metadata["release_notes"] = body.strip()

    return metadata


async def get_latest_release_from_github() -> Optional[dict]:
    """
    Fetch the latest release from GitHub Releases API.

    Returns a normalized dict with:
        version, release_date, release_notes, download_url, file_size,
        sha256, mandatory, min_version, html_url
    Or None if no release is found / API fails.
    """
    now = time.time()

    # Check cache
    cached = _cache.get("latest_release")
    if cached and (now - cached["ts"]) < _CACHE_TTL:
        logger.debug("GitHub release cache hit (age %.0fs)", now - cached["ts"])
        return cached["data"]

    owner = settings.github_owner
    repo = settings.github_repo
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=_github_headers())

            if resp.status_code == 404:
                logger.info("No releases found for %s/%s", owner, repo)
                return None

            resp.raise_for_status()
            data = resp.json()

        # Extract version from tag (strip leading 'v')
        tag = data.get("tag_name", "")
        version = tag.lstrip("v")
        if not _parse_version(version):
            logger.warning("Invalid version tag: %s", tag)
            return None

        # Find the .exe asset and .sha256 asset
        download_url = ""
        file_size = 0
        sha256_url = ""

        for asset in data.get("assets", []):
            name = asset.get("name", "")
            if name.endswith(".exe") and "Setup" in name:
                download_url = asset.get("browser_download_url", "")
                file_size = asset.get("size", 0)
            elif name.endswith(".sha256"):
                sha256_url = asset.get("browser_download_url", "")

        if not download_url:
            logger.warning("No .exe asset found in release %s", tag)
            return None

        # Fetch SHA-256 hash if the .sha256 file exists
        sha256 = ""
        if sha256_url:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    hash_resp = await client.get(sha256_url)
                    if hash_resp.status_code == 200:
                        # .sha256 file format: "hexhash  filename" or just "hexhash"
                        sha256_text = hash_resp.text.strip()
                        sha256 = sha256_text.split()[0] if sha256_text else ""
            except Exception as exc:
                logger.warning("Failed to fetch .sha256 asset: %s", exc)

        # Parse release body for metadata
        body_meta = _parse_release_body(data.get("body", ""))

        release_date = data.get("published_at", "")
        if release_date:
            release_date = release_date[:10]  # "2026-03-03T..." → "2026-03-03"

        result = {
            "version": version,
            "release_date": release_date,
            "release_notes": body_meta["release_notes"],
            "download_url": download_url,
            "file_size": file_size,
            "sha256": sha256,
            "mandatory": body_meta["mandatory"],
            "min_version": body_meta["min_version"],
            "html_url": data.get("html_url", ""),
        }

        # Update cache
        _cache["latest_release"] = {"data": result, "ts": now}
        logger.info("Fetched latest release from GitHub: v%s", version)
        return result

    except httpx.HTTPStatusError as exc:
        logger.error("GitHub API error: %s %s", exc.response.status_code, exc.response.text[:200])
        return None
    except Exception as exc:
        logger.error("Failed to fetch latest release: %s", exc)
        return None


async def check_update_available(current_version: str) -> dict:
    """
    Compare the client's current version with the latest GitHub release.

    Returns a dict suitable for the /api/updates/check response.
    """
    release = await get_latest_release_from_github()

    if not release:
        return {
            "update_available": False,
            "current_version": current_version,
            "latest_version": current_version,
        }

    latest_ver = _parse_version(release["version"])
    current_ver = _parse_version(current_version)

    if not latest_ver or not current_ver:
        return {
            "update_available": False,
            "current_version": current_version,
            "latest_version": release.get("version", current_version),
            "error": "Invalid version format",
        }

    update_available = latest_ver > current_ver

    # Check min_version — if client is below min_version, update is mandatory
    mandatory = release.get("mandatory", False)
    min_ver_str = release.get("min_version", "")
    if min_ver_str:
        min_ver = _parse_version(min_ver_str)
        if min_ver and current_ver < min_ver:
            mandatory = True

    result = {
        "update_available": update_available,
        "current_version": current_version,
        "latest_version": release["version"],
        "release_notes": release.get("release_notes", ""),
        "release_date": release.get("release_date", ""),
        "mandatory": mandatory,
    }

    if update_available:
        # Direct GitHub CDN download URL — client downloads from here
        result["download_url"] = release["download_url"]
        result["file_size"] = release.get("file_size", 0)
        result["sha256"] = release.get("sha256", "")

    return result


async def get_latest_download_info() -> Optional[dict]:
    """
    Get download info for the latest release (used by /download page).

    Returns dict with version, download_url, file_size, release_notes, html_url.
    """
    return await get_latest_release_from_github()
