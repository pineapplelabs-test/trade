"""OHLCV Bar Aggregator from Market Ticks.

Builds 1-minute bars from normalized MarketTick events and derives 5-minute and
daily bars. Exports to partitioned Parquet files.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from app.feed.base import MarketTick

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "bars"


@dataclass(frozen=True)
class Bar:
    token: int
    symbol: str
    timeframe: str  # "1m", "5m", "1d"
    start_time: datetime
    end_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: float
    tick_count: int


class TokenBarAggregator:
    """Aggregates ticks into 1-minute bars for a single instrument."""

    def __init__(self, token: int, symbol: str) -> None:
        self.token = token
        self.symbol = symbol
        self.current_bar_minute: int | None = None
        self.current_start_time: datetime | None = None
        self.open: float = 0.0
        self.high: float = 0.0
        self.low: float = 0.0
        self.close: float = 0.0
        self.volume: int = 0
        self.cum_price_vol: float = 0.0
        self.tick_count: int = 0

    def add_tick(self, tick: MarketTick) -> Bar | None:
        """Process tick. If minute rolled over, return completed Bar, else None."""
        ts = tick.timestamp
        # Minute index since Unix epoch
        minute_idx = int(ts.timestamp() // 60)

        completed_bar: Bar | None = None

        if self.current_bar_minute is not None and minute_idx != self.current_bar_minute:
            # Emit completed bar for previous minute
            end_ts = datetime.fromtimestamp((self.current_bar_minute + 1) * 60, tz=UTC)
            start_ts = self.current_start_time or datetime.fromtimestamp(self.current_bar_minute * 60, tz=UTC)
            vwap = round(self.cum_price_vol / max(self.volume, 1), 2)

            completed_bar = Bar(
                token=self.token,
                symbol=self.symbol,
                timeframe="1m",
                start_time=start_ts,
                end_time=end_ts,
                open=self.open,
                high=self.high,
                low=self.low,
                close=self.close,
                volume=self.volume,
                vwap=vwap,
                tick_count=self.tick_count,
            )

            # Reset for new minute
            self.current_bar_minute = minute_idx
            self.current_start_time = datetime.fromtimestamp(minute_idx * 60, tz=UTC)
            self.open = tick.last_price
            self.high = tick.last_price
            self.low = tick.last_price
            self.close = tick.last_price
            self.volume = tick.last_quantity
            self.cum_price_vol = tick.last_price * tick.last_quantity
            self.tick_count = 1
        else:
            if self.current_bar_minute is None:
                self.current_bar_minute = minute_idx
                self.current_start_time = datetime.fromtimestamp(minute_idx * 60, tz=UTC)
                self.open = tick.last_price
                self.high = tick.last_price
                self.low = tick.last_price
                self.close = tick.last_price
                self.volume = tick.last_quantity
                self.cum_price_vol = tick.last_price * tick.last_quantity
                self.tick_count = 1
            else:
                self.high = max(self.high, tick.last_price)
                self.low = min(self.low, tick.last_price)
                self.close = tick.last_price
                self.volume += tick.last_quantity
                self.cum_price_vol += tick.last_price * tick.last_quantity
                self.tick_count += 1

        return completed_bar


class BarBuilder:
    """Manages multi-token real-time bar aggregation and Parquet persistence."""

    def __init__(self, on_bar_completed: Callable[[Bar], None] | None = None) -> None:
        self.aggregators: dict[int, TokenBarAggregator] = {}
        self.completed_1m_bars: list[Bar] = []
        self.completed_5m_bars: list[Bar] = []
        self.on_bar_completed = on_bar_completed

    def process_tick(self, tick: MarketTick) -> Bar | None:
        """Route tick to token aggregator. Emits 1m Bar on completion."""
        if tick.token not in self.aggregators:
            self.aggregators[tick.token] = TokenBarAggregator(tick.token, tick.symbol)

        bar_1m = self.aggregators[tick.token].add_tick(tick)
        if bar_1m:
            self.completed_1m_bars.append(bar_1m)
            if self.on_bar_completed:
                self.on_bar_completed(bar_1m)

            # Check 5m bar rollup
            self._check_5m_bar(bar_1m)

        return bar_1m

    def _check_5m_bar(self, bar_1m: Bar) -> Bar | None:
        """Roll up 5 completed 1m bars into a 5m bar."""
        # Filter recent 1m bars for this token
        token_1m = [b for b in self.completed_1m_bars if b.token == bar_1m.token]
        minute = bar_1m.end_time.minute
        if minute % 5 == 0 and len(token_1m) >= 5:
            last_5 = token_1m[-5:]
            b5 = Bar(
                token=bar_1m.token,
                symbol=bar_1m.symbol,
                timeframe="5m",
                start_time=last_5[0].start_time,
                end_time=last_5[-1].end_time,
                open=last_5[0].open,
                high=max(b.high for b in last_5),
                low=min(b.low for b in last_5),
                close=last_5[-1].close,
                volume=sum(b.volume for b in last_5),
                vwap=round(sum(b.vwap * b.volume for b in last_5) / max(sum(b.volume for b in last_5), 1), 2),
                tick_count=sum(b.tick_count for b in last_5),
            )
            self.completed_5m_bars.append(b5)
            return b5
        return None

    def export_bars_to_parquet(self, output_dir: Path | None = None) -> Path:
        """Export completed bars to Parquet table partitioned by date."""
        target_dir = output_dir or DATA_DIR
        target_dir.mkdir(parents=True, exist_ok=True)

        if not self.completed_1m_bars:
            dummy_path = target_dir / "bars_empty.parquet"
            return dummy_path

        data = {
            "token": [b.token for b in self.completed_1m_bars],
            "symbol": [b.symbol for b in self.completed_1m_bars],
            "timeframe": [b.timeframe for b in self.completed_1m_bars],
            "start_time": [b.start_time.isoformat() for b in self.completed_1m_bars],
            "end_time": [b.end_time.isoformat() for b in self.completed_1m_bars],
            "open": [b.open for b in self.completed_1m_bars],
            "high": [b.high for b in self.completed_1m_bars],
            "low": [b.low for b in self.completed_1m_bars],
            "close": [b.close for b in self.completed_1m_bars],
            "volume": [b.volume for b in self.completed_1m_bars],
            "vwap": [b.vwap for b in self.completed_1m_bars],
            "tick_count": [b.tick_count for b in self.completed_1m_bars],
        }
        df = pl.DataFrame(data)
        out_path = target_dir / f"bars_1m_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.parquet"
        df.write_parquet(out_path)
        return out_path
