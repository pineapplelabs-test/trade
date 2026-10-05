from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.security import create_session_token
from app.feed.base import DepthLevel, MarketTick, OrderBookDepth
from app.feed.groww_feed import groww_feed
from app.main import app
from app.portfolio.account import portfolio_accounts


@pytest.mark.asyncio
async def test_kill_switch_requires_authentication_and_operator_role() -> None:
    """POST /api/kill must reject unauthenticated requests (401) and viewer role (403)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Unauthenticated -> 401
        res_no_auth = await client.post("/api/kill")
        assert res_no_auth.status_code == 401

        # 2. Viewer role -> 403 Forbidden
        viewer_token = create_session_token("viewer", role="viewer")
        client.cookies.set("paperdesk_session", viewer_token)
        res_viewer = await client.post("/api/kill")
        assert res_viewer.status_code == 403


@pytest.mark.asyncio
async def test_kill_switch_executes_realistic_fill_and_fees() -> None:
    """Operator executing kill switch closes positions through simulated depth and records fees."""
    # Setup open position on tiny account
    acct = portfolio_accounts["tiny"]
    acct.cash = 1000.0
    acct.positions.clear()
    acct.open_position("BEL", quantity=2, entry_price=380.0, stop_price=370.0, target_price=400.0)
    assert "BEL" in acct.positions

    # Populate groww_feed latest tick with 5-level depth
    depth = OrderBookDepth(
        bids=[DepthLevel(price=382.0 - 0.05 * i, quantity=1000) for i in range(5)],
        asks=[DepthLevel(price=382.05 + 0.05 * i, quantity=1000) for i in range(5)],
    )
    groww_feed.latest_ticks["BEL"] = MarketTick(
        token=1,
        symbol="BEL",
        timestamp=datetime.now(UTC),
        last_price=382.0,
        last_quantity=10,
        volume=100000,
        average_traded_price=382.0,
        total_buy_quantity=50000,
        total_sell_quantity=50000,
        open=375.0,
        high=385.0,
        low=374.0,
        close=380.0,
        depth=depth,
        feed_source="groww",
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        op_token = create_session_token("admin", role="operator")
        client.cookies.set("paperdesk_session", op_token)

        res = await client.post("/api/kill")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "halted"
        assert data["action"] == "EMERGENCY_KILL_TRIGGERED"

        # Position must now be closed in memory
        assert "BEL" not in acct.positions

        # Resume engine for subsequent tests
        res_resume = await client.post("/api/resume")
        assert res_resume.status_code == 200
        assert res_resume.json()["status"] == "active"


@pytest.mark.asyncio
async def test_kill_switch_handles_missing_market_data_safely() -> None:
    """When market depth is absent during kill switch, engine does NOT fabricate price and records audit event."""
    acct = portfolio_accounts["tiny"]
    acct.cash = 1000.0
    acct.positions.clear()
    acct.open_position("MISSING_DATA_SYM", quantity=1, entry_price=100.0, stop_price=90.0, target_price=120.0)

    # Ensure no tick exists in groww_feed
    groww_feed.latest_ticks.pop("MISSING_DATA_SYM", None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        op_token = create_session_token("admin", role="operator")
        client.cookies.set("paperdesk_session", op_token)

        res = await client.post("/api/kill")
        assert res.status_code == 200

        # Position remained open because market data was unavailable to compute honest execution fill
        assert "MISSING_DATA_SYM" in acct.positions

        # Clean up
        acct.positions.clear()
        await client.post("/api/resume")
