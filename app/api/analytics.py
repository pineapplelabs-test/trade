"""Edge Health, Strategy Health, and Quantitative Sample Quality Analytics."""

import math
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.portfolio.ledger import global_trade_ledger

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

VALID_ACCOUNTS = {"tiny", "shadow", "real5k"}

ACCOUNT_CONFIGS = {
    "tiny": {"starting_capital": 1000.0, "min_sample_threshold": 30},
    "shadow": {"starting_capital": 100000.0, "min_sample_threshold": 30},
    "real5k": {"starting_capital": 5000.0, "min_sample_threshold": 30},
}


def compute_edge_health(account_id: str, environment: str = "PAPER_LIVE") -> dict[str, Any]:
    """Calculate statistical edge health, fee drag, and sample quality for an isolated account and environment."""
    cfg = ACCOUNT_CONFIGS.get(account_id, {"starting_capital": 1000.0, "min_sample_threshold": 30})
    starting_capital = cfg["starting_capital"]
    min_sample = cfg["min_sample_threshold"]

    all_trades = global_trade_ledger.list_trades_for_account(account_id, limit=1000)
    if environment == "ALL":
        trades = all_trades
    else:
        trades = [t for t in all_trades if t.environment == environment]

    total_closed_trades = len(trades)

    if total_closed_trades == 0:
        return {
            "account_id": account_id,
            "environment": environment,
            "starting_capital": starting_capital,
            "current_equity": starting_capital,
            "realized_net_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "gross_trading_pnl": 0.0,
            "total_transaction_charges": 0.0,
            "execution_slippage_attribution": 0.0,
            "cost_drag_pct": 0.0,
            "total_closed_trades": 0,
            "win_count": 0,
            "loss_count": 0,
            "win_rate_pct": 0.0,
            "avg_winning_trade": 0.0,
            "avg_losing_trade": 0.0,
            "net_expectancy": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
            "average_holding_seconds": 0.0,
            "sample_size": 0,
            "sample_threshold": min_sample,
            "has_sufficient_sample": False,
            "strategy_health_status": "INSUFFICIENT SAMPLE",
            "status_explanation": f"Sample size (0) is below required minimum threshold ({min_sample}) for statistical validity.",
            "accounting_decomposition": {
                "gross_pnl": 0.0,
                "transaction_charges": 0.0,
                "net_pnl": 0.0,
                "execution_price_impact": 0.0,
                "slippage_already_in_fill": True,
            },
        }

    # Aggregate figures
    gross_pnl = sum(t.gross_pnl for t in trades)
    total_charges = sum(t.total_charges for t in trades)
    net_pnl = sum(t.net_pnl for t in trades)
    total_slippage = sum(t.slippage for t in trades)

    winning_trades = [t for t in trades if t.net_pnl > 0]
    losing_trades = [t for t in trades if t.net_pnl < 0]

    win_count = len(winning_trades)
    loss_count = len(losing_trades)
    win_rate = (win_count / total_closed_trades) * 100.0

    gross_wins = sum(t.gross_pnl for t in trades if t.gross_pnl > 0)
    gross_losses = abs(sum(t.gross_pnl for t in trades if t.gross_pnl < 0))

    avg_win = (sum(t.net_pnl for t in winning_trades) / win_count) if win_count > 0 else 0.0
    avg_loss = (abs(sum(t.net_pnl for t in losing_trades)) / loss_count) if loss_count > 0 else 0.0

    net_expectancy = net_pnl / total_closed_trades

    if gross_losses == 0:
        profit_factor = round(gross_wins, 2) if gross_wins > 0 else 0.0
    else:
        profit_factor = round(gross_wins / gross_losses, 2)

    cost_drag_pct = round((total_charges / gross_wins * 100.0), 2) if gross_wins > 0 else 0.0

    durations = [
        (t.exit_timestamp - t.entry_timestamp).total_seconds()
        for t in trades
        if hasattr(t.exit_timestamp, "total_seconds") or hasattr(t.exit_timestamp, "timestamp")
    ]
    avg_holding = sum(durations) / len(durations) if durations else 0.0

    peak = starting_capital
    running_equity = starting_capital
    max_dd_pct = 0.0
    for t in trades:
        running_equity += t.net_pnl
        if running_equity > peak:
            peak = running_equity
        if peak > 0:
            dd = ((peak - running_equity) / peak) * 100.0
            if dd > max_dd_pct:
                max_dd_pct = dd

    current_equity = round(starting_capital + net_pnl, 2)

    has_sufficient = total_closed_trades >= min_sample
    if not has_sufficient:
        status = "INSUFFICIENT SAMPLE"
        explanation = f"Sample size ({total_closed_trades}) is below minimum threshold ({min_sample}). Statistical test cannot reject randomness."
    elif net_expectancy <= 0:
        status = "NEGATIVE NET EDGE"
        explanation = f"Net expectancy ({round(net_expectancy, 2)}) is negative after factoring transaction costs and slippage."
    else:
        std_dev = math.sqrt(
            sum((t.net_pnl - net_expectancy) ** 2 for t in trades) / (total_closed_trades - 1)
        ) if total_closed_trades > 1 else 0.0

        std_err = (std_dev / math.sqrt(total_closed_trades)) if total_closed_trades > 0 and std_dev > 0 else 1.0
        t_stat = (net_expectancy / std_err) if std_err > 0 else 0.0

        if t_stat >= 2.0:
            status = "POSITIVE HISTORICAL EDGE"
            explanation = f"Statistically positive edge confirmed across {total_closed_trades} trades (t-stat {round(t_stat, 2)} >= 2.0, p < 0.05)."
        else:
            status = "EDGE UNDER OBSERVATION"
            explanation = f"Net expectancy is positive ({round(net_expectancy, 2)}), but variance remains high (t-stat {round(t_stat, 2)} < 2.0). Maintain observation."

    return {
        "account_id": account_id,
        "environment": environment,
        "starting_capital": round(starting_capital, 2),
        "current_equity": current_equity,
        "realized_net_pnl": round(net_pnl, 2),
        "unrealized_pnl": 0.0,
        "gross_trading_pnl": round(gross_pnl, 2),
        "total_transaction_charges": round(total_charges, 2),
        "execution_slippage_attribution": round(total_slippage, 2),
        "cost_drag_pct": cost_drag_pct,
        "total_closed_trades": total_closed_trades,
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate_pct": round(win_rate, 2),
        "avg_winning_trade": round(avg_win, 2),
        "avg_losing_trade": round(avg_loss, 2),
        "net_expectancy": round(net_expectancy, 2),
        "profit_factor": profit_factor,
        "max_drawdown_pct": round(max_dd_pct, 2),
        "average_holding_seconds": round(avg_holding, 1),
        "sample_size": total_closed_trades,
        "sample_threshold": min_sample,
        "has_sufficient_sample": has_sufficient,
        "strategy_health_status": status,
        "status_explanation": explanation,
        "accounting_decomposition": {
            "gross_pnl": round(gross_pnl, 2),
            "transaction_charges": round(total_charges, 2),
            "net_pnl": round(net_pnl, 2),
            "execution_price_impact": round(total_slippage, 2),
            "slippage_already_in_fill": True,
        },
    }


@router.get("/edge-health")
async def get_edge_health(
    account: str = Query("tiny"),
    environment: str = Query("PAPER_LIVE"),
) -> dict[str, Any]:
    """Retrieve isolated edge health analytics for specified paper trading account."""
    if account not in VALID_ACCOUNTS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid account '{account}'. Must be one of: {sorted(VALID_ACCOUNTS)}",
        )
    return compute_edge_health(account, environment=environment)


@router.get("/calibration")
async def get_probability_calibration(
    account: str = Query("tiny"),
    environment: str = Query("PAPER_LIVE"),
) -> dict[str, Any]:
    """Calculate empirical win rate vs predicted probability calibration buckets."""
    if account not in VALID_ACCOUNTS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid account '{account}'. Must be one of: {sorted(VALID_ACCOUNTS)}",
        )

    all_trades = global_trade_ledger.list_trades_for_account(account, limit=1000)
    trades = [t for t in all_trades if (environment == "ALL" or t.environment == environment)]

    buckets_def = [
        ("50-55%", 0.50, 0.55),
        ("55-60%", 0.55, 0.60),
        ("60-65%", 0.60, 0.65),
        ("65-70%", 0.65, 0.70),
        ("70-75%", 0.70, 0.75),
        ("75-80%", 0.75, 0.80),
        ("80%+", 0.80, 1.01),
    ]

    calibration_buckets: list[dict[str, Any]] = []
    for label, low, high in buckets_def:
        b_trades = [t for t in trades if low <= t.predicted_probability < high]
        count = len(b_trades)
        wins = sum(1 for t in b_trades if t.net_pnl > 0)
        win_rate = (wins / count * 100.0) if count > 0 else 0.0
        avg_net = (sum(t.net_pnl for t in b_trades) / count) if count > 0 else 0.0
        expected_p = round((low + min(high, 1.0)) / 2.0, 3)

        calibration_buckets.append({
            "bucket": label,
            "trade_count": count,
            "win_count": wins,
            "actual_win_rate_pct": round(win_rate, 2),
            "avg_net_pnl": round(avg_net, 2),
            "expected_probability": expected_p,
            "actual_probability": round(win_rate / 100.0, 3),
        })

    return {
        "account_id": account,
        "environment": environment,
        "total_trades": len(trades),
        "buckets": calibration_buckets,
    }


@router.get("/performance-breakdowns")
async def get_performance_breakdowns(
    account: str = Query("tiny"),
    environment: str = Query("PAPER_LIVE"),
) -> dict[str, Any]:
    """Retrieve multi-dimensional performance breakdowns."""
    if account not in VALID_ACCOUNTS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid account '{account}'. Must be one of: {sorted(VALID_ACCOUNTS)}",
        )

    all_trades = global_trade_ledger.list_trades_for_account(account, limit=1000)
    trades = [t for t in all_trades if (environment == "ALL" or t.environment == environment)]

    # 1. By strategy
    by_strategy: dict[str, dict[str, Any]] = {}
    for t in trades:
        st = t.strategy_name
        if st not in by_strategy:
            by_strategy[st] = {"trades": 0, "wins": 0, "gross_pnl": 0.0, "net_pnl": 0.0}
        by_strategy[st]["trades"] += 1
        if t.net_pnl > 0:
            by_strategy[st]["wins"] += 1
        by_strategy[st]["gross_pnl"] = round(by_strategy[st]["gross_pnl"] + t.gross_pnl, 2)
        by_strategy[st]["net_pnl"] = round(by_strategy[st]["net_pnl"] + t.net_pnl, 2)

    # 2. By symbol
    by_symbol: dict[str, dict[str, Any]] = {}
    for t in trades:
        sym = t.symbol
        if sym not in by_symbol:
            by_symbol[sym] = {"trades": 0, "net_pnl": 0.0}
        by_symbol[sym]["trades"] += 1
        by_symbol[sym]["net_pnl"] = round(by_symbol[sym]["net_pnl"] + t.net_pnl, 2)

    # 3. By time of day (hour IST)
    by_tod: dict[str, dict[str, Any]] = {}
    for t in trades:
        hour = t.entry_timestamp.hour
        hour_label = f"{hour:02d}:00"
        if hour_label not in by_tod:
            by_tod[hour_label] = {"trades": 0, "net_pnl": 0.0}
        by_tod[hour_label]["trades"] += 1
        by_tod[hour_label]["net_pnl"] = round(by_tod[hour_label]["net_pnl"] + t.net_pnl, 2)

    # 4. By OBI bucket
    by_obi = {"negative": {"trades": 0, "net_pnl": 0.0}, "neutral": {"trades": 0, "net_pnl": 0.0}, "positive": {"trades": 0, "net_pnl": 0.0}}
    for t in trades:
        obi = (t.decision_snapshot.obi if t.decision_snapshot and t.decision_snapshot.obi is not None else 0.0)
        bucket = "negative" if obi < -0.1 else ("positive" if obi > 0.1 else "neutral")
        by_obi[bucket]["trades"] += 1
        by_obi[bucket]["net_pnl"] = round(by_obi[bucket]["net_pnl"] + t.net_pnl, 2)

    # 5. By RVOL bucket
    by_rvol = {"low_under_1.5": {"trades": 0, "net_pnl": 0.0}, "mid_1.5_2.5": {"trades": 0, "net_pnl": 0.0}, "high_over_2.5": {"trades": 0, "net_pnl": 0.0}}
    for t in trades:
        rvol = (t.decision_snapshot.rvol if t.decision_snapshot and t.decision_snapshot.rvol is not None else 1.0)
        bucket = "low_under_1.5" if rvol < 1.5 else ("mid_1.5_2.5" if rvol <= 2.5 else "high_over_2.5")
        by_rvol[bucket]["trades"] += 1
        by_rvol[bucket]["net_pnl"] = round(by_rvol[bucket]["net_pnl"] + t.net_pnl, 2)

    return {
        "account_id": account,
        "environment": environment,
        "by_strategy": by_strategy,
        "by_symbol": by_symbol,
        "by_time_of_day": by_tod,
        "by_obi_bucket": by_obi,
        "by_rvol_bucket": by_rvol,
    }
