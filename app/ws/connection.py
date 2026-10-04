"""WebSocket connection manager for 1-second live telemetry broadcast."""

import asyncio
import json
import zoneinfo
from datetime import UTC, datetime

import structlog
from fastapi import WebSocket

from app.config import get_settings

logger = structlog.get_logger()
kolkata_tz = zoneinfo.ZoneInfo("Asia/Kolkata")
settings = get_settings()


class ConnectionManager:
    """Manages active browser WebSocket connections with heartbeat and broadcast."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        self._broadcast_task: asyncio.Task | None = None

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("ws_client_connected", count=len(self.active_connections))

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("ws_client_disconnected", count=len(self.active_connections))

    async def broadcast(self, message: dict) -> None:
        text_data = json.dumps(message)
        for connection in list(self.active_connections):
            try:
                await connection.send_text(text_data)
            except Exception:
                self.disconnect(connection)

    async def start_broadcaster(self) -> None:
        """Background loop pushing live snapshot every second."""
        while True:
            try:
                now_utc = datetime.now(UTC)
                now_ist = now_utc.astimezone(kolkata_tz)
                clock_str = now_ist.strftime("%H:%M:%S")

                scanner_items = []
                if settings.FEED_MODE == "groww":
                    try:
                        from app.feed.groww_feed import groww_feed
                        for sym, tick in groww_feed.latest_ticks.items():
                            chg = round(((tick.last_price - tick.close) / tick.close * 100), 2) if tick.close > 0 else 0.0
                            scanner_items.append({
                                "symbol": sym,
                                "price": tick.last_price,
                                "change": chg,
                                "open": tick.open,
                                "high": tick.high,
                                "low": tick.low,
                                "close": tick.close,
                                "volume": tick.volume,
                                "depth": {
                                    "bids": [{"price": b.price, "qty": b.quantity} for b in tick.depth.bids],
                                    "asks": [{"price": a.price, "qty": a.quantity} for a in tick.depth.asks],
                                },
                            })
                    except Exception as err:
                        logger.debug("groww_ws_scanner_format_error", error=str(err))

                # Compute sample freshness for benchmark symbol (e.g. BEL or first symbol)
                sample_quote_age = 0.0
                sample_depth_age = 0.0
                if scanner_items:
                    tick_sym = str(scanner_items[0]["symbol"])
                    t_obj = groww_feed.latest_ticks.get(tick_sym) if settings.FEED_MODE == "groww" else None
                    if t_obj:
                        delta = (now_utc - t_obj.timestamp).total_seconds() * 1000.0
                        sample_quote_age = round(max(0.0, delta), 1)
                        sample_depth_age = round(max(0.0, delta), 1)

                payload = {
                    "type": "snapshot",
                    "ts": now_utc.isoformat(),
                    "clock": clock_str,
                    "feed": settings.FEED_MODE,
                    "feed_source": "LIVE — Groww" if settings.FEED_MODE == "groww" else "DEMO",
                    "quote_age_ms": sample_quote_age,
                    "depth_age_ms": sample_depth_age,
                    "quality_status": "STALE" if sample_quote_age > 3000.0 else "VALID",
                    "accounts": {
                        "real5k": {"equity": 5000.0, "day_pnl": 0.0, "cash": 5000.0},
                        "tiny": {"equity": 1000.0, "day_pnl": 0.0, "cash": 1000.0},
                        "shadow": {"equity": 100000.0, "day_pnl": 0.0, "cash": 100000.0},
                    },
                    "scanner": scanner_items,
                    "positions": [],
                    "events": [],
                }
                await self.broadcast(payload)
            except Exception as e:
                logger.error("ws_broadcast_error", error=str(e))
            await asyncio.sleep(1.0)


manager = ConnectionManager()
