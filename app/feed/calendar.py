"""NSE Trading Calendar and Session Verification."""

import zoneinfo
from datetime import date, datetime, time

KOLKATA_TZ = zoneinfo.ZoneInfo("Asia/Kolkata")

# Official NSE Trading Holidays (EQ Cash Market)
# Source: National Stock Exchange of India (NSE Circulars)
NSE_HOLIDAYS_2024_2026: set[date] = {
    # 2024
    date(2024, 1, 22),  # Special Holiday
    date(2024, 1, 26),  # Republic Day
    date(2024, 3, 8),   # Mahashivratri
    date(2024, 3, 25),  # Holi
    date(2024, 3, 29),  # Good Friday
    date(2024, 4, 11),  # Id-Ul-Fitr
    date(2024, 4, 17),  # Ram Navami
    date(2024, 5, 1),   # Maharashtra Day
    date(2024, 5, 20),  # General Elections
    date(2024, 6, 17),  # Bakri Id
    date(2024, 7, 17),  # Moharram
    date(2024, 8, 15),  # Independence Day
    date(2024, 10, 2),  # Mahatma Gandhi Jayanti
    date(2024, 11, 1),  # Diwali Laxmi Pujan (Muhurat trading evening only)
    date(2024, 11, 15), # Gurunanak Jayanti
    date(2024, 11, 20), # Maharashtra Assembly Elections
    date(2024, 12, 25), # Christmas
    # 2025
    date(2025, 2, 26),  # Mahashivratri
    date(2025, 3, 14),  # Holi
    date(2025, 3, 31),  # Id-Ul-Fitr
    date(2025, 4, 10),  # Mahavir Jayanti
    date(2025, 4, 14),  # Dr. Baba Saheb Ambedkar Jayanti
    date(2025, 4, 18),  # Good Friday
    date(2025, 5, 1),   # Maharashtra Day
    date(2025, 8, 15),  # Independence Day
    date(2025, 8, 27),  # Ganesh Chaturthi
    date(2025, 10, 2),  # Mahatma Gandhi Jayanti / Dussehra
    date(2025, 10, 21), # Diwali (Laxmi Pujan)
    date(2025, 10, 22), # Diwali Balipratipada
    date(2025, 11, 5),  # Prakash Gurpurb
    date(2025, 12, 25), # Christmas
    # 2026
    date(2026, 1, 26),  # Republic Day
    date(2026, 3, 17),  # Mahashivratri
    date(2026, 3, 20),  # Id-Ul-Fitr
    date(2026, 3, 27),  # Ram Navami
    date(2026, 4, 3),   # Good Friday
    date(2026, 4, 14),  # Ambedkar Jayanti
    date(2026, 5, 1),   # Maharashtra Day
    date(2026, 8, 15),  # Independence Day
    date(2026, 10, 2),  # Gandhi Jayanti
    date(2026, 10, 20), # Dussehra
    date(2026, 11, 9),  # Diwali
    date(2026, 12, 25), # Christmas
}


def is_trading_day(d: date) -> bool:
    """Return True if given date is an official NSE trading day (Mon-Fri, not holiday)."""
    if d.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    return d not in NSE_HOLIDAYS_2024_2026


def get_market_session_phase(dt: datetime) -> str:
    """Return session phase: PRE_OPEN, REGULAR, POST_CLOSE, or CLOSED."""
    ist_dt = dt.astimezone(KOLKATA_TZ)
    if not is_trading_day(ist_dt.date()):
        return "CLOSED"

    t = ist_dt.time()
    if time(9, 0) <= t < time(9, 8):
        return "PRE_OPEN_ORDER_COLLECTION"
    elif time(9, 8) <= t < time(9, 15):
        return "PRE_OPEN_MATCHING"
    elif time(9, 15) <= t <= time(15, 30):
        return "REGULAR"
    elif time(15, 30) < t <= time(16, 0):
        return "POST_CLOSE"
    else:
        return "CLOSED"
