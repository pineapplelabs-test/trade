"""Quantitative Technical Indicators for Intraday Cash Equities."""

from collections.abc import Sequence


def calculate_vwap_deviation(price: float, vwap: float) -> float:
    """Calculate percentage deviation from Volume-Weighted Average Price (VWAP).

    Returns:
        float: (price - vwap) / vwap * 100
    """
    if vwap <= 0:
        return 0.0
    return ((price - vwap) / vwap) * 100.0


def calculate_rvol(current_volume: float, baseline_volume: float) -> float:
    """Calculate Relative Volume (RVOL) compared to historical baseline.

    RVOL > 1.5 indicates statistically abnormal institutional interest.
    """
    if baseline_volume <= 0:
        return 1.0
    return float(current_volume) / float(baseline_volume)


def calculate_true_range(high: float, low: float, prev_close: float) -> float:
    """Calculate True Range (TR)."""
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def calculate_atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> float:
    """Calculate Average True Range (ATR) over given series of bars."""
    n = len(closes)
    if n < 2:
        return highs[0] - lows[0] if n == 1 else 1.0

    tr_list = []
    for i in range(1, n):
        tr = calculate_true_range(highs[i], lows[i], closes[i - 1])
        tr_list.append(tr)

    if not tr_list:
        return 1.0

    eval_window = tr_list[-period:]
    return sum(eval_window) / float(len(eval_window))
