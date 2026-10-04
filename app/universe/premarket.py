"""Pre-Market Intelligence & 2,000+ Stock Funnel Engine (08:30 – 09:10 AM IST).

Filters the broad NSE equity catalog down to an actionable Top 5 Focus Watchlist
before the 09:15 AM opening bell using pre-open auction discovered prices,
14-day ATR, liquidity constraints, and account affordability.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from app.feed.base import OrderBookDepth
from app.indicators.orderbook import calculate_obi


@dataclass(frozen=True)
class PreMarketStockData:
    symbol: str
    name: str
    sector: str
    prev_close: float
    discovered_price: float
    turnover_cr: float
    atr_14: float
    is_asm_gsm: bool = False
    is_circuit_locked: bool = False
    spread_pct: float = 0.05
    auction_volume: int = 15000
    depth: OrderBookDepth | None = None


@dataclass(frozen=True)
class FocusCandidate:
    rank: int
    symbol: str
    name: str
    sector: str
    prev_close: float
    discovered_price: float
    gap_pct: float
    turnover_cr: float
    atr_14: float
    atr_pct: float
    max_affordable_shares: int
    planned_entry: float
    planned_stop: float
    planned_target: float
    reward_risk_ratio: float
    estimated_ev_pct: float
    selection_reason: str


@dataclass(frozen=True)
class QuarantinedStock:
    symbol: str
    reason: str
    stage: str


@dataclass(frozen=True)
class PreMarketReport:
    evaluated_at: str
    account_id: str
    account_capital: float
    market_bias: str                     # "BULLISH", "BEARISH", "NEUTRAL"
    nifty_indicative_change_pct: float
    india_vix: float
    recommended_strategy: str           # "ORB Breakout", "VWAP Mean Reversion"
    total_universe_scanned: int
    passed_tradability: int
    passed_affordability: int
    focus_candidates: list[FocusCandidate]
    quarantined_stocks: list[QuarantinedStock]


# Expanded representative universe of NSE listed equities (including large, mid, small, micro, and surveillance)
NSE_CATALOG_SAMPLE: list[PreMarketStockData] = [
    # Prime liquid equities
    PreMarketStockData("BEL", "Bharat Electronics Ltd", "Defense", 378.00, 384.20, 245.0, 5.40, False, False, 0.04, 85000),
    PreMarketStockData("RELIANCE", "Reliance Industries Ltd", "Energy", 1158.00, 1172.50, 1420.0, 16.50, False, False, 0.03, 120000),
    PreMarketStockData("TMPV", "Tata Motors (TMPV)", "Automobile", 276.00, 280.80, 310.0, 4.20, False, False, 0.05, 95000),
    PreMarketStockData("BHARTIARTL", "Bharti Airtel Ltd", "Telecom", 1728.00, 1748.00, 480.0, 21.00, False, False, 0.04, 62000),
    PreMarketStockData("SBIN", "State Bank of India", "Banking", 804.00, 814.50, 680.0, 11.50, False, False, 0.03, 110000),
    PreMarketStockData("TATASTEEL", "Tata Steel Ltd", "Metals", 163.50, 166.20, 340.0, 2.80, False, False, 0.05, 140000),
    PreMarketStockData("ICICIBANK", "ICICI Bank Ltd", "Banking", 1302.00, 1314.00, 820.0, 15.60, False, False, 0.03, 75000),
    PreMarketStockData("INFY", "Infosys Ltd", "Technology", 1028.00, 1037.00, 610.0, 14.40, False, False, 0.04, 58000),
    PreMarketStockData("HDFCBANK", "HDFC Bank Ltd", "Banking", 722.00, 725.50, 1150.0, 9.20, False, False, 0.03, 180000),
    PreMarketStockData("ITC", "ITC Ltd", "FMCG", 488.00, 491.50, 410.0, 5.80, False, False, 0.04, 90000),
    # High-priced stocks (test affordability filter)
    PreMarketStockData("MRF", "MRF Ltd", "Tyres", 142000.0, 143500.0, 45.0, 1850.0, False, False, 0.08, 1200),
    PreMarketStockData("PAGEIND", "Page Industries Ltd", "Textiles", 45000.0, 45800.0, 28.0, 650.0, False, False, 0.09, 1500),
    # Surveillance & Circuit Traps (test drop filters)
    PreMarketStockData("TRAPCORP", "Trap Corporation", "Unknown", 45.00, 49.50, 1.2, 3.50, True, False, 0.80, 500),    # ASM/GSM flagged
    PreMarketStockData("CIRCUITLOCK", "Circuit Locked Ltd", "Metals", 88.00, 92.40, 2.5, 4.40, False, True, 0.00, 100),  # Upper circuit frozen
    # Illiquid penny stocks (test turnover filter)
    PreMarketStockData("PENNY1", "Penny Micro Share 1", "Finance", 8.50, 8.80, 0.25, 0.40, False, False, 2.50, 1200),
    PreMarketStockData("PENNY2", "Illiquid Textiles Ltd", "Textiles", 14.20, 14.30, 0.80, 0.60, False, False, 1.80, 800),
]


class PreMarketScanner:
    """Pre-Market screening engine narrowing broad catalog to high-probability trade setups."""

    ACCOUNT_ALLOCATION_CAPS = {
        "tiny": {"capital": 1000.0, "max_price": 500.0},
        "real5k": {"capital": 5000.0, "max_price": 1500.0},
        "shadow": {"capital": 100000.0, "max_price": 20000.0},
    }

    def __init__(self, catalog: list[PreMarketStockData] | None = None) -> None:
        self.catalog = catalog or NSE_CATALOG_SAMPLE

    def generate_report(
        self,
        account_id: str = "real5k",
        nifty_gap_pct: float = 0.45,
        india_vix: float = 13.20,
    ) -> PreMarketReport:
        """Run the 4-stage pre-market screening funnel."""
        acct_cfg = self.ACCOUNT_ALLOCATION_CAPS.get(account_id, {"capital": 5000.0, "max_price": 1500.0})
        capital = acct_cfg["capital"]
        max_price = acct_cfg["max_price"]

        quarantined: list[QuarantinedStock] = []
        tradable_survivors: list[PreMarketStockData] = []
        affordable_survivors: list[PreMarketStockData] = []

        total_scanned = len(self.catalog)

        for stock in self.catalog:
            # Stage 1: Tradability & Risk Quarantine
            if stock.is_asm_gsm:
                quarantined.append(QuarantinedStock(stock.symbol, "Under ASM/GSM regulatory surveillance", "SURVEILLANCE"))
                continue
            if stock.is_circuit_locked:
                quarantined.append(QuarantinedStock(stock.symbol, "Locked at circuit limit without two-sided liquidity", "CIRCUIT_TRAP"))
                continue
            if stock.turnover_cr < 5.0:
                quarantined.append(QuarantinedStock(stock.symbol, f"Turnover ₹{stock.turnover_cr:.1f}Cr below ₹5.0Cr threshold", "ILLIQUID"))
                continue
            if stock.discovered_price < 20.0:
                quarantined.append(QuarantinedStock(stock.symbol, f"Price ₹{stock.discovered_price:.2f} below ₹20 minimum", "PENNY_STOCK"))
                continue
            if stock.spread_pct > 0.15:
                quarantined.append(QuarantinedStock(stock.symbol, f"Spread {stock.spread_pct:.2f}% exceeds 0.15% limit", "WIDE_SPREAD"))
                continue

            tradable_survivors.append(stock)

            # Stage 2: Account Affordability
            if stock.discovered_price > max_price:
                quarantined.append(
                    QuarantinedStock(
                        stock.symbol,
                        f"Price ₹{stock.discovered_price:.2f} exceeds account allocation cap ₹{max_price:.2f}",
                        "UNAFFORDABLE",
                    )
                )
                continue

            affordable_survivors.append(stock)

        # Stage 3: Momentum & Pre-Open Auction Gap Ranking
        ranked_candidates: list[tuple[float, PreMarketStockData]] = []
        for stock in affordable_survivors:
            gap_pct = ((stock.discovered_price - stock.prev_close) / stock.prev_close) * 100.0
            atr_pct = (stock.atr_14 / stock.discovered_price) * 100.0

            # Momentum score: Clean gap (0.4% - 2.5%) with strong turnover and ATR volatility
            obi_factor = 1.0
            if stock.depth:
                obi = calculate_obi(stock.depth)
                obi_factor = max(0.5, 1.0 + obi)

            # Favor stocks with positive gap, reasonable ATR, and high liquidity
            score = (gap_pct * 1.5) + (atr_pct * 0.8) + (min(stock.turnover_cr, 500.0) / 250.0) * obi_factor
            ranked_candidates.append((score, stock))

        # Sort highest momentum score first
        ranked_candidates.sort(key=lambda x: x[0], reverse=True)

        # Stage 4: Top 5 Focus Candidates Formation
        focus_list: list[FocusCandidate] = []
        for rank_idx, (_, stock) in enumerate(ranked_candidates[:5], start=1):
            gap_pct = round(((stock.discovered_price - stock.prev_close) / stock.prev_close) * 100.0, 2)
            atr_pct = round((stock.atr_14 / stock.discovered_price) * 100.0, 2)

            # Position sizing for account
            max_alloc = capital * 0.40  # 40% position limit
            shares = max(1, int(max_alloc // stock.discovered_price))

            planned_entry = round(stock.discovered_price, 2)
            stop_dist = round(1.5 * stock.atr_14, 2)
            target_dist = round(2.5 * stock.atr_14, 2)
            planned_stop = round(planned_entry - stop_dist, 2)
            planned_target = round(planned_entry + target_dist, 2)
            rr_ratio = round(target_dist / stop_dist, 2) if stop_dist > 0 else 1.67

            # Estimated Net EV based on clean gap + RVOL expectation
            ev_pct = round(0.18 + (gap_pct * 0.05), 2)
            reason = f"+{gap_pct}% Pre-Open Gap, ₹{stock.atr_14:.2f} ATR (1.5x stop buffer), ₹{stock.turnover_cr:.0f}Cr turnover"

            focus_list.append(
                FocusCandidate(
                    rank=rank_idx,
                    symbol=stock.symbol,
                    name=stock.name,
                    sector=stock.sector,
                    prev_close=stock.prev_close,
                    discovered_price=stock.discovered_price,
                    gap_pct=gap_pct,
                    turnover_cr=stock.turnover_cr,
                    atr_14=stock.atr_14,
                    atr_pct=atr_pct,
                    max_affordable_shares=shares,
                    planned_entry=planned_entry,
                    planned_stop=planned_stop,
                    planned_target=planned_target,
                    reward_risk_ratio=rr_ratio,
                    estimated_ev_pct=ev_pct,
                    selection_reason=reason,
                )
            )

        # Determine Market Bias & Strategy
        market_bias = "BULLISH" if nifty_gap_pct > 0.20 else ("BEARISH" if nifty_gap_pct < -0.20 else "NEUTRAL")
        rec_strat = "ORB Breakout" if india_vix < 18.0 and abs(nifty_gap_pct) > 0.20 else "VWAP Mean Reversion"

        return PreMarketReport(
            evaluated_at=datetime.now(UTC).isoformat(),
            account_id=account_id,
            account_capital=capital,
            market_bias=market_bias,
            nifty_indicative_change_pct=nifty_gap_pct,
            india_vix=india_vix,
            recommended_strategy=rec_strat,
            total_universe_scanned=total_scanned,
            passed_tradability=len(tradable_survivors),
            passed_affordability=len(affordable_survivors),
            focus_candidates=focus_list,
            quarantined_stocks=quarantined[:10],
        )


# Global singleton scanner
global_premarket_scanner = PreMarketScanner()
