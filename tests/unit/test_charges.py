"""Unit tests for exact NSE intraday statutory and brokerage charges."""

from app.broker.charges import calculate_intraday_charges


def test_tiny_trade_charges_1000_inr():
    """Verify charges on a ₹1,000 trade (2 shares bought at ₹500, sold at ₹507.50)."""
    charges = calculate_intraday_charges(qty=2, buy_price=500.0, sell_price=507.50)

    # Buy: ₹1000.00, Sell: ₹1015.00, Turnover: ₹2015.00
    assert charges.buy_value == 1000.00
    assert charges.sell_value == 1015.00
    assert charges.turnover == 2015.00

    # Brokerage: 0.03% on 1000 (0.30) + 0.03% on 1015 (0.30) = 0.60
    assert charges.brokerage == 0.60

    # STT: 0.025% on sell 1015.00 = 0.25
    assert charges.stt == 0.25

    # Exchange Txn: 0.00297% on 2015.00 = 0.06
    assert charges.exchange_txn == 0.06

    # Stamp duty: 0.003% on buy 1000.00 = 0.03
    assert charges.stamp_duty == 0.03

    # Total charges strictly positive
    assert charges.total_charges > 0.0
    assert charges.total_charges == round(
        charges.brokerage + charges.stt + charges.exchange_txn + charges.sebi + charges.stamp_duty + charges.gst,
        2,
    )

    # Gross P&L is 15.00. Net P&L = Gross - Total charges
    gross_pnl = 15.00
    assert charges.net_pnl == round(gross_pnl - charges.total_charges, 2)


def test_brokerage_cap_triggers_on_large_orders():
    """Verify that brokerage is strictly capped at ₹20 per leg on high turnover."""
    # 500 shares @ ₹1000 = ₹5,00,000 buy value.
    # 0.03% would be ₹150, but must be capped at ₹20 per leg = ₹40 total.
    charges = calculate_intraday_charges(qty=500, buy_price=1000.0, sell_price=1010.0)
    assert charges.brokerage == 40.00  # ₹20 buy + ₹20 sell max cap


def test_charges_are_never_negative():
    """Verify no negative values even on break-even or loss."""
    charges = calculate_intraday_charges(qty=10, buy_price=100.0, sell_price=90.0)
    assert charges.brokerage >= 0
    assert charges.stt >= 0
    assert charges.exchange_txn >= 0
    assert charges.stamp_duty >= 0
    assert charges.gst >= 0
    assert charges.total_charges > 0
    assert charges.net_pnl < -100.0  # Loss includes ₹100 gross loss + all charges
