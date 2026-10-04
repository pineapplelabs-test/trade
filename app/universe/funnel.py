"""Multi-stage NSE equity universe funnel."""
from dataclasses import dataclass

from app.feed.base import MarketTick
from app.feed.instruments import InstrumentMeta


@dataclass(frozen=True)
class FunnelConfig:
    min_price: float = 20.0
    max_price: float = 50000.0
    min_volume: int = 25000
    min_turnover_cr: float = 5.0
    max_spread_pct: float = 0.0015
    max_position_pct: float = 0.50
    exclude_circuits: bool = True
    exclude_asm_gsm: bool = True


@dataclass(frozen=True)
class FunnelResult:
    symbol: str
    passed: bool
    stage: str
    reason: str


class UniverseFunnel:
    """Evaluate equity candidates against explicit tradability criteria."""

    def __init__(self, config: FunnelConfig | None = None) -> None:
        self.config = config or FunnelConfig()

    def evaluate(
        self,
        instrument: InstrumentMeta,
        tick: MarketTick,
        account_capital: float,
        upper_circuit: float | None = None,
        lower_circuit: float | None = None,
    ) -> FunnelResult:
        sym = instrument.symbol
        price = tick.last_price

        if not instrument.active:
            return FunnelResult(sym, False, "INSTRUMENT_STATUS", "Instrument inactive")
        if self.config.exclude_asm_gsm and instrument.surveillance_flag in ("ASM", "GSM"):
            return FunnelResult(sym, False, "SURVEILLANCE", f"Flagged under {instrument.surveillance_flag} surveillance")

        if price < self.config.min_price:
            return FunnelResult(sym, False, "PRICE_FLOOR", f"Price ₹{price:.2f} below minimum ₹{self.config.min_price:.2f}")
        if price > self.config.max_price:
            return FunnelResult(sym, False, "PRICE_CEILING", f"Price ₹{price:.2f} above maximum ₹{self.config.max_price:.2f}")

        # Enforce the configured liquidity gates using only information available in the tick.
        if tick.volume < self.config.min_volume:
            return FunnelResult(
                sym, False, "MIN_VOLUME",
                f"Volume {tick.volume:,} below minimum {self.config.min_volume:,}",
            )
        turnover_cr = (tick.last_price * tick.volume) / 10_000_000.0
        if turnover_cr < self.config.min_turnover_cr:
            return FunnelResult(
                sym, False, "MIN_TURNOVER",
                f"Estimated turnover ₹{turnover_cr:.2f}Cr below minimum ₹{self.config.min_turnover_cr:.2f}Cr",
            )

        max_position_cash = account_capital * self.config.max_position_pct
        whole_shares = int(max_position_cash // price) if price > 0 else 0
        if whole_shares < 1:
            return FunnelResult(
                sym, False, "AFFORDABILITY",
                "No whole share is affordable within the configured position cap",
            )

        spread_pct = tick.depth.spread_pct
        if spread_pct > self.config.max_spread_pct:
            return FunnelResult(
                sym, False, "SPREAD",
                f"Spread {spread_pct * 100:.3f}% exceeds maximum {self.config.max_spread_pct * 100:.3f}%",
            )

        if self.config.exclude_circuits:
            if upper_circuit and price >= upper_circuit - 0.05:
                return FunnelResult(sym, False, "CIRCUIT_LIMIT", f"At or near Upper Circuit limit ₹{upper_circuit:.2f}")
            if lower_circuit and price <= lower_circuit + 0.05:
                return FunnelResult(sym, False, "CIRCUIT_LIMIT", f"At or near Lower Circuit limit ₹{lower_circuit:.2f}")

        return FunnelResult(sym, True, "PASSED", "Passed all universe tradability stages")
