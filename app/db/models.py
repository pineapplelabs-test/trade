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


class KiteSession(Base):
    """Encrypted Zerodha Kite Connect daily access token."""

    __tablename__ = "kite_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    encrypted_token: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
