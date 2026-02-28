"""
license_server/app/services/key_generator.py — Generate unique license keys.

Format:  ZRDH-XXXX-XXXX-XXXX-XXXX
Charset: ABCDEFGHJKMNPQRSTUVWXYZ23456789 (no ambiguous 0/O/1/I/L)
"""

import secrets

_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def generate_license_key() -> str:
    """Generate a cryptographically random license key."""
    groups = [
        "".join(secrets.choice(_CHARS) for _ in range(4))
        for _ in range(4)
    ]
    return "ZRDH-" + "-".join(groups)
