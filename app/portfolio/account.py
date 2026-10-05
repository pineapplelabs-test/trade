"""Isolated Paper Trading Account State Model."""

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class PaperPosition:
    symbol: str
    quantity: int
    entry_price: float
    current_price: float
    stop_price: float
    target_price: float
    opened_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def market_value(self) -> float:
        return round(self.quantity * self.current_price, 2)

    @property
    def unrealized_pnl(self) -> float:
        return round(self.quantity * (self.current_price - self.entry_price), 2)

    @property
    def unrealized_pnl_pct(self) -> float:
        if self.entry_price <= 0:
            return 0.0
        return round(((self.current_price - self.entry_price) / self.entry_price) * 100.0, 2)


class PortfolioAccount:
    """Independent paper trading portfolio with cash, equity, and positions."""

    def __init__(self, account_id: str, starting_capital: float, max_positions: int = 5) -> None:
        self.account_id = account_id
        self.starting_capital = starting_capital
        self.cash = starting_capital
        self.max_positions = max_positions
        self.positions: dict[str, PaperPosition] = {}
        self.realized_pnl = 0.0
        self.peak_equity = starting_capital

    @property
    def equity(self) -> float:
        pos_val = sum(p.market_value for p in self.positions.values())
        return round(self.cash + pos_val, 2)

    @property
    def total_unrealized_pnl(self) -> float:
        return round(sum(p.unrealized_pnl for p in self.positions.values()), 2)

    @property
    def drawdown_pct(self) -> float:
        eq = self.equity
        if eq > self.peak_equity:
            self.peak_equity = eq
        if self.peak_equity <= 0:
            return 0.0
        return round(((self.peak_equity - eq) / self.peak_equity) * 100.0, 2)

    def can_open_position(self) -> bool:
        return len(self.positions) < self.max_positions

    def open_position(
        self,
        symbol: str,
        quantity: int,
        entry_price: float,
        stop_price: float,
        target_price: float,
    ) -> bool:
        if symbol in self.positions or not self.can_open_position():
            return False
        cost = quantity * entry_price
        if self.cash < cost:
            return False

        self.cash = round(self.cash - cost, 2)
        self.positions[symbol] = PaperPosition(
            symbol=symbol,
            quantity=quantity,
            entry_price=entry_price,
            current_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
        )
        return True

    def close_position(self, symbol: str, exit_price: float, net_pnl: float) -> PaperPosition | None:
        pos = self.positions.pop(symbol, None)
        if not pos:
            return None
        cost_basis = pos.quantity * pos.entry_price
        self.cash = round(self.cash + cost_basis + net_pnl, 2)
        self.realized_pnl = round(self.realized_pnl + net_pnl, 2)
        return pos

    def restore_position(
        self,
        symbol: str,
        quantity: int,
        entry_price: float,
        current_price: float | None = None,
        stop_price: float = 0.0,
        target_price: float = 0.0,
        opened_at: datetime | None = None,
    ) -> bool:
        """Restore an existing open position after restart without double-deducting beyond capital."""
        if symbol in self.positions:
            return False
        cost = quantity * entry_price
        self.cash = round(self.cash - cost, 2)
        self.positions[symbol] = PaperPosition(
            symbol=symbol,
            quantity=quantity,
            entry_price=entry_price,
            current_price=current_price or entry_price,
            stop_price=stop_price,
            target_price=target_price,
            opened_at=opened_at or datetime.now(UTC),
        )
        return True

    def update_market_price(self, symbol: str, current_price: float) -> None:
        if symbol in self.positions:
            self.positions[symbol].current_price = current_price
            eq = self.equity
            if eq > self.peak_equity:
                self.peak_equity = eq


def init_portfolio_accounts() -> dict[str, PortfolioAccount]:
    """Initialize portfolio accounts using single source of truth accounts.yaml."""
    from app.config import get_accounts_config

    accts_cfg = get_accounts_config()
    res: dict[str, PortfolioAccount] = {}
    for acct_id, spec in accts_cfg.items():
        res[acct_id] = PortfolioAccount(
            account_id=acct_id,
            starting_capital=float(spec.get("starting_capital", 1000.0)),
            max_positions=int(spec.get("max_open_positions", 2)),
        )
    if not res:
        res = {
            "tiny": PortfolioAccount("tiny", starting_capital=1000.0, max_positions=2),
            "shadow": PortfolioAccount("shadow", starting_capital=100000.0, max_positions=5),
            "real5k": PortfolioAccount("real5k", starting_capital=5000.0, max_positions=2),
        }
    return res


# Global in-memory portfolio registry for runtime paper accounts
portfolio_accounts: dict[str, PortfolioAccount] = init_portfolio_accounts()
