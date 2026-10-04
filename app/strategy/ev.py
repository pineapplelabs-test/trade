"""Quantitative Expected Value (EV) Decision Gate.

Calculates Net Expected Value per trade:
    EV = (p * Reward) - ((1 - p) * Loss) - Total_Costs

Only permits simulated trade execution if:
    Net EV >= min_hurdle

Where Total_Costs includes:
- Brokerage (per executed order)
- STT (Securities Transaction Tax)
- Exchange turnover fees
- SEBI charges
- GST (18%)
- Stamp duty
- Expected execution slippage

Rejects non-viable trades immediately to prevent illusionary paper profits.
"""

from dataclasses import dataclass
from enum import StrEnum


class DecisionStatus(StrEnum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"


@dataclass(frozen=True)
class EVParameters:
    win_probability: float           # p in [0.0, 1.0]
    expected_reward: float           # gross win expectation (in ₹/share or %)
    expected_loss: float             # gross loss expectation (in ₹/share or %)
    total_costs: float               # transaction costs + slippage (in ₹/share or %)
    min_hurdle: float = 0.10         # minimum required Net EV (in ₹/share or %)


@dataclass(frozen=True)
class EVDecision:
    status: DecisionStatus
    net_ev: float
    gross_ev: float
    break_even_win_rate: float
    hurdle: float
    reason: str


def calculate_expected_value(params: EVParameters) -> EVDecision:
    """Calculate Net EV and produce an auditable decision."""
    p = max(0.0, min(1.0, params.win_probability))
    w = max(0.0, params.expected_reward)
    loss_amt = max(0.0, params.expected_loss)
    c = max(0.0, params.total_costs)
    hurdle = params.min_hurdle

    # Gross EV before costs
    gross_ev = (p * w) - ((1.0 - p) * loss_amt)

    # Net EV after costs
    net_ev = gross_ev - c

    # Break-even win rate p* = (L + C) / (W + L)
    den = w + loss_amt
    break_even_p = (loss_amt + c) / den if den > 0 else 1.0

    if net_ev < hurdle:
        if net_ev < 0:
            reason = f"Negative edge: Net EV ₹{net_ev:.4f} is negative after costs ₹{c:.4f}"
        else:
            reason = f"Insufficient edge: Net EV ₹{net_ev:.4f} below hurdle threshold ₹{hurdle:.4f}"
        return EVDecision(
            status=DecisionStatus.REJECT,
            net_ev=net_ev,
            gross_ev=gross_ev,
            break_even_win_rate=break_even_p,
            hurdle=hurdle,
            reason=reason,
        )

    return EVDecision(
        status=DecisionStatus.ACCEPT,
        net_ev=net_ev,
        gross_ev=gross_ev,
        break_even_win_rate=break_even_p,
        hurdle=hurdle,
        reason=f"Approved: Net EV ₹{net_ev:.4f} satisfies hurdle threshold ₹{hurdle:.4f}",
    )
