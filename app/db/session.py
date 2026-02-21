import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.pool import NullPool
from app.config import settings
from app.db.base_class import Base

# Configure logger
logger = logging.getLogger("db")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | DB     | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)

logger.info("Initializing database module...")

# Use psycopg (async) driver for better compatibility with Supabase transaction mode
DATABASE_URL = settings.DATABASE_URL

if DATABASE_URL.startswith("postgresql+asyncpg://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg://")
    logger.debug(f"Driver changed: asyncpg → psycopg")

logger.info("Creating async SQLAlchemy engine...")
try:
    engine = create_async_engine(
        DATABASE_URL,
        echo=settings.DEBUG,
        future=True,
        poolclass=NullPool,
        connect_args={
            "application_name": "web_chatbot",
        }
    )
    logger.info("SQLAlchemy async engine created successfully.")
except Exception as e:
    logger.error(f"Failed to create database engine: {e}")
    raise

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

async def get_db():
    """Dependency function for FastAPI to get database sessions."""
    session = async_session_factory()
    logger.debug(f"New database session opened")
    try:
        yield session
        await session.commit()
        logger.debug(f"Session committed successfully")
    except Exception as e:
        await session.rollback()
        logger.error(f"Session rolled back due to error: {type(e).__name__}: {e}")
        raise
    finally:
        await session.close()
        logger.debug(f"Database session closed")

async def init_db():
    """Initialize database tables."""
    logger.info("Starting database initialization...")
    try:
        async with engine.begin() as conn:
            logger.debug("Acquired connection for schema creation.")
            # Don't create tables - assume they exist in Supabase
            pass
        logger.info("Database initialization completed successfully.")
    except Exception as e:
        logger.error(f"Database initialization failed: {type(e).__name__}: {e}")
        raise

async def close_db():
    """Close database engine and clean up connections."""
    logger.info("Shutting down database engine...")
    try:
        await engine.dispose()
        logger.info("Database engine disposed successfully.")
    except Exception as e:
        logger.error(f"Error during engine disposal: {e}")
        raise
