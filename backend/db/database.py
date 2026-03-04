from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from backend.config import settings

# Render/Neon provide postgresql:// but SQLAlchemy async needs postgresql+asyncpg://
_url = settings.DATABASE_URL
if _url.startswith("postgresql://"):
    _url = _url.replace("postgresql://", "postgresql+asyncpg://", 1)
elif _url.startswith("postgres://"):
    _url = _url.replace("postgres://", "postgresql+asyncpg://", 1)

if "sqlite" in _url:
    # SQLite: needs check_same_thread=False
    _connect_args = {"check_same_thread": False}
else:
    # PostgreSQL via asyncpg: strip ?sslmode=... from URL and pass ssl=True instead
    # asyncpg does not recognise the 'sslmode' query parameter
    if "sslmode" in _url:
        _url = _url.split("?")[0]  # remove all query params
    _connect_args = {"ssl": True}

engine = create_async_engine(_url, echo=False, connect_args=_connect_args)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
