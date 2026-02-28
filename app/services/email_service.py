"""
license_server/app/services/email_service.py — Send license key emails via Resend.com.

If RESEND_API_KEY is not set, emails are silently skipped (logged instead).
"""

import logging

from app.config import settings

logger = logging.getLogger(__name__)


async def send_license_email(
    to_email: str,
    license_key: str,
    plan: str,
    expires_at: str | None = None,
) -> bool:
    """
    Send the license key to the user's email.
    Returns True on success, False on failure (never raises).
    """
    if not settings.resend_api_key:
        logger.info(
            "[EMAIL-SKIP] No RESEND_API_KEY configured. "
            "Would send key %s to %s (plan=%s)",
            license_key, to_email, plan,
        )
        return False

    try:
        import resend

        resend.api_key = settings.resend_api_key

        subject = "Your Zerodha Portfolio Dashboard License Key"
        expiry_line = f"<p><strong>Expires:</strong> {expires_at}</p>" if expires_at else ""

        html_body = f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;
                     background:#0a0a0a;color:#e0e0e0;padding:40px;border-radius:12px;">
            <h1 style="color:#60a5fa;margin-bottom:8px;">📊 Zerodha Portfolio Dashboard</h1>
            <p style="color:#888;margin-bottom:32px;">Your license is ready!</p>

            <div style="background:#151515;border:1px solid #2a2a2a;border-radius:8px;
                        padding:24px;text-align:center;margin-bottom:24px;">
                <p style="color:#888;font-size:13px;margin-bottom:8px;">YOUR LICENSE KEY</p>
                <p style="font-size:24px;font-weight:700;letter-spacing:2px;
                          color:#60a5fa;font-family:monospace;">{license_key}</p>
            </div>

            <p><strong>Plan:</strong> {plan.title()}</p>
            {expiry_line}

            <hr style="border:none;border-top:1px solid #2a2a2a;margin:24px 0;">

            <h3 style="color:#e0e0e0;">How to activate:</h3>
            <ol style="color:#888;line-height:1.8;">
                <li>Open the Zerodha Portfolio Dashboard application</li>
                <li>Enter your email: <strong>{to_email}</strong></li>
                <li>Paste the license key above</li>
                <li>Click <strong>Activate</strong></li>
            </ol>

            <hr style="border:none;border-top:1px solid #2a2a2a;margin:24px 0;">
            <p style="color:#555;font-size:12px;">
                Need help? Reply to this email or contact support.
            </p>
        </div>
        """

        params = {
            "from": settings.from_email,
            "to": [to_email],
            "subject": subject,
            "html": html_body,
        }
        resend.Emails.send(params)
        logger.info("[EMAIL] License key sent to %s", to_email)
        return True

    except Exception as exc:
        logger.error("[EMAIL] Failed to send to %s: %s", to_email, exc)
        return False
