"""Unit tests for PortfolioAccount, TradeLedger, and Loss Attribution."""

from app.fees.calculator import FeeCalculator
from app.portfolio.account import PortfolioAccount
from app.portfolio.ledger import LossAttributionTag, attribute_loss


def test_portfolio_account_position_lifecycle():
    account = PortfolioAccount("tiny", starting_capital=1000.0, max_positions=2)
    assert account.equity == 1000.0
    assert account.cash == 1000.0

    # Open position: 2 shares of BEL @ ₹380 = ₹760
    opened = account.open_position("BEL", quantity=2, entry_price=380.0, stop_price=375.0, target_price=395.0)
    assert opened is True
    assert account.cash == 240.0
    assert "BEL" in account.positions
    assert account.positions["BEL"].market_value == 760.0
    assert account.equity == 1000.0

    # Price moves to ₹390 -> market value 780, unrealized pnl +20
    account.update_market_price("BEL", 390.0)
    assert account.positions["BEL"].unrealized_pnl == 20.0
    assert account.equity == 1020.0

    # Close position at 390 with net P&L of +17.50 after charges
    closed = account.close_position("BEL", exit_price=390.0, net_pnl=17.50)
    assert closed is not None
    assert "BEL" not in account.positions
    assert account.realized_pnl == 17.50
    assert account.equity == 1017.50


def test_loss_attribution_tagging():
    # Trade had gross profit +₹10, but charges were ₹15 -> Net P&L -₹5
    tag = attribute_loss(gross_pnl=10.0, net_pnl=-5.0, exit_reason="Target hit but fees dragged")
    assert tag == LossAttributionTag.COST_DRAG

    # Clean loss due to bad hypothesis
    tag_bad = attribute_loss(gross_pnl=-20.0, net_pnl=-25.0, exit_reason="Stop loss hit")
    assert tag_bad == LossAttributionTag.BAD_SIGNAL

    # Time stop
    tag_time = attribute_loss(gross_pnl=-2.0, net_pnl=-5.0, exit_reason="Time stop 45 min expired")
    assert tag_time == LossAttributionTag.TIME_STOP


def test_fee_calculator_matches_intraday_paisa():
    calc = FeeCalculator()
    charges = calc.calculate(quantity=2, buy_price=500.0, sell_price=507.50)
    assert charges.turnover == 2015.00
    assert charges.brokerage == 0.60
    assert charges.stt == 0.25
    assert charges.total_charges > 0.0
    assert charges.net_pnl == round(charges.gross_pnl - charges.total_charges, 2)
