"""WebSocket connection manager for 1-second live telemetry broadcast."""

import asyncio
import json
import zoneinfo
from datetime import UTC, datetime, time

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

                from app.portfolio.account import portfolio_accounts

                # Update open position prices from latest ticks
                if settings.FEED_MODE == "groww":
                    try:
                        from app.feed.groww_feed import groww_feed
                        for acct in portfolio_accounts.values():
                            for sym in acct.positions:
                                if sym in groww_feed.latest_ticks:
                                    acct.update_market_price(sym, groww_feed.latest_ticks[sym].last_price)
                    except Exception as err:
                        logger.debug("ws_position_price_update_error", error=str(err))

                accounts_payload = {}
                open_positions_payload = []
                for acct_id, acct in portfolio_accounts.items():
                    day_pnl = round(acct.equity - acct.starting_capital, 2)
                    accounts_payload[acct_id] = {
                        "equity": acct.equity,
                        "day_pnl": day_pnl,
                        "cash": acct.cash,
                        "open_positions": len(acct.positions),
                        "unrealized_pnl": acct.total_unrealized_pnl,
                        "realized_pnl": acct.realized_pnl,
                    }
                    for sym, pos in acct.positions.items():
                        open_positions_payload.append({
                            "account_id": acct_id,
                            "symbol": sym,
                            "quantity": pos.quantity,
                            "entry_price": pos.entry_price,
                            "current_price": pos.current_price,
                            "stop_price": pos.stop_price,
                            "target_price": pos.target_price,
                            "unrealized_pnl": pos.unrealized_pnl,
                            "unrealized_pnl_pct": pos.unrealized_pnl_pct,
                            "opened_at": pos.opened_at.isoformat() if pos.opened_at else None,
                        })

                # Time window status
                in_force_flat_window = time(15, 15) <= now_ist.time() < time(15, 30)
                market_open = time(9, 15) <= now_ist.time() < time(15, 30)

                payload = {
                    "type": "snapshot",
                    "ts": now_utc.isoformat(),
                    "clock": clock_str,
                    "feed": settings.FEED_MODE,
                    "feed_source": "LIVE — Groww" if settings.FEED_MODE == "groww" else "DEMO",
                    "quote_age_ms": sample_quote_age,
                    "depth_age_ms": sample_depth_age,
                    "quality_status": "STALE" if sample_quote_age > 3000.0 else "VALID",
                    "market_session": {
                        "is_open": market_open,
                        "force_flat_window": in_force_flat_window,
                        "force_flat_cutoff": "15:15:00 IST",
                    },
                    "accounts": accounts_payload,
                    "scanner": scanner_items,
                    "positions": open_positions_payload,
                    "events": [],
                }
                await self.broadcast(payload)
            except Exception as e:
                logger.error("ws_broadcast_error", error=str(e))
            await asyncio.sleep(1.0)


manager = ConnectionManager()
