/**
 * Paper Desk Vanilla ES Module Application
 * Groww-inspired UI with live sparklines, instant search, and WebSocket telemetry.
 */

// Initial Liquid Core Universe (Mirrors Groww All Stocks)
const defaultStocks = [
  { symbol: "RELIANCE", name: "Reliance Industries", price: 2950.40, change: 1.25, score: 2.15, win_prob: 64, ev: 0.28, rvol: 2.4, obi: 0.42, action: "Enter", sparkline: [2920, 2928, 2924, 2935, 2940, 2938, 2950.4] },
  { symbol: "BHARTIARTL", name: "Bharti Airtel", price: 1741.10, change: 0.85, score: 1.80, win_prob: 59, ev: 0.22, rvol: 1.9, obi: 0.28, action: "Enter", sparkline: [1725, 1730, 1728, 1736, 1734, 1741.1] },
  { symbol: "TATAMOTORS", name: "Tata Motors", price: 925.30, change: 1.75, score: 1.65, win_prob: 58, ev: 0.19, rvol: 2.8, obi: 0.35, action: "Enter", sparkline: [910, 915, 912, 920, 918, 922, 925.3] },
  { symbol: "SBIN", name: "State Bank of India", price: 812.50, change: 1.10, score: 1.40, win_prob: 56, ev: 0.17, rvol: 2.1, obi: 0.20, action: "Enter", sparkline: [802, 808, 805, 810, 809, 812.5] },
  { symbol: "ICICIBANK", name: "ICICI Bank", price: 1310.60, change: 0.60, score: 1.15, win_prob: 54, ev: 0.15, rvol: 1.7, obi: 0.15, action: "Watch", sparkline: [1300, 1305, 1302, 1308, 1310.6] },
  { symbol: "HDFCBANK", name: "HDFC Bank", price: 1682.20, change: -0.40, score: 0.45, win_prob: 51, ev: 0.08, rvol: 1.3, obi: -0.05, action: "Watch", sparkline: [1695, 1690, 1692, 1685, 1682.2] },
  { symbol: "TATASTEEL", name: "Tata Steel", price: 165.20, change: 0.90, score: 0.95, win_prob: 53, ev: 0.14, rvol: 1.8, obi: 0.18, action: "Watch", sparkline: [163, 164.5, 163.8, 165, 165.2] },
  { symbol: "BEL", name: "Bharat Electronics", price: 295.60, change: 2.10, score: 1.90, win_prob: 61, ev: 0.24, rvol: 3.2, obi: 0.45, action: "Enter", sparkline: [289, 291, 290, 294, 293, 295.6] },
  { symbol: "INFY", name: "Infosys", price: 1895.00, change: 0.45, score: 0.60, win_prob: 52, ev: 0.11, rvol: 1.4, obi: 0.08, action: "Watch", sparkline: [1885, 1890, 1888, 1892, 1895] },
  { symbol: "ITC", name: "ITC Ltd", price: 505.40, change: -0.15, score: -0.20, win_prob: 48, ev: 0.02, rvol: 0.9, obi: -0.12, action: "Skip", sparkline: [508, 506, 507, 505.4] },
];

// Application State Store
const state = {
  currentAccount: "real5k",
  accounts: {},
  systemHalted: false,
  feedMode: "sim",
  wsConnected: false,
  stocks: [...defaultStocks],
  searchQuery: "",
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
  stockCountDisplay: document.getElementById("stock-count-display"),
  globalSearch: document.getElementById("global-search"),
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

// Generate SVG Sparkline (Groww style green/coral path)
function renderSparklineSVG(points, isPositive = true) {
  if (!points || points.length < 2) return "";
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const w = 100;
  const h = 26;

  const coords = points.map((p, i) => {
    const x = Math.round((i / (points.length - 1)) * w);
    const y = Math.round(h - ((p - min) / range) * (h - 6) - 3);
    return `${x},${y}`;
  }).join(" ");

  const color = isPositive ? "#00D09C" : "#EB5B3C";
  return `
    <svg class="sparkline-svg" viewBox="0 0 ${w} ${h}">
      <polyline fill="none" stroke="${color}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" points="${coords}" />
    </svg>
  `;
}

// Render Scanner Table (Groww All Stocks Format)
function renderScannerTable() {
  if (!dom.scannerTbody) return;

  const query = state.searchQuery.toLowerCase().trim();
  const filtered = state.stocks.filter(s =>
    s.symbol.toLowerCase().includes(query) || s.name.toLowerCase().includes(query)
  );

  dom.stockCountDisplay.textContent = `${filtered.length} Stocks`;

  if (filtered.length === 0) {
    dom.scannerTbody.innerHTML = `
      <tr>
        <td colspan="8" class="empty-state-cell">
          <div class="empty-box">
            <h3 class="empty-title">No stocks match "${state.searchQuery}"</h3>
            <p class="empty-text">Try searching for other liquid NSE EQ symbols.</p>
          </div>
        </td>
      </tr>
    `;
    return;
  }

  dom.scannerTbody.innerHTML = filtered.map(s => {
    const isPos = s.change >= 0;
    const changeClass = isPos ? "pos" : "neg";
    const changeText = `${isPos ? "+" : ""}${s.change.toFixed(2)}%`;

    // Center balanced score bar (-3 to +3 mapped to 50% origin)
    const scoreVal = Math.max(-3, Math.min(3, s.score));
    const barWidthPct = Math.round((Math.abs(scoreVal) / 3.0) * 50);
    const barSide = scoreVal >= 0 ? "pos" : "neg";

    const actionClass = s.action.toLowerCase();

    return `
      <tr data-symbol="${s.symbol}">
        <td class="col-company">
          <div class="company-cell">
            <span class="company-name">${s.name}</span>
            <span class="company-sub">${s.symbol} &bull; EQ</span>
          </div>
        </td>
        <td class="col-chart text-center">
          ${renderSparklineSVG(s.sparkline, isPos)}
        </td>
        <td class="col-price text-right">
          <div class="price-cell">
            <span class="price-val font-mono">₹${s.price.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
            <span class="price-change ${changeClass} font-mono">${changeText}</span>
          </div>
        </td>
        <td class="col-score text-center">
          <div class="spectrum-bar-wrap" title="Score: ${s.score.toFixed(2)}">
            <div class="spectrum-origin"></div>
            <div class="spectrum-bar-fill ${barSide}" style="width: ${barWidthPct}%;"></div>
          </div>
        </td>
        <td class="col-metric text-right font-mono">${s.win_prob}%</td>
        <td class="col-metric text-right font-mono text-emerald">+${s.ev.toFixed(2)}%</td>
        <td class="col-metric text-right font-mono">${s.rvol.toFixed(1)}x</td>
        <td class="col-action text-center">
          <span class="chip-action ${actionClass}">${s.action}</span>
        </td>
      </tr>
    `;
  }).join("");
}

// 1. Tab Router
function setupTabs() {
  dom.tabButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const targetTab = btn.getAttribute("data-tab");
      dom.tabButtons.forEach(b => b.classList.remove("active"));
      dom.tabPanes.forEach(p => p.classList.remove("active"));

      btn.classList.add("active");
      const activePane = document.getElementById(`pane-${targetTab}`);
      if (activePane) activePane.classList.add("active");
    });
  });
}

// 2. Account Selector & Header Metrics Update
function updateHeaderMetrics() {
  const acct = state.accounts[state.currentAccount];
  if (!acct) return;

  dom.headerEquity.textContent = formatINR(acct.equity);
  dom.headerCash.textContent = formatINR(acct.cash);

  const pnlVal = acct.day_pnl || 0.0;
  const pnlPct = acct.day_pnl_pct || 0.0;
  dom.headerDayPnl.textContent = `${formatINR(pnlVal)} (${formatPct(pnlPct)})`;

  dom.headerDayPnl.classList.remove("positive", "negative", "neutral");
  if (pnlVal > 0) dom.headerDayPnl.classList.add("positive");
  else if (pnlVal < 0) dom.headerDayPnl.classList.add("negative");
  else dom.headerDayPnl.classList.add("neutral");
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

// 3. Search Filter Listener
function setupSearch() {
  if (!dom.globalSearch) return;

  dom.globalSearch.addEventListener("input", (e) => {
    state.searchQuery = e.target.value;
    renderScannerTable();
  });

  // ⌘K Keyboard Shortcut
  window.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      dom.globalSearch.focus();
      dom.globalSearch.select();
    }
  });
}

// 4. WebSocket Telemetry Stream with Heartbeat
let ws = null;
let reconnectTimer = null;
let heartbeatInterval = null;

function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    state.wsConnected = true;
    if (reconnectTimer) clearTimeout(reconnectTimer);

    if (heartbeatInterval) clearInterval(heartbeatInterval);
    heartbeatInterval = setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send("ping");
      }
    }, 10000);
  };

  ws.onmessage = (event) => {
    if (event.data === "pong") return;
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === "snapshot") {
        handleSnapshot(msg);
      }
    } catch (e) {
      console.error("Malformed WS message:", e);
    }
  };

  ws.onclose = () => {
    state.wsConnected = false;
    dom.feedText.textContent = "Feed Offline";
    dom.feedPill.className = "feed-badge stale";
    dom.headerClock.textContent = "--:--:-- IST";
    if (heartbeatInterval) clearInterval(heartbeatInterval);
    reconnectTimer = setTimeout(connectWebSocket, 2000);
  };

  ws.onerror = (err) => {
    console.error("WebSocket error:", err);
  };
}

function handleSnapshot(msg) {
  // Update Market Clock
  if (msg.clock) {
    dom.headerClock.textContent = `${msg.clock} IST`;
  }

  // Update Account Balances
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

  // Feed status badge
  if (msg.stale) {
    dom.feedText.textContent = "Feed Stale";
    dom.feedPill.className = "feed-badge stale";
  } else if (msg.feed === "kite") {
    dom.feedText.textContent = "Live Kite";
    dom.feedPill.className = "feed-badge kite";
  } else if (msg.feed === "replay") {
    dom.feedText.textContent = "Replay";
    dom.feedPill.className = "feed-badge replay";
  } else {
    dom.feedText.textContent = "Simulated";
    dom.feedPill.className = "feed-badge sim";
  }
}

// 5. Emergency Halt Modal
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
      const res = await fetch("/api/kill", { method: "POST" });
      const data = await res.json();
      dom.killBtn.textContent = "Engine Halted";
      dom.killBtn.style.backgroundColor = "var(--border-light)";
      dom.killBtn.style.color = "var(--text-muted)";
      dom.killBtn.style.borderColor = "var(--border-subtle)";
    } catch (err) {
      console.error("Failed to execute halt:", err);
    }
  });
}

// 6. Theme Switcher (Default Light matching Groww)
function setupTheme() {
  const savedTheme = localStorage.getItem("paperdesk_theme") || "light";
  document.documentElement.setAttribute("data-theme", savedTheme);

  dom.themeToggleBtn.addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme");
    const next = current === "light" ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("paperdesk_theme", next);
  });
}

// 7. Settings Feed Mode
function setupSettings() {
  const modeButtons = document.querySelectorAll(".pill-btn");
  modeButtons.forEach(btn => {
    btn.addEventListener("click", async () => {
      const mode = btn.getAttribute("data-mode");
      modeButtons.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");

      try {
        await fetch("/api/mode", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ feed: mode }),
        });
      } catch (e) {
        console.error("Failed to switch feed mode:", e);
      }
    });
  });
}

// App Initialization
document.addEventListener("DOMContentLoaded", () => {
  setupTabs();
  setupSearch();
  setupKillSwitch();
  setupTheme();
  setupSettings();
  renderScannerTable();

  dom.accountSelect.addEventListener("change", (e) => {
    state.currentAccount = e.target.value;
    updateHeaderMetrics();
  });

  loadAccounts();
  connectWebSocket();
});
