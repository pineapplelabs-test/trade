"""Unit tests for InstrumentMaster and NSE Trading Calendar."""

import tempfile
import zoneinfo
from datetime import date, datetime
from pathlib import Path

import polars as pl

from app.feed.calendar import get_market_session_phase, is_trading_day
from app.feed.instruments import DEFAULT_INSTRUMENTS, InstrumentMaster, InstrumentMeta

KOLKATA_TZ = zoneinfo.ZoneInfo("Asia/Kolkata")


def test_instrument_master_operations():
    """Verify lookup, surveillance filtering, and Parquet export."""
    master = InstrumentMaster(DEFAULT_INSTRUMENTS)

    # Lookup by token
    rel = master.get_by_token(738561)
    assert rel is not None
    assert rel.symbol == "RELIANCE"

    # Lookup by symbol
    tatamotors = master.get_by_symbol("TATAMOTORS")
    assert tatamotors is not None
    assert tatamotors.token == 884737

    # Surveillance filtering
    master.add_instrument(
        InstrumentMeta(
            token=999999,
            symbol="RISKY",
            name="Risky Stock",
            sector="General",
            tick_size=0.05,
            active=True,
            surveillance_flag="ASM",  # Under ASM
        )
    )

    tradable = master.list_tradable_tokens(allow_asm_gsm=False)
    assert 999999 not in tradable

    all_tokens = master.list_tradable_tokens(allow_asm_gsm=True)
    assert 999999 in all_tokens

    # Export to Parquet
    with tempfile.TemporaryDirectory() as tmp_dir:
        pq_path = master.export_parquet(Path(tmp_dir) / "catalog.parquet")
        assert pq_path.exists()
        df = pl.read_parquet(pq_path)
        assert df.height >= len(DEFAULT_INSTRUMENTS)


def test_nse_calendar_holidays_and_weekends():
    """Verify official NSE trading days and holiday exclusions."""
    # Weekend: Saturday 2026-10-03 -> False
    assert is_trading_day(date(2026, 10, 3)) is False
    assert is_trading_day(date(2026, 10, 4)) is False

    # Official Holiday: Republic Day 2026-01-26 -> False
    assert is_trading_day(date(2026, 1, 26)) is False

    # Gandhi Jayanti 2026-10-02 -> False
    assert is_trading_day(date(2026, 10, 2)) is False

    # Regular trading day: Monday 2026-10-05 -> True
    assert is_trading_day(date(2026, 10, 5)) is True


def test_market_session_phase():
    """Verify market phases: REGULAR during 09:15-15:30 IST on trading day."""
    # Trading day at 10:30 AM IST -> REGULAR
    dt_trading = datetime(2026, 10, 5, 10, 30, tzinfo=KOLKATA_TZ)
    assert get_market_session_phase(dt_trading) == "REGULAR"

    # Pre-open at 09:05 AM IST
    dt_pre = datetime(2026, 10, 5, 9, 5, tzinfo=KOLKATA_TZ)
    assert get_market_session_phase(dt_pre) == "PRE_OPEN_ORDER_COLLECTION"

    # Night at 22:00 IST -> CLOSED
    dt_night = datetime(2026, 10, 5, 22, 0, tzinfo=KOLKATA_TZ)
    assert get_market_session_phase(dt_night) == "CLOSED"
