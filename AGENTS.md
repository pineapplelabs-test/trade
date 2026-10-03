# ANTIGRAVITY SETUP PROMPT: Paper Desk (NSE equity paper trading web app)

## 0. How you must work

You are a senior quant-engineer and full-stack developer. Build the system below as a production-ready web app.

1. **Plan first.** Before writing code, produce a Plan artifact: milestones, files to create, risks, open questions. Wait for my approval.
2. **Build one milestone at a time** (section 15). After each milestone: run all tests, run lint and type checks, show me a short report, then stop for review.
3. **Tests first** for anything that touches money: charges, fills, sizing, risk, P&L. No money logic without unit tests.
4. **Never invent numbers.** Brokerage rates, exchange limits, API limits and market holidays must be read from official sources or config files with an `effective_from` date. If you are unsure, add a TODO and ask me.
5. **Verify APIs against current official docs** (Zerodha Kite Connect docs at kite.trade/docs/connect) before coding against them. Do not rely on memory.
6. Keep code small, typed, documented. No clever abstractions. No dead code.

---

## 1. Mission

Build **Paper Desk**: a web app that connects to live NSE market data, scans all liquid NSE equities continuously, decides which paper trades to take using a rules engine plus a machine learning ranker, simulates execution realistically with exact Indian charges, and shows everything on a fast dashboard.

**Success is not profit. Success is an honest, reproducible measurement of whether the strategy has a real edge after costs.** The system must make it hard to fool myself.

---

## 2. Hard rules (non-negotiable)

- **PAPER ONLY.** The codebase must contain NO function that places a real order. Do not import or call `place_order`, `modify_order`, `cancel_order` from the broker SDK anywhere. Add a CI test that greps the repo and fails if these appear.
- NSE **cash equity only** (EQ series). No F&O, no commodities, no crypto, no margin or leverage.
- All secrets only in environment variables or a secrets manager. Never commit secrets. Add `.env` to `.gitignore` and ship `.env.example`.
- Store all timestamps in UTC. Display and apply market rules in `Asia/Kolkata`.
- The backtester and the live paper engine must run **the same strategy and broker code**. Only the data feed differs (live vs replay).
- No forward data leakage anywhere. Features at time t use only data available at time t.
- This is not financial advice software. Show a clear banner: "Paper money. No real orders are ever sent."

---

## 3. Accounts and capital

Support multiple paper accounts running on the same signals, each with its own config:

| Account | Starting capital | Purpose |
|---|---|---|
| `tiny` | ₹1,000 | The account I asked for. Shows the real effect of share rounding and small size. |
| `shadow` | ₹1,00,000 | Same signals, enough size for statistically meaningful results. |

Both are configurable in `config/accounts.yaml`. Report metrics for both side by side.

**Small account rules (important for ₹1,000):**
- Only consider stocks with `price <= capital * max_position_pct` so at least 1 share is affordable.
- If computed quantity is below 1 share, **skip the trade and log reason `unaffordable`**, never round up.
- Default for `tiny`: `risk_per_trade = 1.0%`, `max_position_pct = 50%`, `max_open_positions = 2`.
- Default for `shadow`: `risk_per_trade = 0.5%`, `max_position_pct = 20%`, `max_open_positions = 5`.
- Keep a per-trade breakdown: gross move, charges, slippage. Show how much of gross profit costs consumed.

---

## 2b. Honesty features (build these in)

- **Pessimistic fill mode** (default ON): extra slippage of 1 tick, execution delay 500 ms to 1 s, random 2% order rejection, partial fills when depth is thin.
- **Loss attribution:** every losing trade is tagged: `bad_signal`, `cost_drag`, `slippage`, `time_stop`, `stop_gap`, `regime`. Dashboard shows the split.
- **Strategy variant counter:** every distinct strategy config tested is logged. Performance page shows "variants tried" next to results as an overfitting warning.
- **Edge decay monitor:** rolling 20 trading day expectancy and win rate. If expectancy goes below 0 for 10 days, show a red banner and auto pause new entries.

---

## 4. Tech stack (use exactly this unless you justify a change)

**Backend (Python 3.12)**
- `FastAPI` + `uvicorn`, WebSocket endpoint for live dashboard updates
- `asyncio` single event loop for ingest; heavy math vectorised with `numpy`; hot functions compiled with `numba`
- `kiteconnect` (Zerodha) for live ticks (KiteTicker, full mode with 5 level depth) and historical candles
- `pydantic` v2 for config and API models
- `SQLAlchemy 2` + `Alembic` migrations, `psycopg` driver
- `PostgreSQL 16` (local Docker, or a Supabase connection string via env var)
- `pyarrow` / `polars` for Parquet tick and bar storage; `pandas` only in research code
- `scikit-learn`, `lightgbm` for ML; `joblib` for model artifacts
- `APScheduler` for jobs (instrument refresh, EOD report, retraining)
- `structlog` for JSON logs, `prometheus-client` for metrics
- Tooling: `pytest`, `hypothesis` (property tests), `ruff`, `mypy --strict` on money modules, `pre-commit`

**Frontend (no framework, no build step)**
- Plain **HTML + CSS + vanilla JavaScript (ES modules)**. No React, no Streamlit, no Tailwind, no bundler.
- Charts: hand written SVG or `<canvas>`. No chart library.
- Live data: native `WebSocket` with auto reconnect and heartbeat.
- Served as static files by FastAPI (or Caddy).

**Infra**
- Docker + docker compose (services: `api`, `worker`, `db`, `caddy`)
- Caddy for automatic HTTPS and reverse proxy
- Host: small VPS in Mumbai region (for example AWS ap-south-1), 2 to 4 vCPU, 8 GB RAM
- GitHub Actions CI: lint, type check, tests, the "no real orders" grep test, Docker build
- Nightly Postgres backup to object storage; keep 14 days

---

## 5. Architecture

```
Kite WebSocket / Replay / Simulator   (one Feed interface)
        |
   tick queue (asyncio) -> batch every 250 ms
        |
   MarketState (numpy arrays per symbol: price, volume, depth, bars)
        |
   FeatureEngine (vectorised) -> UniverseFilter -> Scorer -> MLRanker
        |
   DecisionEngine (EV check, one per account)
        |
   RiskGate (hard veto) -> PaperBroker (fills, slippage, charges)
        |
   Positions / P&L / Equity -> Postgres + WebSocket push -> Dashboard
        |
   Telegram alerts, EOD report, logs, metrics
```

**Three feed modes behind one interface** (`FeedBase`):
1. `KiteFeed`: live ticks.
2. `ReplayFeed`: replays recorded ticks or bars at any speed. Used for backtests with the same code path as live.
3. `SimFeed`: random walk simulator so the app runs with no paid data. Clearly labelled "Simulated" in the UI.

**Folder structure**
```
paper-desk/
  AGENTS.md  README.md  docker-compose.yml  Caddyfile  .env.example
  config/   accounts.yaml  risk.yaml  charges.yaml  strategy.yaml
  app/
    main.py  api/  ws/  auth/
    feed/        base.py kite_feed.py replay_feed.py sim_feed.py
    state/       market_state.py
    features/    indicators.py orderbook.py
    scoring/     universe_filter.py scorer.py ev.py
    strategies/  orb.py vwap_reversion.py
    ml/          labeling.py train.py calibrate.py infer.py registry.py
    risk/        risk_gate.py sizing.py
    broker/      paper_broker.py fills.py charges.py
    reporting/   telegram.py eod_report.py attribution.py
    jobs/        scheduler.py
    db/          models.py migrations/
  web/   index.html  css/  js/  (ES modules)
  tests/ unit/ property/ integration/ replay/
  scripts/ backtest.py train_model.py record_ticks.py
  data/  (git ignored) ticks/ bars/ models/
```

---

## 6. Data layer

- **Instrument master:** download daily, keep NSE EQ series only, map symbol to token, store tick size and surveillance flags (ASM/GSM) from NSE files.
- **Kite session:** Kite access tokens expire daily and require login. Build a `/login/kite` page that redirects to Zerodha login, handles the `request_token` callback, exchanges it for an access token, stores it encrypted, and shows connection status on the Settings page. Do NOT automate the login by scripting credentials or TOTP.
- **Subscriptions:** subscribe to the filtered liquid universe in full mode, respecting current Kite WebSocket limits (read them from docs).
- **Bars:** build 1 minute bars from ticks; derive 5 minute and daily bars. Store in Parquet partitioned by date.
- **Recording:** a `record_ticks.py` job saves raw ticks every market day so replay and ML training have real data.
- **History for training:** pull from the Kite historical API within its limits; use NSE bhavcopy for daily EOD data.
- **Market calendar:** NSE trading holidays from an official source, stored in DB. Session 09:15 to 15:30 IST.
- **Data health:** if no tick for more than 3 seconds on the index, mark feed stale, block new entries, show red status.

---

## 7. Math specification

Let P = price, V = volume, H/L/C = bar high/low/close, E = account equity.

### 7.1 Features (computed vectorised for all symbols)
```
Return over n bars:       r_n = P_t / P_(t-n) - 1               (n = 5, 15, 60)
Z-score:                  z = (P - mean_n) / std_n
VWAP:                     VWAP = SUM(P_i * V_i) / SUM(V_i)
VWAP deviation:           d = (P - VWAP) / VWAP
True range:               TR = max(H-L, |H-C_prev|, |L-C_prev|)
ATR:                      ATR_n = EMA_n(TR)    (n = 14)
RSI:                      RSI = 100 - 100 / (1 + avg_gain / avg_loss)
Relative volume:          RVOL = V_now / mean(V at same minute, last 20 days)
Gap:                      gap = (Open - PrevClose) / PrevClose
Opening range breakout:   ORB = (P - High_first15min) / ATR     when P > High_first15min
Order book imbalance:     OBI = (SUM bidQty - SUM askQty) / (SUM bidQty + SUM askQty)   (5 levels)
Microprice:               MP = (Ask*BidQty + Bid*AskQty) / (BidQty + AskQty)
Spread:                   s = (Ask - Bid) / Mid
Relative strength:        RS = r_stock - beta * r_nifty
Realised volatility:      std of 1 minute log returns over n bars
```
Also include time-of-day bucket, Nifty trend state, India VIX level.

### 7.2 Universe funnel
1. All NSE EQ stocks.
2. Tradability: average daily traded value above Rs 5 crore, price above Rs 20, spread under 0.15%, not ASM/GSM, not at circuit, price affordable for the account (see section 3).
3. Activity: RVOL above 1.5 OR move above 0.7 ATR in last 15 minutes.
4. Full scoring on survivors only.

### 7.3 Composite score (rules baseline)
Cross sectional z-score per feature at each scoring moment, clipped to +/-3:
```
z(i,k) = clip( (x(i,k) - mean_k) / std_k , -3 , +3 )
S(i)   = SUM_k  w_k * z(i,k)
```
Starter weights in `config/strategy.yaml`: momentum 0.25, RVOL 0.20, OBI 0.15, VWAP deviation 0.15, relative strength 0.15, spread penalty 0.10.

### 7.3b Strategies
- **A. Opening range breakout:** after 09:30, long when price breaks first 15 minute high with RVOL > 1.5, price above VWAP, OBI > 0.
- **B. VWAP mean reversion (range days only):** long when z < -2 and microprice > mid, only when VIX is low and Nifty flat.
Long only in v1.

### 7.4 Expected value (the decision rule)
```
EV = p * W - (1 - p) * L - C
```
p = calibrated win probability (from ML, or from the score in the baseline), W = average win %, L = average loss %, C = round trip charges + slippage in %.
**Trade only if EV >= ev_min** (default 0.15% for the tiny account, 0.10% for shadow).
```
Break-even win rate:   p* = (L + C) / (W + L)
```

### 7.5 Position sizing
```
shares = floor( min( (E * r) / (k * ATR),  (E * max_position_pct) / price,  cash / price ) )
```
r = risk per trade, k = stop distance in ATR (default 1.5). If `shares < 1`, skip with reason `unaffordable`.

Fractional Kelly as a hard ceiling, never a target:
```
f* = p - (1 - p) / b,   b = W / L,   use 0.25 * f*
```

### 7.6 Exits
- Stop: `entry - k * ATR` (never widened)
- Target: `entry + m * ATR`, m = 2.5, require reward to risk >= 1.5
- Trailing: after +1 ATR, trail 1 ATR behind the high
- Time stop: 45 minutes without progress
- Force flat all positions at 15:15 IST
- No entries 09:15 to 09:20 and after 15:00

### 7.7 Charges (intraday equity, load rates from `config/charges.yaml` with effective dates; verify against the official Zerodha brokerage calculator)
```
Brokerage      = min(0.03% * order value, Rs 20)  per executed order
STT            = 0.025% * sell value
Exchange txn   = about 0.003% * turnover (NSE)
SEBI fee       = Rs 10 per crore of turnover
GST            = 18% * (brokerage + exchange txn + SEBI fee)
Stamp duty     = 0.003% * buy value
Net P&L        = (Exit - Entry) * Qty - all charges - slippage
```

### 7.8 Fill simulation
- Market order of Q shares walks the live 5 level book; average fill = weighted price across consumed levels.
- Apply configured delay (500 to 1000 ms) and fill at the book as of `t + delay`.
- Limit orders fill only if market trades through the price.
- Partial fills when depth is insufficient; reject at circuit limits and outside session hours.
- Pessimistic mode adds 1 tick slippage and a 2% random rejection rate.

### 7.9 Risk limits (hard coded in RiskGate, not changeable by the ML model)
Risk per trade per account config; daily loss limit 2% then halt; weekly 5% then pause; max drawdown 10% then stop and require manual restart; max 40% in one sector; stale feed blocks entries; kill switch endpoint flattens all and halts.

### 7.10 Performance metrics
```
Expectancy      = win% * avg_win - loss% * avg_loss   (net of costs)
Profit factor   = gross profit / gross loss
Sharpe (daily)  = (mean(r_d) - r_f) / std(r_d) * sqrt(252)
Sortino         = (mean(r_d) - r_f) / downside_std(r_d) * sqrt(252)
Max drawdown    = max_t (Peak_t - Equity_t) / Peak_t
Calmar          = annualised return / max drawdown
Cost drag       = total charges / gross profit
Brier score     = mean( (p_hat - outcome)^2 )
```
Show Deflated Sharpe or at least a "variants tried" count next to any Sharpe.

---

## 8. Machine learning (what to build from scratch)

**Do NOT train a large neural network or an LLM for price prediction.** It overfits, is slow and is hard to debug. Build this instead, in order:

**Stage 1: rules baseline (no ML).** Strategies A and B with the hand weighted score. This is the benchmark. Every ML model must beat it out of sample.

**Stage 2: meta-labeling model (the main model).**
- Rules generate candidate trades. A **LightGBM gradient boosted classifier** (trained from scratch on my recorded data) predicts `P(win)` for each candidate. This filters bad trades instead of inventing trades.
- **Labels:** triple barrier. For each candidate at time t: upper barrier `+m*ATR`, lower barrier `-k*ATR`, vertical barrier T minutes. Label 1 if upper hit first, else 0.
- **Features:** all section 7.1 features plus time-of-day, regime, Nifty state, VIX, symbol liquidity bucket.
- **Validation:** walk-forward splits, **purged K-fold with embargo** to prevent overlapping label leakage. Never random shuffle. Keep the last 2 months as an untouched holdout, used once.
- **Calibration:** isotonic regression or Platt scaling. Report reliability curve and Brier score. A "60% confidence" must win about 60% of the time.
- **Baselines to beat:** logistic regression and the rules-only score. Keep the ML model only if it wins out of sample.
- **Registry:** save each model with training window, feature list hash, metrics, and git commit. Load the active model at startup. Inference for the whole candidate batch must stay under 5 ms.

**Stage 3 (optional, later): regime filter.** A simple volatility-percentile rule first; a 2 state HMM only if it improves out of sample results.

**Stage 4 (slow lane only): LLM news filter.** Summarise results announcements and headlines and tag stocks "avoid today". It runs outside the millisecond loop and can only veto, never create trades. Also writes the daily post market review.

Rules for ML: minimum 300 trades before trusting any result; log every experiment; no peeking at forward data; retrain on a schedule and compare against the live model before swapping.

---

## 9. Database schema (Postgres, Alembic migrations)

`instruments(token, symbol, name, sector, tick_size, active, surveillance_flag)`
`accounts(id, name, starting_capital, config_json)`
`signals(id, ts, token, strategy, score, p_hat, ev_pct, features_json, decision, reject_reason)`
`orders(id, account_id, signal_id, ts, token, side, qty, order_type, limit_price, status)`
`fills(id, order_id, ts, qty, price, slippage, brokerage, stt, exchange, gst, sebi, stamp)`
`positions(id, account_id, token, qty, avg_price, stop, target, opened_at, closed_at, net_pnl, exit_reason, loss_tag)`
`equity_curve(account_id, ts, cash, equity, day_pnl, drawdown_pct)`
`risk_events(ts, account_id, rule, value, limit, action)`
`model_runs(id, ts, model_type, train_window, test_window, metrics_json, artifact_path, active)`
`config_versions(id, effective_from, json)` so any past trade can be replayed with that day's config
`strategy_variants(id, ts, config_hash, notes)` for the overfitting counter
`kite_session(id, ts, encrypted_token, expires_at)`

---

## 10. API contract

REST (all behind auth, JSON):
```
GET  /api/health                       status of feed, db, model, clock
GET  /api/accounts                     list accounts with equity, day P&L
GET  /api/scanner?account=tiny         ranked candidates
GET  /api/positions?account=tiny
GET  /api/trades?account=tiny&limit=100
GET  /api/performance?account=tiny     all metrics + equity curve
GET  /api/risk?account=tiny            meters and events
POST /api/kill                         flatten all paper positions and halt
POST /api/resume                       manual restart after a halt
POST /api/mode                         {"feed":"kite|replay|sim"}
GET  /login/kite  and  /login/kite/callback
```
WebSocket `/ws` pushes every second:
```json
{"type":"snapshot","ts":"...","feed":"kite","clock":"10:12:03",
 "accounts":{"tiny":{"equity":1004.2,"day_pnl":4.2,"cash":620.0}},
 "scanner":[{"symbol":"...","price":0,"score":0,"p_hat":0,"ev_pct":0,"rvol":0,"obi":0,"action":"Enter"}],
 "positions":[],"events":[]}
```

---

## 11. Frontend specification (HTML, CSS, vanilla JS)

- Pages (tabs): **Scanner, Positions, Trades, Performance, Risk, Settings**. Account switcher (`tiny` / `shadow`) in the header.
- Header always shows: equity, day P&L, cash, market clock, feed status (Live / Replay / Simulated / Stale), and a **Kill switch** button with a confirm step.
- Scanner: top 20 ranked stocks. Each row: symbol, price (flashes green or red on change), change %, **centre-balanced score bar** (green right, red left), win chance, EV %, relative volume, book imbalance, action chip (Enter, Watch, Skip, Holding, Halted).
- Trades: every closed trade with entry, exit, qty, gross, charges, slippage, net, R multiple, exit reason, **loss tag**, and a plain-words "why it entered" line.
- Performance: equity curve (SVG), drawdown chart, all metrics from 7.10, P&L by hour and by strategy, cost drag, variants-tried counter, tiny vs shadow comparison.
- Risk: meters for daily loss, open positions, exposure; rules in force; risk event log; edge decay status.
- Settings: Kite connection status and login button, feed mode, pessimistic fill toggle, account configs (read only display of YAML values).
- Design: sentence case, clear hierarchy, light and dark themes via CSS variables and `prefers-color-scheme`, tabular numbers, responsive down to 360 px width, visible keyboard focus, `prefers-reduced-motion` respected, no external UI kits. Safe area insets for mobile.
- Empty states explain what will appear and why. Errors say what failed and what to do. A persistent banner: "Paper money. No real orders are ever sent."
- JS: ES modules, one small store, render functions per tab, reconnecting WebSocket with exponential backoff and a heartbeat. Never block the main thread; update only changed rows.

---

## 12. Security and operations

- Single user auth: password login with Argon2 hashing, secure httpOnly session cookie, CSRF protection, rate limited login. Optional TOTP later.
- HTTPS only via Caddy. Strict security headers and CORS (same origin).
- Encrypt the stored Kite access token (Fernet key from env).
- Structured JSON logs with request ids. `/metrics` for Prometheus: tick lag, loop latency, features compute time, fills, rejects, WebSocket clients.
- Graceful shutdown: persist state, close sockets. On restart, restore open paper positions from the DB.
- Health checks and Docker restart policy. Telegram alert on: feed stale, risk halt, kill switch, daily summary.

---

## 13. Performance targets (measure and report, do not assume)

- Parse tick batch and update state: under 5 ms
- Features for the whole filtered universe: under 30 ms
- Score, rank, ML inference, EV, risk gate: under 15 ms
- Total internal time per cycle: under 50 ms (network latency is separate and uncontrollable)
- Dashboard update latency from tick to screen: under 500 ms
Add a benchmark script and fail CI if these regress by more than 30%.

---

## 14. Testing and acceptance criteria

Unit and property tests (hypothesis):
- `charges.py` matches 10 hand calculated trades to the paisa; charges never negative.
- `fills.py`: a buy never fills below the best ask; average fill price is monotonic in quantity; partial fills never exceed displayed depth.
- `sizing.py`: shares never exceed cash, never exceed max position, never negative; returns 0 when unaffordable.
- `risk_gate.py`: daily loss limit halts entries; stale feed blocks entries; force flat at 15:15.
- P&L reconciles: cash + positions value equals equity at every step in a randomized replay.
- No lookahead: a test that shuffles future data and asserts features at t do not change.
- The "no real order API" grep test passes.
Integration tests: replay one recorded day end to end and assert deterministic results (same inputs give identical trades). Run the same day through backtest and "live" replay path and assert identical output.
Frontend: smoke test that every tab renders with empty and populated data and that the WebSocket reconnects.

---

## 15. Milestones (stop for my review after each)

1. **Scaffold:** repo, Docker compose, config files, DB migrations, CI, `AGENTS.md`, health endpoint, auth, empty dashboard shell with tabs and banner.
2. **Feeds and data:** `SimFeed`, `ReplayFeed`, `KiteFeed` with login flow, instrument master, bar builder, tick recorder, data health checks.
3. **Features and scanner:** vectorised feature engine, universe funnel, composite score, scanner API and tab. Benchmarks meet section 13.
4. **Paper broker and risk:** charges, depth walking fills, pessimistic mode, sizing, risk gate, positions, equity, both accounts. All money tests green.
5. **Strategies and EV engine:** strategies A and B, EV decision rule, exits, loss attribution, trade log and performance tabs.
6. **Backtest and validation:** replay backtester using the live code path, walk-forward runner, metrics report, variants counter.
7. **ML meta-labeling:** triple barrier labels, LightGBM training script, purged CV, calibration, registry, inference integrated, comparison report against baseline.
8. **Reports and alerts:** Telegram alerts, EOD report with LLM written review (slow lane), edge decay monitor, Settings tab.
9. **Hardening and deploy:** security review, backups, load test, production docker compose with Caddy, deployment guide, runbook.

---

## 16. Out of scope for v1

Real order placement, F&O, shorting, leverage, multiple users, mobile app, deep learning price prediction, high frequency or colocated execution.

---

## 17. Final deliverables

Working repo, `README.md` with setup in under 15 minutes, `docs/RUNBOOK.md`, `docs/MATH.md` explaining every formula above with the code location, `docs/RESULTS_TEMPLATE.md` for weekly honest reviews, and a final report stating what works, what is unproven, and the go or no go gates I should use before ever considering real money (60+ trading days forward test, 300+ trades, positive net expectancy after costs, profit factor above 1.3, max drawdown below 10%).
