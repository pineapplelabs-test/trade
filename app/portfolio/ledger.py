"""Immutable Trade Ledger with Forensic Audit Snapshots, Execution Records, and Loss Attribution."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class LossAttributionTag(StrEnum):
    NONE = "NONE"
    BAD_SIGNAL = "bad_signal"        # Price moved immediately against hypothesis
    COST_DRAG = "cost_drag"          # Trade had positive gross move but fees caused net loss
    SLIPPAGE = "slippage"            # Slippage exceeded expected ATR buffer
    TIME_STOP = "time_stop"          # Exited due to 45-min stall
    STOP_GAP = "stop_gap"            # Price gapped over stop
    REGIME = "regime"                # Market-wide adverse trend


@dataclass(frozen=True)
class DecisionSnapshot:
    """Original decision criteria and indicators recorded at decision moment."""
    rvol: float | None = None
    obi: float | None = None
    microprice: float | None = None
    vwap_deviation: float | None = None
    atr: float | None = None
    spread: float | None = None
    win_probability: float | None = None
    expected_reward: float | None = None
    expected_loss: float | None = None
    expected_costs: float | None = None
    net_ev: float | None = None
    ev_hurdle: float | None = None
    decision: str = "ENTER"
    decision_reason: str = "EV hurdle cleared"
    eval_timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class LevelFillDetail:
    """Discrete depth fill per price level."""
    level: int
    price: float
    quantity: int


@dataclass(frozen=True)
class ExecutionForensics:
    """Simulated execution details, book depth, latency and slippage."""
    market_data_ts: datetime | None = None
    decision_ts: datetime | None = None
    simulated_execution_ts: datetime = field(default_factory=lambda: datetime.now(UTC))
    configured_latency_ms: int = 500
    best_bid: float | None = None
    best_ask: float | None = None
    requested_quantity: int = 1
    filled_quantity: int = 1
    unfilled_quantity: int = 0
    vwap_fill_price: float = 0.0
    slippage_ticks: int = 1
    slippage_amount: float = 0.0
    levels_consumed: list[LevelFillDetail] = field(default_factory=list)
    depth_snapshot: dict[str, list[dict[str, Any]]] | None = None


@dataclass(frozen=True)
class DetailedFeeBreakdown:
    """Statutory, exchange, and brokerage charges down to the paisa."""
    schedule_id: str
    effective_date: str
    turnover: float
    buy_value: float
    sell_value: float
    brokerage: float
    stt: float
    exchange_txn: float
    sebi: float
    gst: float
    stamp_duty: float
    total_charges: float


@dataclass(frozen=True)
class AuditEvent:
    """Chronological event in the life cycle of a paper trade."""
    seq: int
    event_name: str
    timestamp: datetime
    description: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TradeRecord:
    trade_id: str
    account_id: str
    symbol: str
    strategy_name: str
    strategy_version: str
    direction: str                     # "BUY" (Cash equity long)
    quantity: int
    entry_price: float
    exit_price: float
    entry_timestamp: datetime
    exit_timestamp: datetime
    gross_pnl: float
    total_charges: float
    slippage: float
    net_pnl: float
    r_multiple: float
    trade_status: str                  # "CLOSED", "FILLED", "PARTIALLY_FILLED", "REJECTED"
    exit_reason: str
    loss_tag: LossAttributionTag
    decision_reason: str
    decision_snapshot: DecisionSnapshot | None = None
    execution_forensics: ExecutionForensics | None = None
    fee_breakdown: DetailedFeeBreakdown | None = None
    audit_timeline: list[AuditEvent] = field(default_factory=list)
    environment: str = "PAPER_LIVE"   # "DEMO" vs "PAPER_LIVE"
    predicted_probability: float = 0.50
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def attribute_loss(gross_pnl: float, net_pnl: float, exit_reason: str) -> LossAttributionTag:
    """Classify the root cause of a losing trade."""
    if net_pnl >= 0:
        return LossAttributionTag.NONE
    if gross_pnl > 0 and net_pnl < 0:
        return LossAttributionTag.COST_DRAG
    if "time" in exit_reason.lower():
        return LossAttributionTag.TIME_STOP
    if "gap" in exit_reason.lower():
        return LossAttributionTag.STOP_GAP
    return LossAttributionTag.BAD_SIGNAL


class TradeLedger:
    """Thread-safe historical record of all completed paper trades with isolated account lookup and SQLite persistence."""

    def __init__(self) -> None:
        self.trades: list[TradeRecord] = []

    def record_trade(self, trade: TradeRecord) -> bool:
        """Record trade idempotently. If trade_id already exists, skip to prevent duplicates."""
        for t in self.trades:
            if t.trade_id == trade.trade_id:
                return False
        self.trades.append(trade)
        return True

    def get_trade_by_id(self, trade_id: str) -> TradeRecord | None:
        for t in self.trades:
            if t.trade_id == trade_id:
                return t
        return None

    def list_trades_for_account(
        self,
        account_id: str,
        limit: int = 100,
        environment: str | None = None,
    ) -> list[TradeRecord]:
        matched = [
            t for t in self.trades
            if t.account_id == account_id and (environment is None or t.environment == environment)
        ]
        return matched[-limit:]

    def get_loss_attribution_summary(
        self,
        account_id: str,
        environment: str | None = None,
    ) -> dict[str, int]:
        summary: dict[str, int] = {}
        for t in self.trades:
            if t.account_id == account_id and (environment is None or t.environment == environment):
                if t.loss_tag != LossAttributionTag.NONE:
                    tag_str = t.loss_tag.value
                    summary[tag_str] = summary.get(tag_str, 0) + 1
        return summary

    async def save_trade_to_db(self, trade: TradeRecord) -> None:
        """Persist trade, decision snapshot, forensics, fees, and audit timeline to SQLite."""
        import json

        from sqlalchemy import select

        from app.db.models import (
            Account,
            DurableAuditEvent,
            DurableDecisionSnapshot,
            DurableExecutionForensics,
            DurableFeeBreakdown,
            DurableTradeRecord,
        )
        from app.db.session import async_session_factory

        async with async_session_factory() as session:
            # Ensure account exists in DB for foreign key integrity
            acct_res = await session.execute(select(Account).where(Account.id == trade.account_id))
            if acct_res.scalar_one_or_none() is None:
                new_acct = Account(
                    id=trade.account_id,
                    name=trade.account_id.capitalize(),
                    starting_capital=1000.0 if trade.account_id == "tiny" else 100000.0,
                    config_json="{}",
                )
                session.add(new_acct)
                await session.flush()

            # 1. Upsert DurableTradeRecord
            existing_trade = await session.get(DurableTradeRecord, trade.trade_id)
            if existing_trade is None:
                durable_trade = DurableTradeRecord(
                    trade_id=trade.trade_id,
                    account_id=trade.account_id,
                    symbol=trade.symbol,
                    strategy_name=trade.strategy_name,
                    strategy_version=trade.strategy_version,
                    direction=trade.direction,
                    quantity=trade.quantity,
                    entry_price=trade.entry_price,
                    exit_price=trade.exit_price,
                    entry_timestamp=trade.entry_timestamp,
                    exit_timestamp=trade.exit_timestamp,
                    gross_pnl=trade.gross_pnl,
                    total_charges=trade.total_charges,
                    slippage=trade.slippage,
                    net_pnl=trade.net_pnl,
                    r_multiple=trade.r_multiple,
                    trade_status=trade.trade_status,
                    exit_reason=trade.exit_reason,
                    loss_tag=trade.loss_tag.value if isinstance(trade.loss_tag, LossAttributionTag) else str(trade.loss_tag),
                    decision_reason=trade.decision_reason,
                    environment=trade.environment,
                    predicted_probability=trade.predicted_probability,
                    created_at=trade.created_at,
                )
                session.add(durable_trade)
            else:
                existing_trade.exit_price = trade.exit_price
                existing_trade.exit_timestamp = trade.exit_timestamp
                existing_trade.gross_pnl = trade.gross_pnl
                existing_trade.total_charges = trade.total_charges
                existing_trade.net_pnl = trade.net_pnl
                existing_trade.r_multiple = trade.r_multiple
                existing_trade.trade_status = trade.trade_status
                existing_trade.exit_reason = trade.exit_reason
                existing_trade.loss_tag = trade.loss_tag.value if isinstance(trade.loss_tag, LossAttributionTag) else str(trade.loss_tag)

            # 2. Decision Snapshot
            if trade.decision_snapshot:
                existing_ds = await session.get(DurableDecisionSnapshot, trade.trade_id)
                ds = trade.decision_snapshot
                if existing_ds is None:
                    durable_ds = DurableDecisionSnapshot(
                        trade_id=trade.trade_id,
                        symbol=trade.symbol,
                        eval_timestamp=ds.eval_timestamp,
                        last_price=trade.entry_price,
                        bid=(trade.execution_forensics.best_bid if trade.execution_forensics and trade.execution_forensics.best_bid is not None else trade.entry_price),
                        ask=(trade.execution_forensics.best_ask if trade.execution_forensics and trade.execution_forensics.best_ask is not None else trade.entry_price),
                        spread=ds.spread or 0.0,
                        obi=ds.obi or 0.0,
                        microprice=ds.microprice or 0.0,
                        rvol=ds.rvol or 1.0,
                        vwap=trade.entry_price,
                        vwap_deviation=ds.vwap_deviation or 0.0,
                        atr=ds.atr or 0.0,
                        strategy_signal=trade.strategy_name,
                        predicted_probability=trade.predicted_probability,
                        expected_reward=ds.expected_reward or 0.0,
                        expected_loss=ds.expected_loss or 0.0,
                        expected_costs=ds.expected_costs or 0.0,
                        calculated_ev=ds.net_ev or 0.0,
                        minimum_hurdle=ds.ev_hurdle or 0.0,
                        decision=ds.decision,
                        rejection_reason=None,
                    )
                    session.add(durable_ds)

            # 3. Execution Forensics
            if trade.execution_forensics:
                ef = trade.execution_forensics
                existing_ef = await session.get(DurableExecutionForensics, trade.trade_id)
                levels_json = json.dumps([
                    {"level": lvl.level, "price": lvl.price, "quantity": lvl.quantity}
                    for lvl in ef.levels_consumed
                ])
                depth_json = json.dumps(ef.depth_snapshot or {})
                if existing_ef is None:
                    durable_ef = DurableExecutionForensics(
                        trade_id=trade.trade_id,
                        market_data_ts=ef.market_data_ts,
                        decision_ts=ef.decision_ts,
                        simulated_execution_ts=ef.simulated_execution_ts,
                        configured_latency_ms=ef.configured_latency_ms,
                        best_bid=ef.best_bid,
                        best_ask=ef.best_ask,
                        requested_quantity=ef.requested_quantity,
                        filled_quantity=ef.filled_quantity,
                        unfilled_quantity=ef.unfilled_quantity,
                        vwap_fill_price=ef.vwap_fill_price,
                        slippage_ticks=ef.slippage_ticks,
                        slippage_amount=ef.slippage_amount,
                        levels_consumed_json=levels_json,
                        depth_snapshot_json=depth_json,
                    )
                    session.add(durable_ef)

            # 4. Fee Breakdown
            if trade.fee_breakdown:
                fb = trade.fee_breakdown
                existing_fb = await session.get(DurableFeeBreakdown, trade.trade_id)
                if existing_fb is None:
                    durable_fb = DurableFeeBreakdown(
                        trade_id=trade.trade_id,
                        schedule_id=fb.schedule_id,
                        effective_date=fb.effective_date,
                        turnover=fb.turnover,
                        buy_value=fb.buy_value,
                        sell_value=fb.sell_value,
                        brokerage=fb.brokerage,
                        stt=fb.stt,
                        exchange_txn=fb.exchange_txn,
                        sebi=fb.sebi,
                        gst=fb.gst,
                        stamp_duty=fb.stamp_duty,
                        total_charges=fb.total_charges,
                    )
                    session.add(durable_fb)

            # 5. Audit Timeline
            for event in trade.audit_timeline:
                durable_event = DurableAuditEvent(
                    event_id=f"EVT-{trade.trade_id}-{event.seq}",
                    timestamp=event.timestamp,
                    account_id=trade.account_id,
                    symbol=trade.symbol,
                    trade_id=trade.trade_id,
                    event_type=event.event_name,
                    data_json=json.dumps(event.metadata),
                    reason=event.description,
                )
                session.add(durable_event)

            await session.commit()

    async def save_audit_event_to_db(
        self,
        event_id: str,
        account_id: str,
        symbol: str,
        event_type: str,
        data: dict[str, Any],
        reason: str = "",
        trade_id: str | None = None,
    ) -> None:
        """Persist a standalone audit log event to SQLite."""
        import json

        from app.db.models import DurableAuditEvent
        from app.db.session import async_session_factory

        async with async_session_factory() as session:
            ev = DurableAuditEvent(
                event_id=event_id,
                timestamp=datetime.now(UTC),
                account_id=account_id,
                symbol=symbol,
                trade_id=trade_id,
                event_type=event_type,
                data_json=json.dumps(data),
                reason=reason,
            )
            session.add(ev)
            await session.commit()

    async def load_trades_from_db(self) -> int:
        """Reload all durable trades and associated records from SQLite into runtime ledger."""
        import json

        from sqlalchemy import select

        from app.db.models import (
            DurableAuditEvent,
            DurableDecisionSnapshot,
            DurableExecutionForensics,
            DurableFeeBreakdown,
            DurableTradeRecord,
        )
        from app.db.session import async_session_factory
        from app.portfolio.account import portfolio_accounts

        loaded_count = 0
        async with async_session_factory() as session:
            trades_res = await session.execute(
                select(DurableTradeRecord).order_by(DurableTradeRecord.entry_timestamp)
            )
            durable_trades = trades_res.scalars().all()

            for dt in durable_trades:
                # 1. Fetch decision snapshot
                ds_res = await session.execute(
                    select(DurableDecisionSnapshot).where(DurableDecisionSnapshot.trade_id == dt.trade_id)
                )
                raw_ds = ds_res.scalar_one_or_none()
                snap: DecisionSnapshot | None = None
                if raw_ds:
                    snap = DecisionSnapshot(
                        rvol=raw_ds.rvol,
                        obi=raw_ds.obi,
                        microprice=raw_ds.microprice,
                        vwap_deviation=raw_ds.vwap_deviation,
                        atr=raw_ds.atr,
                        spread=raw_ds.spread,
                        win_probability=raw_ds.predicted_probability,
                        expected_reward=raw_ds.expected_reward,
                        expected_loss=raw_ds.expected_loss,
                        expected_costs=raw_ds.expected_costs,
                        net_ev=raw_ds.calculated_ev,
                        ev_hurdle=raw_ds.minimum_hurdle,
                        decision=raw_ds.decision,
                        decision_reason=raw_ds.rejection_reason or "Loaded from DB",
                        eval_timestamp=raw_ds.eval_timestamp,
                    )

                # 2. Fetch execution forensics
                ef_res = await session.execute(
                    select(DurableExecutionForensics).where(DurableExecutionForensics.trade_id == dt.trade_id)
                )
                raw_ef = ef_res.scalar_one_or_none()
                forensics: ExecutionForensics | None = None
                if raw_ef:
                    levels_raw = json.loads(raw_ef.levels_consumed_json or "[]")
                    depth_raw = json.loads(raw_ef.depth_snapshot_json or "{}")
                    levels = [
                        LevelFillDetail(level=lvl["level"], price=lvl["price"], quantity=lvl["quantity"])
                        for lvl in levels_raw
                    ]
                    forensics = ExecutionForensics(
                        market_data_ts=raw_ef.market_data_ts,
                        decision_ts=raw_ef.decision_ts,
                        simulated_execution_ts=raw_ef.simulated_execution_ts,
                        configured_latency_ms=raw_ef.configured_latency_ms,
                        best_bid=raw_ef.best_bid,
                        best_ask=raw_ef.best_ask,
                        requested_quantity=raw_ef.requested_quantity,
                        filled_quantity=raw_ef.filled_quantity,
                        unfilled_quantity=raw_ef.unfilled_quantity,
                        vwap_fill_price=raw_ef.vwap_fill_price,
                        slippage_ticks=raw_ef.slippage_ticks,
                        slippage_amount=raw_ef.slippage_amount,
                        levels_consumed=levels,
                        depth_snapshot=depth_raw,
                    )

                # 3. Fetch fee breakdown
                fb_res = await session.execute(
                    select(DurableFeeBreakdown).where(DurableFeeBreakdown.trade_id == dt.trade_id)
                )
                raw_fb = fb_res.scalar_one_or_none()
                fees: DetailedFeeBreakdown | None = None
                if raw_fb:
                    fees = DetailedFeeBreakdown(
                        schedule_id=raw_fb.schedule_id,
                        effective_date=raw_fb.effective_date,
                        turnover=raw_fb.turnover,
                        buy_value=raw_fb.buy_value,
                        sell_value=raw_fb.sell_value,
                        brokerage=raw_fb.brokerage,
                        stt=raw_fb.stt,
                        exchange_txn=raw_fb.exchange_txn,
                        sebi=raw_fb.sebi,
                        gst=raw_fb.gst,
                        stamp_duty=raw_fb.stamp_duty,
                        total_charges=raw_fb.total_charges,
                    )

                # 4. Fetch audit events
                ae_res = await session.execute(
                    select(DurableAuditEvent)
                    .where(DurableAuditEvent.trade_id == dt.trade_id)
                    .order_by(DurableAuditEvent.id)
                )
                raw_events = ae_res.scalars().all()
                timeline = [
                    AuditEvent(
                        seq=idx + 1,
                        event_name=ev.event_type,
                        timestamp=ev.timestamp,
                        description=ev.reason,
                        metadata=json.loads(ev.data_json or "{}"),
                    )
                    for idx, ev in enumerate(raw_events)
                ]

                # Map loss tag enum safely
                loss_tag_val = LossAttributionTag.NONE
                for tag in LossAttributionTag:
                    if tag.value == dt.loss_tag:
                        loss_tag_val = tag
                        break

                trade = TradeRecord(
                    trade_id=dt.trade_id,
                    account_id=dt.account_id,
                    symbol=dt.symbol,
                    strategy_name=dt.strategy_name,
                    strategy_version=dt.strategy_version,
                    direction=dt.direction,
                    quantity=dt.quantity,
                    entry_price=dt.entry_price,
                    exit_price=dt.exit_price,
                    entry_timestamp=dt.entry_timestamp,
                    exit_timestamp=dt.exit_timestamp,
                    gross_pnl=dt.gross_pnl,
                    total_charges=dt.total_charges,
                    slippage=dt.slippage,
                    net_pnl=dt.net_pnl,
                    r_multiple=dt.r_multiple,
                    trade_status=dt.trade_status,
                    exit_reason=dt.exit_reason,
                    loss_tag=loss_tag_val,
                    decision_reason=dt.decision_reason,
                    decision_snapshot=snap,
                    execution_forensics=forensics,
                    fee_breakdown=fees,
                    audit_timeline=timeline,
                    environment=dt.environment,
                    predicted_probability=dt.predicted_probability,
                    created_at=dt.created_at,
                )

                if self.record_trade(trade):
                    loaded_count += 1

                # If trade is currently OPEN, restore the position in PortfolioAccount
                if dt.trade_status in ("OPEN", "FILLED"):
                    acct = portfolio_accounts.get(dt.account_id)
                    if acct and dt.symbol not in acct.positions:
                        acct.restore_position(
                            symbol=dt.symbol,
                            quantity=dt.quantity,
                            entry_price=dt.entry_price,
                            current_price=dt.entry_price,
                            stop_price=round(dt.entry_price * 0.98, 2),
                            target_price=round(dt.entry_price * 1.04, 2),
                            opened_at=dt.entry_timestamp,
                        )

        return loaded_count


# Global singleton ledger instance shared across portfolio and API queries
global_trade_ledger = TradeLedger()

