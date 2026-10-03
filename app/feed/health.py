"""Market Data Health & Stale Feed Monitor."""

from datetime import UTC, datetime

import structlog

from app.config import get_risk_config
from app.feed.base import MarketTick

logger = structlog.get_logger()


class DataHealthMonitor:
    """Monitors incoming tick timestamps and flags feed staleness."""

    def __init__(self, index_token: int = 256265) -> None:  # Default 256265 = NIFTY 50
        self.index_token = index_token
        self.last_tick_time: dict[int, datetime] = {}
        self.last_any_tick_time: datetime | None = None
        self.config = get_risk_config()

    def update_tick(self, tick: MarketTick) -> None:
        """Update last seen tick timestamp."""
        now = datetime.now(UTC)
        self.last_tick_time[tick.token] = now
        self.last_any_tick_time = now

    def get_stale_seconds(self, token: int | None = None) -> float:
        """Return elapsed seconds since last received tick for token or overall."""
        target_token = token or self.index_token
        last = self.last_tick_time.get(target_token) or self.last_any_tick_time
        if last is None:
            return 999.0
        return (datetime.now(UTC) - last).total_seconds()

    def is_stale(self, token: int | None = None) -> bool:
        """Return True if no tick has arrived within threshold (default 3.0s)."""
        limit = float(self.config.get("data_health", {}).get("stale_tick_timeout_seconds", 3.0))
        return bool(self.get_stale_seconds(token) > limit)
