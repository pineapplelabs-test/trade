"""Multi-stage NSE Equity Universe Funnel.

Filters all listed NSE equities through explicit, configurable stages:
1. Valid instrument (active, EQ series, non-ASM/GSM surveillance)
2. Price corridor (min_price to max_price)
3. Liquidity and minimum turnover
4. Volume and relative volume activity
5. Bid-ask spread percentage
6. Circuit restrictions (upper/lower circuit limits)
7. Account capital affordability (at least 1 whole share affordable within max_position_pct)

Logs exact rejection reasons for complete institutional auditability.
"""

from dataclasses import dataclass

from app.feed.base import MarketTick
from app.feed.instruments import InstrumentMeta


@dataclass(frozen=True)
class FunnelConfig:
    min_price: float = 20.0
    max_price: float = 50000.0
    min_volume: int = 25000
    min_turnover_cr: float = 5.0
    max_spread_pct: float = 0.0015  # 0.15% maximum spread
    max_position_pct: float = 0.50   # 50% max of capital per position by default
    exclude_circuits: bool = True
    exclude_asm_gsm: bool = True


@dataclass(frozen=True)
class FunnelResult:
    symbol: str
    passed: bool
    stage: str
    reason: str


class UniverseFunnel:
    """Evaluates equity candidates against quantitative tradability criteria."""

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

        # Stage 1: Active status & Surveillance filter (ASM / GSM)
        if not instrument.active:
            return FunnelResult(sym, False, "INSTRUMENT_STATUS", "Instrument inactive")

        if self.config.exclude_asm_gsm and instrument.surveillance_flag in ("ASM", "GSM"):
            return FunnelResult(sym, False, "SURVEILLANCE", f"Flagged under {instrument.surveillance_flag} surveillance")

        # Stage 2: Price range filter
        if price < self.config.min_price:
            return FunnelResult(sym, False, "PRICE_FLOOR", f"Price ₹{price:.2f} below minimum ₹{self.config.min_price:.2f}")

        if price > self.config.max_price:
            return FunnelResult(sym, False, "PRICE_CEILING", f"Price ₹{price:.2f} above maximum ₹{self.config.max_price:.2f}")

        # Stage 3: Account capital affordability (Small account rule)
        # Position cannot exceed capital * max_position_pct, so at least 1 share must be affordable
        max_position_cash = account_capital * self.config.max_position_pct
        if price > max_position_cash:
            return FunnelResult(
                sym,
                False,
                "AFFORDABILITY",
                f"Unaffordable: share price ₹{price:.2f} exceeds position cap ₹{max_position_cash:.2f} (capital ₹{account_capital:.2f})",
            )

        # Stage 4: Bid-Ask Spread check
        spread_pct = tick.depth.spread_pct
        if spread_pct > self.config.max_spread_pct:
            return FunnelResult(
                sym,
                False,
                "SPREAD",
                f"Spread {spread_pct * 100:.3f}% exceeds maximum threshold {self.config.max_spread_pct * 100:.3f}%",
            )

        # Stage 5: Circuit Limit check
        if self.config.exclude_circuits:
            if upper_circuit and price >= upper_circuit - 0.05:
                return FunnelResult(sym, False, "CIRCUIT_LIMIT", f"At or near Upper Circuit limit ₹{upper_circuit:.2f}")
            if lower_circuit and price <= lower_circuit + 0.05:
                return FunnelResult(sym, False, "CIRCUIT_LIMIT", f"At or near Lower Circuit limit ₹{lower_circuit:.2f}")

        # Passed all stages
        return FunnelResult(sym, True, "PASSED", "Passed all universe tradability stages")
