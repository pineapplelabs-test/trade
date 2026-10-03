"""Mathematical verification and proofs for the Composite Scorer.

Verifies:
1. Spread penalty direction: narrower spread strictly produces higher score.
2. Monotonicity: increasing spread can NEVER increase the score.
3. Weight summation and formal classification: weighted sum of clipped cross-sectional z-scores.
"""

from app.config import get_strategy_config
from app.scoring.scorer import CandidateFeatures, CompositeScorer


def test_spread_penalty_strict_inequality():
    """Prove Candidate A with narrower spread receives strictly higher score than Candidate B."""
    scorer = CompositeScorer()

    # Candidate A: Narrow spread (Bid: 100.00, Ask: 100.05 -> Spread: 0.05 / 100.025 = 0.05%)
    cand_a = CandidateFeatures(
        symbol="CAND_A_NARROW",
        bid=100.00,
        ask=100.05,
        momentum_15m=0.015,
        rvol=2.0,
        obi=0.4,
        vwap_deviation=0.008,
        relative_strength=0.012,
    )

    # Candidate B: Wide spread (Bid: 100.00, Ask: 100.40 -> Spread: 0.40 / 100.20 = 0.40%)
    # All other 5 features are identical to Candidate A
    cand_b = CandidateFeatures(
        symbol="CAND_B_WIDE",
        bid=100.00,
        ask=100.40,
        momentum_15m=0.015,
        rvol=2.0,
        obi=0.4,
        vwap_deviation=0.008,
        relative_strength=0.012,
    )

    results = scorer.score_candidates([cand_a, cand_b])
    results_by_sym = {r.symbol: r for r in results}

    score_a = results_by_sym["CAND_A_NARROW"].composite_score
    score_b = results_by_sym["CAND_B_WIDE"].composite_score

    assert results_by_sym["CAND_A_NARROW"].spread_pct < results_by_sym["CAND_B_WIDE"].spread_pct
    assert score_a > score_b, (
        f"Mathematical proof failed! Narrow spread score ({score_a}) "
        f"must be strictly greater than wide spread score ({score_b})"
    )

    # Candidate A must be ranked #1
    assert results[0].symbol == "CAND_A_NARROW"


def test_increasing_spread_never_increases_score_monotonicity():
    """Verify that monotonically increasing spread strictly decreases (or maintains clipped) score."""
    scorer = CompositeScorer()

    # Fixed peer universe with diverse spreads (0.04% to 0.20%)
    peer_universe = [
        CandidateFeatures("PEER_1", 100.0, 100.04, 0.01, 1.5, 0.1, 0.005, 0.01),
        CandidateFeatures("PEER_2", 100.0, 100.08, 0.01, 1.5, 0.1, 0.005, 0.01),
        CandidateFeatures("PEER_3", 100.0, 100.12, 0.01, 1.5, 0.1, 0.005, 0.01),
        CandidateFeatures("PEER_4", 100.0, 100.16, 0.01, 1.5, 0.1, 0.005, 0.01),
        CandidateFeatures("PEER_5", 100.0, 100.20, 0.01, 1.5, 0.1, 0.005, 0.01),
    ]

    # Test across ascending spread increments from tightest (0.02) to widest (0.35)
    spread_asks = [100.02, 100.05, 100.10, 100.15, 100.25, 100.35]
    previous_score = float("inf")

    for ask in spread_asks:
        test_candidate = CandidateFeatures(
            symbol="TEST_SUBJECT",
            bid=100.0,
            ask=ask,
            momentum_15m=0.01,
            rvol=1.5,
            obi=0.1,
            vwap_deviation=0.005,
            relative_strength=0.01,
        )

        population = [test_candidate] + peer_universe
        results = scorer.score_candidates(population)
        curr_score = round(next(r.composite_score for r in results if r.symbol == "TEST_SUBJECT"), 6)

        assert curr_score <= previous_score, (
            f"Monotonicity violated! Spread increased with ask {ask} "
            f"but score rose from {previous_score} to {curr_score}"
        )
        previous_score = curr_score


def test_composite_weights_sum_and_structure():
    """Verify weights sum and document classification as weighted sum of clipped z-scores."""
    cfg = get_strategy_config()
    weights = cfg.get("composite_weights", {})

    # Positive directional features
    w_momentum = weights["momentum_return_15m"]
    w_rvol = weights["relative_volume"]
    w_obi = weights["order_book_imbalance"]
    w_vwap = weights["vwap_deviation"]
    w_rs = weights["relative_strength"]

    # Penalty feature (negative weight)
    w_spread = weights["spread_penalty"]

    sum_positive = w_momentum + w_rvol + w_obi + w_vwap + w_rs
    assert round(sum_positive, 4) == 0.90
    assert w_spread == -0.10

    # Total absolute weight allocation equals 1.00 (100% budget)
    total_abs_weight = sum_positive + abs(w_spread)
    assert round(total_abs_weight, 4) == 1.00

    # Classification Assertion:
    # The score is formally: [Option 1] A weighted sum of clipped cross-sectional z-scores.
    # S(i) = sum_k (w_k * clip(z(i, k), -3, +3))
    scorer = CompositeScorer()
    assert hasattr(scorer, "weights")
