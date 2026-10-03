"""WebSocket connection manager for 1-second live telemetry broadcast."""

import asyncio
import json
import zoneinfo
from datetime import UTC, datetime

import structlog
from fastapi import WebSocket

logger = structlog.get_logger()
kolkata_tz = zoneinfo.ZoneInfo("Asia/Kolkata")


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

                payload = {
                    "type": "snapshot",
                    "ts": now_utc.isoformat(),
                    "clock": clock_str,
                    "feed": "sim",
                    "accounts": {
                        "real5k": {"equity": 5000.0, "day_pnl": 0.0, "cash": 5000.0},
                        "tiny": {"equity": 1000.0, "day_pnl": 0.0, "cash": 1000.0},
                        "shadow": {"equity": 100000.0, "day_pnl": 0.0, "cash": 100000.0},
                    },
                    "scanner": [],
                    "positions": [],
                    "events": [],
                }
                await self.broadcast(payload)
            except Exception as e:
                logger.error("ws_broadcast_error", error=str(e))
            await asyncio.sleep(1.0)


manager = ConnectionManager()
