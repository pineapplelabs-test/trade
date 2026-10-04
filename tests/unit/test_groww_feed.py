"""Unit tests for Groww Trade API feed adapter (GrowwFeed)."""

from unittest.mock import MagicMock, patch

import pytest

from app.feed.base import MarketTick
from app.feed.groww_feed import GrowwFeed, normalize_groww_quote
from app.feed.instruments import InstrumentMaster, InstrumentMeta


def test_normalize_groww_quote_structure():
    """Verify raw Groww quote translates correctly to canonical MarketTick contract."""
    mock_quote = {
        "last_price": 1167.7,
        "volume": 542000,
        "average_price": 1172.5,
        "total_buy_quantity": 45000,
        "total_sell_quantity": 38000,
        "last_trade_quantity": 25,
        "last_trade_time": 1790850593,
        "ohlc": {
            "open": 1180.1,
            "high": 1183.9,
            "low": 1160.8,
            "close": 1167.7,
        },
        "depth": {
            "buy": [
                {"price": 1167.5, "quantity": 150, "orderCount": 3},
                {"price": 1167.0, "quantity": 300, "orderCount": 5},
            ],
            "sell": [
                {"price": 1167.8, "quantity": 200, "orderCount": 2},
                {"price": 1168.0, "quantity": 400, "orderCount": 4},
            ],
        },
    }

    master = InstrumentMaster()
    master.add_instrument(InstrumentMeta(token=2885, symbol="RELIANCE", name="Reliance Industries", sector="Energy", tick_size=0.05, active=True, surveillance_flag="NORMAL"))

    tick = normalize_groww_quote("RELIANCE", mock_quote, master)

    assert isinstance(tick, MarketTick)
    assert tick.symbol == "RELIANCE"
    assert tick.token == 2885
    assert tick.last_price == 1167.7
    assert tick.open == 1180.1
    assert tick.high == 1183.9
    assert tick.low == 1160.8
    assert tick.close == 1167.7
    assert tick.volume == 542000
    assert tick.average_traded_price == 1172.5
    assert tick.feed_source == "groww"
    assert len(tick.depth.bids) == 2
    assert len(tick.depth.asks) == 2
    assert tick.depth.best_bid == 1167.5
    assert tick.depth.best_ask == 1167.8
    assert tick.depth.spread == pytest.approx(0.3, rel=1e-3)


def test_normalize_groww_quote_offmarket_fallback():
    """Verify off-market quote with last_price 0 falls back to close price."""
    mock_quote = {
        "last_price": 0.0,
        "ohlc": {"open": 250.0, "high": 255.0, "low": 248.0, "close": 252.0},
        "depth": {"buy": [], "sell": []},
    }
    tick = normalize_groww_quote("TATAMOTORS", mock_quote)
    assert tick.last_price == 252.0
    assert tick.depth.best_bid == 0.0
    assert tick.depth.best_ask == 0.0


@pytest.mark.asyncio
async def test_groww_feed_lifecycle_mocked():
    """Verify connect, subscribe, and tick streaming logic."""
    feed = GrowwFeed()
    feed.subscribe_symbols(["RELIANCE", "TATAMOTORS"])
    assert "RELIANCE" in feed.subscribed_symbols
    assert "TATAMOTORS" in feed.subscribed_symbols

    mock_client = MagicMock()
    mock_client.get_quote.return_value = {
        "last_price": 500.0,
        "ohlc": {"open": 495.0, "high": 505.0, "low": 490.0, "close": 500.0},
    }

    with patch("app.feed.groww_feed.GrowwAPI") as mock_api:
        mock_api.get_access_token.return_value = "mock_token_123"
        mock_api.return_value = mock_client

        with patch("app.feed.groww_feed.settings") as mock_settings:
            mock_settings.GROWW_API_KEY = "test_key"
            mock_settings.GROWW_TOTP_TOKEN = "7KUVJYQAZ4ZDMYJHI3B7CNPVXTMIZI5S"

            await feed.connect()
            assert feed.is_running is True
            assert feed.access_token == "mock_token_123"

            # Test fetch_live_quote
            tick = await feed.fetch_live_quote("RELIANCE")
            assert tick is not None
            assert tick.last_price == 500.0

            await feed.disconnect()
            assert feed.is_running is False
