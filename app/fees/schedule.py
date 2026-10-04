"""Versioned Indian Intraday Equity Fee Schedule Specification.

Allows historical replays and backtests to use the exact fee schedule
effective on any past trading date.
"""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class FeeSchedule:
    broker_name: str
    schedule_id: str
    effective_from: date
    effective_to: date | None = None

    # Intraday Cash Equity Rates (NSE)
    brokerage_rate_pct: float = 0.0003       # 0.03%
    brokerage_max_cap_per_leg: float = 20.0  # Max ₹20 per executed leg
    stt_rate_pct: float = 0.00025            # 0.025% on sell turnover
    exchange_txn_rate_pct: float = 0.0000297 # ~0.00297% on NSE turnover
    sebi_rate_per_crore: float = 10.0        # ₹10 per crore
    gst_rate_pct: float = 0.18               # 18% on (brokerage + exchange + sebi)
    stamp_duty_rate_pct: float = 0.00003     # 0.003% on buy turnover


# Official Zerodha / NSE default schedule (effective from 2024-10-01)
DEFAULT_FEE_SCHEDULE = FeeSchedule(
    broker_name="Zerodha / NSE Cash Equity",
    schedule_id="NSE_EQ_INTRADAY_V2024",
    effective_from=date(2024, 10, 1),
    effective_to=None,
    brokerage_rate_pct=0.0003,
    brokerage_max_cap_per_leg=20.0,
    stt_rate_pct=0.00025,
    exchange_txn_rate_pct=0.0000297,
    sebi_rate_per_crore=10.0,
    gst_rate_pct=0.18,
    stamp_duty_rate_pct=0.00003,
)
