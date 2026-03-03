"""
license_server/app/routes/download_page.py — Public download page.

Serves a clean HTML page at GET /download where first-time users
can download the application.  The download button links directly to
the GitHub Release asset (CDN-backed, permanent).
"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.services.update_service import get_latest_download_info

logger = logging.getLogger(__name__)
router = APIRouter(tags=["download"])

# ── The full HTML is inline so we don't need a templates directory on Render ──

_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Download — Zerodha Portfolio Dashboard</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        *{{margin:0;padding:0;box-sizing:border-box;}}
        :root{{--bg:#0a0a0a;--card:#151515;--border:#2a2a2a;--text:#e0e0e0;
               --muted:#888;--accent:#60a5fa;--success:#4ade80;--danger:#f87171;}}
        body{{font-family:'Inter',sans-serif;background:var(--bg);color:var(--text);
            line-height:1.6;min-height:100vh;display:flex;flex-direction:column;}}
        .container{{max-width:720px;margin:0 auto;padding:0 24px;flex:1;}}

        .hero{{text-align:center;padding:80px 20px 40px;}}
        .hero h1{{font-size:36px;font-weight:700;letter-spacing:-1px;margin-bottom:12px;}}
        .hero h1 span{{color:var(--accent);}}
        .hero p{{color:var(--muted);font-size:16px;max-width:500px;margin:0 auto;}}

        .download-card{{background:var(--card);border:1px solid var(--border);
            border-radius:16px;padding:40px;text-align:center;margin:30px auto;max-width:520px;}}
        .download-card .version{{font-size:14px;color:var(--muted);margin-bottom:4px;}}
        .download-card .version strong{{color:var(--text);font-size:16px;}}
        .download-card .meta{{font-size:13px;color:var(--muted);margin-top:4px;}}
        .download-card .dl-btn{{display:inline-flex;align-items:center;gap:10px;
            padding:14px 36px;background:var(--accent);color:#000;font-size:16px;
            font-weight:600;border:none;border-radius:10px;cursor:pointer;
            text-decoration:none;margin-top:24px;transition:opacity .2s;}}
        .download-card .dl-btn:hover{{opacity:0.85;}}
        .download-card .dl-btn svg{{width:20px;height:20px;}}

        .notes{{background:var(--card);border:1px solid var(--border);border-radius:12px;
            padding:24px;margin:20px auto;max-width:520px;text-align:left;}}
        .notes h3{{font-size:14px;font-weight:600;margin-bottom:8px;}}
        .notes p,.notes ul{{font-size:13px;color:var(--muted);}}
        .notes ul{{padding-left:20px;margin-top:8px;}}
        .notes ul li{{margin-bottom:4px;}}

        .requirements{{background:var(--card);border:1px solid var(--border);border-radius:12px;
            padding:24px;margin:20px auto;max-width:520px;text-align:left;}}
        .requirements h3{{font-size:14px;font-weight:600;margin-bottom:8px;}}
        .requirements ul{{list-style:none;padding:0;}}
        .requirements ul li{{font-size:13px;color:var(--muted);padding:4px 0;}}
        .requirements ul li::before{{content:'✓ ';color:var(--success);}}

        .no-release{{color:var(--muted);font-size:14px;padding:40px 0;}}

        .footer{{text-align:center;padding:40px 0;border-top:1px solid var(--border);
            color:var(--muted);font-size:12px;margin-top:60px;}}
        .footer a{{color:var(--accent);text-decoration:none;}}
    </style>
</head>
<body>
    <div class="container">
        <section class="hero">
            <h1>📊 Zerodha Portfolio <span>Dashboard</span></h1>
            <p>Download the desktop application for Windows</p>
        </section>

        {download_section}

        <div class="requirements">
            <h3>System Requirements</h3>
            <ul>
                <li>Windows 10 or later (64-bit)</li>
                <li>Internet connection (for stock data &amp; license activation)</li>
                <li>Active Zerodha Kite account with API access</li>
                <li>~150 MB disk space</li>
            </ul>
        </div>

        <div class="notes">
            <h3>Installation</h3>
            <ul>
                <li>Download the installer and run it — no admin rights needed</li>
                <li>The app installs to your user profile (AppData\\Local)</li>
                <li>A desktop shortcut is created automatically</li>
                <li>After install, you'll be prompted to activate with your license key</li>
                <li>Already have a previous version? Just run the new installer — your settings and data are preserved</li>
            </ul>
        </div>
    </div>

    <footer class="footer">
        <p>Zerodha Portfolio Dashboard &copy; 2026 | <a href="mailto:support@example.com">support@example.com</a></p>
    </footer>
</body>
</html>"""


def _download_section_html(info: dict) -> str:
    """Build the download card HTML from release info."""
    version = info.get("version", "?")
    url = info.get("download_url", "#")
    size_mb = info.get("file_size", 0) / (1024 * 1024)
    date = info.get("release_date", "")
    notes = info.get("release_notes", "")

    size_str = f"{size_mb:.1f} MB" if size_mb > 0 else ""
    date_str = f" · Released {date}" if date else ""

    section = f"""
        <div class="download-card">
            <div class="version">Latest version: <strong>v{version}</strong></div>
            <div class="meta">{size_str}{date_str}</div>
            <a href="{url}" class="dl-btn">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                    <polyline points="7 10 12 15 17 10"/>
                    <line x1="12" y1="15" x2="12" y2="3"/>
                </svg>
                Download for Windows
            </a>
        </div>"""

    if notes:
        section += f"""
        <div class="notes">
            <h3>Release Notes — v{version}</h3>
            <p>{notes}</p>
        </div>"""

    return section


def _no_release_html() -> str:
    return '<div class="no-release">No releases available yet. Check back soon!</div>'


@router.get("/download", response_class=HTMLResponse)
async def download_page():
    """
    Public download page for first-time users.

    Fetches the latest release from GitHub and renders a download page
    with a direct link to the installer.
    """
    info = await get_latest_download_info()

    if info:
        download_section = _download_section_html(info)
    else:
        download_section = _no_release_html()

    html = _PAGE_TEMPLATE.format(download_section=download_section)
    return HTMLResponse(content=html)
