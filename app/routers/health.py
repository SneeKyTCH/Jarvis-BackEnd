"""Health check endpoints"""

from fastapi import APIRouter, HTTPException
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health")
async def health_check():
    """
    Health check endpoint - basic liveness probe
    Used by load balancers and Kubernetes
    """
    return {
        "status": "healthy",
        "service": "JARVIS Backend API",
    }


@router.get("/health/ready")
async def readiness_check():
    """
    Readiness check - verify dependencies are available
    Database, Redis, external APIs, etc.
    """
    checks = {
        "database": "pending",
        "cache": "pending",
        "llm_api": "pending",
        "voice_api": "pending",
    }

    # TODO: Add actual dependency checks
    # For now, all pass in development
    checks["database"] = "ok"
    checks["cache"] = "ok"
    checks["llm_api"] = "ok"
    checks["voice_api"] = "ok"

    all_ok = all(v == "ok" for v in checks.values())

    if not all_ok:
        raise HTTPException(status_code=503, detail="Service not ready")

    return {
        "status": "ready",
        "checks": checks,
    }


@router.get("/health/live")
async def liveness_check():
    """
    Liveness check - verify service is running
    Used by Kubernetes for restart decisions
    """
    return {
        "status": "alive",
        "service": "JARVIS Backend API",
    }
