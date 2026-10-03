/**
 * Paper Desk Vanilla ES Module Application
 * High-performance UI updates, WebSocket streaming, and state store.
 */

// Application State Store
const state = {
  currentAccount: "real5k",
  accounts: {},
  systemHalted: false,
  feedMode: "sim",
  wsConnected: false,
};

// DOM Element References
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
  tabButtons: document.querySelectorAll(".nav-tab"),
  tabPanes: document.querySelectorAll(".tab-pane"),
};

// Format currency in Indian Rupees (₹)
function formatINR(val) {
  if (typeof val !== "number" || isNaN(val)) return "₹0.00";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(val);
}

// Format percentages
function formatPct(val) {
  if (typeof val !== "number" || isNaN(val)) return "0.00%";
  const prefix = val > 0 ? "+" : "";
  return `${prefix}${val.toFixed(2)}%`;
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

// 3. WebSocket Telemetry Stream with Auto-Reconnect & Heartbeat
let ws = null;
let reconnectTimer = null;
let heartbeatInterval = null;

function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    state.wsConnected = true;
    console.log("WebSocket connected to Paper Desk live telemetry");
    if (reconnectTimer) clearTimeout(reconnectTimer);

    // Heartbeat ping every 10s
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
    dom.feedPill.className = "feed-status-pill stale";
    dom.headerClock.textContent = "--:--:--";
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
    dom.feedPill.className = "feed-status-pill stale";
  } else if (msg.feed === "kite") {
    dom.feedText.textContent = "Live Kite";
    dom.feedPill.className = "feed-status-pill kite";
  } else if (msg.feed === "replay") {
    dom.feedText.textContent = "Replay";
    dom.feedPill.className = "feed-status-pill replay";
  } else {
    dom.feedText.textContent = "Simulated";
    dom.feedPill.className = "feed-status-pill sim";
  }
}

// 4. Kill Switch Modal & API Call
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
      dom.killBtn.style.backgroundColor = "var(--bg-subtle)";
      dom.killBtn.style.color = "var(--text-secondary)";
      dom.killBtn.style.borderColor = "var(--border-subtle)";
    } catch (err) {
      console.error("Failed to execute halt:", err);
    }
  });
}

// 5. Theme Switcher
function setupTheme() {
  const savedTheme = localStorage.getItem("paperdesk_theme") || "dark";
  document.documentElement.setAttribute("data-theme", savedTheme);

  dom.themeToggleBtn.addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("paperdesk_theme", next);
  });
}

// 6. Settings Interactions (Feed Mode, Pessimistic Toggle)
function setupSettings() {
  const modeButtons = document.querySelectorAll(".btn-toggle");
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

// Initialization on DOMContentLoaded
document.addEventListener("DOMContentLoaded", () => {
  setupTabs();
  setupKillSwitch();
  setupTheme();
  setupSettings();

  dom.accountSelect.addEventListener("change", (e) => {
    state.currentAccount = e.target.value;
    updateHeaderMetrics();
  });

  loadAccounts();
  connectWebSocket();
});
