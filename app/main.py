"""
JARVIS Backend API - FastAPI Application Entry Point
Multi-model AI, Voice I/O, Web Research, Multi-language support
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import json
from contextlib import asynccontextmanager

from app.config import settings
from app.routers import auth, chat, voice, health, research
from app.db import init_db

# ─── Logging Configuration ───
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ─── Lifespan Context Manager ───
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup and shutdown events.
    Initialize connections, cleanup resources.
    """
    # Startup
    logger.info("[JARVIS Backend] Starting up...")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Debug: {settings.debug}")
    logger.info(f"Database: {settings.database_url}")
    logger.info(f"AI Model: {settings.preferred_model}")

    # Initialize database tables
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")

    yield

    # Shutdown
    logger.info("[JARVIS Backend] Shutting down...")


# ─── FastAPI Application Factory ───
def create_app() -> FastAPI:
    """Create and configure FastAPI application"""

    app = FastAPI(
        title=settings.api_title,
        description=settings.api_description,
        version=settings.api_version,
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url="/api/v1/redoc",
        lifespan=lifespan,
    )

    # ─── Middleware Stack ───

    # ─── Custom Middleware ───

    @app.middleware("http")
    async def auth_header_middleware(request, call_next):
        """Extract Authorization header and add to request.state for easy access"""
        auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
        if auth_header:
            request.state.auth_header = auth_header
        response = await call_next(request)
        return response

    # CORS - Allow cross-origin requests from web/mobile clients
    logger.info(f"CORS Origins configured: {settings.cors_origins}")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=r"https://.*\.vercel\.app.*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ─── API Routers ───
    app.include_router(
        health.router,
        tags=["Health"],
    )
    app.include_router(
        auth.router,
        prefix="/api/v1/auth",
        tags=["Authentication"],
    )
    app.include_router(
        chat.router,
        prefix="/api/v1/chat",
        tags=["Chat"],
    )
    app.include_router(
        voice.router,
        prefix="/api/v1/voice",
        tags=["Voice"],
    )
    app.include_router(
        research.router,
        prefix="/api/v1/research",
        tags=["Research"],
    )

    # ─── Root Endpoint ───
    @app.get("/")
    async def root():
        """API root - returns service information"""
        return {
            "service": "JARVIS Backend API",
            "version": settings.api_version,
            "status": "operational",
            "docs_url": "/api/v1/docs",
            "environment": settings.environment,
        }

    # ─── Error Handlers ───
    @app.exception_handler(Exception)
    async def general_exception_handler(request, exc):
        """Handle unexpected exceptions"""
        logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "error_type": type(exc).__name__,
            },
        )

    return app


# ─── Application Instance ───
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
