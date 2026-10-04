from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.premarket import get_premarket_report
from app.universe.premarket import (
    PreMarketScanner,
    PreMarketStockData,
    global_premarket_scanner,
)


def test_premarket_scanner_quarantine_filters() -> None:
    # 1. Clean valid stock
    valid_stock = PreMarketStockData(
        symbol="RELIANCE",
        name="Reliance Industries",
        sector="Energy",
        prev_close=2500.0,
        discovered_price=2520.0,
        turnover_cr=85.0,
        atr_14=30.0,
        is_asm_gsm=False,
        is_circuit_locked=False,
        spread_pct=0.04,
    )

    # 2. ASM/GSM quarantined stock
    asm_stock = PreMarketStockData(
        symbol="SHADY",
        name="Shady Stock",
        sector="Unknown",
        prev_close=98.0,
        discovered_price=100.0,
        turnover_cr=20.0,
        atr_14=4.0,
        is_asm_gsm=True,
        is_circuit_locked=False,
        spread_pct=0.05,
    )

    # 3. Illiquid stock (< 5 Cr turnover)
    illiquid_stock = PreMarketStockData(
        symbol="ILLIQ",
        name="Illiquid Stock",
        sector="Textiles",
        prev_close=148.0,
        discovered_price=150.0,
        turnover_cr=1.5,
        atr_14=3.0,
        is_asm_gsm=False,
        is_circuit_locked=False,
        spread_pct=0.05,
    )

    # 4. Penny stock (< 20 Rs)
    penny_stock = PreMarketStockData(
        symbol="PENNY",
        name="Penny Stock",
        sector="Finance",
        prev_close=11.5,
        discovered_price=12.0,
        turnover_cr=10.0,
        atr_14=0.5,
        is_asm_gsm=False,
        is_circuit_locked=False,
        spread_pct=0.08,
    )

    # 5. Wide spread stock (> 0.15%)
    wide_spread = PreMarketStockData(
        symbol="WIDE",
        name="Wide Spread Stock",
        sector="Consumer",
        prev_close=295.0,
        discovered_price=300.0,
        turnover_cr=15.0,
        atr_14=6.0,
        is_asm_gsm=False,
        is_circuit_locked=False,
        spread_pct=0.25,
    )

    # 6. Circuit freeze
    circuit_stock = PreMarketStockData(
        symbol="CIRCUIT",
        name="Circuit Locked",
        sector="Metals",
        prev_close=100.0,
        discovered_price=105.0,
        turnover_cr=12.0,
        atr_14=2.0,
        is_asm_gsm=False,
        is_circuit_locked=True,
        spread_pct=0.00,
    )

    stocks = [valid_stock, asm_stock, illiquid_stock, penny_stock, wide_spread, circuit_stock]
    scanner = PreMarketScanner(catalog=stocks)
    report = scanner.generate_report(account_id="shadow")

    # Only RELIANCE survives tradability & affordability
    survivor_symbols = [c.symbol for c in report.focus_candidates]
    assert "RELIANCE" in survivor_symbols
    assert "SHADY" not in survivor_symbols
    assert "ILLIQ" not in survivor_symbols
    assert "PENNY" not in survivor_symbols
    assert "WIDE" not in survivor_symbols
    assert "CIRCUIT" not in survivor_symbols

    # Verify quarantined list has the dropped stocks
    quarantined_symbols = {q.symbol: q.stage for q in report.quarantined_stocks}
    assert quarantined_symbols["SHADY"] == "SURVEILLANCE"
    assert quarantined_symbols["CIRCUIT"] == "CIRCUIT_TRAP"
    assert quarantined_symbols["ILLIQ"] == "ILLIQUID"
    assert quarantined_symbols["PENNY"] == "PENNY_STOCK"
    assert quarantined_symbols["WIDE"] == "WIDE_SPREAD"


def test_premarket_scanner_affordability_isolation() -> None:
    # Stock price 1200
    mid_price_stock = PreMarketStockData(
        symbol="INFY",
        name="Infosys Ltd",
        sector="IT",
        prev_close=1190.0,
        discovered_price=1200.0,
        turnover_cr=50.0,
        atr_14=18.0,
        is_asm_gsm=False,
        is_circuit_locked=False,
        spread_pct=0.04,
    )

    scanner = PreMarketScanner(catalog=[mid_price_stock])

    # Tiny account (max price 500) -> dropped as UNAFFORDABLE
    tiny_report = scanner.generate_report(account_id="tiny")
    assert len(tiny_report.focus_candidates) == 0
    assert any(q.symbol == "INFY" and q.stage == "UNAFFORDABLE" for q in tiny_report.quarantined_stocks)

    # Real5k account (max price 1500) -> survives
    real5k_report = scanner.generate_report(account_id="real5k")
    assert len(real5k_report.focus_candidates) == 1
    assert real5k_report.focus_candidates[0].symbol == "INFY"

    # Shadow account (max price 20000) -> survives
    shadow_report = scanner.generate_report(account_id="shadow")
    assert len(shadow_report.focus_candidates) == 1
    assert shadow_report.focus_candidates[0].symbol == "INFY"


def test_premarket_report_generation() -> None:
    report = global_premarket_scanner.generate_report(account_id="real5k")

    assert report.total_universe_scanned == len(global_premarket_scanner.catalog)
    assert report.passed_tradability > 0
    assert report.passed_affordability > 0
    assert len(report.focus_candidates) <= 5
    assert len(report.focus_candidates) > 0

    top = report.focus_candidates[0]
    assert top.symbol != ""
    assert top.gap_pct >= 0.0
    assert top.planned_entry > top.planned_stop
    assert top.planned_target > top.planned_entry
    assert top.reward_risk_ratio >= 1.5
    assert top.estimated_ev_pct > 0.0


@pytest.mark.asyncio
async def test_premarket_api_fails_closed_without_real_data() -> None:
    with pytest.raises(HTTPException) as exc:
        await get_premarket_report(account="real5k")
    assert exc.value.status_code == 503
    assert "PREMARKET_UNAVAILABLE" in str(exc.value.detail)
