"""Modular Strategy Interface Contract.

Decouples alpha signal generation from market data and execution simulator.
Every strategy produces structured, fully explainable signal decisions.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.feed.base import MarketTick
from app.strategy.ev import EVDecision


@dataclass(frozen=True)
class StrategySignal:
    symbol: str
    action: str              # "BUY" | "SELL" | "HOLD"
    strategy_name: str
    strategy_version: str
    features: dict[str, float]
    win_probability: float
    expected_reward: float
    expected_loss: float
    estimated_cost: float
    ev_decision: EVDecision
    explanation: str


class StrategyBase(ABC):
    """Abstract base class for all systematic intraday trading strategies."""

    def __init__(self, name: str, version: str = "1.0.0") -> None:
        self.name = name
        self.version = version

    @abstractmethod
    def calculate_features(self, tick: MarketTick, context: dict[str, Any]) -> dict[str, float]:
        """Compute indicator vector from normalized market data strictly at time t."""
        pass

    @abstractmethod
    def generate_signal(self, tick: MarketTick, context: dict[str, Any]) -> StrategySignal | None:
        """Generate structured trading signal with explicit mathematical explanation."""
        pass
