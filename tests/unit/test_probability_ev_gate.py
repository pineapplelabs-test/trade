from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.strategy.ev import (
    DecisionStatus,
    EVParameters,
    calculate_break_even_win_rate,
    calculate_expected_value,
)


def test_ev_calculation_requires_valid_probability() -> None:
    """EV engine: when win_probability is invalid or uncalibrated, EV cannot be positive."""
    # Break-even win rate calculation
    be = calculate_break_even_win_rate(expected_loss=1.0, total_costs=0.2, expected_reward=2.0)
    # (1.0 + 0.2) / (2.0 + 1.0) = 1.2 / 3.0 = 0.40
    assert abs(be - 0.40) < 1e-4

    # EV parameters with negative EV
    p_bad = EVParameters(
        win_probability=0.35,
        expected_reward=1.0,
        expected_loss=1.0,
        total_costs=0.20,
        min_hurdle=0.10,
    )
    res_bad = calculate_expected_value(p_bad)
    assert res_bad.status == DecisionStatus.REJECT
    assert res_bad.net_ev < 0.0


@pytest.mark.asyncio
async def test_scanner_disables_entry_when_probability_uncalibrated() -> None:
    """Scanner endpoint must report UNAVAILABLE probability & EV, and disable entry decisions."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/scanner?account=tiny")
        assert resp.status_code == 200
        data = resp.json()

        assert data["probability_status"] == "UNAVAILABLE"
        assert data["ev_status"] == "UNAVAILABLE"
        assert data["entry_decisions_enabled"] is False
        assert data["reason"] == "NO_CALIBRATED_MODEL"

        for cand in data["candidates"]:
            # Neither win_chance nor ev_pct can be fabricated
            assert cand["win_chance"] is None
            assert cand["ev_pct"] is None
            # Heuristic score is exposed honestly as heuristic
            assert "heuristic_score" in cand
            # Action must be Watch (never Enter)
            assert cand["action"] in {"Watch", "Skip", "Blocked"}
            assert cand["action"] != "Enter"
