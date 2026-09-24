"""
database.py — Async SQLAlchemy engine + session factory for Neon Postgres.

Connection strategy:
  - DATABASE_URL  → Neon POOLER string (PgBouncer) — used at runtime.
  - Asyncpg doesn't parse `sslmode`/`channel_binding` query params;
    we strip them and pass ssl=True via connect_args instead.
  - pool_size is deliberately small (5) because Neon's PgBouncer is the
    real connection pool upstream — don't double-pool aggressively.
  - pool_pre_ping=True recovers from Neon's idle-connection timeouts.
"""
import os
import re
from dotenv import load_dotenv

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

# Load .env file automatically
load_dotenv()


def _to_asyncpg_url(url: str) -> str:
    """
    Convert a standard postgresql:// URL to postgresql+asyncpg://
    and strip query params asyncpg can't handle.
    """
    url = re.sub(r"^postgresql://", "postgresql+asyncpg://", url)
    url = re.sub(r"^postgres://", "postgresql+asyncpg://", url)

    # asyncpg doesn't understand these Postgres/PgBouncer params
    for param in ("sslmode", "channel_binding", "connect_timeout"):
        url = re.sub(rf"[?&]{param}=[^&]*", "", url)

    # tidy up any orphaned ? or leading &
    url = re.sub(r"\?&", "?", url)
    url = re.sub(r"&{2,}", "&", url)
    url = re.sub(r"\?$", "", url)
    return url


DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://neondb_owner:npg_ViDAL85XTkGy@ep-wispy-cell-avnuagc7-pooler.c-11.us-east-1.aws.neon.tech/neondb?channel_binding=require&sslmode=require"
)

engine = create_async_engine(
    _to_asyncpg_url(DATABASE_URL),
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    connect_args={"ssl": True},  # asyncpg SSL flag — Neon requires TLS
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def create_db_and_tables() -> None:
    """Create tables if they don't exist. Fine for v1; add Alembic at first migration."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
