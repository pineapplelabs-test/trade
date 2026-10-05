"""Groww Trade API Market Data Feed Adapter (GrowwFeed).

READ-ONLY MARKET DATA STREAMING:
Subscribes to live NSE cash equity market depth, LTP, and historical candles.
Contains ZERO order placement or execution functions (strictly paper trading).
"""

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pyotp
import structlog
from growwapi import GrowwAPI
from growwapi import GrowwFeed as SDKGrowwFeed

from app.config import get_settings
from app.feed.base import DepthLevel, FeedBase, MarketTick, OrderBookDepth
from app.feed.instruments import InstrumentMaster

logger = structlog.get_logger()
settings = get_settings()


def normalize_groww_quote(
    symbol: str,
    raw_quote: dict[str, Any],
    master: InstrumentMaster | None = None,
) -> MarketTick:
    """Normalize raw quote dictionary from Groww Trade API into canonical MarketTick contract."""
    token = 0
    if master:
        inst = master.get_by_symbol(symbol)
        if inst:
            token = inst.token

    trade_time_raw = raw_quote.get("last_trade_time")
    if trade_time_raw and isinstance(trade_time_raw, (int, float)):
        ts = datetime.fromtimestamp(trade_time_raw, tz=UTC)
    else:
        ts = datetime.now(UTC)

    ohlc = raw_quote.get("ohlc", {}) or {}
    raw_depth = raw_quote.get("depth", {}) or {}
    raw_bids = raw_depth.get("buy", []) or []
    raw_asks = raw_depth.get("sell", []) or []

    bids = [
        DepthLevel(
            price=float(b.get("price", 0.0)),
            quantity=int(b.get("quantity", 0)),
            orders=int(b.get("orderCount", 1)),
        )
        for b in raw_bids
        if float(b.get("price", 0.0)) > 0
    ]
    asks = [
        DepthLevel(
            price=float(a.get("price", 0.0)),
            quantity=int(a.get("quantity", 0)),
            orders=int(a.get("orderCount", 1)),
        )
        for a in raw_asks
        if float(a.get("price", 0.0)) > 0
    ]

    last_price = float(raw_quote.get("last_price", 0.0))
    # Fallback to close price if last_price is 0 (off-market)
    if last_price <= 0 and ohlc.get("close"):
        last_price = float(ohlc.get("close", 0.0))

    return MarketTick(
        token=token,
        symbol=symbol,
        timestamp=ts,
        last_price=last_price,
        last_quantity=int(raw_quote.get("last_trade_quantity", 0)),
        volume=int(raw_quote.get("volume", 0)),
        average_traded_price=float(raw_quote.get("average_price") or last_price),
        total_buy_quantity=int(raw_quote.get("total_buy_quantity", 0)),
        total_sell_quantity=int(raw_quote.get("total_sell_quantity", 0)),
        open=float(ohlc.get("open", 0.0)),
        high=float(ohlc.get("high", 0.0)),
        low=float(ohlc.get("low", 0.0)),
        close=float(ohlc.get("close", 0.0)),
        depth=OrderBookDepth(bids=bids, asks=asks),
        feed_source="groww",
    )


class GrowwFeed(FeedBase):
    """Groww Trade API live and polling market data feed client.

    Maintains session using TOTP auto-generation, handles market depth streaming,
    and supports off-hours quote fetching so paper testing runs 24/7.
    """

    def __init__(self, master: InstrumentMaster | None = None) -> None:
        self.master = master or InstrumentMaster()
        self.subscribed_tokens: set[int] = set()
        self.subscribed_symbols: set[str] = set()
        self.is_running = False
        self._tick_queue: asyncio.Queue[MarketTick] = asyncio.Queue(maxsize=10000)
        self.latest_ticks: dict[str, MarketTick] = {}
        self.api_client: GrowwAPI | None = None
        self.feed_client: SDKGrowwFeed | None = None
        self.access_token: str | None = None
        self._poll_task: asyncio.Task | None = None

    async def connect(self) -> None:
        """Authenticate with Groww API using TOTP token & initialize client."""
        if not settings.GROWW_API_KEY or not settings.GROWW_TOTP_TOKEN:
            logger.warn("groww_feed_missing_credentials", reason="Missing GROWW_API_KEY or GROWW_TOTP_TOKEN")
            return

        try:
            # Auto-compute 6-digit TOTP code
            totp_code = pyotp.TOTP(settings.GROWW_TOTP_TOKEN).now()
            # Request access token
            token_response = await asyncio.to_thread(
                GrowwAPI.get_access_token,
                api_key=settings.GROWW_API_KEY,
                totp=totp_code,
            )

            if isinstance(token_response, str):
                self.access_token = token_response
            elif isinstance(token_response, dict):
                self.access_token = token_response.get("token") or token_response.get("access_token")
            else:
                self.access_token = str(token_response)

            self.api_client = GrowwAPI(self.access_token)
            self.is_running = True
            logger.info("groww_feed_authenticated_successfully")

            # Launch background quote polling task for subscribed symbols
            self._poll_task = asyncio.create_task(self._poll_quotes_loop())

        except Exception as e:
            logger.error("groww_feed_auth_failed", error=str(e))
            self.is_running = False

    async def disconnect(self) -> None:
        """Disconnect and clean up tasks."""
        self.is_running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        logger.info("groww_feed_disconnected")

    async def subscribe(self, tokens: list[int]) -> None:
        """Subscribe to token identifiers and map to trading symbols."""
        for t in tokens:
            self.subscribed_tokens.add(t)
            inst = self.master.get_by_token(t)
            if inst:
                self.subscribed_symbols.add(inst.symbol)

    def subscribe_symbols(self, symbols: list[str]) -> None:
        """Directly subscribe symbols (e.g. RELIANCE, TATAMOTORS)."""
        for sym in symbols:
            self.subscribed_symbols.add(sym)

    async def unsubscribe(self, tokens: list[int]) -> None:
        """Unsubscribe from tokens."""
        for t in tokens:
            self.subscribed_tokens.discard(t)
            inst = self.master.get_by_token(t)
            if inst:
                self.subscribed_symbols.discard(inst.symbol)

    def fetch_quote_sync(self, symbol: str) -> MarketTick | None:
        """Synchronously fetch quote from Groww API and normalize."""
        if not self.api_client:
            return None
        try:
            groww_sym = {"TATAMOTORS": "TMPV"}.get(symbol, symbol)
            raw = self.api_client.get_quote(trading_symbol=groww_sym, exchange="NSE", segment="CASH")
            if raw:
                return normalize_groww_quote(symbol, raw, self.master)
        except Exception as e:
            logger.debug("groww_quote_fetch_failed", symbol=symbol, error=str(e))
        return None

    async def fetch_live_quote(self, symbol: str) -> MarketTick | None:
        """Async helper to get quote without blocking event loop."""
        return await asyncio.to_thread(self.fetch_quote_sync, symbol)

    async def _poll_quotes_loop(self) -> None:
        """Continuous background loop updating quotes for active watchlist."""
        # Default priority symbols if none subscribed yet
        default_symbols = ["RELIANCE", "TMPV", "BHARTIARTL", "BEL", "INFY", "TCS", "HDFCBANK", "ICICIBANK", "TATASTEEL", "SBIN"]

        while self.is_running:
            active_symbols = list(self.subscribed_symbols) or default_symbols
            for symbol in active_symbols:
                if not self.is_running:
                    break
                try:
                    tick = await self.fetch_live_quote(symbol)
                    if tick:
                        self.latest_ticks[symbol] = tick
                        try:
                            self._tick_queue.put_nowait(tick)
                        except asyncio.QueueFull:
                            try:
                                self._tick_queue.get_nowait()
                                self._tick_queue.put_nowait(tick)
                            except Exception:
                                pass
                except Exception as e:
                    logger.debug("groww_poll_error", symbol=symbol, error=str(e))
                # Slight throttle between symbol requests to stay within rate limits
                await asyncio.sleep(0.35)
            # Interval between full scan cycles
            await asyncio.sleep(1.0)

    async def stream_ticks(self) -> AsyncGenerator[MarketTick, None]:
        """Yield normalized MarketTick events from queue."""
        while self.is_running:
            try:
                tick = await asyncio.wait_for(self._tick_queue.get(), timeout=1.0)
                yield tick
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break


# Module-level default Groww feed instance
groww_feed = GrowwFeed()

