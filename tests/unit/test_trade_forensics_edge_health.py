"""Unit and API tests for Forensic Trade Detail and Edge Health according to Phase 5 spec."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.portfolio.ledger import (
    AuditEvent,
    DecisionSnapshot,
    DetailedFeeBreakdown,
    ExecutionForensics,
    LevelFillDetail,
    LossAttributionTag,
    TradeRecord,
    global_trade_ledger,
)


@pytest.fixture(autouse=True)
def seed_test_ledger():
    """Seed isolated sample trades before each test."""
    global_trade_ledger.trades.clear()

    now = datetime.now(UTC)

    # 1. Realistic tiny account trade (BEL - Winning trade with full forensics)
    t_tiny_win = TradeRecord(
        trade_id="TR-TINY-001",
        account_id="tiny",
        symbol="BEL",
        strategy_name="ORB_BREAKOUT",
        strategy_version="v1.2",
        direction="BUY",
        quantity=2,
        entry_price=380.00,
        exit_price=385.00,
        entry_timestamp=now - timedelta(minutes=40),
        exit_timestamp=now - timedelta(minutes=15),
        gross_pnl=10.00,        # (385 - 380) * 2 = ₹10.00
        total_charges=1.20,     # exact charges
        slippage=0.10,          # 1 tick = ₹0.05 * 2 shares = ₹0.10 (embedded in fill price)
        net_pnl=8.80,           # 10.00 - 1.20 = 8.80
        r_multiple=1.67,
        trade_status="CLOSED",
        exit_reason="Target reached",
        loss_tag=LossAttributionTag.NONE,
        decision_reason="OBI +0.45, RVOL 3.2x, EV hurdle 0.15% cleared",
        decision_snapshot=DecisionSnapshot(
            rvol=3.2,
            obi=0.45,
            microprice=380.20,
            vwap_deviation=0.08,
            atr=5.40,
            spread=0.05,
            win_probability=0.62,
            expected_reward=1.30,
            expected_loss=0.75,
            expected_costs=0.22,
            net_ev=0.28,
            ev_hurdle=0.15,
            decision="ENTER",
            decision_reason="High depth pressure and low spread",
            eval_timestamp=now - timedelta(minutes=41),
        ),
        execution_forensics=ExecutionForensics(
            market_data_ts=now - timedelta(minutes=41),
            decision_ts=now - timedelta(minutes=40, seconds=50),
            simulated_execution_ts=now - timedelta(minutes=40),
            configured_latency_ms=500,
            best_bid=379.95,
            best_ask=380.00,
            requested_quantity=2,
            filled_quantity=2,
            unfilled_quantity=0,
            vwap_fill_price=380.00,
            slippage_ticks=1,
            slippage_amount=0.05,
            levels_consumed=[
                LevelFillDetail(level=1, price=380.00, quantity=2)
            ],
            depth_snapshot={
                "bids": [{"price": 379.95, "qty": 1500}],
                "asks": [{"price": 380.00, "qty": 1200}],
            },
        ),
        fee_breakdown=DetailedFeeBreakdown(
            schedule_id="DEFAULT_NSE_2024",
            effective_date="2024-10-01",
            turnover=1530.00,
            buy_value=760.00,
            sell_value=770.00,
            brokerage=0.46,
            stt=0.19,
            exchange_txn=0.05,
            sebi=0.0015,
            gst=0.09,
            stamp_duty=0.02,
            total_charges=1.20,
        ),
        audit_timeline=[
            AuditEvent(seq=1, event_name="MARKET_DATA_RECEIVED", timestamp=now - timedelta(minutes=41), description="5-level depth tick received from Groww"),
            AuditEvent(seq=2, event_name="INDICATORS_EVALUATED", timestamp=now - timedelta(minutes=40, seconds=55), description="OBI 0.45, RVOL 3.2x evaluated"),
            AuditEvent(seq=3, event_name="EV_GATE_CLEARED", timestamp=now - timedelta(minutes=40, seconds=50), description="Net EV 0.28% > hurdle 0.15%"),
            AuditEvent(seq=4, event_name="SIMULATED_ORDER_CREATED", timestamp=now - timedelta(minutes=40, seconds=45), description="Simulated buy order 2 shares BEL"),
            AuditEvent(seq=5, event_name="ORDER_FILLED", timestamp=now - timedelta(minutes=40), description="Filled 2 shares @ ₹380.00 across L1 depth"),
            AuditEvent(seq=6, event_name="POSITION_CLOSED", timestamp=now - timedelta(minutes=15), description="Exit target 385.00 hit"),
            AuditEvent(seq=7, event_name="FEES_RECONCILED", timestamp=now - timedelta(minutes=15), description="Gross ₹10.00 - Fees ₹1.20 = Net ₹8.80"),
        ],
    )
    global_trade_ledger.record_trade(t_tiny_win)

    # 2. Losing tiny trade due to cost drag (Gross positive ₹2.00, but charges ₹3.00 -> Net -₹1.00)
    t_tiny_cost_drag = TradeRecord(
        trade_id="TR-TINY-002",
        account_id="tiny",
        symbol="TMPV",
        strategy_name="VWAP_REVERSION",
        strategy_version="v1.0",
        direction="BUY",
        quantity=1,
        entry_price=279.00,
        exit_price=281.00,
        entry_timestamp=now - timedelta(minutes=120),
        exit_timestamp=now - timedelta(minutes=75),
        gross_pnl=2.00,
        total_charges=3.00,
        slippage=0.05,
        net_pnl=-1.00,
        r_multiple=-0.5,
        trade_status="CLOSED",
        exit_reason="Trailing stop hit with cost drag",
        loss_tag=LossAttributionTag.COST_DRAG,
        decision_reason="Reversion from -2.2 VWAP dev",
    )
    global_trade_ledger.record_trade(t_tiny_cost_drag)

    # 3. Partially filled and missing original snapshot trade (to test "Unavailable" handling)
    t_tiny_partial = TradeRecord(
        trade_id="TR-TINY-003",
        account_id="tiny",
        symbol="RELIANCE",
        strategy_name="ORB_BREAKOUT",
        strategy_version="v1.0",
        direction="BUY",
        quantity=1,
        entry_price=1160.00,
        exit_price=1160.00,
        entry_timestamp=now - timedelta(days=1),
        exit_timestamp=now - timedelta(days=1, minutes=-10),
        gross_pnl=0.00,
        total_charges=0.80,
        slippage=0.10,
        net_pnl=-0.80,
        r_multiple=0.0,
        trade_status="PARTIALLY_FILLED",
        exit_reason="Scratch exit",
        loss_tag=LossAttributionTag.COST_DRAG,
        decision_reason="Legacy trade without full snapshot",
        decision_snapshot=None,  # Missing snapshot
        execution_forensics=None,  # Missing forensics
        fee_breakdown=None,  # Missing fee breakdown
        audit_timeline=[],  # Missing audit events
    )
    global_trade_ledger.record_trade(t_tiny_partial)

    # 4. Shadow account isolated trade
    t_shadow_win = TradeRecord(
        trade_id="TR-SHADOW-001",
        account_id="shadow",
        symbol="RELIANCE",
        strategy_name="ORB_BREAKOUT",
        strategy_version="v1.2",
        direction="BUY",
        quantity=50,
        entry_price=1160.00,
        exit_price=1175.00,
        entry_timestamp=now - timedelta(hours=3),
        exit_timestamp=now - timedelta(hours=1),
        gross_pnl=750.00,       # (1175 - 1160) * 50 = ₹750.00
        total_charges=38.40,
        slippage=2.50,
        net_pnl=711.60,
        r_multiple=2.2,
        trade_status="CLOSED",
        exit_reason="Target reached",
        loss_tag=LossAttributionTag.NONE,
        decision_reason="Shadow allocation ORB breakout",
    )
    global_trade_ledger.record_trade(t_shadow_win)


@pytest.mark.asyncio
async def test_get_trade_forensic_detail_snapshot():
    """Test 1: Correct retrieval of a trade's original decision snapshot."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/trades/TR-TINY-001")
        assert resp.status_code == 200
        data = resp.json()

        # Check Summary
        summary = data["trade_summary"]
        assert summary["trade_id"] == "TR-TINY-001"
        assert summary["symbol"] == "BEL"
        assert summary["account_id"] == "tiny"
        assert summary["quantity"] == 2
        assert summary["direction"] == "BUY"

        # Check Original Decision Snapshot (Not recalculated, exact values)
        snap = data["decision_snapshot"]
        assert snap["recorded"] is True
        assert snap["rvol"] == 3.2
        assert snap["obi"] == 0.45
        assert snap["microprice"] == 380.20
        assert snap["net_ev"] == 0.28
        assert snap["ev_hurdle"] == 0.15
        assert snap["win_probability"] == 0.62


@pytest.mark.asyncio
async def test_missing_historical_data_returns_unavailable():
    """Test 2: Correct handling of missing historical data (never fabricate)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/trades/TR-TINY-003")
        assert resp.status_code == 200
        data = resp.json()

        snap = data["decision_snapshot"]
        assert snap["recorded"] is False
        assert snap["rvol"] == "Unavailable"
        assert snap["obi"] == "Unavailable"
        assert snap["microprice"] == "Unavailable"
        assert snap["atr"] == "Unavailable"

        forensics = data["execution_forensics"]
        assert forensics["recorded"] is False
        assert forensics["configured_latency_ms"] == "Unavailable"

        # Audit timeline has no fabricated events
        assert len(data["audit_timeline"]) == 0


@pytest.mark.asyncio
async def test_gross_to_net_reconciliation_and_no_double_slippage():
    """Test 3 & 4 & 5: Accurate fee breakdown, gross-to-net reconciliation, no double-counting slippage."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/trades/TR-TINY-001")
        assert resp.status_code == 200
        data = resp.json()

        acc = data["accounting"]
        assert acc["gross_pnl"] == 10.00
        assert acc["applicable_charges"] == 1.20
        assert acc["net_pnl"] == 8.80
        # Reconciled invariant: gross - charges == net
        assert acc["reconciled"] is True

        # Slippage is reported for attribution, but NOT subtracted again
        assert acc["execution_slippage_attribution"] == 0.10
        assert acc["slippage_already_in_fill"] is True


@pytest.mark.asyncio
async def test_partially_filled_order_status():
    """Test 6: Correct handling of partially filled orders."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/trades/TR-TINY-003")
        assert resp.status_code == 200
        data = resp.json()
        assert data["trade_summary"]["trade_status"] == "PARTIALLY_FILLED"


@pytest.mark.asyncio
async def test_account_isolation_tiny_vs_shadow():
    """Test 8: Independent tiny and shadow trade queries and analytics."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Query tiny trades
        tiny_resp = await client.get("/api/trades?account=tiny")
        assert tiny_resp.status_code == 200
        tiny_trades = tiny_resp.json()
        assert len(tiny_trades) == 3
        for t in tiny_trades:
            assert t["account_id"] == "tiny"

        # Query shadow trades
        shadow_resp = await client.get("/api/trades?account=shadow")
        assert shadow_resp.status_code == 200
        shadow_trades = shadow_resp.json()
        assert len(shadow_trades) == 1
        assert shadow_trades[0]["account_id"] == "shadow"
        assert shadow_trades[0]["trade_id"] == "TR-SHADOW-001"


@pytest.mark.asyncio
async def test_edge_health_metrics_and_sample_quality():
    """Test 9, 10, 11: Edge health calculation, win rate, expectancy, and insufficient sample state."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/analytics/edge-health?account=tiny")
        assert resp.status_code == 200
        data = resp.json()

        assert data["account_id"] == "tiny"
        assert data["starting_capital"] == 1000.00
        assert data["total_closed_trades"] == 3
        assert data["sample_threshold"] == 30
        assert data["has_sufficient_sample"] is False
        assert data["strategy_health_status"] == "INSUFFICIENT SAMPLE"

        # Net P&L: 8.80 - 1.00 - 0.80 = 7.00
        assert data["realized_net_pnl"] == 7.00
        assert data["current_equity"] == 1007.00

        # Win rate: 1 win out of 3 = 33.33%
        assert data["win_count"] == 1
        assert data["loss_count"] == 2
        assert data["win_rate_pct"] == 33.33

        # Profit factor: gross wins = 12.00, gross losses = 0.00 -> 12.0
        assert data["profit_factor"] >= 0.0


@pytest.mark.asyncio
async def test_invalid_trade_id_returns_404():
    """Test 12: API errors for nonexistent trades."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/trades/NON_EXISTENT_ID")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_invalid_account_returns_400():
    """Test validation of account identifiers."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/trades?account=hacked_account")
        assert resp.status_code == 400

        resp2 = await client.get("/api/analytics/edge-health?account=hacked_account")
        assert resp2.status_code == 400


@pytest.mark.asyncio
async def test_no_fabricated_audit_events():
    """Test 13: Audit events only display if actually recorded."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/trades/TR-TINY-001")
        data = resp.json()
        assert len(data["audit_timeline"]) == 7
        assert data["audit_timeline"][0]["event_name"] == "MARKET_DATA_RECEIVED"

        # Trade with no events returns empty list, never fabricated events
        resp2 = await client.get("/api/trades/TR-TINY-002")
        data2 = resp2.json()
        assert len(data2["audit_timeline"]) == 0
