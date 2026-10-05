"""Data Freshness & Order Book Integrity Validator."""

from datetime import UTC, datetime
from enum import StrEnum

from app.feed.base import MarketTick


class FreshnessStatus(StrEnum):
    VALID = "VALID"
    STALE = "STALE"
    FUTURE_LEAK = "FUTURE_LEAK"
    INVALID_DEPTH = "INVALID_DEPTH"
    INSUFFICIENT_DEPTH = "INSUFFICIENT_DEPTH"
    IMPOSSIBLE_PRICE = "IMPOSSIBLE_PRICE"
    DUPLICATE_TICK = "DUPLICATE_TICK"
    CLOCK_SKEW = "CLOCK_SKEW"
    VOLUME_REGRESSION = "VOLUME_REGRESSION"
    SYMBOL_MISMATCH = "SYMBOL_MISMATCH"


class MarketDataValidator:
    """Validates market data freshness, temporal causality, depth completeness, and tick consistency."""

    def __init__(
        self,
        max_quote_age_ms: int = 3000,
        max_depth_age_ms: int = 3000,
        require_full_5_level: bool = True,
        max_clock_skew_seconds: float = 10.0,
    ) -> None:
        self.max_quote_age_ms = max_quote_age_ms
        self.max_depth_age_ms = max_depth_age_ms
        self.require_full_5_level = require_full_5_level
        self.max_clock_skew_seconds = max_clock_skew_seconds
        self._last_seen_ticks: dict[str, MarketTick] = {}

    def validate_tick(
        self,
        tick: MarketTick,
        decision_timestamp: datetime | None = None,
        now: datetime | None = None,
        expected_symbol: str | None = None,
    ) -> tuple[FreshnessStatus, str]:
        """Validate tick against time constraints, future leakage, and book structure."""
        curr_now = now or datetime.now(UTC)
        dec_ts = decision_timestamp or curr_now

        # 0. Symbol / Instrument Mismatch
        if expected_symbol is not None and tick.symbol != expected_symbol:
            return (
                FreshnessStatus.SYMBOL_MISMATCH,
                f"Symbol mismatch: tick symbol '{tick.symbol}' does not match expected '{expected_symbol}'",
            )

        # 1. Price Sanity Check
        if tick.last_price <= 0.0:
            return (
                FreshnessStatus.IMPOSSIBLE_PRICE,
                f"Impossible price: last_price ₹{tick.last_price} must be strictly positive",
            )

        # 2. Temporal Integrity / Forward-Looking Data Leakage Check
        # Rule: tick.timestamp MUST be <= decision_timestamp
        if tick.timestamp > dec_ts:
            delta_ms = (tick.timestamp - dec_ts).total_seconds() * 1000.0
            return (
                FreshnessStatus.FUTURE_LEAK,
                f"Future market data detected: tick timestamp ({tick.timestamp.isoformat()}) > decision timestamp ({dec_ts.isoformat()}) by {delta_ms:.1f}ms",
            )

        # 3. Freshness Check (Age vs current clock)
        age_ms = (curr_now - tick.timestamp).total_seconds() * 1000.0
        if age_ms > self.max_quote_age_ms:
            return (
                FreshnessStatus.STALE,
                f"Market quote too old: age {age_ms:.1f}ms exceeds maximum threshold of {self.max_quote_age_ms}ms",
            )

        # 4. Clock Skew Check (Receive Timestamp vs Source Timestamp)
        if hasattr(tick, "received_timestamp") and tick.received_timestamp is not None:
            skew_sec = abs((tick.received_timestamp - tick.timestamp).total_seconds())
            if skew_sec > self.max_clock_skew_seconds:
                return (
                    FreshnessStatus.CLOCK_SKEW,
                    f"Clock skew detected: difference between source ({tick.timestamp.isoformat()}) and receive ({tick.received_timestamp.isoformat()}) is {skew_sec:.1f}s (max {self.max_clock_skew_seconds}s)",
                )

        # 5. Duplicate Tick Check & Volume Consistency
        prev_tick = self._last_seen_ticks.get(tick.symbol)
        if prev_tick is not None:
            if (
                tick.timestamp == prev_tick.timestamp
                and tick.last_price == prev_tick.last_price
                and tick.volume == prev_tick.volume
            ):
                return (
                    FreshnessStatus.DUPLICATE_TICK,
                    f"Duplicate tick detected for {tick.symbol} at {tick.timestamp.isoformat()} (identical price ₹{tick.last_price} and volume {tick.volume})",
                )

            if tick.volume < prev_tick.volume:
                return (
                    FreshnessStatus.VOLUME_REGRESSION,
                    f"Volume regression detected for {tick.symbol}: current volume {tick.volume} < previous {prev_tick.volume}",
                )

        # 6. Order Book Completeness
        if self.require_full_5_level and not tick.depth.is_complete_5_level:
            return (
                FreshnessStatus.INSUFFICIENT_DEPTH,
                f"Insufficient market depth: bids={len(tick.depth.bids)}, asks={len(tick.depth.asks)} (require 5 full levels)",
            )

        # 7. Depth Sanity, Monotonicity, and Crossed/Locked Book
        valid_depth, err = tick.depth.validate_sanity()
        if not valid_depth:
            return (
                FreshnessStatus.INVALID_DEPTH,
                f"Invalid order book structure: {err}",
            )

        self._last_seen_ticks[tick.symbol] = tick
        return FreshnessStatus.VALID, "Valid"
