"""Cross-sectional composite scorer implementing AGENTS.md Section 7.1 & 7.3."""

from dataclasses import dataclass

import numpy as np

from app.config import get_strategy_config


@dataclass
class CandidateFeatures:
    symbol: str
    bid: float
    ask: float
    momentum_15m: float
    rvol: float
    obi: float
    vwap_deviation: float
    relative_strength: float

    @property
    def mid(self) -> float:
        """Midpoint price."""
        return (self.ask + self.bid) / 2.0

    @property
    def spread_pct(self) -> float:
        """Relative spread percentage: (Ask - Bid) / Mid."""
        m = self.mid
        if m <= 0.0:
            return 0.0
        return (self.ask - self.bid) / m


@dataclass
class ScoredCandidate:
    symbol: str
    composite_score: float
    spread_pct: float
    features: dict[str, float]
    z_scores: dict[str, float]


class CompositeScorer:
    """Computes cross-sectional z-score ranking for candidate equities.

    Mathematical Definition:
        For N candidates and each feature k:
            z(i, k) = clip( (x(i, k) - mean_k) / std_k, -3.0, +3.0 )
            S(i)    = SUM_k ( w_k * z(i, k) )

        Where spread_penalty weight w_spread is negative (-0.10),
        ensuring dS/d(spread) <= 0 monotonically.
    """

    def __init__(self) -> None:
        cfg = get_strategy_config()
        self.weights = cfg.get("composite_weights", {
            "momentum_return_15m": 0.25,
            "relative_volume": 0.20,
            "order_book_imbalance": 0.15,
            "vwap_deviation": 0.15,
            "relative_strength": 0.15,
            "spread_penalty": -0.10,
        })

    def score_candidates(self, candidates: list[CandidateFeatures]) -> list[ScoredCandidate]:
        """Compute composite scores across candidate population and return sorted descending."""
        if not candidates:
            return []

        n = len(candidates)
        symbols = [c.symbol for c in candidates]

        # Extract raw feature matrix (N, 6)
        raw_matrix = np.zeros((n, 6), dtype=np.float64)
        for i, c in enumerate(candidates):
            raw_matrix[i, 0] = c.momentum_15m
            raw_matrix[i, 1] = c.rvol
            raw_matrix[i, 2] = c.obi
            raw_matrix[i, 3] = c.vwap_deviation
            raw_matrix[i, 4] = c.relative_strength
            raw_matrix[i, 5] = c.spread_pct

        feature_names = [
            "momentum_return_15m",
            "relative_volume",
            "order_book_imbalance",
            "vwap_deviation",
            "relative_strength",
            "spread_penalty",
        ]

        # Cross-sectional z-score with clipping to [-3.0, +3.0]
        if n > 1:
            means = np.mean(raw_matrix, axis=0)
            stds = np.std(raw_matrix, axis=0)
            stds = np.where(stds < 1e-8, 1.0, stds)
            z_matrix = np.clip((raw_matrix - means) / stds, -3.0, 3.0)
        else:
            # Single candidate cross-section defaults to 0 z-score
            z_matrix = np.zeros_like(raw_matrix)

        # Weight vector
        weight_vec = np.array([self.weights.get(name, 0.0) for name in feature_names], dtype=np.float64)

        # Composite score = weighted sum of clipped z-scores
        scores = np.dot(z_matrix, weight_vec)

        scored = []
        for i in range(n):
            c = candidates[i]
            feat_dict = {feature_names[j]: float(raw_matrix[i, j]) for j in range(6)}
            z_dict = {feature_names[j]: float(z_matrix[i, j]) for j in range(6)}
            scored.append(
                ScoredCandidate(
                    symbol=symbols[i],
                    composite_score=float(scores[i]),
                    spread_pct=c.spread_pct,
                    features=feat_dict,
                    z_scores=z_dict,
                )
            )

        # Sort descending by composite score
        scored.sort(key=lambda x: x.composite_score, reverse=True)
        return scored
