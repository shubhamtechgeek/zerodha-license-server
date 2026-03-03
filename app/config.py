"""
license_server/app/config.py — Application settings from environment variables.
"""

from typing import List, Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/licenses"

    # JWT
    license_jwt_secret: str = "change-me"
    license_jwt_algorithm: str = "HS256"
    license_jwt_expire_days: int = 30

    # Admin
    admin_api_key: str = "change-me"
    admin_password: str = "change-me"

    # Razorpay
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    # Email (Resend.com)
    resend_api_key: str = ""
    from_email: str = "noreply@yourdomain.com"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: List[str] = ["http://localhost:5000", "http://127.0.0.1:5000"]

    # GitHub Releases — used for update distribution
    # Set these in your Render environment variables
    github_token: str = ""          # Personal Access Token with repo scope
    github_owner: str = "shubhamtechgeek"
    github_repo: str = "zerodha-license-server"  # or a dedicated releases repo

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
