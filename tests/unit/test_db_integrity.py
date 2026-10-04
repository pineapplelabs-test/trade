"""Unit tests verifying database integrity and state persistence across restarts."""

import os
import tempfile

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import (
    Account,
    ConfigVersion,
    EquityCurve,
    Fill,
    Instrument,
    MarketSession,
    ModelRun,
    Order,
    Position,
    RiskEvent,
    Signal,
    StrategyVariant,
)


def test_all_12_models_have_primary_keys():
    """Verify all 12 database models define primary keys."""
    models = [
        Instrument,
        Account,
        Signal,
        Order,
        Fill,
        Position,
        EquityCurve,
        RiskEvent,
        ModelRun,
        ConfigVersion,
        StrategyVariant,
        MarketSession,
    ]
    assert len(models) == 12

    for model in models:
        table = model.__table__
        pks = [col.name for col in table.primary_key.columns]
        assert len(pks) >= 1, f"Model {model.__name__} has no primary key!"


@pytest.mark.asyncio
async def test_account_state_survives_restart():
    """Verify database persists account state across engine restart."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
        db_path = tmp_file.name

    db_url = f"sqlite+aiosqlite:///{db_path}"

    try:
        # Phase 1: Initialize DB, insert account with updated equity
        engine1 = create_async_engine(db_url)
        async with engine1.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        session_factory1 = async_sessionmaker(engine1, class_=AsyncSession, expire_on_commit=False)
        async with session_factory1() as session:
            acct = Account(id="persist_test", name="Persist Test", starting_capital=5000.0)
            session.add(acct)
            pos = Position(
                account_id="persist_test",
                token=1001,
                qty=10,
                avg_price=250.0,
                stop=240.0,
                target=270.0,
            )
            session.add(pos)
            await session.commit()

        await engine1.dispose()

        # Phase 2: Simulate complete app restart with a fresh engine connection
        engine2 = create_async_engine(db_url)
        session_factory2 = async_sessionmaker(engine2, class_=AsyncSession, expire_on_commit=False)
        async with session_factory2() as session:
            res_acct = await session.execute(select(Account).where(Account.id == "persist_test"))
            loaded_acct = res_acct.scalar_one_or_none()
            assert loaded_acct is not None
            assert loaded_acct.starting_capital == 5000.0

            res_pos = await session.execute(select(Position).where(Position.account_id == "persist_test"))
            loaded_pos = res_pos.scalar_one_or_none()
            assert loaded_pos is not None
            assert loaded_pos.token == 1001
            assert loaded_pos.qty == 10

        await engine2.dispose()
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
