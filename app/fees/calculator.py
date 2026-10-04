"""Decimal-safe Indian Intraday Equity Fee Calculator."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.fees.schedule import DEFAULT_FEE_SCHEDULE, FeeSchedule


def to_dec(val: float | str | int) -> Decimal:
    return Decimal(str(val))


def quantize_paisa(val: Decimal) -> Decimal:
    """Quantize to 2 decimal places (1 paisa)."""
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class TradeCharges:
    schedule_id: str
    buy_value: float
    sell_value: float
    turnover: float
    brokerage: float
    stt: float
    exchange_txn: float
    sebi: float
    gst: float
    stamp_duty: float
    total_charges: float
    gross_pnl: float
    net_pnl: float


class FeeCalculator:
    """Calculates all statutory, exchange, and brokerage charges for equity trades."""

    def __init__(self, schedule: FeeSchedule = DEFAULT_FEE_SCHEDULE) -> None:
        self.schedule = schedule

    def calculate(self, quantity: int, buy_price: float, sell_price: float) -> TradeCharges:
        q = to_dec(quantity)
        bp = to_dec(buy_price)
        sp = to_dec(sell_price)

        buy_val = quantize_paisa(q * bp)
        sell_val = quantize_paisa(q * sp)
        turnover = buy_val + sell_val

        # Brokerage: min(rate * value, max_cap) per leg
        brok_rate = to_dec(self.schedule.brokerage_rate_pct)
        brok_cap = to_dec(self.schedule.brokerage_max_cap_per_leg)

        buy_brok = quantize_paisa(min(buy_val * brok_rate, brok_cap))
        sell_brok = quantize_paisa(min(sell_val * brok_rate, brok_cap))
        brokerage = buy_brok + sell_brok

        # STT: 0.025% on sell value
        stt_rate = to_dec(self.schedule.stt_rate_pct)
        stt = quantize_paisa(sell_val * stt_rate)

        # Exchange Transaction: ~0.00297% on turnover
        exch_rate = to_dec(self.schedule.exchange_txn_rate_pct)
        exch_txn = quantize_paisa(turnover * exch_rate)

        # SEBI: ₹10 per crore (0.000001)
        sebi = quantize_paisa(turnover * (to_dec(self.schedule.sebi_rate_per_crore) / Decimal("10000000")))

        # GST: 18% on (brokerage + exchange_txn + sebi)
        gst_base = brokerage + exch_txn + sebi
        gst_rate = to_dec(self.schedule.gst_rate_pct)
        gst = quantize_paisa(gst_base * gst_rate)

        # Stamp duty: 0.003% on buy value
        stamp_rate = to_dec(self.schedule.stamp_duty_rate_pct)
        stamp_duty = quantize_paisa(buy_val * stamp_rate)

        total_charges = quantize_paisa(brokerage + stt + exch_txn + sebi + gst + stamp_duty)

        gross_pnl = quantize_paisa(sell_val - buy_val)
        net_pnl = quantize_paisa(gross_pnl - total_charges)

        return TradeCharges(
            schedule_id=self.schedule.schedule_id,
            buy_value=float(buy_val),
            sell_value=float(sell_val),
            turnover=float(turnover),
            brokerage=float(brokerage),
            stt=float(stt),
            exchange_txn=float(exch_txn),
            sebi=float(sebi),
            gst=float(gst),
            stamp_duty=float(stamp_duty),
            total_charges=float(total_charges),
            gross_pnl=float(gross_pnl),
            net_pnl=float(net_pnl),
        )
