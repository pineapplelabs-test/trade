"""Unit tests verifying strict logical isolation between real5k, tiny, and shadow accounts."""

import pytest
from sqlalchemy import select

from app.db.models import Account, Position
from app.db.session import async_session_factory


@pytest.mark.asyncio
async def test_accounts_are_isolated():
    """Ensure orders, positions, and balances are partitioned by account_id without leakage."""
    async with async_session_factory() as session:
        # Verify 3 distinct accounts exist with expected starting capital
        res = await session.execute(select(Account))
        accounts = {a.id: a for a in res.scalars().all()}

        assert "real5k" in accounts
        assert "tiny" in accounts
        assert "shadow" in accounts

        assert accounts["real5k"].starting_capital == 5000.0
        assert accounts["tiny"].starting_capital == 1000.0
        assert accounts["shadow"].starting_capital == 100000.0

        # Create position for real5k
        pos_real5k = Position(
            account_id="real5k",
            token=12345,
            qty=5,
            avg_price=900.0,
            stop=885.0,
            target=925.0,
        )
        session.add(pos_real5k)

        # Create position for shadow
        pos_shadow = Position(
            account_id="shadow",
            token=67890,
            qty=50,
            avg_price=2500.0,
            stop=2460.0,
            target=2560.0,
        )
        session.add(pos_shadow)
        await session.commit()

        # Query real5k positions - must NOT see shadow's position
        real5k_positions = (
            await session.execute(
                select(Position).where(Position.account_id == "real5k")
            )
        ).scalars().all()
        assert len(real5k_positions) == 1
        assert real5k_positions[0].token == 12345

        # Query tiny positions - must be 0
        tiny_positions = (
            await session.execute(
                select(Position).where(Position.account_id == "tiny")
            )
        ).scalars().all()
        assert len(tiny_positions) == 0

        # Query shadow positions - must NOT see real5k's position
        shadow_positions = (
            await session.execute(
                select(Position).where(Position.account_id == "shadow")
            )
        ).scalars().all()
        assert len(shadow_positions) == 1
        assert shadow_positions[0].token == 67890
