"""Risk Gate: Deterministic veto engine enforcing hard account limits."""

from dataclasses import dataclass
from datetime import time

from app.config import get_risk_config


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    action: str  # "ALLOW", "REJECT", "HALT", "FORCE_FLAT"
    reason: str | None = None


class RiskGate:
    """Enforces non-negotiable risk limits. Immune to ML overrides."""

    def __init__(self) -> None:
        self.config = get_risk_config()

    def evaluate_entry(
        self,
        account_id: str,
        starting_capital: float,
        current_equity: float,
        day_pnl: float,
        current_time_ist: time,
        stale_tick_seconds: float = 0.0,
        kill_switch_active: bool = False,
        current_open_positions: int = 0,
        max_open_positions: int = 2,
    ) -> RiskDecision:
        """Evaluate whether a new trade entry is allowed under hard limits."""
        # 1. Kill Switch Check
        if kill_switch_active:
            return RiskDecision(
                allowed=False,
                action="REJECT",
                reason="KILL_SWITCH_ACTIVE",
            )

        # 2. Feed Freshness Check (>3s timeout)
        stale_limit = self.config.get("data_health", {}).get("stale_tick_timeout_seconds", 3.0)
        if stale_tick_seconds > stale_limit:
            return RiskDecision(
                allowed=False,
                action="REJECT",
                reason="DATA_FEED_STALE",
            )

        # 3. Market Session Hours
        # No entries 09:15 - 09:20 and after 15:00. Force flat at 15:15.
        entry_start = time(9, 20, 0)
        entry_stop = time(15, 0, 0)
        force_flat = time(15, 15, 0)

        if current_time_ist >= force_flat:
            return RiskDecision(
                allowed=False,
                action="FORCE_FLAT",
                reason="MANDATORY_EOD_SQUAREOFF",
            )

        if current_time_ist < entry_start:
            return RiskDecision(
                allowed=False,
                action="REJECT",
                reason="MARKET_OPENING_NOISE_WINDOW",
            )

        if current_time_ist > entry_stop:
            return RiskDecision(
                allowed=False,
                action="REJECT",
                reason="AFTER_HOURS_ENTRY_CUTOFF",
            )

        # 4. Daily Loss Limit (2.0% halt)
        daily_loss_pct = self.config.get("limits", {}).get("daily_loss_limit_pct", 2.0)
        max_daily_loss = -(starting_capital * (daily_loss_pct / 100.0))
        if day_pnl <= max_daily_loss:
            return RiskDecision(
                allowed=False,
                action="HALT",
                reason=f"DAILY_LOSS_LIMIT_REACHED_{daily_loss_pct}PCT",
            )

        # 5. Position Limits
        if current_open_positions >= max_open_positions:
            return RiskDecision(
                allowed=False,
                action="REJECT",
                reason="MAX_OPEN_POSITIONS_REACHED",
            )

        return RiskDecision(allowed=True, action="ALLOW")
