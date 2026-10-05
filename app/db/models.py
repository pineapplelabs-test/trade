"""SQLAlchemy 2.0 database models for Paper Desk according to AGENTS.md Section 9."""

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    """Return current UTC timestamp without timezone offset issues."""
    return datetime.now(UTC)


class Instrument(Base):
    """NSE equity instrument master."""

    __tablename__ = "instruments"

    token: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), default="")
    sector: Mapped[str] = mapped_column(String(64), default="General", index=True)
    tick_size: Mapped[float] = mapped_column(Float, default=0.05)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    surveillance_flag: Mapped[str] = mapped_column(String(16), default="NORMAL")  # NORMAL, ASM, GSM


class Account(Base):
    """Trading account configurations and state."""

    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # e.g. "real5k", "tiny", "shadow"
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    starting_capital: Mapped[float] = mapped_column(Float, nullable=False)
    config_json: Mapped[str] = mapped_column(Text, default="{}")

    positions: Mapped[list["Position"]] = relationship("Position", back_populates="account")
    orders: Mapped[list["Order"]] = relationship("Order", back_populates="account")


class Signal(Base):
    """Generated trading signals and candidate rankings."""

    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    token: Mapped[int] = mapped_column(Integer, ForeignKey("instruments.token"), index=True)
    strategy: Mapped[str] = mapped_column(String(32), index=True)  # "orb", "vwap_reversion"
    score: Mapped[float] = mapped_column(Float, default=0.0)
    p_hat: Mapped[float] = mapped_column(Float, default=0.5)
    ev_pct: Mapped[float] = mapped_column(Float, default=0.0)
    features_json: Mapped[str] = mapped_column(Text, default="{}")
    decision: Mapped[str] = mapped_column(String(16))  # "ENTER", "WATCH", "SKIP"
    reject_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Order(Base):
    """Paper orders submitted by decision engine."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String(32), ForeignKey("accounts.id"), index=True)
    signal_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("signals.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    token: Mapped[int] = mapped_column(Integer, ForeignKey("instruments.token"), index=True)
    side: Mapped[str] = mapped_column(String(8))  # "BUY", "SELL"
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    order_type: Mapped[str] = mapped_column(String(16), default="MARKET")
    limit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="SUBMITTED", index=True)  # SUBMITTED, FILLED, REJECTED, CANCELLED

    account: Mapped["Account"] = relationship("Account", back_populates="orders")
    fills: Mapped[list["Fill"]] = relationship("Fill", back_populates="order")


class Fill(Base):
    """Simulated execution fills with exact statutory charge attribution."""

    __tablename__ = "fills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("orders.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    slippage: Mapped[float] = mapped_column(Float, default=0.0)
    brokerage: Mapped[float] = mapped_column(Float, default=0.0)
    stt: Mapped[float] = mapped_column(Float, default=0.0)
    exchange: Mapped[float] = mapped_column(Float, default=0.0)
    gst: Mapped[float] = mapped_column(Float, default=0.0)
    sebi: Mapped[float] = mapped_column(Float, default=0.0)
    stamp: Mapped[float] = mapped_column(Float, default=0.0)

    order: Mapped["Order"] = relationship("Order", back_populates="fills")


class Position(Base):
    """Open and closed paper trading positions."""

    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String(32), ForeignKey("accounts.id"), index=True)
    token: Mapped[int] = mapped_column(Integer, ForeignKey("instruments.token"), index=True)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_price: Mapped[float] = mapped_column(Float, nullable=False)
    stop: Mapped[float] = mapped_column(Float, nullable=False)
    target: Mapped[float] = mapped_column(Float, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    net_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)  # TARGET, STOP, TIME_STOP, EOD_FLAT, KILL_SWITCH
    loss_tag: Mapped[str | None] = mapped_column(String(32), nullable=True)  # bad_signal, cost_drag, slippage, time_stop, stop_gap, regime

    account: Mapped["Account"] = relationship("Account", back_populates="positions")


class EquityCurve(Base):
    """Historical equity snapshots for performance curve and drawdown metrics."""

    __tablename__ = "equity_curve"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str] = mapped_column(String(32), ForeignKey("accounts.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    cash: Mapped[float] = mapped_column(Float, nullable=False)
    equity: Mapped[float] = mapped_column(Float, nullable=False)
    day_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    drawdown_pct: Mapped[float] = mapped_column(Float, default=0.0)

    __table_args__ = (Index("ix_equity_account_ts", "account_id", "ts"),)


class RiskEvent(Base):
    """Audit log of all risk limit triggers and vetoes."""

    __tablename__ = "risk_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    account_id: Mapped[str] = mapped_column(String(32), ForeignKey("accounts.id"), index=True)
    rule: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[float] = mapped_column(Float, default=0.0)
    limit: Mapped[float] = mapped_column(Float, default=0.0)
    action: Mapped[str] = mapped_column(String(32), nullable=False)  # REJECT, HALT_ENTRIES, PAUSE_WEEK, FORCE_FLAT


class ModelRun(Base):
    """ML Model training experiments and registry metadata."""

    __tablename__ = "model_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    model_type: Mapped[str] = mapped_column(String(32))  # "LightGBM", "LogisticRegression"
    train_window: Mapped[str] = mapped_column(String(64))
    test_window: Mapped[str] = mapped_column(String(64))
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    artifact_path: Mapped[str] = mapped_column(String(256))
    active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class ConfigVersion(Base):
    """Effective-dated configurations for past trade replay."""

    __tablename__ = "config_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    json: Mapped[str] = mapped_column(Text, nullable=False)


class StrategyVariant(Base):
    """Overfitting counter logging every unique strategy configuration run."""

    __tablename__ = "strategy_variants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    config_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    notes: Mapped[str] = mapped_column(Text, default="")


class MarketSession(Base):
    """Encrypted market data daily access token / credentials."""

    __tablename__ = "market_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    encrypted_token: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# Backward-compatible alias
KiteSession = MarketSession


# =========================================================================
# PHASE FINAL: DURABLE PERSISTENCE MODELS FOR PAPER TRADES & AUDITS
# =========================================================================

class DurableTradeRecord(Base):
    """Durable record of completed and open paper trades."""

    __tablename__ = "durable_trades"

    trade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(32), ForeignKey("accounts.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    strategy_name: Mapped[str] = mapped_column(String(64))
    strategy_version: Mapped[str] = mapped_column(String(32))
    direction: Mapped[str] = mapped_column(String(8), default="BUY")
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[float] = mapped_column(Float, nullable=False)
    entry_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    exit_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    gross_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    total_charges: Mapped[float] = mapped_column(Float, default=0.0)
    slippage: Mapped[float] = mapped_column(Float, default=0.0)
    net_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    r_multiple: Mapped[float] = mapped_column(Float, default=0.0)
    trade_status: Mapped[str] = mapped_column(String(32), default="CLOSED")
    exit_reason: Mapped[str] = mapped_column(String(64), default="")
    loss_tag: Mapped[str] = mapped_column(String(32), default="NONE")
    decision_reason: Mapped[str] = mapped_column(Text, default="")
    environment: Mapped[str] = mapped_column(String(32), default="PAPER_LIVE", index=True)  # DEMO vs PAPER_LIVE
    predicted_probability: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DurableDecisionSnapshot(Base):
    """Immutable record of the exact indicator values observed at decision time."""

    __tablename__ = "durable_decision_snapshots"

    trade_id: Mapped[str] = mapped_column(String(64), ForeignKey("durable_trades.trade_id"), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32))
    eval_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_price: Mapped[float] = mapped_column(Float, default=0.0)
    bid: Mapped[float] = mapped_column(Float, default=0.0)
    ask: Mapped[float] = mapped_column(Float, default=0.0)
    spread: Mapped[float] = mapped_column(Float, default=0.0)
    obi: Mapped[float] = mapped_column(Float, default=0.0)
    microprice: Mapped[float] = mapped_column(Float, default=0.0)
    rvol: Mapped[float] = mapped_column(Float, default=1.0)
    vwap: Mapped[float] = mapped_column(Float, default=0.0)
    vwap_deviation: Mapped[float] = mapped_column(Float, default=0.0)
    atr: Mapped[float] = mapped_column(Float, default=0.0)
    strategy_signal: Mapped[str] = mapped_column(String(32), default="ENTER")
    predicted_probability: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    expected_reward: Mapped[float] = mapped_column(Float, default=0.0)
    expected_loss: Mapped[float] = mapped_column(Float, default=0.0)
    expected_costs: Mapped[float] = mapped_column(Float, default=0.0)
    calculated_ev: Mapped[float] = mapped_column(Float, default=0.0)
    minimum_hurdle: Mapped[float] = mapped_column(Float, default=0.0)
    decision: Mapped[str] = mapped_column(String(32), default="ENTER")
    rejection_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)


class DurableExecutionForensics(Base):
    """Immutable simulated depth-walking fill details and latency."""

    __tablename__ = "durable_execution_forensics"

    trade_id: Mapped[str] = mapped_column(String(64), ForeignKey("durable_trades.trade_id"), primary_key=True)
    market_data_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    simulated_execution_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    configured_latency_ms: Mapped[int] = mapped_column(Integer, default=500)
    best_bid: Mapped[float | None] = mapped_column(Float, nullable=True)
    best_ask: Mapped[float | None] = mapped_column(Float, nullable=True)
    requested_quantity: Mapped[int] = mapped_column(Integer, default=1)
    filled_quantity: Mapped[int] = mapped_column(Integer, default=1)
    unfilled_quantity: Mapped[int] = mapped_column(Integer, default=0)
    vwap_fill_price: Mapped[float] = mapped_column(Float, default=0.0)
    slippage_ticks: Mapped[int] = mapped_column(Integer, default=1)
    slippage_amount: Mapped[float] = mapped_column(Float, default=0.0)
    levels_consumed_json: Mapped[str] = mapped_column(Text, default="[]")
    depth_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")


class DurableFeeBreakdown(Base):
    """Detailed statutory taxes and brokerage attached to a specific trade."""

    __tablename__ = "durable_fee_breakdowns"

    trade_id: Mapped[str] = mapped_column(String(64), ForeignKey("durable_trades.trade_id"), primary_key=True)
    schedule_id: Mapped[str] = mapped_column(String(64), default="DEFAULT_NSE_2024")
    effective_date: Mapped[str] = mapped_column(String(32), default="2024-10-01")
    turnover: Mapped[float] = mapped_column(Float, default=0.0)
    buy_value: Mapped[float] = mapped_column(Float, default=0.0)
    sell_value: Mapped[float] = mapped_column(Float, default=0.0)
    brokerage: Mapped[float] = mapped_column(Float, default=0.0)
    stt: Mapped[float] = mapped_column(Float, default=0.0)
    exchange_txn: Mapped[float] = mapped_column(Float, default=0.0)
    sebi: Mapped[float] = mapped_column(Float, default=0.0)
    gst: Mapped[float] = mapped_column(Float, default=0.0)
    stamp_duty: Mapped[float] = mapped_column(Float, default=0.0)
    total_charges: Mapped[float] = mapped_column(Float, default=0.0)


class DurableAuditEvent(Base):
    """Chronological event audit log for individual paper trades and risk checks."""

    __tablename__ = "durable_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    account_id: Mapped[str] = mapped_column(String(32), index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    trade_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    data_json: Mapped[str] = mapped_column(Text, default="{}")
    reason: Mapped[str] = mapped_column(Text, default="")


class DurableMarketSnapshot(Base):
    """Persisted market state snapshots for audits, replay, and strategy validation."""

    __tablename__ = "durable_market_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    market_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_price: Mapped[float] = mapped_column(Float, default=0.0)
    volume: Mapped[int] = mapped_column(Integer, default=0)
    vwap: Mapped[float] = mapped_column(Float, default=0.0)
    open: Mapped[float] = mapped_column(Float, default=0.0)
    high: Mapped[float] = mapped_column(Float, default=0.0)
    low: Mapped[float] = mapped_column(Float, default=0.0)
    close: Mapped[float] = mapped_column(Float, default=0.0)
    bids_json: Mapped[str] = mapped_column(Text, default="[]")
    asks_json: Mapped[str] = mapped_column(Text, default="[]")
    source: Mapped[str] = mapped_column(String(32), default="groww")
    data_age_ms: Mapped[float] = mapped_column(Float, default=0.0)
    is_complete_5_level: Mapped[bool] = mapped_column(Boolean, default=True)

