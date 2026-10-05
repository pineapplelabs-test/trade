/**
 * Paper Desk Vanilla ES Module Application
 * Groww-inspired Explore Dashboard with Spacious Layout & Agent Intelligence.
 */

// Initial Liquid Core Universe (NSE Cash Equities)
const defaultStocks = [
  { symbol: "BEL", name: "Bharat Electronics", price: 383.10, change: 1.45, score: 0.0, win_prob: null, ev: null, rvol: 1.0, obi: 0.0, atr: 5.40, action: "Watch", sparkline: [378, 380, 379, 381, 382, 383.1] },
  { symbol: "RELIANCE", name: "Reliance Industries", price: 1167.70, change: 0.65, score: 0.0, win_prob: null, ev: null, rvol: 1.0, obi: 0.0, atr: 16.50, action: "Watch", sparkline: [1160, 1162, 1165, 1164, 1166, 1167.7] },
  { symbol: "TMPV", name: "Tata Motors (TMPV)", price: 279.40, change: 0.85, score: 0.0, win_prob: null, ev: null, rvol: 1.0, obi: 0.0, atr: 4.20, action: "Watch", sparkline: [275, 276.5, 278, 277.2, 278.9, 279.4] },
  { symbol: "BHARTIARTL", name: "Bharti Airtel", price: 1741.10, change: 0.85, score: 0.0, win_prob: null, ev: null, rvol: 1.0, obi: 0.0, atr: 21.00, action: "Watch", sparkline: [1725, 1730, 1728, 1736, 1734, 1741.1] },
  { symbol: "SBIN", name: "State Bank of India", price: 812.50, change: 1.10, score: 0.0, win_prob: null, ev: null, rvol: 1.0, obi: 0.0, atr: 11.50, action: "Watch", sparkline: [802, 808, 805, 810, 809, 812.5] },
  { symbol: "TATASTEEL", name: "Tata Steel", price: 165.20, change: 0.90, score: 0.0, win_prob: null, ev: null, rvol: 1.0, obi: 0.0, atr: 2.80, action: "Watch", sparkline: [163, 164.5, 163.8, 165, 165.2] },
  { symbol: "ICICIBANK", name: "ICICI Bank", price: 1310.60, change: 0.60, score: 0.0, win_prob: null, ev: null, rvol: 1.0, obi: 0.0, atr: 15.60, action: "Watch", sparkline: [1300, 1305, 1302, 1308, 1310.6] },
  { symbol: "INFY", name: "Infosys", price: 1035.00, change: 0.45, score: 0.0, win_prob: null, ev: null, rvol: 1.0, obi: 0.0, atr: 14.40, action: "Watch", sparkline: [1028, 1030, 1032, 1034, 1035] },
  { symbol: "TCS", name: "Tata Consultancy Services", price: 2075.00, change: 0.35, score: 0.0, win_prob: null, ev: null, rvol: 1.0, obi: 0.0, atr: 28.50, action: "Watch", sparkline: [2060, 2068, 2072, 2075] },
  { symbol: "HDFCBANK", name: "HDFC Bank", price: 721.20, change: -0.40, score: 0.0, win_prob: null, ev: null, rvol: 1.0, obi: 0.0, atr: 9.20, action: "Watch", sparkline: [725, 723, 722, 721.2] },
];

// Application State Store
const state = {
  currentAccount: "real5k",
  accounts: {},
  systemHalted: false,
  feedMode: "sim",
  wsConnected: false,
  stocks: [...defaultStocks],
  selectedSymbol: "BEL",
  searchQuery: "",
  activeFilter: "all",
  logs: [],
};

// DOM References
const dom = {
  accountSelect: document.getElementById("account-select"),
  headerEquity: document.getElementById("header-equity"),
  headerDayPnl: document.getElementById("header-day-pnl"),
  headerCash: document.getElementById("header-cash"),
  headerClock: document.getElementById("header-clock"),
  feedPill: document.getElementById("feed-status-pill"),
  feedText: document.getElementById("feed-status-text"),
  killBtn: document.getElementById("kill-switch-btn"),
  killModal: document.getElementById("kill-modal"),
  modalCancelBtn: document.getElementById("modal-cancel-btn"),
  modalConfirmBtn: document.getElementById("modal-confirm-kill-btn"),
  themeToggleBtn: document.getElementById("theme-toggle-btn"),
  tabButtons: document.querySelectorAll(".nav-item"),
  tabPanes: document.querySelectorAll(".tab-pane"),
  scannerTbody: document.getElementById("scanner-tbody"),
  globalSearch: document.getElementById("global-search"),
  
  // Hero cards
  heroCards: document.querySelectorAll(".groww-stock-card"),
  
  // Depth & Microprice
  depthSymbol: document.getElementById("depth-target-symbol"),
  depthMicroprice: document.getElementById("depth-microprice"),
  depthObiVal: document.getElementById("depth-obi-val"),
  depthObiBar: document.getElementById("depth-obi-bar"),
  depthBids: document.getElementById("depth-bids"),
  depthAsks: document.getElementById("depth-asks"),
  depthTotalBids: document.getElementById("depth-total-bids"),
  depthTotalAsks: document.getElementById("depth-total-asks"),

  // Intelligence Logs
  agentLogContainer: document.getElementById("agent-log-container"),
  logCountBadge: document.getElementById("log-count-badge"),
  
  // Funnel
  funnelTotal: document.getElementById("funnel-total"),
  funnelLiquid: document.getElementById("funnel-liquid"),
  funnelActive: document.getElementById("funnel-active"),
  funnelScored: document.getElementById("funnel-scored"),
  funnelEntered: document.getElementById("funnel-entered"),
  funnelLatency: document.getElementById("funnel-latency"),
  
  // Filter pills
  filterPills: document.querySelectorAll(".filter-pill"),
};

// Currency Formatter (₹)
function formatINR(val) {
  if (typeof val !== "number" || isNaN(val)) return "₹0.00";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(val);
}

// Percentage Formatter
function formatPct(val) {
  if (typeof val !== "number" || isNaN(val)) return "0.00%";
  const prefix = val > 0 ? "+" : "";
  return `${prefix}${val.toFixed(2)}%`;
}

// SVG Sparkline
function renderSparklineSVG(points, isPositive = true) {
  if (!points || points.length < 2) return "";
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const w = 84;
  const h = 24;

  const coords = points.map((p, i) => {
    const x = Math.round((i / (points.length - 1)) * w);
    const y = Math.round(h - ((p - min) / range) * (h - 4) - 2);
    return `${x},${y}`;
  }).join(" ");

  const color = isPositive ? "#00D09C" : "#EB5B3C";
  return `
    <svg class="sparkline-svg" viewBox="0 0 ${w} ${h}">
      <polyline fill="none" stroke="${color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" points="${coords}" />
    </svg>
  `;
}

// Update 5-Level Depth Matrix
function updateDepthMatrix(stock) {
  if (!stock || !dom.depthSymbol) return;

  dom.depthSymbol.textContent = `${stock.symbol} // CASH`;
  
  const tickSize = 0.05;
  const mid = stock.price;
  const skew = stock.obi || 0.2;
  
  const bids = [];
  const asks = [];
  let totalBidQty = 0;
  let totalAskQty = 0;

  if (stock.depth && stock.depth.bids && stock.depth.bids.length >= 5) {
    stock.depth.bids.slice(0, 5).forEach(b => {
      bids.push({ price: b.price, qty: b.quantity });
      totalBidQty += b.quantity;
    });
    stock.depth.asks.slice(0, 5).forEach(a => {
      asks.push({ price: a.price, qty: a.quantity });
      totalAskQty += a.quantity;
    });
  } else {
    for (let i = 1; i <= 5; i++) {
      const bidPrice = mid - (i * tickSize);
      const askPrice = mid + (i * tickSize);
      const bidQty = Math.round((1200 - (i * 150)) * (1 + skew));
      const askQty = Math.round((1200 - (i * 150)) * (1 - skew));
      bids.push({ price: bidPrice, qty: Math.max(10, bidQty) });
      asks.push({ price: askPrice, qty: Math.max(10, askQty) });
      totalBidQty += bidQty;
      totalAskQty += askQty;
    }
  }

  const b1 = bids[0];
  const a1 = asks[0];
  const microprice = ((a1.price * b1.qty) + (b1.price * a1.qty)) / (b1.qty + a1.qty);
  
  dom.depthMicroprice.textContent = `₹${microprice.toFixed(2)}`;
  dom.depthMicroprice.className = microprice >= mid ? "positive" : "negative";

  const obi = (totalBidQty - totalAskQty) / (totalBidQty + totalAskQty);
  const obiPrefix = obi > 0 ? "+" : "";
  dom.depthObiVal.textContent = `OBI: ${obiPrefix}${obi.toFixed(2)}`;
  dom.depthObiVal.className = obi >= 0 ? "positive" : "negative";

  const absObi = Math.min(1.0, Math.abs(obi));
  const barWidth = Math.round(absObi * 50);
  if (obi >= 0) {
    dom.depthObiBar.className = "depth-obi-bar positive";
    dom.depthObiBar.style.left = "50%";
    dom.depthObiBar.style.width = `${barWidth}%`;
  } else {
    dom.depthObiBar.className = "depth-obi-bar negative";
    dom.depthObiBar.style.left = `${50 - barWidth}%`;
    dom.depthObiBar.style.width = `${barWidth}%`;
  }

  dom.depthBids.innerHTML = bids.map(b => `
    <div class="ladder-item">
      <span class="qty-val">${b.qty.toLocaleString("en-IN")}</span>
      <span class="price-bid font-mono">${b.price.toFixed(2)}</span>
    </div>
  `).join("");

  dom.depthAsks.innerHTML = asks.map(a => `
    <div class="ladder-item">
      <span class="price-ask font-mono">${a.price.toFixed(2)}</span>
      <span class="qty-val">${a.qty.toLocaleString("en-IN")}</span>
    </div>
  `).join("");

  dom.depthTotalBids.textContent = totalBidQty.toLocaleString("en-IN");
  dom.depthTotalAsks.textContent = totalAskQty.toLocaleString("en-IN");
}

// Render Main Scanned Stocks Table
function renderScannerTable() {
  if (!dom.scannerTbody) return;

  const query = state.searchQuery.toLowerCase().trim();
  let filtered = state.stocks.filter(s =>
    s.symbol.toLowerCase().includes(query) || s.name.toLowerCase().includes(query)
  );

  // Apply Pill Filters
  if (state.activeFilter === "rvol") {
    filtered = filtered.filter(s => s.rvol >= 1.5);
  } else if (state.activeFilter === "affordable") {
    filtered = filtered.filter(s => s.price <= 500);
  } else if (state.activeFilter === "orb") {
    filtered = filtered.filter(s => s.action === "Enter");
  }

  if (filtered.length === 0) {
    dom.scannerTbody.innerHTML = `
      <tr>
        <td colspan="8" class="empty-state-cell" style="padding: 40px; text-align: center; color: var(--text-muted);">
          No stocks match the selected criteria.
        </td>
      </tr>
    `;
    return;
  }

  dom.scannerTbody.innerHTML = filtered.map(s => {
    const isPos = s.change >= 0;
    const changeClass = isPos ? "pos" : "neg";
    const changeText = `${isPos ? "+" : ""}${s.change.toFixed(2)}%`;
    const isSelected = s.symbol === state.selectedSymbol;
    const selectedClass = isSelected ? "selected" : "";
    const obiPrefix = s.obi > 0 ? "+" : "";

    return `
      <tr class="${selectedClass}" data-symbol="${s.symbol}">
        <td class="col-company">
          <div class="company-cell">
            <span class="company-name font-mono">${s.symbol}</span>
            <span class="company-sub">${s.name} &bull; EQ</span>
          </div>
        </td>
        <td class="col-chart text-center">
          ${renderSparklineSVG(s.sparkline, isPos)}
        </td>
        <td class="col-price text-right font-mono">
          <span class="price-val">₹${s.price.toFixed(2)}</span>
          <span class="price-change ${changeClass}">${changeText}</span>
        </td>
        <td class="col-metric text-right font-mono">${s.win_prob ? s.win_prob.toFixed(1) + "%" : '<span class="badge-neutral" title="Uncalibrated - requires 300+ out-of-sample trades">UNAVAILABLE</span>'}</td>
        <td class="col-metric text-right font-mono ${s.ev !== null && s.ev !== undefined ? (s.ev >= 0 ? "text-emerald" : "text-coral") : "text-muted"}">${s.ev !== null && s.ev !== undefined ? (s.ev >= 0 ? "+" : "") + s.ev.toFixed(2) + "%" : "--"}</td>
        <td class="col-metric text-right font-mono">${s.rvol.toFixed(1)}x</td>
        <td class="col-metric text-right font-mono ${s.obi >= 0 ? "text-emerald" : "text-coral"}">${obiPrefix}${s.obi.toFixed(2)}</td>
        <td class="col-action text-center">
          <span class="chip-action ${s.action.toLowerCase()}">${s.action}</span>
        </td>
      </tr>
    `;
  }).join("");

  // Attach Row Click Handler
  const rows = dom.scannerTbody.querySelectorAll("tr[data-symbol]");
  rows.forEach(r => {
    r.addEventListener("click", () => {
      const sym = r.getAttribute("data-symbol");
      selectStock(sym);
    });
  });
}

function selectStock(sym) {
  const stock = state.stocks.find(s => s.symbol === sym);
  if (!stock) return;

  state.selectedSymbol = sym;

  // Highlight top card if present
  dom.heroCards.forEach(c => {
    c.classList.toggle("active-card", c.getAttribute("data-symbol") === sym);
  });

  updateDepthMatrix(stock);
  renderScannerTable();
}

// Render Agent Live Decisions Feed
function renderAgentLogs() {
  if (!dom.agentLogContainer) return;

  dom.agentLogContainer.innerHTML = state.logs.map(l => `
    <div class="decision-item">
      <div class="decision-item-top font-mono">
        <span class="decision-symbol">${l.symbol}</span>
        <span class="decision-tag ${l.tag.toLowerCase()}">${l.tag}</span>
      </div>
      <div class="decision-text">${l.reason}</div>
      <div class="decision-time font-mono">${l.time}</div>
    </div>
  `).join("");

  if (dom.logCountBadge) {
    dom.logCountBadge.textContent = `${state.logs.length} LOGS`;
  }
}

function addAgentLog(entry) {
  state.logs.unshift(entry);
  if (state.logs.length > 20) state.logs.pop();
  renderAgentLogs();
}

// Start Stream Simulation
function startSimulation() {
  const sampleDecisions = [
    {
      symbol: "SYSTEM",
      tag: "Audit",
      reason: "Market data streaming active. Uncalibrated ML probabilities set to UNAVAILABLE until 300+ trades recorded.",
    },
    {
      symbol: "RISK",
      tag: "Enforced",
      reason: "Deterministic limits armed: Daily loss 2%, Weekly loss 5%, Max drawdown 10%, Sector cap 40%.",
    },
    {
      symbol: "GROWW",
      tag: "Feed",
      reason: "Read-only NSE live market quotes active. Real broker execution calls strictly disabled.",
    },
  ];

  // Seed initial system audit logs
  sampleDecisions.forEach((d, idx) => {
    const now = new Date(Date.now() - (idx * 2000));
    const timeStr = now.toTimeString().split(" ")[0];
    state.logs.push({ ...d, time: timeStr });
  });
  renderAgentLogs();

  // Initial poll and recurring real evaluation stream
  refreshScanner();
  setInterval(refreshScanner, 3500);
}

async function refreshScanner() {
  try {
    const res = await fetch(`/api/scanner?account=${state.currentAccount}`);
    if (!res.ok) return;
    const data = await res.json();
    const now = new Date();
    const timeStr = now.toTimeString().split(" ")[0];

    if (data.feed_source) {
      const srcEl = document.getElementById("quality-source");
      if (srcEl) srcEl.textContent = data.feed_source;
    }

    if (data.session_phase) {
      const sessEl = document.getElementById("market-session-status");
      if (sessEl) sessEl.textContent = `NSE Session: ${data.session_phase}`;
    }

    if (data.candidates && data.candidates.length > 0) {
      data.candidates.forEach((cand) => {
        const existing = state.stocks.find((s) => s.symbol === cand.symbol);
        if (existing) {
          existing.price = cand.price;
          existing.change = cand.change;
          if (cand.score !== undefined) existing.score = cand.score;
          existing.win_prob = cand.win_chance !== undefined ? cand.win_chance : null;
          existing.ev = cand.ev_pct !== undefined ? cand.ev_pct : null;
          if (cand.rvol !== undefined) existing.rvol = cand.rvol;
          if (cand.obi !== undefined) existing.obi = cand.obi;
          if (cand.action !== undefined) existing.action = cand.action;
          if (cand.depth && cand.depth.bids && cand.depth.bids.length > 0) {
            existing.depth = cand.depth;
          }
        }
      });
      renderScannerTable();
      updateHeroCards();
      const current = state.stocks.find((s) => s.symbol === state.selectedSymbol);
      if (current) updateDepthMatrix(current);

      // Section 19: Agent Mind reports actual live data & indicators (deterministic top candidate)
      const featured = data.candidates && data.candidates.length > 0 ? data.candidates[0] : null;
      if (featured) {
        const tag = featured.action === "Enter" ? "Approved" : (featured.action === "Blocked" ? "Blocked" : (featured.action === "Skip" ? "Risk" : "Watching"));
        const evDisplay = featured.ev_pct !== null && featured.ev_pct !== undefined ? `Net EV ${featured.ev_pct}%` : "EV Uncalibrated";
        const reason = featured.rejection_reason || featured.reason || `RVOL ${featured.rvol}x | OBI ${featured.obi > 0 ? "+" : ""}${featured.obi} | ${evDisplay}`;
        addAgentLog({ symbol: featured.symbol, tag, reason, time: timeStr });
      }
    }

    if (data.funnel_stats) {
      const elMonitored = document.getElementById("funnel-monitored");
      const elLiquid = document.getElementById("funnel-liquid");
      const elSignals = document.getElementById("funnel-signals");
      const elLatency = document.getElementById("funnel-latency");

      if (elMonitored) elMonitored.textContent = data.funnel_stats.monitored;
      if (elLiquid) elLiquid.textContent = data.funnel_stats.liquid;
      if (elSignals) elSignals.textContent = data.funnel_stats.approved;
      if (elLatency) elLatency.textContent = data.cycle_time_ms ? `${data.cycle_time_ms.toFixed(1)} ms` : "realtime";
    }
  } catch (err) {
    console.debug("refreshScanner fetch error:", err);
  }
}

function updateHeroCards() {
  dom.heroCards.forEach(card => {
    const sym = card.getAttribute("data-symbol");
    const stock = state.stocks.find(s => s.symbol === sym);
    if (!stock) return;
    const priceEl = card.querySelector(".card-price");
    const changeEl = card.querySelector(".card-change");
    if (priceEl && stock.price > 0) priceEl.textContent = `₹${stock.price.toFixed(2)}`;
    if (changeEl) {
      const isPos = stock.change >= 0;
      changeEl.textContent = `${isPos ? "+" : ""}${stock.change.toFixed(2)}%`;
      changeEl.className = `card-change font-mono ${isPos ? "positive" : "negative"}`;
    }
  });
}

// Core Handlers
function setupTabs() {
  dom.tabButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const targetTab = btn.getAttribute("data-tab");
      dom.tabButtons.forEach(b => b.classList.remove("active"));
      dom.tabPanes.forEach(p => p.classList.remove("active"));

      btn.classList.add("active");
      const activePane = document.getElementById(`pane-${targetTab}`);
      if (activePane) activePane.classList.add("active");

      if (targetTab === "trades" || targetTab === "performance") {
        refreshTradesAndEdgeHealth();
      }
    });
  });
}

function updateHeaderMetrics() {
  const acct = state.accounts[state.currentAccount];
  if (!acct) return;

  dom.headerEquity.textContent = formatINR(acct.equity);
  dom.headerCash.textContent = formatINR(acct.cash);

  const pnlVal = acct.day_pnl || 0.0;
  const pnlPct = acct.day_pnl_pct || 0.0;
  dom.headerDayPnl.textContent = `Day P&L: ${formatINR(pnlVal)} (${formatPct(pnlPct)})`;

  dom.headerDayPnl.classList.remove("positive", "negative");
  if (pnlVal > 0) dom.headerDayPnl.classList.add("positive");
  else if (pnlVal < 0) dom.headerDayPnl.classList.add("negative");
}

async function loadAccounts() {
  try {
    const res = await fetch("/api/accounts");
    if (!res.ok) return;
    const data = await res.json();
    data.forEach(a => {
      state.accounts[a.id] = a;
    });
    updateHeaderMetrics();
  } catch (err) {
    console.error("Failed to load accounts:", err);
  }
}

function setupSearchAndFilters() {
  if (dom.globalSearch) {
    dom.globalSearch.addEventListener("input", (e) => {
      state.searchQuery = e.target.value;
      renderScannerTable();
    });
  }

  // Filter Pills
  dom.filterPills.forEach(pill => {
    pill.addEventListener("click", () => {
      dom.filterPills.forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      state.activeFilter = pill.getAttribute("data-filter");
      renderScannerTable();
    });
  });

  // Top Card Click Listeners
  dom.heroCards.forEach(card => {
    card.addEventListener("click", () => {
      const sym = card.getAttribute("data-symbol");
      selectStock(sym);
    });
  });
}

// WebSocket
let ws = null;
function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws`;

  ws = new WebSocket(wsUrl);
  ws.onmessage = (event) => {
    if (event.data === "pong") return;
    try {
      const msg = JSON.parse(event.data);
      if (msg.clock) dom.headerClock.textContent = `${msg.clock} IST`;
      if (msg.feed) {
        state.feedMode = msg.feed;
        if (dom.feedText) {
          dom.feedText.textContent = msg.feed === "groww" ? "Groww Feed (Live)" : (msg.feed === "replay" ? "Replay Feed" : "Simulated Feed");
        }
      }

      // Update Phase 6 Data Quality Indicator
      const qSource = document.getElementById("quality-source");
      if (qSource && msg.feed_source) qSource.textContent = msg.feed_source;

      const qQuote = document.getElementById("quality-quote-age");
      if (qQuote && msg.quote_age_ms !== undefined) qQuote.textContent = `Quote: ${msg.quote_age_ms}ms`;

      const qDepth = document.getElementById("quality-depth-age");
      if (qDepth && msg.depth_age_ms !== undefined) qDepth.textContent = `Depth: ${msg.depth_age_ms}ms`;

      const qDot = document.getElementById("quality-dot");
      const qConn = document.getElementById("quality-conn");
      if (qDot && qConn) {
        if (msg.quality_status === "STALE") {
          qDot.className = "quality-dot stale";
          qConn.textContent = "STALE";
          qConn.style.color = "var(--groww-coral)";
        } else {
          qDot.className = "quality-dot live";
          qConn.textContent = "CONNECTED";
          qConn.style.color = "var(--text-muted)";
        }
      }

      if (msg.accounts) {
        for (const [acctId, data] of Object.entries(msg.accounts)) {
          if (state.accounts[acctId]) {
            state.accounts[acctId].equity = data.equity;
            state.accounts[acctId].cash = data.cash;
            state.accounts[acctId].day_pnl = data.day_pnl;
          }
        }
        updateHeaderMetrics();
      }
      if (msg.scanner && msg.scanner.length > 0) {
        msg.scanner.forEach((remoteItem) => {
          const localItem = state.stocks.find((s) => s.symbol === remoteItem.symbol);
          if (localItem) {
            localItem.price = remoteItem.price;
            localItem.change = remoteItem.change;
            if (remoteItem.depth) localItem.depth = remoteItem.depth;
            if (!localItem.sparkline) localItem.sparkline = [remoteItem.price];
            else {
              localItem.sparkline.push(remoteItem.price);
              if (localItem.sparkline.length > 10) localItem.sparkline.shift();
            }
          }
        });
        renderScannerTable();
        const sel = state.stocks.find((s) => s.symbol === state.selectedSymbol);
        if (sel) updateDepthMatrix(sel);
      }
    } catch (e) {}
  };

  ws.onclose = () => {
    setTimeout(connectWebSocket, 2500);
  };
}

// Emergency Halt Modal
function setupKillSwitch() {
  dom.killBtn.addEventListener("click", () => {
    dom.killModal.style.display = "flex";
  });

  dom.modalCancelBtn.addEventListener("click", () => {
    dom.killModal.style.display = "none";
  });

  dom.modalConfirmBtn.addEventListener("click", async () => {
    dom.killModal.style.display = "none";
    try {
      await fetch("/api/kill", { method: "POST" });
      dom.killBtn.textContent = "Engine Halted";
      dom.killBtn.style.backgroundColor = "#E2E8F0";
      dom.killBtn.style.color = "#64748B";
    } catch (err) {
      console.error("Failed to execute halt:", err);
    }
  });
}

// =========================================================================
// PHASE 5: TRADE LEDGER, FORENSIC TRADE MODAL & EDGE HEALTH PANEL
// =========================================================================

async function refreshTradesAndEdgeHealth() {
  await Promise.all([loadTradesTable(), loadEdgeHealth()]);
}

async function loadTradesTable() {
  const tbody = document.getElementById("trades-tbody");
  if (!tbody) return;

  try {
    const res = await fetch(`/api/trades?account=${state.currentAccount}&limit=100`);
    if (!res.ok) return;
    const trades = await res.json();

    if (!trades || trades.length === 0) {
      tbody.innerHTML = `
        <tr class="empty-row">
          <td colspan="12" class="empty-state-cell">
            <div class="empty-box">
              <h3 class="empty-title">No Orders Executed for ${state.currentAccount}</h3>
              <p class="empty-text">Closed trades will show here with every paisa of brokerage, STT, and exchange fees itemized.</p>
            </div>
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = trades.map(t => {
      const isPos = t.net_pnl >= 0;
      const netClass = isPos ? "positive text-emerald" : "negative text-coral";
      const grossClass = t.gross_pnl >= 0 ? "positive" : "negative";
      const ts = t.exit_timestamp ? t.exit_timestamp.split("T")[1]?.slice(0, 8) || t.exit_timestamp : "--";
      const lossTagClass = t.loss_tag === "cost_drag" ? "badge-red" : (t.loss_tag === "NONE" ? "badge-green" : "badge-gray");

      return `
        <tr data-trade-id="${t.trade_id}" class="trade-row-item" title="Click to view full forensic execution and fee audit">
          <td class="font-mono" style="font-weight: 600; color: #4F46E5;">${t.trade_id}</td>
          <td class="font-mono text-muted">${ts}</td>
          <td class="font-mono font-bold">${t.symbol}</td>
          <td><span class="direction-badge">${t.direction}</span></td>
          <td class="text-right font-mono">${t.quantity}</td>
          <td class="text-right font-mono">₹${t.entry_price.toFixed(2)}</td>
          <td class="text-right font-mono">₹${t.exit_price.toFixed(2)}</td>
          <td class="text-right font-mono ${grossClass}">₹${t.gross_pnl.toFixed(2)}</td>
          <td class="text-right font-mono text-coral">₹${t.total_charges.toFixed(2)}</td>
          <td class="text-right font-mono ${netClass}" style="font-weight: 700;">₹${t.net_pnl.toFixed(2)}</td>
          <td class="text-center"><span class="chip-action enter">${t.trade_status}</span></td>
          <td class="text-center"><span class="${lossTagClass}">${t.loss_tag}</span></td>
        </tr>
      `;
    }).join("");

    // Attach click listener for forensic trade modal
    tbody.querySelectorAll("tr[data-trade-id]").forEach(row => {
      row.addEventListener("click", () => {
        const tradeId = row.getAttribute("data-trade-id");
        openForensicModal(tradeId);
      });
    });

  } catch (err) {
    console.error("loadTradesTable error:", err);
  }
}

async function loadEdgeHealth() {
  const panel = document.getElementById("edge-health-panel");
  if (!panel) return;

  try {
    const res = await fetch(`/api/analytics/edge-health?account=${state.currentAccount}`);
    if (!res.ok) return;
    const data = await res.json();

    // Account tag and Sample Tag
    const tagEl = document.getElementById("edge-account-tag");
    if (tagEl) tagEl.textContent = `Account: ${data.account_id} (${formatINR(data.starting_capital)})`;

    const sampleEl = document.getElementById("edge-sample-tag");
    if (sampleEl) sampleEl.textContent = `Sample: ${data.sample_size} / ${data.sample_threshold} trades`;

    // Status Badge & Explanation
    const badgeEl = document.getElementById("edge-health-badge");
    if (badgeEl) {
      badgeEl.textContent = data.strategy_health_status;
      badgeEl.className = "status-badge";
      if (data.strategy_health_status === "INSUFFICIENT SAMPLE") badgeEl.classList.add("insufficient");
      else if (data.strategy_health_status === "NEGATIVE NET EDGE") badgeEl.classList.add("negative");
      else if (data.strategy_health_status === "EDGE UNDER OBSERVATION") badgeEl.classList.add("observation");
      else if (data.strategy_health_status === "POSITIVE HISTORICAL EDGE") badgeEl.classList.add("positive");
    }

    const expEl = document.getElementById("edge-explanation-text");
    if (expEl) expEl.textContent = data.status_explanation;

    // Stat Boxes
    const rPnlEl = document.getElementById("edge-realized-pnl");
    if (rPnlEl) {
      rPnlEl.textContent = formatINR(data.realized_net_pnl);
      rPnlEl.className = `edge-stat-value font-mono ${data.realized_net_pnl >= 0 ? "positive" : "negative"}`;
    }

    const gPnlEl = document.getElementById("edge-gross-pnl");
    if (gPnlEl) {
      gPnlEl.textContent = formatINR(data.gross_trading_pnl);
      gPnlEl.className = `edge-stat-value font-mono ${data.gross_trading_pnl >= 0 ? "positive" : "negative"}`;
    }

    const chgEl = document.getElementById("edge-total-charges");
    if (chgEl) chgEl.textContent = formatINR(data.total_transaction_charges);

    const slipEl = document.getElementById("edge-slippage-drag");
    if (slipEl) slipEl.textContent = formatINR(data.execution_slippage_attribution);

    const wrEl = document.getElementById("edge-win-rate");
    if (wrEl) wrEl.textContent = `${data.win_rate_pct.toFixed(1)}%`;

    const wlEl = document.getElementById("edge-win-loss-count");
    if (wlEl) wlEl.textContent = `${data.win_count} W / ${data.loss_count} L`;

    const expValEl = document.getElementById("edge-expectancy");
    if (expValEl) {
      expValEl.textContent = formatINR(data.net_expectancy);
      expValEl.className = `edge-stat-value font-mono ${data.net_expectancy >= 0 ? "positive" : "negative"}`;
    }

    const pfEl = document.getElementById("edge-profit-factor");
    if (pfEl) pfEl.textContent = data.profit_factor.toFixed(2);

    const ddEl = document.getElementById("edge-max-dd");
    if (ddEl) ddEl.textContent = `${data.max_drawdown_pct.toFixed(2)}%`;

    // Decomposition Bar
    const decGross = document.getElementById("decomp-gross");
    if (decGross) decGross.textContent = formatINR(data.gross_trading_pnl);

    const decCharges = document.getElementById("decomp-charges");
    if (decCharges) decCharges.textContent = formatINR(data.total_transaction_charges);

    const decNet = document.getElementById("decomp-net");
    if (decNet) {
      decNet.textContent = formatINR(data.realized_net_pnl);
      decNet.className = data.realized_net_pnl >= 0 ? "positive" : "negative text-coral";
    }

    // Performance Analytics Tab sync (pane-performance)
    const statExp = document.getElementById("stat-expectancy");
    if (statExp) {
      statExp.textContent = data.total_closed_trades > 0 ? formatINR(data.net_expectancy) : "--";
      statExp.className = `box-val font-mono ${data.net_expectancy >= 0 ? "positive" : "negative"}`;
    }
    const statPf = document.getElementById("stat-profit-factor");
    if (statPf) statPf.textContent = data.total_closed_trades > 0 ? data.profit_factor.toFixed(2) : "--";

    const statWr = document.getElementById("stat-win-rate");
    if (statWr) statWr.textContent = data.total_closed_trades > 0 ? `${data.win_rate_pct.toFixed(1)}%` : "--";

    const statCd = document.getElementById("stat-cost-drag");
    if (statCd) statCd.textContent = data.total_closed_trades > 0 ? `${data.cost_drag_pct.toFixed(1)}%` : "--";

    const statDd = document.getElementById("stat-max-dd");
    if (statDd) statDd.textContent = data.total_closed_trades > 0 ? `${data.max_drawdown_pct.toFixed(2)}%` : "--";

  } catch (err) {
    console.error("loadEdgeHealth error:", err);
  }
}

async function openForensicModal(tradeId) {
  const modal = document.getElementById("forensic-modal");
  if (!modal) return;

  try {
    const res = await fetch(`/api/trades/${tradeId}`);
    if (!res.ok) {
      alert(`Trade '${tradeId}' forensic record not found.`);
      return;
    }
    const data = await res.json();
    const s = data.trade_summary;
    const snap = data.decision_snapshot;
    const exec = data.execution_forensics;
    const fee = data.fee_breakdown;
    const acc = data.accounting;

    // Header Info
    document.getElementById("modal-trade-id").textContent = s.trade_id;
    document.getElementById("modal-trade-side").textContent = s.direction;
    document.getElementById("modal-trade-account").textContent = s.account_id;
    document.getElementById("modal-trade-status").textContent = s.trade_status;
    document.getElementById("modal-trade-symbol").textContent = `${s.symbol} // CASH`;
    document.getElementById("modal-strategy-meta").textContent = `Strategy: ${s.strategy} ${s.strategy_version} \u2022 Exit Reason: ${s.exit_reason}`;

    // Section A: Summary & P&L
    document.getElementById("modal-fill-price").textContent = `₹${s.entry_price.toFixed(2)}`;
    document.getElementById("modal-requested-qty").textContent = `Qty: ${s.quantity} Filled`;
    document.getElementById("modal-exit-price").textContent = `₹${s.exit_price.toFixed(2)}`;
    document.getElementById("modal-exit-time").textContent = `Closed: ${s.exit_timestamp ? s.exit_timestamp.split("T")[1]?.slice(0, 8) : "--"}`;

    const grossEl = document.getElementById("modal-gross-pnl");
    grossEl.textContent = `₹${s.gross_pnl.toFixed(2)}`;
    grossEl.className = `cell-val font-mono ${s.gross_pnl >= 0 ? "positive text-emerald" : "negative text-coral"}`;

    const netEl = document.getElementById("modal-net-pnl");
    netEl.textContent = `₹${s.net_pnl.toFixed(2)}`;
    netEl.className = `cell-val font-mono ${s.net_pnl >= 0 ? "positive text-emerald" : "negative text-coral"}`;
    document.getElementById("modal-loss-tag").textContent = `Attribution: ${s.loss_tag}`;

    // Section B: Original Decision Snapshot
    const formatOrUnavail = (val, prefix = "", suffix = "") => {
      if (val === undefined || val === null || val === "Unavailable") return "Unavailable";
      return `${prefix}${val}${suffix}`;
    };

    document.getElementById("modal-snap-obi").textContent = formatOrUnavail(snap.obi, snap.obi > 0 ? "+" : "");
    document.getElementById("modal-snap-rvol").textContent = formatOrUnavail(snap.rvol, "", "x");
    document.getElementById("modal-snap-microprice").textContent = formatOrUnavail(snap.microprice, "₹");
    document.getElementById("modal-snap-vwap").textContent = formatOrUnavail(snap.vwap_deviation, "", "%");
    document.getElementById("modal-snap-atr").textContent = formatOrUnavail(snap.atr, "₹");
    document.getElementById("modal-snap-spread").textContent = formatOrUnavail(snap.spread, "", "%");
    document.getElementById("modal-snap-win-prob").textContent = typeof snap.win_probability === "number" ? `${(snap.win_probability * 100).toFixed(0)}%` : formatOrUnavail(snap.win_probability);
    document.getElementById("modal-snap-net-ev").textContent = formatOrUnavail(snap.net_ev, "+", "%");
    document.getElementById("modal-snap-ev-hurdle").textContent = `Hurdle: ${formatOrUnavail(snap.ev_hurdle, "", "%")}`;
    document.getElementById("modal-snap-decision").textContent = snap.decision || "ENTER";
    document.getElementById("modal-snap-reason").textContent = snap.decision_reason || "--";

    // Section C: Execution Forensics
    document.getElementById("modal-exec-market-ts").textContent = exec.market_data_ts ? exec.market_data_ts.split("T")[1]?.slice(0, 8) || exec.market_data_ts : "Unavailable";
    document.getElementById("modal-exec-sim-ts").textContent = exec.simulated_execution_ts ? exec.simulated_execution_ts.split("T")[1]?.slice(0, 8) || exec.simulated_execution_ts : "Unavailable";
    document.getElementById("modal-exec-latency").textContent = `Latency: ${exec.configured_latency_ms} ms`;
    document.getElementById("modal-exec-vwap").textContent = `₹${(exec.vwap_fill_price || s.entry_price).toFixed(2)}`;
    document.getElementById("modal-exec-slippage").textContent = `₹${(exec.slippage_amount || 0).toFixed(4)}`;
    document.getElementById("modal-exec-slippage-ticks").textContent = `${exec.slippage_ticks} Tick slippage applied`;

    // Consumed levels table
    const levelsTbody = document.getElementById("modal-levels-tbody");
    if (exec.levels_consumed && exec.levels_consumed.length > 0) {
      levelsTbody.innerHTML = exec.levels_consumed.map(lvl => `
        <tr>
          <td>Level ${lvl.level}</td>
          <td>₹${lvl.price.toFixed(2)}</td>
          <td class="text-right">${lvl.quantity}</td>
        </tr>
      `).join("");
    } else {
      levelsTbody.innerHTML = `<tr><td colspan="3" class="text-muted">Single-level market fill (${s.quantity} shares @ ₹${s.entry_price.toFixed(2)})</td></tr>`;
    }

    // Section D: Fee Breakdown
    document.getElementById("modal-fee-schedule").textContent = `${fee.schedule_id} (Eff: ${fee.effective_date})`;
    document.getElementById("fee-turnover").textContent = `₹${(fee.turnover || 0).toFixed(2)}`;
    document.getElementById("fee-brokerage").textContent = typeof fee.brokerage === "number" ? `₹${fee.brokerage.toFixed(2)}` : fee.brokerage;
    document.getElementById("fee-stt").textContent = typeof fee.stt === "number" ? `₹${fee.stt.toFixed(2)}` : fee.stt;
    document.getElementById("fee-exchange").textContent = typeof fee.exchange_txn === "number" ? `₹${fee.exchange_txn.toFixed(2)}` : fee.exchange_txn;
    document.getElementById("fee-sebi").textContent = typeof fee.sebi === "number" ? `₹${fee.sebi.toFixed(4)}` : fee.sebi;
    document.getElementById("fee-gst").textContent = typeof fee.gst === "number" ? `₹${fee.gst.toFixed(2)}` : fee.gst;
    document.getElementById("fee-stamp").textContent = typeof fee.stamp_duty === "number" ? `₹${fee.stamp_duty.toFixed(2)}` : fee.stamp_duty;
    document.getElementById("fee-total").textContent = `₹${(fee.total_charges || 0).toFixed(2)}`;

    // Section E: Final Reconciliation
    document.getElementById("recon-gross").textContent = `₹${acc.gross_pnl.toFixed(2)}`;
    document.getElementById("recon-charges").textContent = `\u2212₹${acc.applicable_charges.toFixed(2)}`;
    const reconNetEl = document.getElementById("recon-net");
    reconNetEl.textContent = `₹${acc.net_pnl.toFixed(2)}`;
    reconNetEl.className = acc.net_pnl >= 0 ? "positive text-emerald" : "negative text-coral";
    document.getElementById("recon-slippage").textContent = `₹${acc.execution_slippage_attribution.toFixed(2)}`;

    // Section F: Audit Timeline
    const timelineEl = document.getElementById("modal-audit-timeline");
    if (data.audit_timeline && data.audit_timeline.length > 0) {
      timelineEl.innerHTML = data.audit_timeline.map(ev => {
        const evTs = ev.timestamp ? ev.timestamp.split("T")[1]?.slice(0, 8) || ev.timestamp : "--";
        return `
          <div class="timeline-item font-mono">
            <span class="timeline-seq">${ev.seq}</span>
            <div class="timeline-content">
              <div>
                <span class="timeline-event-name">${ev.event_name}</span>
                <span class="timeline-ts">${evTs} UTC</span>
              </div>
              <div class="timeline-desc">${ev.description}</div>
            </div>
          </div>
        `;
      }).join("");
    } else {
      timelineEl.innerHTML = `<div class="timeline-empty">No intermediate audit events recorded for this trade.</div>`;
    }

    modal.style.display = "flex";

  } catch (err) {
    console.error("openForensicModal error:", err);
  }
}

function setupForensicModalListeners() {
  const modal = document.getElementById("forensic-modal");
  const closeBtn = document.getElementById("forensic-modal-close");
  const dismissBtn = document.getElementById("forensic-modal-dismiss-btn");

  if (closeBtn) closeBtn.addEventListener("click", () => modal.style.display = "none");
  if (dismissBtn) dismissBtn.addEventListener("click", () => modal.style.display = "none");

  // Close when clicking modal backdrop
  if (modal) {
    modal.addEventListener("click", (e) => {
      if (e.target === modal) modal.style.display = "none";
    });
  }
}

async function fetchAndRenderReadiness() {
  const grid = document.getElementById("readiness-checks-grid");
  const badge = document.getElementById("readiness-status-badge");
  const summary = document.getElementById("readiness-summary-text");
  if (!grid) return;

  try {
    const res = await fetch("/api/readiness");
    const data = await res.json();
    if (badge) {
      badge.textContent = data.overall_status;
      badge.style.color = data.ready ? "#00B386" : "#EB5B3C";
    }
    if (summary) {
      summary.textContent = `${data.passed_checks}/${data.total_checks} sub-systems passed. Target: ${data.market_open_target}. Evaluated: ${new Date(data.evaluated_at).toLocaleTimeString()}`;
    }

    grid.innerHTML = Object.entries(data.checks).map(([name, check]) => {
      const isPass = check.status === "PASS";
      const color = isPass ? "#00D09C" : "#EB5B3C";
      const bg = isPass ? "rgba(0, 208, 156, 0.08)" : "rgba(235, 91, 60, 0.08)";
      return `
        <div style="background: ${bg}; border: 1px solid ${color}33; border-radius: 6px; padding: 10px; font-size: 12px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <span style="font-weight: 600; color: var(--text-primary);">${name}</span>
            <span style="font-weight: 700; color: ${color}; font-size: 11px; padding: 2px 6px; border-radius: 4px; background: ${color}22;">${check.status}</span>
          </div>
          <div style="color: var(--text-muted); font-size: 11px; line-height: 1.3;">${check.detail}</div>
        </div>
      `;
    }).join("");
  } catch (err) {
    if (summary) summary.textContent = `Diagnostic check failed: ${err.message}`;
  }
}

function setupReadinessDiagnostics() {
  const btn = document.getElementById("btn-run-readiness");
  if (btn) {
    btn.addEventListener("click", () => fetchAndRenderReadiness());
  }
  fetchAndRenderReadiness();
}

// 08:30 – 09:10 AM Pre-Market Intelligence Loader
async function loadPreMarketReport() {
  const tbody = document.getElementById("premarket-tbody");
  if (!tbody) return;

  try {
    const res = await fetch(`/api/premarket/report?account=${state.currentAccount}`);
    if (res.status === 503) {
      const errData = await res.json().catch(() => ({}));
      tbody.innerHTML = `<tr><td colspan="11" style="text-align: center; color: var(--text-muted); padding: 24px;">
        <div style="font-weight: 600; color: var(--text-secondary); margin-bottom: 6px;">PRE-MARKET AUCTION FEED UNAVAILABLE</div>
        <div style="font-size: 12px; color: var(--text-muted);">${errData.detail || "Live 09:00–09:08 pre-open auction order book is not provided by broker feed adapter. Synthetic test report available via ?demo=true."}</div>
      </td></tr>`;
      return;
    }
    if (!res.ok) return;
    const data = await res.json();

    // Update Macro & Funnel Header
    const biasEl = document.getElementById("pm-bias-val");
    if (biasEl) {
      const sign = data.nifty_indicative_change_pct >= 0 ? "+" : "";
      biasEl.textContent = `${data.market_bias} (${sign}${data.nifty_indicative_change_pct.toFixed(2)}%)`;
      biasEl.className = data.nifty_indicative_change_pct >= 0 ? "macro-val positive font-mono" : "macro-val negative font-mono";
    }

    const vixEl = document.getElementById("pm-vix-val");
    if (vixEl) vixEl.textContent = data.india_vix.toFixed(2);

    const stratEl = document.getElementById("pm-strategy-val");
    if (stratEl) stratEl.textContent = data.recommended_strategy;

    const scannedEl = document.getElementById("pm-scanned-count");
    if (scannedEl) scannedEl.textContent = data.total_universe_scanned.toLocaleString();

    const tradableEl = document.getElementById("pm-tradable-count");
    if (tradableEl) tradableEl.textContent = data.passed_tradability.toLocaleString();

    const affordableEl = document.getElementById("pm-affordable-count");
    if (affordableEl) affordableEl.textContent = data.passed_affordability.toLocaleString();

    const focusCountEl = document.getElementById("pm-focus-count");
    if (focusCountEl) focusCountEl.textContent = data.focus_candidates ? data.focus_candidates.length : 0;

    const acctLabel = document.getElementById("pm-account-label");
    if (acctLabel) acctLabel.textContent = data.account_id;

    // Render Focus Candidates
    if (!data.focus_candidates || data.focus_candidates.length === 0) {
      tbody.innerHTML = `<tr><td colspan="11" style="text-align: center; color: var(--text-muted); padding: 18px;">No setups passed criteria for ${data.account_id} today.</td></tr>`;
      return;
    }

    tbody.innerHTML = data.focus_candidates.map((c) => {
      const rankBadge = c.rank === 1 ? `<span class="premarket-rank-badge premarket-rank-1">#1</span>` : `<span class="premarket-rank-badge">#${c.rank}</span>`;
      const gapSign = c.gap_pct >= 0 ? "+" : "";
      const gapClass = c.gap_pct >= 0 ? "positive" : "negative";
      const evCell = c.estimated_ev_pct !== null && c.estimated_ev_pct !== undefined
        ? `+${c.estimated_ev_pct.toFixed(2)}%`
        : '<span class="badge-neutral" title="Uncalibrated model">UNAVAILABLE</span>';

      return `
        <tr>
          <td>${rankBadge}</td>
          <td>
            <strong>${c.symbol}</strong>
            <div style="font-size: 11px; color: var(--text-muted);">${c.sector}</div>
          </td>
          <td class="font-mono">₹${c.discovered_price.toFixed(2)}</td>
          <td class="font-mono ${gapClass}">${gapSign}${c.gap_pct.toFixed(2)}%</td>
          <td class="font-mono">₹${c.atr_14.toFixed(2)} (${c.atr_pct.toFixed(1)}%)</td>
          <td class="font-mono text-brand font-bold">₹${c.planned_entry.toFixed(2)}</td>
          <td class="font-mono negative">₹${c.planned_stop.toFixed(2)}</td>
          <td class="font-mono positive">₹${c.planned_target.toFixed(2)}</td>
          <td class="font-mono">${c.max_affordable_shares} sh</td>
          <td class="font-mono positive font-bold">${evCell}</td>
          <td><span class="reason-tag">${c.selection_reason}</span></td>
        </tr>
      `;
    }).join("");

  } catch (err) {
    console.error("Failed to load premarket report:", err);
  }
}

// App Initialization
document.addEventListener("DOMContentLoaded", () => {
  setupTabs();
  setupSearchAndFilters();
  setupKillSwitch();
  setupForensicModalListeners();
  setupReadinessDiagnostics();

  const initialStock = state.stocks[0];
  updateDepthMatrix(initialStock);
  renderScannerTable();

  dom.accountSelect.addEventListener("change", (e) => {
    state.currentAccount = e.target.value;
    updateHeaderMetrics();
    refreshScanner();
    refreshTradesAndEdgeHealth();
    loadPreMarketReport();
  });

  loadAccounts();
  loadPreMarketReport();
  connectWebSocket();
  startSimulation();
  refreshTradesAndEdgeHealth();
});

