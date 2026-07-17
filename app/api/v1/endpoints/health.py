"""Health & readiness probes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.database import get_session

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Liveness: process is up."""
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env.value}


@router.get("/ready")
async def ready(session: Annotated[AsyncSession, Depends(get_session)]) -> dict:
    """Readiness: dependencies (DB) are reachable."""
    checks = {"database": "ok"}
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"error: {exc}"
    status = "ready" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": status, "checks": checks}
