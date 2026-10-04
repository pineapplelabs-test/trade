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


class MarketDataValidator:
    """Validates market data freshness, temporal causality, and depth completeness."""

    def __init__(
        self,
        max_quote_age_ms: int = 3000,
        max_depth_age_ms: int = 3000,
        require_full_5_level: bool = True,
    ) -> None:
        self.max_quote_age_ms = max_quote_age_ms
        self.max_depth_age_ms = max_depth_age_ms
        self.require_full_5_level = require_full_5_level

    def validate_tick(
        self,
        tick: MarketTick,
        decision_timestamp: datetime | None = None,
        now: datetime | None = None,
    ) -> tuple[FreshnessStatus, str]:
        """Validate tick against time constraints, future leakage, and book structure."""
        curr_now = now or datetime.now(UTC)
        dec_ts = decision_timestamp or curr_now

        # 1. Temporal Integrity / Forward-Looking Data Leakage Check
        # Rule: tick.timestamp MUST be <= decision_timestamp
        if tick.timestamp > dec_ts:
            delta_ms = (tick.timestamp - dec_ts).total_seconds() * 1000.0
            return (
                FreshnessStatus.FUTURE_LEAK,
                f"Future market data detected: tick timestamp ({tick.timestamp.isoformat()}) > decision timestamp ({dec_ts.isoformat()}) by {delta_ms:.1f}ms",
            )

        # 2. Freshness Check (Age vs current clock)
        age_ms = (curr_now - tick.timestamp).total_seconds() * 1000.0
        if age_ms > self.max_quote_age_ms:
            return (
                FreshnessStatus.STALE,
                f"Market quote too old: age {age_ms:.1f}ms exceeds maximum threshold of {self.max_quote_age_ms}ms",
            )

        # 3. Order Book Completeness
        if self.require_full_5_level and not tick.depth.is_complete_5_level:
            return (
                FreshnessStatus.INSUFFICIENT_DEPTH,
                f"Insufficient market depth: bids={len(tick.depth.bids)}, asks={len(tick.depth.asks)} (require 5 full levels)",
            )

        # 4. Depth Sanity & Monotonicity
        valid_depth, err = tick.depth.validate_sanity()
        if not valid_depth:
            return (
                FreshnessStatus.INVALID_DEPTH,
                f"Invalid order book structure: {err}",
            )

        return FreshnessStatus.VALID, "Valid"
