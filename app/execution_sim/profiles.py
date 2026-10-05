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
    latency_ms: int = 500
    slippage_ticks: int = 1
    rejection_rate: float = 0.02
    allow_partial_fills: bool = True

    def __init__(
        self,
        mode: ProfileMode = ProfileMode.PESSIMISTIC,
        latency_ms: int | None = None,
        slippage_ticks: int | None = None,
        rejection_rate: float | None = None,
        allow_partial_fills: bool = True,
    ) -> None:
        object.__setattr__(self, "mode", mode)
        if latency_ms is None:
            latency_ms = 500 if mode in {ProfileMode.PESSIMISTIC, ProfileMode.EXTREME} else 100
        object.__setattr__(self, "latency_ms", latency_ms)

        if slippage_ticks is None:
            slippage_ticks = 1 if mode in {ProfileMode.PESSIMISTIC, ProfileMode.EXTREME} else 0
        object.__setattr__(self, "slippage_ticks", slippage_ticks)

        if rejection_rate is None:
            rejection_rate = 0.02 if mode in {ProfileMode.PESSIMISTIC, ProfileMode.EXTREME} else 0.0
        object.__setattr__(self, "rejection_rate", rejection_rate)

        object.__setattr__(self, "allow_partial_fills", allow_partial_fills)
