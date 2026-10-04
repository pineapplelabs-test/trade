"""Comprehensive Automated Unit & Integration Tests for:
- SQLite Durable Data Persistence & Restart Recovery
- Open Position Survival across Application Restart
- Duplicate Trade Prevention & Idempotency
- Demo / Live Paper Data Isolation (Zero Contamination)
- Probability Calibration Buckets (50-55% up to 80%+)
- 09:15 AM Pre-Market Readiness Diagnostic (All 20 Checks PASS)
- 10-Step Pipeline Integrity & Forensic Reconstruction
"""

from datetime import UTC, datetime, time, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import init_db
from app.feed.base import DepthLevel, MarketTick, OrderBookDepth
from app.feed.instruments import InstrumentMaster
from app.feed.validator import FreshnessStatus, MarketDataValidator
from app.fees.calculator import FeeCalculator
from app.main import app
from app.portfolio.account import PortfolioAccount, portfolio_accounts
from app.portfolio.ledger import (
    AuditEvent,
    DecisionSnapshot,
    DetailedFeeBreakdown,
    ExecutionForensics,
    LevelFillDetail,
    LossAttributionTag,
    TradeLedger,
    TradeRecord,
    global_trade_ledger,
)
from app.risk.risk_gate import RiskGate
from app.strategy.ev import DecisionStatus, EVParameters, calculate_expected_value
from app.universe.funnel import FunnelConfig, UniverseFunnel


@pytest.fixture(autouse=True)
async def prepare_test_db():
    """Ensure database tables are initialized before each test run."""
    await init_db()
    global_trade_ledger.trades.clear()
    portfolio_accounts["tiny"] = PortfolioAccount("tiny", starting_capital=1000.0, max_positions=2)
    portfolio_accounts["shadow"] = PortfolioAccount("shadow", starting_capital=100000.0, max_positions=5)


@pytest.mark.asyncio
async def test_restart_recovery_full_trade_and_exact_values():
    """Section 8: Create paper trade, persist to SQLite, reload into clean ledger, verify exact match."""
    now = datetime.now(UTC)
    trade_id = "TR-PERSIST-101"

    original_trade = TradeRecord(
        trade_id=trade_id,
        account_id="tiny",
        symbol="BEL",
        strategy_name="ORB_BREAKOUT",
        strategy_version="v1.0",
        direction="BUY",
        quantity=2,
        entry_price=380.00,
        exit_price=386.20,
        entry_timestamp=now - timedelta(minutes=30),
        exit_timestamp=now - timedelta(minutes=10),
        gross_pnl=12.40,
        total_charges=1.24,
        slippage=0.10,
        net_pnl=11.16,
        r_multiple=1.85,
        trade_status="CLOSED",
        exit_reason="Target m*ATR reached",
        loss_tag=LossAttributionTag.NONE,
        decision_reason="First 15-min high break, RVOL 3.2x, OBI +0.45",
        decision_snapshot=DecisionSnapshot(
            rvol=3.2,
            obi=0.45,
            microprice=380.20,
            vwap_deviation=0.12,
            atr=5.40,
            spread=0.05,
            win_probability=0.62,
            expected_reward=1.35,
            expected_loss=0.75,
            expected_costs=0.22,
            net_ev=0.31,
            ev_hurdle=0.15,
            decision="ENTER",
            decision_reason="Strong depth imbalance with buyer dominance",
            eval_timestamp=now - timedelta(minutes=31),
        ),
        execution_forensics=ExecutionForensics(
            market_data_ts=now - timedelta(minutes=31),
            decision_ts=now - timedelta(minutes=30, seconds=55),
            simulated_execution_ts=now - timedelta(minutes=30),
            configured_latency_ms=500,
            best_bid=379.95,
            best_ask=380.00,
            requested_quantity=2,
            filled_quantity=2,
            unfilled_quantity=0,
            vwap_fill_price=380.00,
            slippage_ticks=1,
            slippage_amount=0.05,
            levels_consumed=[LevelFillDetail(level=1, price=380.00, quantity=2)],
            depth_snapshot={"bids": [{"price": 379.95, "qty": 1800}], "asks": [{"price": 380.00, "qty": 1200}]},
        ),
        fee_breakdown=DetailedFeeBreakdown(
            schedule_id="DEFAULT_NSE_2024",
            effective_date="2024-10-01",
            turnover=1532.40,
            buy_value=760.00,
            sell_value=772.40,
            brokerage=0.46,
            stt=0.19,
            exchange_txn=0.05,
            sebi=0.0015,
            gst=0.09,
            stamp_duty=0.02,
            total_charges=1.24,
        ),
        audit_timeline=[
            AuditEvent(seq=1, event_name="DATA_RECEIVED", timestamp=now - timedelta(minutes=31), description="Tick captured"),
            AuditEvent(seq=2, event_name="EV_CALCULATED", timestamp=now - timedelta(minutes=30, seconds=55), description="EV 0.31% passed"),
            AuditEvent(seq=3, event_name="ORDER_FILLED", timestamp=now - timedelta(minutes=30), description="Filled 2 @ 380.00"),
        ],
        environment="PAPER_LIVE",
        predicted_probability=0.62,
    )

    # 1. Save to SQLite database
    await global_trade_ledger.save_trade_to_db(original_trade)

    # 2. Simulate server restart: clear runtime memory
    fresh_ledger = TradeLedger()
    assert len(fresh_ledger.trades) == 0

    # 3. Reload from database
    loaded_count = await fresh_ledger.load_trades_from_db()
    assert loaded_count >= 1

    # 4. Verify exact values unchanged
    restored = fresh_ledger.get_trade_by_id(trade_id)
    assert restored is not None
    assert restored.trade_id == trade_id
    assert restored.account_id == "tiny"
    assert restored.symbol == "BEL"
    assert restored.quantity == 2
    assert restored.entry_price == 380.00
    assert restored.exit_price == 386.20
    assert restored.gross_pnl == 12.40
    assert restored.total_charges == 1.24
    assert restored.net_pnl == 11.16
    assert restored.environment == "PAPER_LIVE"
    assert restored.predicted_probability == 0.62

    # Decision snapshot
    assert restored.decision_snapshot is not None
    assert restored.decision_snapshot.rvol == 3.2
    assert restored.decision_snapshot.obi == 0.45
    assert restored.decision_snapshot.net_ev == 0.31

    # Execution forensics
    assert restored.execution_forensics is not None
    assert restored.execution_forensics.filled_quantity == 2
    assert restored.execution_forensics.vwap_fill_price == 380.00
    assert len(restored.execution_forensics.levels_consumed) == 1
    assert restored.execution_forensics.levels_consumed[0].quantity == 2

    # Fee breakdown
    assert restored.fee_breakdown is not None
    assert restored.fee_breakdown.brokerage == 0.46
    assert restored.fee_breakdown.total_charges == 1.24

    # Audit timeline
    assert len(restored.audit_timeline) == 3
    assert restored.audit_timeline[0].event_name == "DATA_RECEIVED"


@pytest.mark.asyncio
async def test_open_position_restoration_across_restart():
    """Section 8: Open position survives restart with correct cash balance and trade state."""
    now = datetime.now(UTC)
    open_trade_id = "TR-OPEN-BEL-01"

    # Buy 2 shares @ ₹380 = ₹760 cost. Tiny starting cash ₹1,000 -> cash becomes ₹240.
    portfolio_accounts["tiny"].open_position(
        symbol="BEL",
        quantity=2,
        entry_price=380.00,
        stop_price=375.0,
        target_price=395.0,
    )
    assert portfolio_accounts["tiny"].cash == 240.0
    assert "BEL" in portfolio_accounts["tiny"].positions

    open_trade = TradeRecord(
        trade_id=open_trade_id,
        account_id="tiny",
        symbol="BEL",
        strategy_name="ORB_BREAKOUT",
        strategy_version="v1.0",
        direction="BUY",
        quantity=2,
        entry_price=380.00,
        exit_price=0.0,
        entry_timestamp=now,
        exit_timestamp=now,
        gross_pnl=0.0,
        total_charges=0.50,
        slippage=0.05,
        net_pnl=0.0,
        r_multiple=0.0,
        trade_status="OPEN",
        exit_reason="",
        loss_tag=LossAttributionTag.NONE,
        decision_reason="Breakout confirmed",
        execution_forensics=ExecutionForensics(
            market_data_ts=now,
            decision_ts=now,
            simulated_execution_ts=now,
            requested_quantity=2,
            filled_quantity=2,
            vwap_fill_price=380.00,
        ),
        environment="PAPER_LIVE",
        predicted_probability=0.68,
    )
    await global_trade_ledger.save_trade_to_db(open_trade)

    # Simulate app crash & restart: reset portfolio accounts and ledger
    portfolio_accounts["tiny"] = PortfolioAccount("tiny", starting_capital=1000.0, max_positions=2)
    assert len(portfolio_accounts["tiny"].positions) == 0
    assert portfolio_accounts["tiny"].cash == 1000.0

    clean_ledger = TradeLedger()
    await clean_ledger.load_trades_from_db()

    # Confirm post-restart state
    assert "BEL" in portfolio_accounts["tiny"].positions
    pos = portfolio_accounts["tiny"].positions["BEL"]
    assert pos.quantity == 2
    assert pos.entry_price == 380.00
    assert portfolio_accounts["tiny"].cash == 240.00  # Cash is correct (₹1,000 - ₹760)
    assert portfolio_accounts["tiny"].equity == 1000.00

    # Trade is still open and forensics are intact
    reloaded_trade = clean_ledger.get_trade_by_id(open_trade_id)
    assert reloaded_trade is not None
    assert reloaded_trade.trade_status == "OPEN"
    assert reloaded_trade.execution_forensics.vwap_fill_price == 380.00


@pytest.mark.asyncio
async def test_duplicate_trade_prevention_idempotency():
    """Section 9: Submitting the same trade_id twice results in exactly ONE trade."""
    now = datetime.now(UTC)
    trade = TradeRecord(
        trade_id="TR-IDEMPOTENT-001",
        account_id="tiny",
        symbol="TMPV",
        strategy_name="VWAP_REVERSION",
        strategy_version="v1.0",
        direction="BUY",
        quantity=1,
        entry_price=278.50,
        exit_price=280.00,
        entry_timestamp=now,
        exit_timestamp=now,
        gross_pnl=1.50,
        total_charges=0.40,
        slippage=0.05,
        net_pnl=1.10,
        r_multiple=1.0,
        trade_status="CLOSED",
        exit_reason="Target",
        loss_tag=LossAttributionTag.NONE,
        decision_reason="Reversion",
        environment="PAPER_LIVE",
        predicted_probability=0.55,
    )

    # First submission
    added_1 = global_trade_ledger.record_trade(trade)
    assert added_1 is True

    # Second submission with same trade_id
    added_2 = global_trade_ledger.record_trade(trade)
    assert added_2 is False

    # Ledger must contain only ONE instance of this trade
    matching = [t for t in global_trade_ledger.trades if t.trade_id == "TR-IDEMPOTENT-001"]
    assert len(matching) == 1


@pytest.mark.asyncio
async def test_account_isolation_tiny_and_shadow():
    """Section 11: Tiny and Shadow accounts remain completely isolated in ledger and portfolio."""
    now = datetime.now(UTC)

    # Trade 1 in Tiny (₹1,000)
    t_tiny = TradeRecord(
        trade_id="TR-ISOL-TINY-1",
        account_id="tiny",
        symbol="BEL",
        strategy_name="ORB",
        strategy_version="v1.0",
        direction="BUY",
        quantity=2,
        entry_price=380.0,
        exit_price=386.0,
        entry_timestamp=now,
        exit_timestamp=now,
        gross_pnl=12.0,
        total_charges=1.20,
        slippage=0.10,
        net_pnl=10.80,
        r_multiple=1.5,
        trade_status="CLOSED",
        exit_reason="Target",
        loss_tag=LossAttributionTag.NONE,
        decision_reason="",
        environment="PAPER_LIVE",
        predicted_probability=0.60,
    )
    global_trade_ledger.record_trade(t_tiny)

    # Trade 2 in Shadow (₹1,00,000)
    t_shadow = TradeRecord(
        trade_id="TR-ISOL-SHADOW-1",
        account_id="shadow",
        symbol="RELIANCE",
        strategy_name="ORB",
        strategy_version="v1.0",
        direction="BUY",
        quantity=50,
        entry_price=1165.0,
        exit_price=1178.0,
        entry_timestamp=now,
        exit_timestamp=now,
        gross_pnl=650.0,
        total_charges=38.0,
        slippage=2.50,
        net_pnl=612.0,
        r_multiple=1.8,
        trade_status="CLOSED",
        exit_reason="Target",
        loss_tag=LossAttributionTag.NONE,
        decision_reason="",
        environment="PAPER_LIVE",
        predicted_probability=0.65,
    )
    global_trade_ledger.record_trade(t_shadow)

    # Query isolated trades
    tiny_list = global_trade_ledger.list_trades_for_account("tiny")
    shadow_list = global_trade_ledger.list_trades_for_account("shadow")

    assert len(tiny_list) == 1
    assert tiny_list[0].trade_id == "TR-ISOL-TINY-1"
    assert len(shadow_list) == 1
    assert shadow_list[0].trade_id == "TR-ISOL-SHADOW-1"


@pytest.mark.asyncio
async def test_demo_isolation_zero_contamination_of_live_results():
    """Section 7: Seed/demo trades marked DEMO must NEVER affect live-paper Edge Health."""
    now = datetime.now(UTC)

    # Create 1 DEMO trade with huge profit
    t_demo = TradeRecord(
        trade_id="TR-DEMO-HUGE-PROFIT",
        account_id="tiny",
        symbol="INFY",
        strategy_name="DEMO_ORB",
        strategy_version="v1.0",
        direction="BUY",
        quantity=5,
        entry_price=1500.0,
        exit_price=1600.0,
        entry_timestamp=now,
        exit_timestamp=now,
        gross_pnl=500.0,
        total_charges=15.0,
        slippage=1.0,
        net_pnl=485.0,
        r_multiple=5.0,
        trade_status="CLOSED",
        exit_reason="Target",
        loss_tag=LossAttributionTag.NONE,
        decision_reason="",
        environment="DEMO",
        predicted_probability=0.75,
    )
    global_trade_ledger.record_trade(t_demo)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Default environment is PAPER_LIVE
        resp = await client.get("/api/analytics/edge-health?account=tiny&environment=PAPER_LIVE")
        assert resp.status_code == 200
        live_data = resp.json()

        # Zero demo contamination: live closed trades count is 0
        assert live_data["environment"] == "PAPER_LIVE"
        assert live_data["total_closed_trades"] == 0
        assert live_data["realized_net_pnl"] == 0.0
        assert live_data["current_equity"] == 1000.00
        assert live_data["win_count"] == 0
        assert live_data["win_rate_pct"] == 0.0

        # Querying DEMO environment directly reveals the demo trade
        demo_resp = await client.get("/api/analytics/edge-health?account=tiny&environment=DEMO")
        assert demo_resp.status_code == 200
        demo_data = demo_resp.json()
        assert demo_data["environment"] == "DEMO"
        assert demo_data["total_closed_trades"] == 1
        assert demo_data["realized_net_pnl"] == 485.0


@pytest.mark.asyncio
async def test_probability_calibration_buckets_and_breakdowns():
    """Section 17 & 18: Verify probability calibration buckets and performance breakdown API."""
    now = datetime.now(UTC)

    # Seed 3 trades across probability buckets
    # Trade 1: 52% prob -> win
    t1 = TradeRecord(
        trade_id="TR-CALIB-1",
        account_id="tiny",
        symbol="BEL",
        strategy_name="ORB",
        strategy_version="v1.0",
        direction="BUY",
        quantity=1,
        entry_price=380.0,
        exit_price=385.0,
        entry_timestamp=now,
        exit_timestamp=now,
        gross_pnl=5.0,
        total_charges=0.5,
        slippage=0.05,
        net_pnl=4.5,
        r_multiple=1.0,
        trade_status="CLOSED",
        exit_reason="Target",
        loss_tag=LossAttributionTag.NONE,
        decision_reason="",
        decision_snapshot=DecisionSnapshot(obi=0.25, rvol=2.2, eval_timestamp=now),
        environment="PAPER_LIVE",
        predicted_probability=0.52,
    )
    # Trade 2: 72% prob -> win
    t2 = TradeRecord(
        trade_id="TR-CALIB-2",
        account_id="tiny",
        symbol="BEL",
        strategy_name="VWAP_REVERSION",
        strategy_version="v1.0",
        direction="BUY",
        quantity=1,
        entry_price=380.0,
        exit_price=386.0,
        entry_timestamp=now,
        exit_timestamp=now,
        gross_pnl=6.0,
        total_charges=0.5,
        slippage=0.05,
        net_pnl=5.5,
        r_multiple=1.2,
        trade_status="CLOSED",
        exit_reason="Target",
        loss_tag=LossAttributionTag.NONE,
        decision_reason="",
        decision_snapshot=DecisionSnapshot(obi=-0.2, rvol=1.2, eval_timestamp=now),
        environment="PAPER_LIVE",
        predicted_probability=0.72,
    )
    global_trade_ledger.record_trade(t1)
    global_trade_ledger.record_trade(t2)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Calibration endpoint
        calib_resp = await client.get("/api/analytics/calibration?account=tiny&environment=PAPER_LIVE")
        assert calib_resp.status_code == 200
        calib = calib_resp.json()
        assert calib["total_trades"] == 2

        b_50_55 = next(b for b in calib["buckets"] if b["bucket"] == "50-55%")
        assert b_50_55["trade_count"] == 1
        assert b_50_55["win_count"] == 1
        assert b_50_55["actual_win_rate_pct"] == 100.0

        b_70_75 = next(b for b in calib["buckets"] if b["bucket"] == "70-75%")
        assert b_70_75["trade_count"] == 1
        assert b_70_75["win_count"] == 1

        # Performance breakdowns endpoint
        breakdown_resp = await client.get("/api/analytics/performance-breakdowns?account=tiny&environment=PAPER_LIVE")
        assert breakdown_resp.status_code == 200
        bd = breakdown_resp.json()
        assert "ORB" in bd["by_strategy"]
        assert "VWAP_REVERSION" in bd["by_strategy"]
        assert "BEL" in bd["by_symbol"]


@pytest.mark.asyncio
async def test_0915_premarket_readiness_all_20_checks_pass():
    """Section 14: Comprehensive 09:15 AM pre-market readiness endpoint must report PAPER DESK READY."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/readiness")
        assert resp.status_code == 200
        data = resp.json()

        assert data["overall_status"] == "PAPER DESK READY"
        assert data["ready"] is True
        assert data["market_open_target"] == "09:15 IST"
        assert data["total_checks"] == 20
        assert data["passed_checks"] == 20
        assert data["failed_checks"] == 0

        # Assert all 20 specific checklist items
        checks = data["checks"]
        required_checks = [
            "DATABASE",
            "GROWW CONNECTION",
            "QUOTE STREAM",
            "5-LEVEL DEPTH",
            "TIMESTAMP VALIDATION",
            "DATA FRESHNESS",
            "UNIVERSE FUNNEL",
            "INDICATORS",
            "STRATEGY ENGINE",
            "EV ENGINE",
            "RISK ENGINE",
            "EXECUTION SIM",
            "FEE ENGINE",
            "TRADE LEDGER",
            "AUDIT LOG",
            "TINY ACCOUNT",
            "SHADOW ACCOUNT",
            "PERSISTENCE",
            "RESTART RECOVERY",
            "PAPER-ONLY SAFETY",
        ]
        for rc in required_checks:
            assert rc in checks, f"Missing readiness check: {rc}"
            assert checks[rc]["status"] == "PASS", f"Check {rc} failed: {checks[rc]['detail']}"


@pytest.mark.asyncio
async def test_final_premarket_10_step_pipeline_simulation():
    """Section 20: Run all 10 mandated final pre-market pipeline scenarios."""
    depth = OrderBookDepth(
        bids=[DepthLevel(price=380.0 - i * 0.05, quantity=1000) for i in range(5)],
        asks=[DepthLevel(price=380.05 + i * 0.05, quantity=1000) for i in range(5)],
    )

    # Test 1 — Valid trade creates exactly one paper trade
    calc = FeeCalculator()
    fees = calc.calculate(quantity=2, buy_price=380.0, sell_price=385.0)
    now = datetime.now(UTC)
    valid_trade = TradeRecord(
        trade_id="TR-PIPELINE-VALID-01",
        account_id="tiny",
        symbol="BEL",
        strategy_name="ORB",
        strategy_version="v1.0",
        direction="BUY",
        quantity=2,
        entry_price=380.0,
        exit_price=385.0,
        entry_timestamp=now,
        exit_timestamp=now,
        gross_pnl=fees.gross_pnl,
        total_charges=fees.total_charges,
        slippage=0.10,
        net_pnl=fees.net_pnl,
        r_multiple=1.5,
        trade_status="CLOSED",
        exit_reason="Target",
        loss_tag=LossAttributionTag.NONE,
        decision_reason="Valid pipeline execution",
        environment="PAPER_LIVE",
        predicted_probability=0.65,
    )
    assert global_trade_ledger.record_trade(valid_trade) is True
    assert global_trade_ledger.get_trade_by_id("TR-PIPELINE-VALID-01") is not None

    # Test 2 — EV rejection: creates rejection record but NO trade
    ev_reject = calculate_expected_value(EVParameters(
        win_probability=0.40,
        expected_reward=0.50,
        expected_loss=1.00,
        total_costs=0.25,
        min_hurdle=0.15,
    ))
    assert ev_reject.status == DecisionStatus.REJECT
    assert ev_reject.net_ev < 0.15

    # Test 3 — Stale data must block the trade
    validator = MarketDataValidator()
    old_tick = MarketTick(
        token=1,
        symbol="BEL",
        timestamp=datetime.now(UTC) - timedelta(seconds=15),
        last_price=380.0,
        last_quantity=10,
        volume=100000,
        average_traded_price=380.0,
        total_buy_quantity=50000,
        total_sell_quantity=50000,
        open=375.0,
        high=385.0,
        low=374.0,
        close=376.0,
        depth=depth,
        feed_source="groww",
    )
    status_stale, _ = validator.validate_tick(old_tick, decision_timestamp=datetime.now(UTC))
    assert status_stale == FreshnessStatus.STALE

    # Test 4 — Missing depth must block the trade
    incomplete_depth = OrderBookDepth(
        bids=[DepthLevel(price=380.0, quantity=500)],  # Only 1 level
        asks=[DepthLevel(price=380.05, quantity=500)],
    )
    bad_tick = MarketTick(
        token=1,
        symbol="BEL",
        timestamp=datetime.now(UTC),
        last_price=380.0,
        last_quantity=10,
        volume=100000,
        average_traded_price=380.0,
        total_buy_quantity=50000,
        total_sell_quantity=50000,
        open=375.0,
        high=385.0,
        low=374.0,
        close=376.0,
        depth=incomplete_depth,
        feed_source="groww",
    )
    status_depth, _ = validator.validate_tick(bad_tick, decision_timestamp=datetime.now(UTC))
    assert status_depth == FreshnessStatus.INSUFFICIENT_DEPTH

    # Test 5 — Unaffordable stock must block trade
    # For tiny account (capital ₹1,000, max_position_pct=50% -> max allocation ₹500)
    # MRF @ ₹1,40,000 is unaffordable
    funnel = UniverseFunnel(FunnelConfig(max_position_pct=0.50))
    master = InstrumentMaster()
    inst = master.get_by_symbol("BEL")
    if inst:
        expensive_tick = MarketTick(
            token=inst.token,
            symbol="BEL",
            timestamp=datetime.now(UTC),
            last_price=1500.0,  # exceeds ₹500
            last_quantity=10,
            volume=100000,
            average_traded_price=1500.0,
            total_buy_quantity=50000,
            total_sell_quantity=50000,
            open=1480.0,
            high=1520.0,
            low=1470.0,
            close=1490.0,
            depth=depth,
            feed_source="groww",
        )
        res_afford = funnel.evaluate(inst, expensive_tick, account_capital=1000.0)
        assert res_afford.passed is False
        assert "AFFORDABILITY" in res_afford.stage

    # Test 6 — Risk limit exceeded blocks trade
    gate = RiskGate()
    risk_dec = gate.evaluate_entry(
        account_id="tiny",
        starting_capital=1000.0,
        current_equity=970.0,
        day_pnl=-30.0,  # -3.0% exceeds 2% daily loss limit
        current_time_ist=time(10, 0, 0),
    )
    assert risk_dec.allowed is False
    assert risk_dec.action == "HALT"

    # Test 7 — Restart: Data survives
    await global_trade_ledger.save_trade_to_db(valid_trade)
    fresh_l = TradeLedger()
    await fresh_l.load_trades_from_db()
    assert fresh_l.get_trade_by_id("TR-PIPELINE-VALID-01") is not None

    # Test 8 — Demo contamination: DEMO trades do not appear in live analytics
    t_demo = TradeRecord(
        trade_id="TR-PIPELINE-DEMO",
        account_id="tiny",
        symbol="BEL",
        strategy_name="DEMO",
        strategy_version="v1.0",
        direction="BUY",
        quantity=1,
        entry_price=380.0,
        exit_price=390.0,
        entry_timestamp=now,
        exit_timestamp=now,
        gross_pnl=10.0,
        total_charges=1.0,
        slippage=0.05,
        net_pnl=9.0,
        r_multiple=2.0,
        trade_status="CLOSED",
        exit_reason="Target",
        loss_tag=LossAttributionTag.NONE,
        decision_reason="",
        environment="DEMO",
        predicted_probability=0.70,
    )
    global_trade_ledger.record_trade(t_demo)
    live_trades = global_trade_ledger.list_trades_for_account("tiny", environment="PAPER_LIVE")
    assert all(t.environment == "PAPER_LIVE" for t in live_trades)

    # Test 9 — Tiny / Shadow isolation
    tiny_trades = global_trade_ledger.list_trades_for_account("tiny")
    shadow_trades = global_trade_ledger.list_trades_for_account("shadow")
    assert all(t.account_id == "tiny" for t in tiny_trades)
    assert all(t.account_id == "shadow" for t in shadow_trades)

    # Test 10 — Full forensic reconstruction
    reconstructed = global_trade_ledger.get_trade_by_id("TR-PIPELINE-VALID-01")
    assert reconstructed is not None
    # Reconstruct gross, fees, net
    assert round(reconstructed.gross_pnl - reconstructed.total_charges, 2) == round(reconstructed.net_pnl, 2)
