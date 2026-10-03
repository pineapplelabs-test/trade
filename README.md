# Paper Desk

**Paper Desk** is an institutional-grade paper trading platform for NSE cash equities (EQ series). It is designed for realistic execution simulation with exact Indian statutory taxes (STT, exchange turnover fees, GST, SEBI fee, stamp duty), 5-level orderbook depth consumption, and machine learning trade qualification.

> ⚠️ **PAPER TRADING ONLY**: This codebase contains **NO** ability to submit real orders to any broker or exchange. Real order APIs are strictly barred by automated CI safety checks.

---

## Target Paper Accounts

| Account | Capital | Sizing Rule | Focus |
|---|---|---|---|
| `real5k` | ₹5,000 | Max 50% (₹2,500/stock), 2 concurrent | Real user capital validation on liquid mid/large caps |
| `tiny` | ₹1,000 | Max 50% (₹500/stock), 2 concurrent | Severe statutory tax & share rounding stress-test |
| `shadow` | ₹1,00,000 | Max 20% (₹20,000/stock), 5 concurrent | Statistical control benchmark |

---

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2.0, AsyncSQLite / PostgreSQL 16, Structlog
- **Data & Math**: NumPy, Polars, PyArrow Parquet
- **Frontend**: Plain HTML5 + CSS3 + Vanilla JavaScript (native ES Modules, zero build step)
- **Live Stream**: Native WebSockets with 1-second snapshots, auto-reconnect, and heartbeat
- **Container**: Docker, Docker Compose, Caddy reverse proxy

---

## Quickstart (Under 2 Minutes)

### 1. Local Python Setup
```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Copy environment config
cp .env.example .env

# Run FastAPI development server
uvicorn app.main:app --reload --port 8000
```
Open **`http://localhost:8000`** in your browser.

### 2. Docker Compose
```bash
docker compose up -d
```

---

## Running Verification Tests & Linter

```bash
# Run test suite
pytest -v

# Run linter
ruff check .

# Run type checker
mypy app/
```
