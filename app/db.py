"""
Database configuration and session management
Supports both SQLite (local dev) and PostgreSQL (production)
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
import logging
from app.config import settings
from app.models import Base

logger = logging.getLogger(__name__)

# ─── Database URL Selection ───

def get_database_url() -> str:
    """Get appropriate database URL based on configuration"""

    # For local development, default to SQLite
    # PostgreSQL support can be enabled when deployed with proper async drivers
    logger.info("Using SQLite database (local development)")
    return settings.sqlite_url


# ─── SQLite Special Configuration ───

def configure_sqlite(dbapi_conn, connection_record):
    """Enable foreign keys for SQLite"""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# ─── Engine Creation ───

database_url = get_database_url()
logger.info(f"Database URL: {database_url[:50]}...")

# Create engine with appropriate settings
if "sqlite" in database_url:
    # SQLite configuration for local development
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=settings.debug,
    )
    # Enable foreign keys for SQLite
    event.listen(engine, "connect", configure_sqlite)
else:
    # PostgreSQL configuration for production
    engine = create_engine(
        database_url,
        echo=settings.debug,
        pool_pre_ping=True,  # Verify connections before using
        pool_size=20,
        max_overflow=40,
    )

# ─── Session Factory ───

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


# ─── Dependency Injection ───

def get_db() -> Session:
    """
    Dependency for FastAPI endpoints to get database session

    Usage in endpoint:
        @app.get("/users")
        async def get_users(db: Session = Depends(get_db)):
            return db.query(User).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ─── Initialize Database ───

def init_db():
    """Create all tables in database"""
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialized")


def drop_db():
    """Drop all tables (for testing/reset)"""
    Base.metadata.drop_all(bind=engine)
    logger.warning("Database tables dropped")


# ─── Context Manager ───

class DatabaseSession:
    """Context manager for database sessions"""

    def __init__(self):
        self.db = None

    def __enter__(self) -> Session:
        self.db = SessionLocal()
        return self.db

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.db.close()
