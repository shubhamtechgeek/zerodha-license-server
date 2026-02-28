"""
license_server/app/main.py — FastAPI application entry point.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine
from app.models import Base
from app.routes import admin, license, webhook

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables on startup (dev convenience — use Alembic for prod)."""
    logger.info("Creating database tables if they don't exist...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database ready.")
    yield
    await engine.dispose()


app = FastAPI(
    title="Zerodha Portfolio Dashboard — License Server",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(license.router)
app.include_router(webhook.router)
app.include_router(admin.router)


@app.get("/")
async def root():
    return {
        "service": "Zerodha Portfolio Dashboard — License Server",
        "status": "running",
        "docs": "/docs",
        "admin": "/admin/dashboard",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
