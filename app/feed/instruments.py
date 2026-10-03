"""NSE Equity Instrument Master & Local Cache."""

from dataclasses import dataclass
from pathlib import Path

import polars as pl

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


@dataclass(frozen=True)
class InstrumentMeta:
    token: int
    symbol: str
    name: str
    sector: str
    tick_size: float
    active: bool
    surveillance_flag: str  # NORMAL, ASM, GSM


# Liquid core NSE EQ universe seed (top liquid equities for offline/testing)
DEFAULT_INSTRUMENTS: list[InstrumentMeta] = [
    InstrumentMeta(token=256265, symbol="NIFTY 50", name="Nifty 50 Index", sector="Index", tick_size=0.05, active=True, surveillance_flag="NORMAL"),
    InstrumentMeta(token=738561, symbol="RELIANCE", name="Reliance Industries Ltd", sector="Energy", tick_size=0.05, active=True, surveillance_flag="NORMAL"),
    InstrumentMeta(token=884737, symbol="TATAMOTORS", name="Tata Motors Ltd", sector="Automobile", tick_size=0.05, active=True, surveillance_flag="NORMAL"),
    InstrumentMeta(token=341249, symbol="HDFCBANK", name="HDFC Bank Ltd", sector="Financials", tick_size=0.05, active=True, surveillance_flag="NORMAL"),
    InstrumentMeta(token=779521, symbol="SBIN", name="State Bank of India", sector="Financials", tick_size=0.05, active=True, surveillance_flag="NORMAL"),
    InstrumentMeta(token=424961, symbol="ITC", name="ITC Ltd", sector="FMCG", tick_size=0.05, active=True, surveillance_flag="NORMAL"),
    InstrumentMeta(token=895745, symbol="TATASTEEL", name="Tata Steel Ltd", sector="Metals", tick_size=0.05, active=True, surveillance_flag="NORMAL"),
    InstrumentMeta(token=1270529, symbol="ICICIBANK", name="ICICI Bank Ltd", sector="Financials", tick_size=0.05, active=True, surveillance_flag="NORMAL"),
    InstrumentMeta(token=408065, symbol="INFY", name="Infosys Ltd", sector="Technology", tick_size=0.05, active=True, surveillance_flag="NORMAL"),
    InstrumentMeta(token=2714625, symbol="BHARTIARTL", name="Bharti Airtel Ltd", sector="Telecom", tick_size=0.05, active=True, surveillance_flag="NORMAL"),
    InstrumentMeta(token=3861249, symbol="BEL", name="Bharat Electronics Ltd", sector="Defense", tick_size=0.05, active=True, surveillance_flag="NORMAL"),
]


class InstrumentMaster:
    """Manages instrument master catalog, token mapping, and surveillance filters."""

    def __init__(self, instruments: list[InstrumentMeta] | None = None) -> None:
        self._instruments: dict[int, InstrumentMeta] = {}
        self._symbol_map: dict[str, int] = {}

        initial = instruments or DEFAULT_INSTRUMENTS
        for inst in initial:
            self.add_instrument(inst)

    def add_instrument(self, inst: InstrumentMeta) -> None:
        self._instruments[inst.token] = inst
        self._symbol_map[inst.symbol] = inst.token

    def get_by_token(self, token: int) -> InstrumentMeta | None:
        return self._instruments.get(token)

    def get_by_symbol(self, symbol: str) -> InstrumentMeta | None:
        token = self._symbol_map.get(symbol)
        if token is not None:
            return self._instruments.get(token)
        return None

    def list_tradable_tokens(self, allow_asm_gsm: bool = False) -> list[int]:
        """Return active tokens, excluding ASM/GSM surveillance categories if specified."""
        tokens = []
        for inst in self._instruments.values():
            if not inst.active:
                continue
            if not allow_asm_gsm and inst.surveillance_flag in ("ASM", "GSM"):
                continue
            tokens.append(inst.token)
        return tokens

    def export_parquet(self, file_path: Path | None = None) -> Path:
        """Export catalog to partitioned Parquet table."""
        path = file_path or (DATA_DIR / "instruments_catalog.parquet")
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "token": [i.token for i in self._instruments.values()],
            "symbol": [i.symbol for i in self._instruments.values()],
            "name": [i.name for i in self._instruments.values()],
            "sector": [i.sector for i in self._instruments.values()],
            "tick_size": [i.tick_size for i in self._instruments.values()],
            "active": [i.active for i in self._instruments.values()],
            "surveillance_flag": [i.surveillance_flag for i in self._instruments.values()],
        }
        df = pl.DataFrame(data)
        df.write_parquet(path)
        return path
