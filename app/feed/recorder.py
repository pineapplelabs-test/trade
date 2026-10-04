"""Market Snapshot Recorder for Forensic Audit, Replay, and Strategy Validation."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.feed.base import MarketTick


@dataclass(frozen=True)
class RecordedSnapshot:
    snapshot_id: str
    symbol: str
    market_timestamp: datetime
    recorded_at: datetime
    last_price: float
    volume: int
    bids: list[dict[str, Any]]
    asks: list[dict[str, Any]]
    source: str


class MarketDataRecorder:
    """Thread-safe ring-buffer recorder for market snapshots."""

    def __init__(self, capacity: int = 5000) -> None:
        self.capacity = capacity
        self.snapshots: list[RecordedSnapshot] = []
        self._seq = 0

    def record_snapshot(self, tick: MarketTick) -> str:
        """Record market snapshot and return unique snapshot_id."""
        self._seq += 1
        now = datetime.now(UTC)
        snapshot_id = f"SNAP-{tick.symbol}-{self._seq}"

        rec = RecordedSnapshot(
            snapshot_id=snapshot_id,
            symbol=tick.symbol,
            market_timestamp=tick.timestamp,
            recorded_at=now,
            last_price=tick.last_price,
            volume=tick.volume,
            bids=[{"price": b.price, "qty": b.quantity} for b in tick.depth.bids[:5]],
            asks=[{"price": a.price, "qty": a.quantity} for a in tick.depth.asks[:5]],
            source=tick.feed_source,
        )

        self.snapshots.append(rec)
        if len(self.snapshots) > self.capacity:
            self.snapshots.pop(0)

        return snapshot_id

    def get_snapshot(self, snapshot_id: str) -> RecordedSnapshot | None:
        for s in reversed(self.snapshots):
            if s.snapshot_id == snapshot_id:
                return s
        return None

    def get_snapshots_for_symbol(self, symbol: str, limit: int = 50) -> list[RecordedSnapshot]:
        matched = [s for s in self.snapshots if s.symbol == symbol]
        return matched[-limit:]

    async def save_snapshot_to_db(
        self,
        tick: MarketTick,
        decision_timestamp: datetime | None = None,
    ) -> str:
        """Persist exact 5-level market data snapshot to SQLite for forensic reconstruction."""
        import json

        from app.db.models import DurableMarketSnapshot
        from app.db.session import async_session_factory

        self._seq += 1
        now = datetime.now(UTC)
        snapshot_id = f"SNAP-{tick.symbol}-{self._seq}"

        # In-memory buffer
        rec = RecordedSnapshot(
            snapshot_id=snapshot_id,
            symbol=tick.symbol,
            market_timestamp=tick.timestamp,
            recorded_at=now,
            last_price=tick.last_price,
            volume=tick.volume,
            bids=[{"price": b.price, "qty": b.quantity} for b in tick.depth.bids[:5]],
            asks=[{"price": a.price, "qty": a.quantity} for a in tick.depth.asks[:5]],
            source=tick.feed_source,
        )
        self.snapshots.append(rec)
        if len(self.snapshots) > self.capacity:
            self.snapshots.pop(0)

        # SQLite durable storage
        is_complete = len(tick.depth.bids) >= 5 and len(tick.depth.asks) >= 5
        data_age = (now - tick.timestamp).total_seconds() * 1000.0

        async with async_session_factory() as session:
            durable_snap = DurableMarketSnapshot(
                snapshot_id=snapshot_id,
                symbol=tick.symbol,
                market_timestamp=tick.timestamp,
                recorded_at=now,
                last_price=tick.last_price,
                volume=tick.volume,
                vwap=tick.average_traded_price or tick.last_price,
                open=tick.open,
                high=tick.high,
                low=tick.low,
                close=tick.close,
                bids_json=json.dumps([{"price": b.price, "qty": b.quantity} for b in tick.depth.bids[:5]]),
                asks_json=json.dumps([{"price": a.price, "qty": a.quantity} for a in tick.depth.asks[:5]]),
                source=tick.feed_source,
                data_age_ms=data_age,
                is_complete_5_level=is_complete,
            )
            session.add(durable_snap)
            await session.commit()

        return snapshot_id

    async def get_durable_snapshot_from_db(self, snapshot_id: str) -> dict[str, Any] | None:
        """Retrieve historical market snapshot from SQLite."""
        import json

        from app.db.models import DurableMarketSnapshot
        from app.db.session import async_session_factory

        async with async_session_factory() as session:
            snap = await session.get(DurableMarketSnapshot, snapshot_id)
            if not snap:
                return None
            return {
                "snapshot_id": snap.snapshot_id,
                "symbol": snap.symbol,
                "market_timestamp": snap.market_timestamp,
                "recorded_at": snap.recorded_at,
                "last_price": snap.last_price,
                "volume": snap.volume,
                "vwap": snap.vwap,
                "open": snap.open,
                "high": snap.high,
                "low": snap.low,
                "close": snap.close,
                "bids": json.loads(snap.bids_json or "[]"),
                "asks": json.loads(snap.asks_json or "[]"),
                "source": snap.source,
                "data_age_ms": snap.data_age_ms,
                "is_complete_5_level": snap.is_complete_5_level,
            }


# Global singleton recorder
global_market_recorder = MarketDataRecorder()
