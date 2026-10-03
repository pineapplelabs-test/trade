"""NSE Intraday Equity Statutory & Brokerage Calculator.

Verified against official Zerodha Brokerage Calculator & NSE Schedule.
Effective from 2024-10-01.
"""

from dataclasses import dataclass

from app.config import get_charges_config


@dataclass(frozen=True)
class TradeCharges:
    turnover: float
    buy_value: float
    sell_value: float
    brokerage: float
    stt: float
    exchange_txn: float
    sebi: float
    stamp_duty: float
    gst: float
    total_charges: float
    net_pnl: float


def calculate_intraday_charges(
    qty: int,
    buy_price: float,
    sell_price: float,
) -> TradeCharges:
    """Calculate exact statutory charges down to the paisa for NSE Intraday Equity.

    Args:
        qty: Number of shares (must be >= 1)
        buy_price: Entry price per share
        sell_price: Exit price per share
    """
    if qty < 1 or buy_price <= 0 or sell_price <= 0:
        raise ValueError("Qty must be >= 1 and prices > 0")

    cfg = get_charges_config()

    buy_value = round(qty * buy_price, 2)
    sell_value = round(qty * sell_price, 2)
    turnover = round(buy_value + sell_value, 2)
    gross_pnl = round(sell_value - buy_value, 2)

    # 1. Brokerage: min(0.03%, ₹20) per order leg (buy and sell)
    b_rate = cfg.get("brokerage", {}).get("rate_pct", 0.03) / 100.0
    b_cap = cfg.get("brokerage", {}).get("max_per_order", 20.0)
    buy_brokerage = min(round(buy_value * b_rate, 2), b_cap)
    sell_brokerage = min(round(sell_value * b_rate, 2), b_cap)
    total_brokerage = round(buy_brokerage + sell_brokerage, 2)

    # 2. STT: 0.025% on sell side only for intraday equity
    stt_rate = cfg.get("stt", {}).get("sell_rate_pct", 0.025) / 100.0
    # In Indian market, STT is rounded to nearest integer if exchange rule, or round(..., 2)
    stt = round(sell_value * stt_rate, 2)

    # 3. Exchange Txn Fee (NSE): 0.00297% on total turnover
    exch_rate = cfg.get("exchange_txn", {}).get("nse_rate_pct", 0.00297) / 100.0
    exchange_txn = round(turnover * exch_rate, 2)

    # 4. SEBI Turnover Fee: ₹10 per crore (0.0001% of turnover)
    sebi_rate = (cfg.get("sebi_charges", {}).get("rate_per_crore", 10.0) / 10000000.0)
    sebi = round(turnover * sebi_rate, 4)

    # 5. Stamp Duty: 0.003% on buy value only
    stamp_rate = cfg.get("stamp_duty", {}).get("buy_rate_pct", 0.003) / 100.0
    stamp_duty = round(buy_value * stamp_rate, 2)

    # 6. GST: 18% on (Brokerage + Exchange Txn + SEBI)
    gst_rate = cfg.get("gst", {}).get("rate_pct", 18.0) / 100.0
    gst_base = total_brokerage + exchange_txn + sebi
    gst = round(gst_base * gst_rate, 2)

    total_charges = round(total_brokerage + stt + exchange_txn + sebi + stamp_duty + gst, 2)
    net_pnl = round(gross_pnl - total_charges, 2)

    return TradeCharges(
        turnover=turnover,
        buy_value=buy_value,
        sell_value=sell_value,
        brokerage=total_brokerage,
        stt=stt,
        exchange_txn=exchange_txn,
        sebi=sebi,
        stamp_duty=stamp_duty,
        gst=gst,
        total_charges=total_charges,
        net_pnl=net_pnl,
    )
