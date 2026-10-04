"""Execution simulation profiles: NORMAL, PESSIMISTIC, EXTREME."""

from dataclasses import dataclass
from enum import StrEnum


class ProfileMode(StrEnum):
    NORMAL = "NORMAL"
    PESSIMISTIC = "PESSIMISTIC"
    EXTREME = "EXTREME"


@dataclass(frozen=True)
class ExecutionProfile:
    mode: ProfileMode = ProfileMode.PESSIMISTIC
    latency_ms: int = 500         # 500ms simulated network/decision latency
    slippage_ticks: int = 1       # 1 tick extra slippage in pessimistic mode
    rejection_rate: float = 0.02  # 2% random rejection rate (circuit/broker reject)
    allow_partial_fills: bool = True
