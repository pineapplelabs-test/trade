"""Database session factory and initialization logic."""

import json
from collections.abc import AsyncGenerator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_accounts_config, get_settings
from app.db.base import Base
from app.db.models import Account

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for providing an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create all tables and seed default configured accounts."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed accounts if not already present
    async with async_session_factory() as session:
        accounts_cfg = get_accounts_config()
        for acct_id, acct_data in accounts_cfg.items():
            existing = await session.execute(select(Account).where(Account.id == acct_id))
            if existing.scalar_one_or_none() is None:
                new_account = Account(
                    id=acct_id,
                    name=acct_data.get("name", acct_id),
                    starting_capital=float(acct_data.get("starting_capital", 1000.0)),
                    config_json=json.dumps(acct_data),
                )
                session.add(new_account)
        await session.commit()
