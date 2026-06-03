/**
 * LockNLog console — /api/v1/logs, /api/v1/dashboard, CEO: /api/v1/ceo/chat
 */
(function () {
  "use strict";

  // Surface JS errors in the UI (helps when charts don't render).
  window.addEventListener("error", (ev) => {
    try {
      const b = document.getElementById("error-banner");
      if (!b) return;
      const msg = ev && ev.message ? ev.message : "Unexpected error";
      b.textContent = "UI error: " + msg;
      b.classList.remove("hidden");
    } catch {
      // ignore
    }
  });

  const state = {
    role: (window.__LOCKNLOG_ROLE__ || "").toLowerCase(),
    logs: [],
    dashboard: null,
    dashboardError: null,
    sortKey: "timestamp",
    sortDir: -1,
    page: 1,
    pageSize: 40,
    filterText: "",
    filterSeverity: "",
    filterType: "",
    filterRisk: "",
    filterAsset: "",
    filterUser: "",
    filterStart: "",
    filterEnd: "",
    expanded: new Set(),
    chatHistory: [],
    ceoChatReady: false,
    ceoTabsWired: false,
    accessInfo: null,
    __chartRetry: null,
    __ceoLogDebugged: false,
  };

  const el = (id) => document.getElementById(id);

  function fmtNum(n) {
    if (n == null || Number.isNaN(n)) return "—";
    return typeof n === "number" ? n.toFixed(2) : String(n);
  }

  function fmtTs(iso) {
    if (!iso) return "—";
    try {
      const d = new Date(iso);
      return d.toLocaleString();
    } catch {
      return iso;
    }
  }

  function badgeClassLogType(t) {
    const x = (t || "").toLowerCase();
    if (x === "soc") return "badge-soc";
    if (x === "finance") return "badge-finance";
    if (x === "hr") return "badge-hr";
    return "";
  }

  function badgeClassSeverity(s) {
    const x = (s || "").toLowerCase();
    if (x === "low") return "badge-sev-low";
    if (x === "medium") return "badge-sev-medium";
    if (x === "high") return "badge-sev-high";
    if (x === "critical") return "badge-sev-critical";
    return "";
  }

  function badgeClassRisk(b) {
    const x = (b || "").toUpperCase();
    if (x === "LOW") return "badge-risk-low";
    if (x === "MEDIUM") return "badge-risk-medium";
    if (x === "HIGH") return "badge-risk-high";
    if (x === "CRITICAL") return "badge-risk-critical";
    return "";
  }

  async function fetchJson(url) {
    const res = await fetch(url, { credentials: "same-origin" });
    const text = await res.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = { raw: text };
    }
    if (!res.ok) {
      const err = new Error((data && data.error) || res.statusText || "Request failed");
      err.status = res.status;
      err.body = data;
      throw err;
    }
    return data;
  }

  async function fetchPostJson(url, body) {
    const res = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const text = await res.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = { raw: text };
    }
    if (!res.ok) {
      const err = new Error((data && data.error) || res.statusText || "Request failed");
      err.status = res.status;
      err.body = data;
      throw err;
    }
    return data;
  }

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  /** Minimal markdown: **bold** and newlines (safe after full escape). */
  function renderMdLite(text) {
    let s = escapeHtml(text || "");
    s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/\n/g, "<br>");
    return s;
  }

  function scrollChatToBottom() {
    const thread = el("chat-thread");
    if (thread) thread.scrollTop = thread.scrollHeight;
  }

  function appendChatBubble(role, content) {
    const thread = el("chat-thread");
    if (!thread) return;
    const div = document.createElement("div");
    div.className = `chat-bubble chat-bubble--${role}`;
    if (role === "assistant") {
      div.innerHTML = renderMdLite(content);
    } else {
      div.innerHTML = `<div class="chat-plain">${escapeHtml(content)}</div>`;
    }
    thread.appendChild(div);
    scrollChatToBottom();
  }

  function renderChatThreadFromHistory() {
    const thread = el("chat-thread");
    if (!thread) return;
    thread.innerHTML = "";
    state.chatHistory.forEach((m) => {
      appendChatBubble(m.role === "user" ? "user" : "assistant", m.content);
    });
  }

  async function bootstrapCeoChat() {
    if (state.role !== "ceo" || state.ceoChatReady) return;
    const thread = el("chat-thread");
    if (!thread) return;
    const status = el("chat-status");
    try {
      const data = await fetchJson("/api/v1/ceo/chat/bootstrap");
      state.chatHistory = [{ role: "assistant", content: data.message || "Hello." }];
      thread.innerHTML = "";
      appendChatBubble("assistant", state.chatHistory[0].content);
      state.ceoChatReady = true;
    } catch (e) {
      if (status) status.textContent = e.message || "Could not load assistant.";
    }
  }

  async function sendCeoChat() {
    const input = el("ceo-chat-input");
    const status = el("chat-status");
    const msg = (input && input.value.trim()) || "";
    if (!msg) return;
    if (status) status.textContent = "";
    appendChatBubble("user", msg);
    state.chatHistory.push({ role: "user", content: msg });
    if (input) input.value = "";

    const sendBtn = el("ceo-chat-send");
    if (sendBtn) sendBtn.disabled = true;
    try {
      const res = await fetchPostJson("/api/v1/ceo/chat", {
        message: msg,
        history: state.chatHistory.slice(0, -1),
      });
      const reply = res.reply || "(empty response)";
      state.chatHistory.push({ role: "assistant", content: reply });
      appendChatBubble("assistant", reply);
      if (res.sources && res.sources.length && status) {
        const ids = res.sources.map((s) => s.id).join(", ");
        status.textContent = `Sources: playbook ids ${ids}`;
      }
    } catch (e) {
      if (status) status.textContent = e.message || "Send failed.";
      appendChatBubble("assistant", `**Error:** ${e.message || "request failed"}`);
    } finally {
      if (sendBtn) sendBtn.disabled = false;
      if (input) input.focus();
    }
  }

  function clearCeoChat() {
    state.chatHistory = [];
    state.ceoChatReady = false;
    const thread = el("chat-thread");
    if (thread) thread.innerHTML = "";
    const status = el("chat-status");
    if (status) status.textContent = "";
    void bootstrapCeoChat();
  }

  function wireCeoChat() {
    if (state.role !== "ceo") return;
    const send = el("ceo-chat-send");
    const input = el("ceo-chat-input");
    const clr = el("ceo-chat-clear");
    if (send) send.addEventListener("click", () => void sendCeoChat());
    if (clr) clr.addEventListener("click", () => clearCeoChat());
    if (input) {
      input.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" && !ev.shiftKey) {
          ev.preventDefault();
          void sendCeoChat();
        }
      });
    }
    void bootstrapCeoChat();
  }

  function deriveViewType() {
    const ft = (state.filterType || "").toLowerCase();
    if (ft === "soc" || ft === "finance" || ft === "hr") return ft;
    // Default to role where possible; otherwise SOC view is the safest for admin-style explorers.
    if (state.role === "soc" || state.role === "finance" || state.role === "hr") return state.role;
    return "soc";
  }

  function normalizeStatusForSoc(status) {
    const s = (status || "").toLowerCase();
    if (s === "success" || s === "allowed" || s === "ok") return "allowed";
    if (s === "failed" || s === "denied" || s === "unauthorized") return "denied";
    return s || "—";
  }

  function financeAccessLabel(row) {
    const s = (row.status || "").toLowerCase();
    const flagged = !!(row.metadata && (row.metadata.flagged === true || row.metadata.flagged === "true" || row.metadata.flagged === 1));
    if (s === "unauthorized") return "unauthorized";
    if ((row.anomaly_score != null && Number(row.anomaly_score) >= 0.78) || flagged) return "unusual";
    return "normal";
  }

  function hrAccessLabel(row) {
    const s = (row.status || "").toLowerCase();
    const off = !!(row.metadata && row.metadata.off_hours);
    if (s === "unauthorized") return "unauthorized";
    if ((row.anomaly_score != null && Number(row.anomaly_score) >= 0.78) || off) return "unusual";
    return "normal";
  }

  function clearLogFilters() {
    state.filterText = "";
    state.filterSeverity = "";
    state.filterType = "";
    state.filterRisk = "";
    state.filterAsset = "";
    state.filterUser = "";
    state.filterStart = "";
    state.filterEnd = "";
    state.page = 1;
    const search = el("filter-search");
    const sev = el("filter-severity");
    const lt = el("filter-type");
    const as = el("filter-asset");
    const us = el("filter-user");
    const rk = el("filter-risk");
    const st = el("filter-start");
    const en = el("filter-end");
    if (search) search.value = "";
    if (sev) sev.value = "";
    if (lt) lt.value = "";
    if (as) as.value = "";
    if (us) us.value = "";
    if (rk) rk.value = "";
    if (st) st.value = "";
    if (en) en.value = "";
    renderTable();
  }

  function wireClearFilters() {
    const b = el("btn-clear-filters");
    if (b) b.addEventListener("click", () => clearLogFilters());
  }

  function renderOverviewStats(container, dashboard, role, logCount) {
    if (!container) return;
    if (!dashboard) {
      const n = logCount != null ? logCount : "—";
      container.innerHTML = `
        <div class="stat-grid">
          <div class="stat"><div class="stat-value">${n}</div><div class="stat-label">Logs in explorer</div></div>
        </div>
        <p style="margin:0.75rem 0 0;font-size:0.82rem;color:var(--muted)">Dashboard JSON is not available for this account. The table below still lists all logs allowed for your role.</p>`;
      return;
    }

    if (role === "ceo") {
      const s = dashboard.summary || {};
      const intel = dashboard.intelligence || {};
      const ft = (dashboard.ceo_charts && dashboard.ceo_charts.finance_totals) || {};
      const vol = ft.volume_sum != null ? ft.volume_sum : 0;
      const volStr =
        vol >= 1e6 ? (vol / 1e6).toFixed(2) + "M" : vol >= 1000 ? (vol / 1000).toFixed(1) + "k" : fmtNum(vol);
      container.innerHTML = `
        <p class="ceo-coverage-lead">Stream volume and recent-sample intelligence — complements momentum above.</p>
        <div class="stat-grid ceo-stat-grid--coverage">
          <div class="stat"><div class="stat-value">${s.soc_events ?? 0}</div><div class="stat-label">SOC events</div></div>
          <div class="stat"><div class="stat-value">${s.finance_events ?? 0}</div><div class="stat-label">Finance tx</div></div>
          <div class="stat"><div class="stat-value">${s.hr_events ?? 0}</div><div class="stat-label">HR</div></div>
          <div class="stat stat--neutral"><div class="stat-value">${fmtNum(intel.avg_risk_score)}</div><div class="stat-label">Avg risk (recent sample)</div></div>
          <div class="stat stat--neutral"><div class="stat-value">${fmtNum(intel.avg_anomaly_score)}</div><div class="stat-label">Avg anomaly (sample)</div></div>
        </div>
        <h4 class="ceo-mini-heading">Finance flow</h4>
        <div class="stat-grid ceo-stat-grid--coverage">
          <div class="stat"><div class="stat-value">${volStr}</div><div class="stat-label">Finance volume (sum)</div></div>
          <div class="stat"><div class="stat-value">${fmtNum(ft.avg_transaction)}</div><div class="stat-label">Avg tx amount</div></div>
          <div class="stat"><div class="stat-value">${ft.high_value_count ?? 0}</div><div class="stat-label">High-value (≥100k)</div></div>
        </div>
      `;
      return;
    }

    if (role === "observer") {
      const intel = dashboard.intelligence || {};
      container.innerHTML = `
        <div class="stat-grid">
          <div class="stat"><div class="stat-value">${fmtNum(intel.avg_risk_score)}</div><div class="stat-label">Avg risk (sample)</div></div>
          <div class="stat"><div class="stat-value">${fmtNum(intel.avg_anomaly_score)}</div><div class="stat-label">Avg anomaly</div></div>
        </div>
      `;
      return;
    }

    if (role === "soc") {
      const intel = dashboard.intelligence || {};
      container.innerHTML = `
        <div class="stat-grid">
          <div class="stat"><div class="stat-value">${dashboard.total_events ?? 0}</div><div class="stat-label">Total events</div></div>
          <div class="stat"><div class="stat-value">${fmtNum(intel.avg_risk_score)}</div><div class="stat-label">Avg risk</div></div>
          <div class="stat"><div class="stat-value">${fmtNum(intel.avg_anomaly_score)}</div><div class="stat-label">Avg anomaly</div></div>
        </div>
      `;
      return;
    }

    if (role === "finance") {
      const intel = dashboard.intelligence || {};
      const sf = dashboard.success_vs_failed || {};
      container.innerHTML = `
        <div class="stat-grid">
          <div class="stat"><div class="stat-value">${dashboard.total_transactions ?? 0}</div><div class="stat-label">Transactions</div></div>
          <div class="stat"><div class="stat-value">${sf.success ?? 0}</div><div class="stat-label">Success</div></div>
          <div class="stat"><div class="stat-value">${sf.failed ?? 0}</div><div class="stat-label">Non-success</div></div>
          <div class="stat"><div class="stat-value">${fmtNum(intel.avg_risk_score)}</div><div class="stat-label">Avg risk</div></div>
        </div>
      `;
      return;
    }

    if (role === "hr") {
      const intel = dashboard.intelligence || {};
      container.innerHTML = `
        <div class="stat-grid">
          <div class="stat"><div class="stat-value">${dashboard.activity_count ?? 0}</div><div class="stat-label">Activities</div></div>
          <div class="stat"><div class="stat-value">${dashboard.off_hour_activity ?? 0}</div><div class="stat-label">Off-hours</div></div>
          <div class="stat"><div class="stat-value">${fmtNum(intel.avg_risk_score)}</div><div class="stat-label">Avg risk</div></div>
        </div>
      `;
      return;
    }

    container.innerHTML = `
      <div class="stat-grid">
        <div class="stat"><div class="stat-value">${logCount ?? 0}</div><div class="stat-label">Logs visible</div></div>
      </div>
      <p style="margin:0.75rem 0 0;font-size:0.82rem;color:var(--muted)">Use the explorer below for details.</p>`;
  }

  function destroyCeoCharts() {
    [
      "__ceoChartFinFlow",
      "__ceoChartFinStatus",
      "__ceoChartDomain",
      "__ceoChartRisk",
      "__ceoChartDeptBar",
      "__ceoChartRiskTrend",
      "__ceoChartFinExpose",
      "__ceoChartAssetsBar",
      "__ceoChartTopUsers",
      "__ceoChartRiskHeatmap",
      "__socTimeline",
      "__socSpike",
      "__socHeatmap",
      "__socRiskTrend",
      "__socEventDist",
      "__socSeverityBar",
      "__finVolume",
      "__finStatusBar",
      "__finHighValueBar",
      "__finViolationsBar",
      "__finExposureTrend",
      "__hrActivityTrend",
      "__hrActivityDist",
      "__hrActivityOverTime",
      "__hrTopUsersBar",
      "__hrOffHoursBar",
      "__hrViolationsBar",
      "__hrSensitivePie",
    ].forEach((k) => {
      if (window[k]) {
        if (typeof window[k].destroy === "function") window[k].destroy();
        window[k] = null;
      }
    });
  }

  const COLORS = {
    low: "#22c55e",
    medium: "#facc15",
    high: "#f97316",
    critical: "#ef4444",
    anomaly: "#a855f7",
    purple: "#7c3aed",
    blue: "#3b82f6",
    grid: "#2a3544",
    tick: "#8b9aad",
  };

  function setupChartDefaults() {
    if (typeof Chart === "undefined" || !Chart) return;
    const d = Chart.defaults;
    d.color = COLORS.tick;
    d.borderColor = "rgba(139,154,173,0.12)";
    d.animation = { duration: 650, easing: "easeOutQuart" };

    d.plugins = d.plugins || {};
    d.plugins.legend = d.plugins.legend || {};
    d.plugins.legend.labels = d.plugins.legend.labels || {};
    d.plugins.legend.labels.color = COLORS.tick;

    d.plugins.tooltip = d.plugins.tooltip || {};
    d.plugins.tooltip.backgroundColor = "rgba(11,11,15,0.96)";
    d.plugins.tooltip.borderColor = "rgba(124,58,237,0.45)";
    d.plugins.tooltip.borderWidth = 1;
    d.plugins.tooltip.cornerRadius = 10;
    d.plugins.tooltip.padding = 10;
    d.plugins.tooltip.displayColors = true;
    d.plugins.tooltip.callbacks = {
      label: (ctx) => {
        const label = ctx.dataset && ctx.dataset.label ? ctx.dataset.label : "value";
        return `${label}: ${ctx.formattedValue}`;
      },
      afterLabel: (ctx) => {
        const raw = ctx.raw || {};
        return raw.timestamp ? `timestamp: ${raw.timestamp}` : "";
      },
    };

    d.scales = d.scales || {};
    d.scales.category = d.scales.category || {};
    d.scales.category.grid = d.scales.category.grid || {};
    d.scales.category.grid.color = "rgba(139,154,173,0.09)";
    d.scales.category.ticks = d.scales.category.ticks || {};
    d.scales.category.ticks.autoSkip = true;
    d.scales.linear = d.scales.linear || {};
    d.scales.linear.grid = d.scales.linear.grid || {};
    d.scales.linear.grid.color = "rgba(139,154,173,0.09)";
    d.scales.linear.ticks = d.scales.linear.ticks || {};
    d.scales.linear.ticks.autoSkip = true;

    d.datasets = d.datasets || {};
    d.datasets.line = d.datasets.line || {};
    d.datasets.line.tension = 0.4;
    d.datasets.line.fill = true;
    d.datasets.line.pointRadius = 2;
    d.datasets.line.pointHoverRadius = 5;
    d.datasets.line.pointHitRadius = 12;
    d.datasets.line.borderWidth = 2;
    d.datasets.bar = d.datasets.bar || {};
    d.datasets.bar.borderRadius = 8;
    d.datasets.bar.borderSkipped = false;
    d.datasets.bar.hoverBorderWidth = 1;
    d.datasets.bar.hoverBorderColor = "rgba(124,58,237,0.9)";
    d.datasets.doughnut = d.datasets.doughnut || {};
    d.datasets.doughnut.cutout = "68%";
    d.datasets.doughnut.hoverOffset = 8;
    d.datasets.pie = d.datasets.pie || {};
    d.datasets.pie.hoverOffset = 8;
  }

  function ensureMatrixRegistered() {
    try {
      if (typeof Chart === "undefined" || !Chart || typeof Chart.register !== "function") return false;
      // If already registered, this will be a no-op.
      const pkg = window["chartjs-chart-matrix"];
      if (pkg && pkg.MatrixController && pkg.MatrixElement) {
        Chart.register(pkg.MatrixController, pkg.MatrixElement);
        return true;
      }
      return false;
    } catch {
      return false;
    }
  }

  function riskBandColor(band) {
    const b = String(band || "").toUpperCase();
    if (b === "LOW") return COLORS.low;
    if (b === "MEDIUM") return COLORS.medium;
    if (b === "HIGH") return COLORS.high;
    if (b === "CRITICAL") return COLORS.critical;
    return "#64748b";
  }

  function showDeptCharts(which) {
    const container = el("chart-container");
    const grid = el("dept-charts");
    if (container) container.classList.remove("hidden");
    if (grid) grid.classList.remove("hidden");
    [
      "soc-chart-wrap",
      "soc-spike-wrap",
      "soc-heatmap-wrap",
      "soc-risktrend-wrap",
      "soc-eventdist-wrap",
      "soc-sevbar-wrap",
      "soc-topassets-wrap",
      "finance-chart-wrap",
      "fin-status-wrap",
      "fin-highvalue-wrap",
      "fin-violations-wrap",
      "fin-exposure-wrap",
      "hr-trend-wrap",
      "hr-dist-wrap",
      "hr-over-time-wrap",
      "hr-topusers-wrap",
      "hr-offhours-wrap",
      "hr-violations-wrap",
      "hr-sensitive-wrap",
    ].forEach((id) => {
      const n = el(id);
      if (!n) return;
      n.classList.add("hidden");
    });

    const show = (ids) => ids.forEach((id) => el(id) && el(id).classList.remove("hidden"));
    if (which === "soc")
      show([
        "soc-chart-wrap",
        "soc-spike-wrap",
        "soc-heatmap-wrap",
        "soc-risktrend-wrap",
        "soc-eventdist-wrap",
        "soc-sevbar-wrap",
        "soc-topassets-wrap",
      ]);
    if (which === "finance")
      show([
        "finance-chart-wrap",
        "fin-status-wrap",
        "fin-highvalue-wrap",
        "fin-violations-wrap",
        "fin-exposure-wrap",
      ]);
    if (which === "hr")
      show([
        "hr-trend-wrap",
        "hr-dist-wrap",
        "hr-over-time-wrap",
        "hr-topusers-wrap",
        "hr-offhours-wrap",
        "hr-violations-wrap",
        "hr-sensitive-wrap",
      ]);
  }

  function renderSocDashboardCharts(d) {
    showDeptCharts("soc");
    const tl = (d && (d.attack_timeline || d.events_over_time)) || [];
    const spikes = (d && d.alert_spikes) || {};
    const heat = (d && d.asset_risk_heatmap) || null;
    const trend = (d && d.asset_risk_trend) || null;
    const evt = (d && d.event_distribution) || {};
    const sev = (d && d.events_by_severity) || {};
    const top = (d && d.top_risky_assets) || [];

    const socSum = el("soc-summary-timeline");
    if (socSum) socSum.textContent = tl.length ? `Buckets: ${tl.length}. Latest: ${tl[tl.length - 1].count || 0} events.` : "No timeline buckets yet.";

    const spikeSum = el("soc-summary-spikes");
    if (spikeSum) {
      const s = spikes.spikes || [];
      spikeSum.textContent = s.length ? `Detected ${s.length} spike(s). Threshold z≥${spikes.z_threshold}.` : "No spikes detected for this window.";
    }

    const topHost = el("socTopAssets");
    if (topHost) {
      topHost.innerHTML = top.length
        ? `<ol class="ceo-bullet">${top
            .slice(0, 8)
            .map((a) => `<li><strong>${escapeHtml(a.asset_id)}</strong> — avg ${fmtNum(a.avg_risk_score)} (${a.count} events)</li>`)
            .join("")}</ol>`
        : `<p class="ceo-muted" style="margin:0">No risky-asset ranking yet.</p>`;
    }

    // Timeline
    const ctx = el("socChart");
    if (ctx && tl.length) {
      window.__socTimeline = new Chart(ctx.getContext("2d"), {
        type: "line",
        data: {
          labels: tl.map((x) => x.bucket),
          datasets: [
            {
              label: "Events / bucket",
              data: tl.map((x) => x.count),
              borderColor: COLORS.blue,
              backgroundColor: "rgba(59,130,246,0.10)",
              fill: true,
              tension: 0.4,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: "index", intersect: false },
          plugins: { legend: { position: "bottom", labels: { color: COLORS.tick, boxWidth: 10, font: { size: 10 } } } },
          scales: {
            x: { ticks: { color: COLORS.tick, maxRotation: 45, font: { size: 9 } }, grid: { color: COLORS.grid } },
            y: { ticks: { color: COLORS.tick }, grid: { color: COLORS.grid }, beginAtZero: true },
          },
        },
      });
    }

    // Spike chart: same series, but point color for spikes
    const sp = el("socSpikeChart");
    if (sp && tl.length) {
      const spikeSet = new Set(((spikes.spikes || [])).map((s) => s.bucket));
      window.__socSpike = new Chart(sp.getContext("2d"), {
        type: "line",
        data: {
          labels: tl.map((x) => x.bucket),
          datasets: [
            {
              label: "Events (spikes highlighted)",
              data: tl.map((x) => x.count),
              borderColor: COLORS.purple,
              backgroundColor: "rgba(124,58,237,0.10)",
              fill: true,
              tension: 0.4,
              pointRadius: 3,
              pointBackgroundColor: tl.map((x) => (spikeSet.has(x.bucket) ? COLORS.critical : COLORS.purple)),
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { position: "bottom", labels: { color: COLORS.tick, boxWidth: 10, font: { size: 10 } } } },
          scales: {
            x: { ticks: { color: COLORS.tick, maxRotation: 45, font: { size: 9 } }, grid: { color: COLORS.grid } },
            y: { ticks: { color: COLORS.tick }, grid: { color: COLORS.grid }, beginAtZero: true },
          },
        },
      });
    }

    // Heatmap — proper risk matrix grid (chartjs-chart-matrix)
    const hm = el("socHeatmapChart");
    if (hm && heat && heat.assets && heat.assets.length) {
      const ok = ensureMatrixRegistered();
      if (!ok && el("error-banner")) {
        const b = el("error-banner");
        b.innerHTML =
          "UI error: Chart.js matrix controller not registered. " +
          "Ensure `static/vendor/chartjs-chart-matrix.min.js` is loaded.";
        b.classList.remove("hidden");
      }
      const assets = heat.assets;
      const levels = heat.levels || ["LOW", "MEDIUM", "HIGH", "CRITICAL"];
      const matrix = heat.matrix || [];
      // Transform into [{x: asset_name, y: risk_band, v: count}]
      const data = [];
      let maxV = 0;
      for (let yi = 0; yi < levels.length; yi++) {
        for (let xi = 0; xi < assets.length; xi++) {
          const v = (matrix[yi] && matrix[yi][xi]) || 0;
          if (v > maxV) maxV = v;
          data.push({ x: assets[xi], y: levels[yi], v });
        }
      }
      maxV = Math.max(1, maxV);

      const ctx = hm.getContext("2d");
      window.__socHeatmap = new Chart(ctx, {
        type: "matrix",
        data: {
          datasets: [
            {
              label: "Events",
              data,
              borderWidth: (c) => (c.active ? 2 : 1),
              borderColor: (c) => (c.active ? "rgba(255,255,255,0.35)" : "rgba(42,53,68,0.85)"),
              borderRadius: 4,
              backgroundColor: (c) => {
                const r = c.raw || {};
                const base = riskBandColor(r.y);
                const alpha = Math.max(0.12, Math.min(0.95, (Number(r.v) || 0) / maxV));
                // Convert hex to rgba
                const hex = base.replace("#", "");
                const rr = parseInt(hex.substring(0, 2), 16);
                const gg = parseInt(hex.substring(2, 4), 16);
                const bb = parseInt(hex.substring(4, 6), 16);
                return `rgba(${rr},${gg},${bb},${alpha.toFixed(2)})`;
              },
              width: (ctx) => {
                const a = assets.length || 1;
                const area = ctx.chart.chartArea;
                if (!area) return 18;
                return Math.max(16, Math.floor((area.right - area.left) / a) - 6);
              },
              height: (ctx) => {
                const l = levels.length || 1;
                const area = ctx.chart.chartArea;
                if (!area) return 18;
                return Math.max(16, Math.floor((area.bottom - area.top) / l) - 6);
              },
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: { duration: 450 },
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                title: (items) => {
                  const r = items && items[0] && items[0].raw ? items[0].raw : {};
                  return `${r.x || ""}`;
                },
                label: (ctx) => {
                  const r = ctx.raw || {};
                  return `Risk ${r.y}: ${r.v} event(s)`;
                },
              },
            },
          },
          scales: {
            x: {
              type: "category",
              labels: assets,
              grid: { display: false },
              ticks: { color: COLORS.tick, maxRotation: 28, minRotation: 28, font: { size: 9 } },
            },
            y: {
              type: "category",
              labels: levels,
              offset: true,
              grid: { display: false },
              ticks: { color: COLORS.tick, font: { size: 10 } },
            },
          },
        },
      });
    }

    // Risk trend by asset (multi-line)
    const rt = el("socRiskTrendChart");
    if (rt && trend && trend.buckets && trend.buckets.length) {
      const buckets = trend.buckets;
      const ids = (trend.assets || []).map((a) => a.asset_id);
      const palette = [COLORS.blue, COLORS.purple, COLORS.high, COLORS.low];
      const datasets = ids.slice(0, 4).map((aid, i) => ({
        label: aid,
        data: (trend.series && trend.series[aid]) || [],
        borderColor: palette[i % palette.length],
        tension: 0.4,
        spanGaps: true,
      }));
      window.__socRiskTrend = new Chart(rt.getContext("2d"), {
        type: "line",
        data: { labels: buckets, datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: "index", intersect: false },
          plugins: { legend: { position: "bottom", labels: { color: COLORS.tick, boxWidth: 10, font: { size: 10 } } } },
          scales: {
            x: { ticks: { color: COLORS.tick, maxRotation: 45, font: { size: 9 } }, grid: { color: COLORS.grid } },
            y: { min: 0, max: 1, ticks: { color: COLORS.tick }, grid: { color: COLORS.grid } },
          },
        },
      });
    }

    // Event dist donut
    const ed = el("socEventDistChart");
    if (ed && evt) {
      const labels = Object.keys(evt).slice(0, 8);
      const vals = labels.map((k) => evt[k]);
      if (labels.length) {
        window.__socEventDist = new Chart(ed.getContext("2d"), {
          type: "doughnut",
          data: {
            labels,
            datasets: [{ data: vals, backgroundColor: ["#3b82f6", "#a855f7", "#f97316", "#ef4444", "#22c55e", "#eab308", "#38bdf8", "#f59e0b"] }],
          },
          options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: "bottom", labels: { color: COLORS.tick, boxWidth: 10, font: { size: 10 } } } } },
        });
      }
    }

    // Severity bar
    const sb = el("socSeverityBar");
    if (sb && sev) {
      const labels = ["low", "medium", "high", "critical"];
      const vals = labels.map((k) => sev[k] || 0);
      window.__socSeverityBar = new Chart(sb.getContext("2d"), {
        type: "bar",
        data: {
          labels,
          datasets: [
            {
              label: "Count",
              data: vals,
              backgroundColor: [COLORS.low, COLORS.medium, COLORS.high, COLORS.critical].map((c) => c + "AA"),
              borderColor: [COLORS.low, COLORS.medium, COLORS.high, COLORS.critical],
              borderWidth: 1,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { ticks: { color: COLORS.tick, font: { size: 10 } }, grid: { color: COLORS.grid } },
            y: { ticks: { color: COLORS.tick }, grid: { color: COLORS.grid }, beginAtZero: true },
          },
        },
      });
    }
  }

  function renderFinanceDashboardCharts(d) {
    showDeptCharts("finance");
    const flow = (d && d.transaction_volume_trend) || [];
    const sf = (d && d.success_vs_failed) || {};
    const hv = (d && d.top_high_value) || [];
    const v = (d && d.access_violations) || {};
    const exp = (d && d.financial_risk_exposure) || {};

    // Existing donut preserved, but now in its own chart too
    const fc = el("finChart");
    if (fc && flow.length) {
      window.__finVolume = new Chart(fc.getContext("2d"), {
        type: "line",
        data: {
          labels: flow.map((x) => x.bucket),
          datasets: [
            {
              label: "Tx count",
              data: flow.map((x) => x.count),
              borderColor: COLORS.blue,
              tension: 0.4,
            },
            {
              label: "Amount sum ($)",
              data: flow.map((x) => x.amount_total || 0),
              borderColor: COLORS.high,
              tension: 0.4,
              yAxisID: "y1",
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: "index", intersect: false },
          plugins: { legend: { position: "bottom", labels: { color: COLORS.tick, boxWidth: 10, font: { size: 10 } } } },
          scales: {
            x: { ticks: { color: COLORS.tick, maxRotation: 45, font: { size: 9 } }, grid: { color: COLORS.grid } },
            y: { ticks: { color: COLORS.tick }, grid: { color: COLORS.grid }, beginAtZero: true },
            y1: { position: "right", ticks: { color: COLORS.tick }, grid: { drawOnChartArea: false }, beginAtZero: true },
          },
        },
      });
    }

    const sb = el("finStatusBar");
    if (sb) {
      window.__finStatusBar = new Chart(sb.getContext("2d"), {
        type: "bar",
        data: {
          labels: ["success", "failure/other"],
          datasets: [{ label: "Count", data: [sf.success || 0, sf.failed || 0], backgroundColor: [COLORS.low + "AA", COLORS.critical + "AA"], borderColor: [COLORS.low, COLORS.critical], borderWidth: 1 }],
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { ticks: { color: COLORS.tick }, grid: { color: COLORS.grid } }, y: { ticks: { color: COLORS.tick }, grid: { color: COLORS.grid }, beginAtZero: true } } },
      });
    }

    const hvb = el("finHighValueBar");
    if (hvb && hv.length) {
      const top = hv.slice(0, 10);
      window.__finHighValueBar = new Chart(hvb.getContext("2d"), {
        type: "bar",
        data: {
          labels: top.map((l) => (l.asset_name || l.asset_id || "").slice(0, 14) + " #" + l.id),
          datasets: [{ label: "Amount", data: top.map((l) => l.amount || 0), backgroundColor: COLORS.high + "AA", borderColor: COLORS.high }],
        },
        options: { indexAxis: "y", responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { ticks: { color: COLORS.tick }, grid: { color: COLORS.grid }, beginAtZero: true }, y: { ticks: { color: COLORS.tick, font: { size: 9 } }, grid: { color: COLORS.grid } } } },
      });
    }

    const vb = el("finViolationsBar");
    if (vb) {
      window.__finViolationsBar = new Chart(vb.getContext("2d"), {
        type: "bar",
        data: { labels: ["policy", "insider"], datasets: [{ label: "Count", data: [v.policy_violations || 0, v.insider_indicators || 0], backgroundColor: [COLORS.medium + "AA", COLORS.anomaly + "AA"], borderColor: [COLORS.medium, COLORS.anomaly], borderWidth: 1 }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { ticks: { color: COLORS.tick }, grid: { color: COLORS.grid } }, y: { ticks: { color: COLORS.tick }, grid: { color: COLORS.grid }, beginAtZero: true } } },
      });
    }

    const ex = el("finExposureTrend");
    const kpi = el("fin-exposure-kpi");
    if (kpi) kpi.textContent = exp.total_exposure != null ? `Estimated exposure: $${Number(exp.total_exposure).toLocaleString()}` : "Estimated exposure: —";
    if (ex && exp.trend && exp.trend.length) {
      window.__finExposureTrend = new Chart(ex.getContext("2d"), {
        type: "line",
        data: { labels: exp.trend.map((t) => t.bucket), datasets: [{ label: "Exposure ($)", data: exp.trend.map((t) => t.exposure), borderColor: COLORS.purple, backgroundColor: "rgba(124,58,237,0.10)", fill: true, tension: 0.4 }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: "bottom", labels: { color: COLORS.tick, boxWidth: 10, font: { size: 10 } } } }, scales: { x: { ticks: { color: COLORS.tick, maxRotation: 45, font: { size: 9 } }, grid: { color: COLORS.grid } }, y: { ticks: { color: COLORS.tick }, grid: { color: COLORS.grid }, beginAtZero: true } } },
      });
    }
  }

  function renderHrDashboardCharts(d) {
    showDeptCharts("hr");
    const trend = (d && d.user_activity_trend) || [];
    const dist = (d && d.activity_type_distribution) || {};
    const over = (d && d.activity_type_over_time) || {};
    const top = (d && d.top_users) || [];
    const off = (d && d.off_hours_compare) || {};
    const vio = (d && d.violations_access) || {};
    const sens = (d && d.sensitive_data_access) || {};

    const t = el("hrActivityTrend");
    if (t && trend.length) {
      window.__hrActivityTrend = new Chart(t.getContext("2d"), {
        type: "line",
        data: { labels: trend.map((x) => x.bucket), datasets: [{ label: "Actions / bucket", data: trend.map((x) => x.count), borderColor: COLORS.blue, backgroundColor: "rgba(59,130,246,0.10)", fill: true, tension: 0.4 }] },
        options: { responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false }, plugins: { legend: { position: "bottom", labels: { color: COLORS.tick, boxWidth: 10, font: { size: 10 } } } }, scales: { x: { ticks: { color: COLORS.tick, maxRotation: 45, font: { size: 9 } }, grid: { color: COLORS.grid } }, y: { ticks: { color: COLORS.tick }, grid: { color: COLORS.grid }, beginAtZero: true } } },
      });
    }

    const d1 = el("hrActivityDist");
    const distLabels = Object.keys(dist);
    if (d1 && distLabels.length) {
      window.__hrActivityDist = new Chart(d1.getContext("2d"), {
        type: "doughnut",
        data: { labels: distLabels, datasets: [{ data: distLabels.map((k) => dist[k]), backgroundColor: [COLORS.low, COLORS.medium, COLORS.high, COLORS.critical, COLORS.purple, COLORS.blue].slice(0, distLabels.length) }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: "bottom", labels: { color: COLORS.tick, boxWidth: 10, font: { size: 10 } } } } },
      });
    }

    const ot = el("hrActivityOverTime");
    if (ot && over.buckets && over.buckets.length) {
      const keys = Object.keys(over.series || {}).slice(0, 6);
      const palette = [COLORS.blue, COLORS.purple, COLORS.low, COLORS.medium, COLORS.high, COLORS.critical];
      window.__hrActivityOverTime = new Chart(ot.getContext("2d"), {
        type: "line",
        data: {
          labels: over.buckets,
          datasets: keys.map((k, i) => ({ label: k, data: over.series[k], borderColor: palette[i % palette.length], tension: 0.4 })),
        },
        options: { responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false }, plugins: { legend: { position: "bottom", labels: { color: COLORS.tick, boxWidth: 10, font: { size: 10 } } } }, scales: { x: { ticks: { color: COLORS.tick, maxRotation: 45, font: { size: 9 } }, grid: { color: COLORS.grid } }, y: { ticks: { color: COLORS.tick }, grid: { color: COLORS.grid }, beginAtZero: true } } },
      });
    }

    const tu = el("hrTopUsersBar");
    if (tu && top.length) {
      const top10 = top.slice(0, 10);
      window.__hrTopUsersBar = new Chart(tu.getContext("2d"), {
        type: "bar",
        data: { labels: top10.map((u) => "User " + u.user_id), datasets: [{ label: "Events", data: top10.map((u) => u.count), backgroundColor: COLORS.purple + "AA", borderColor: COLORS.purple }] },
        options: { indexAxis: "y", responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { ticks: { color: COLORS.tick }, grid: { color: COLORS.grid }, beginAtZero: true }, y: { ticks: { color: COLORS.tick, font: { size: 9 } }, grid: { color: COLORS.grid } } } },
      });
    }

    const oh = el("hrOffHoursBar");
    if (oh) {
      window.__hrOffHoursBar = new Chart(oh.getContext("2d"), {
        type: "bar",
        data: { labels: ["normal", "off-hours"], datasets: [{ label: "Count", data: [off.normal_hours || 0, off.off_hours || 0], backgroundColor: [COLORS.low + "AA", COLORS.anomaly + "AA"], borderColor: [COLORS.low, COLORS.anomaly] }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { ticks: { color: COLORS.tick }, grid: { color: COLORS.grid } }, y: { ticks: { color: COLORS.tick }, grid: { color: COLORS.grid }, beginAtZero: true } } },
      });
    }

    const vv = el("hrViolationsBar");
    if (vv) {
      window.__hrViolationsBar = new Chart(vv.getContext("2d"), {
        type: "bar",
        data: { labels: ["denied/failed", "suspicious"], datasets: [{ label: "Count", data: [vio.denied_or_failed || 0, vio.suspicious || 0], backgroundColor: [COLORS.critical + "AA", COLORS.anomaly + "AA"], borderColor: [COLORS.critical, COLORS.anomaly] }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { ticks: { color: COLORS.tick }, grid: { color: COLORS.grid } }, y: { ticks: { color: COLORS.tick }, grid: { color: COLORS.grid }, beginAtZero: true } } },
      });
    }

    const sp = el("hrSensitivePie");
    const sl = Object.keys(sens);
    if (sp && sl.length) {
      window.__hrSensitivePie = new Chart(sp.getContext("2d"), {
        type: "pie",
        data: { labels: sl, datasets: [{ data: sl.map((k) => sens[k]), backgroundColor: sl.map((k) => (String(k).toLowerCase().includes("salary") ? COLORS.critical : String(k).toLowerCase().includes("personal") ? COLORS.high : COLORS.blue)) }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: "bottom", labels: { color: COLORS.tick, boxWidth: 10, font: { size: 10 } } } } },
      });
    }
  }

  function kpiSeverityClass(sev) {
    const s = (sev || "").toLowerCase();
    if (s === "critical") return "ceo-kpi-strip--critical";
    if (s === "high") return "ceo-kpi-strip--high";
    if (s === "medium") return "ceo-kpi-strip--medium";
    return "ceo-kpi-strip--low";
  }

  function renderCeoExecutivePanels(dashboard) {
    const ex = dashboard && dashboard.executive;
    if (!ex) return;
    const pos = ex.positive_signals || {};

    const winsEl = el("ceo-overview-wins");
    if (winsEl) {
      if (!pos.telemetry_total) {
        winsEl.innerHTML = `
          <div class="card ceo-card--momentum">
            <div class="card-head"><h2>Operational momentum</h2></div>
            <div class="card-body"><p class="ceo-muted" style="margin:0">Ingest telemetry to see momentum metrics next to risk.</p></div>
          </div>`;
      } else {
        const calmWin =
          pos.recent_days_window > 0
            ? `${pos.recent_calm_days}/${pos.recent_days_window}`
            : "—";
        const deptOk = `${pos.department_streams_on_track}/${pos.department_streams_total}`;
        const finStat =
          pos.finance_success_pct != null && pos.finance_total > 0
            ? `<div class="stat stat--positive"><div class="stat-value">${pos.finance_success_pct}%</div><div class="stat-label">Finance success rate</div></div>`
            : `<div class="stat stat--positive"><div class="stat-value">${Number(pos.telemetry_total).toLocaleString()}</div><div class="stat-label">Events ingested</div></div>`;
        winsEl.innerHTML = `
          <div class="card ceo-card--momentum">
            <div class="card-head ceo-card-head--split">
              <h2>Operational momentum</h2>
              <span class="ceo-pill ceo-pill--ok">Balanced story</span>
            </div>
            <div class="card-body">
              <p class="ceo-wins-headline">${escapeHtml(pos.headline || "")}</p>
              <div class="stat-grid ceo-stat-grid--wins">
                <div class="stat stat--positive"><div class="stat-value">${pos.low_medium_share_pct}%</div><div class="stat-label">LOW + MEDIUM share</div></div>
                <div class="stat stat--positive"><div class="stat-value">${pos.non_critical_share_pct}%</div><div class="stat-label">Not CRITICAL</div></div>
                ${finStat}
                <div class="stat stat--positive"><div class="stat-value">${Number(pos.distinct_assets).toLocaleString()}</div><div class="stat-label">Assets monitored</div></div>
                <div class="stat stat--positive"><div class="stat-value">${deptOk}</div><div class="stat-label">Dept streams on track</div></div>
                <div class="stat stat--positive"><div class="stat-value">${calmWin}</div><div class="stat-label">Calm days (rollup)</div></div>
              </div>
            </div>
          </div>`;
      }
    }

    const kpi = ex.overall_kpi || {};
    const kpiEl = el("ceo-kpi-strip");
    if (kpiEl) {
      const ch = kpi.change_percent;
      const chHtml =
        ch == null
          ? "<span class=\"ceo-kpi-change\">No prior-window baseline</span>"
          : `<span class="ceo-kpi-change ${ch > 0 ? "is-up" : ch < 0 ? "is-down" : ""}">7d vs prior 7d: <strong>${ch > 0 ? "+" : ""}${ch}%</strong></span>`;
      kpiEl.className = "ceo-kpi-strip " + kpiSeverityClass(kpi.severity);
      kpiEl.innerHTML = `
        <div class="ceo-kpi-main">
          <div class="ceo-kpi-score">${fmtNum(kpi.score)}</div>
          <div class="ceo-kpi-meta">
            <div class="ceo-kpi-label">Portfolio risk (avg risk_score)</div>
            <div class="ceo-kpi-sev">${escapeHtml(kpi.severity || "—")}</div>
            ${chHtml}
          </div>
        </div>
        <p class="ceo-kpi-note">${escapeHtml(kpi.window_note || "")}</p>
      `;
    }
    const sum = el("ceo-exec-summary");
    if (sum) {
      const ft = ex.financial_exposure || {};
      const comp = ex.compliance || {};
      const strengthLines = (pos.summary_lines || []).slice(0, 4);
      const strengthsHtml = strengthLines.length
        ? `<ul class="ceo-exec-bullets">${strengthLines.map((t) => `<li>${escapeHtml(t)}</li>`).join("")}</ul>`
        : `<p class="ceo-muted" style="margin:0">Momentum lines populate as coverage grows.</p>`;
      sum.innerHTML = `
        <div class="card ceo-card--snapshot">
          <div class="card-head ceo-card-head--split">
            <h2>Executive snapshot</h2>
            <span class="ceo-pill">Strengths &amp; attention</span>
          </div>
          <div class="card-body">
            <div class="ceo-exec-split">
              <div class="ceo-exec-col ceo-exec-col--good">
                <h3 class="ceo-exec-col-title">What&apos;s working</h3>
                ${strengthsHtml}
              </div>
              <div class="ceo-exec-col ceo-exec-col--watch">
                <h3 class="ceo-exec-col-title">Where to steer</h3>
                <div class="ceo-exec-watch-row">
                  <span class="ceo-exec-label">Financial exposure (est.)</span>
                  <span class="ceo-exec-value">$${Number(ft.estimated_impact || 0).toLocaleString()}</span>
                </div>
                <div class="ceo-exec-watch-row">
                  <span class="ceo-exec-label">Compliance</span>
                  <span class="ceo-exec-value">${escapeHtml(comp.level || "—")} <span class="ceo-exec-sub">(${comp.score ?? "—"}/100)</span></span>
                </div>
                <p class="ceo-muted ceo-exec-footnote">${escapeHtml((comp.reasons && comp.reasons[0]) || "")}</p>
              </div>
            </div>
            <p class="ceo-snapshot-footer">Charts live under <strong>Risk analytics</strong>; playbooks under <strong>Recommendations</strong>. The assistant summarizes both.</p>
          </div>
        </div>`;
    }
    const compCard = el("ceo-compliance-card");
    if (compCard) {
      const c = ex.compliance || {};
      compCard.innerHTML = `
        <div class="card">
          <div class="card-head"><h2>Compliance posture</h2></div>
          <div class="card-body">
            <p><strong>${escapeHtml(c.level || "—")}</strong> — score ${c.score ?? "—"}/100</p>
            <ul class="ceo-bullet">${(c.reasons || []).map((r) => `<li>${escapeHtml(r)}</li>`).join("")}</ul>
          </div>
        </div>
      `;
    }
    const mx = el("ceo-risk-matrix");
    if (mx) {
      const rows = ex.risk_category_matrix || [];
      mx.innerHTML = `
        <table class="data-table">
          <thead><tr><th>Band</th><th>Logs</th><th>Business impact</th><th>Ownership</th></tr></thead>
          <tbody>
            ${rows
              .map(
                (r) => `<tr>
              <td><span class="badge">${escapeHtml(r.band)}</span></td>
              <td>${r.log_count ?? 0}</td>
              <td>${escapeHtml(r.business_impact || "")}</td>
              <td>${escapeHtml(r.owner || "")}</td>
            </tr>`
              )
              .join("")}
          </tbody>
        </table>
      `;
    }
    const recHost = el("ceo-dept-recommendations");
    if (recHost) {
      const recs = ex.department_recommendations || [];
      recHost.innerHTML = recs
        .map(
          (r) => `
        <div class="ceo-rec-card">
          <div class="ceo-rec-head"><span class="ceo-rec-dept">${escapeHtml(r.department || "")}</span><span class="ceo-rec-pri">${escapeHtml(r.priority || "")}</span></div>
          <p class="ceo-rec-issues"><strong>Issues:</strong> ${escapeHtml((r.identified_issues || []).join(" "))}</p>
          <ul class="ceo-bullet">${(r.actions || []).map((a) => `<li>${escapeHtml(a)}</li>`).join("")}</ul>
        </div>
      `
        )
        .join("");
    }
    const fut = el("ceo-future-list");
    if (fut) {
      const fs = (ex.future_scope && ex.future_scope.items) || [];
      fut.innerHTML = fs.map((t) => `<li>${escapeHtml(t)}</li>`).join("");
    }
    const alerts = el("ceo-insider-alerts");
    if (alerts) {
      const items = ex.insider_alerts || [];
      alerts.innerHTML = items.length
        ? items
            .map(
              (a) => `
        <div class="ceo-alert ceo-alert--${escapeHtml(a.severity || "medium")}">
          <div class="ceo-alert-title">${escapeHtml(a.title || "")}</div>
          <div class="ceo-alert-detail">${escapeHtml(a.detail || "")}</div>
        </div>
      `
            )
            .join("")
        : `<div class="ceo-muted">No automated insider-pattern alerts for this snapshot.</div>`;
    }
    const at = el("ceo-assets-table");
    if (at) {
      const assets = ex.top_risky_assets || [];
      at.innerHTML = assets.length
        ? `<table class="data-table">
        <thead><tr><th>Asset</th><th>Dept</th><th>Avg risk</th><th>Avg anomaly</th><th>Critical #</th><th>Level</th></tr></thead>
        <tbody>${assets
          .map(
            (a) => `<tr>
          <td>${escapeHtml(a.asset_name || a.asset_id)}</td>
          <td>${escapeHtml(a.department || "—")}</td>
          <td>${fmtNum(a.avg_risk_score)}</td>
          <td>${fmtNum(a.avg_anomaly_score)}</td>
          <td>${a.critical_count ?? 0}</td>
          <td>${escapeHtml(a.risk_level || "—")}</td>
        </tr>`
          )
          .join("")}</tbody></table>`
        : `<p class="ceo-muted">No asset-level aggregates yet.</p>`;
    }

    const pri = el("ceo-top-priority");
    if (pri) {
      const top = ex.top_priority || {};
      const rb = String(top.risk_band || "LOW").toUpperCase();
      pri.className = `ceo-priority-card ${rb === "CRITICAL" ? "glow-critical" : rb === "HIGH" ? "glow-high" : rb === "MEDIUM" ? "glow-medium" : "glow-low"}`;
      pri.innerHTML = `
        <div class="ceo-priority-title">TOP PRIORITY</div>
        <div class="ceo-priority-main">${escapeHtml(top.title || "No priority item")}</div>
        <div class="ceo-muted" style="margin:0.2rem 0 0.15rem">${escapeHtml(top.issue || "-")}</div>
        <div class="ceo-priority-band ${badgeClassRisk(rb)}">${escapeHtml(rb)}</div>
        <p class="ceo-priority-reason">${escapeHtml(top.reason || "")}</p>
      `;
    }

    const hints = el("ceo-decision-hints");
    if (hints) {
      const rows = ex.decision_hints || [];
      hints.innerHTML = rows.length
        ? `<ul class="ceo-bullet">${rows
            .slice(0, 8)
            .map((r) => `<li><strong>${escapeHtml(String(r.widget || "").replaceAll("_", " "))}:</strong> ${escapeHtml(r.hint || "")}</li>`)
            .join("")}</ul>`
        : `<p class="ceo-muted" style="margin:0">Decision hints will appear when risk patterns are available.</p>`;
    }

    const hot = el("ceo-anomaly-hotspots");
    if (hot) {
      const rows = ex.anomaly_hotspots || [];
      hot.innerHTML = rows.length
        ? `<ol class="ceo-bullet">${rows
            .slice(0, 10)
            .map(
              (r) =>
                `<li><strong>${escapeHtml(r.summary || "")}</strong><br><span class="ceo-muted">max risk ${fmtNum(
                  r.max_risk_score
                )}, avg anomaly ${fmtNum(r.avg_anomaly_score)}, latest ${escapeHtml(fmtTs(r.latest_timestamp))}</span></li>`
            )
            .join("")}</ol>`
        : `<p class="ceo-muted" style="margin:0">No anomaly hotspots yet.</p>`;
    }

    const feed = el("ceo-critical-feed");
    if (feed) {
      const rows = ex.critical_alerts_feed || [];
      feed.innerHTML = rows.length
        ? `<ol class="ceo-bullet">${rows
            .slice(0, 15)
            .map(
              (r) =>
                `<li class="${String(r.risk_band || "").toUpperCase() === "CRITICAL" ? "ceo-feed-critical" : ""}">
                  <strong>${escapeHtml((r.risk_band || "CRITICAL").toUpperCase())}</strong> ${escapeHtml(r.event_type || "")}
                  on ${escapeHtml(r.asset_name || r.asset_id || "—")} — ${r.count ?? 1} event(s)
                  <span class="ceo-muted">• latest ${escapeHtml(fmtTs(r.latest_timestamp))}</span>
                </li>`
            )
            .join("")}</ol>`
        : `<p class="ceo-muted" style="margin:0">No CRITICAL alerts in this snapshot.</p>`;
    }
  }

  function wireCeoTabs() {
    if (state.role !== "ceo" || state.ceoTabsWired) return;
    state.ceoTabsWired = true;
    const tabs = document.querySelectorAll(".ceo-tab[data-ceo-tab]");
    const panels = document.querySelectorAll("[data-ceo-panel]");
    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        const id = tab.getAttribute("data-ceo-tab");
        tabs.forEach((t) => {
          t.classList.toggle("is-active", t.getAttribute("data-ceo-tab") === id);
          t.setAttribute("aria-selected", t.getAttribute("data-ceo-tab") === id ? "true" : "false");
        });
        panels.forEach((p) => {
          const on = p.getAttribute("data-ceo-panel") === id;
          p.classList.toggle("is-active", on);
          p.hidden = !on;
        });
        requestAnimationFrame(() => {
          [
            "__ceoChartFinFlow",
            "__ceoChartFinStatus",
            "__ceoChartDomain",
            "__ceoChartRisk",
            "__ceoChartDeptBar",
            "__ceoChartRiskTrend",
            "__ceoChartFinExpose",
            "__ceoChartAssetsBar",
          ].forEach((k) => {
            const c = window[k];
            if (c && typeof c.resize === "function") c.resize();
          });
        });
      });
    });
    const focusBtn = el("btn-focus-assistant");
    if (focusBtn) {
      focusBtn.addEventListener("click", () => {
        const aside = el("ceo-aside");
        if (aside) {
          aside.scrollIntoView({ behavior: "smooth", block: "nearest" });
          const card = el("ceo-assistant-card");
          if (card) {
            card.classList.add("ceo-assistant-card--pulse");
            setTimeout(() => card.classList.remove("ceo-assistant-card--pulse"), 1200);
          }
        }
      });
    }
  }

  function setCeoChartSummary(id, text) {
    const n = el(id);
    if (n) n.textContent = text || "";
  }

  /** One-line takeaways under each CEO chart (data-driven). */
  function updateCeoChartSummaries(dashboard) {
    const ex = (dashboard && dashboard.executive) || {};
    const cc = (dashboard && dashboard.ceo_charts) || {};

    const dr = ex.department_risk || [];
    if (dr.length) {
      let peak = dr[0];
      for (let i = 1; i < dr.length; i++) {
        if ((dr[i].avg_risk_score || 0) > (peak.avg_risk_score || 0)) peak = dr[i];
      }
      const crit = dr.reduce((a, d) => a + (Number(d.critical_count) || 0), 0);
      setCeoChartSummary(
        "ceo-summary-dept",
        `Highest avg risk: ${peak.department} (${fmtNum(peak.avg_risk_score)}). ${crit} critical logs across these departments.`
      );
    } else {
      setCeoChartSummary("ceo-summary-dept", "No department risk breakdown for this snapshot.");
    }

    const rt = ex.risk_trend_daily || [];
    if (rt.length) {
      const last = rt[rt.length - 1];
      const sumCrit = rt.reduce((a, r) => a + (Number(r.critical_count) || 0), 0);
      setCeoChartSummary(
        "ceo-summary-trend",
        `Latest ${last.date}: avg ${fmtNum(last.avg_risk_score)}, ${last.critical_count ?? 0} critical that day. ${sumCrit} critical events in window.`
      );
    } else {
      setCeoChartSummary("ceo-summary-trend", "No daily portfolio trend in this window.");
    }

    const fe = ex.financial_exposure || {};
    const feTrend = fe.trend || [];
    const estNote =
      fe.estimated_impact != null
        ? `Estimated exposure $${Number(fe.estimated_impact).toLocaleString()}.`
        : "";
    if (feTrend.length) {
      const vols = feTrend.map((t) => Number(t.volume) || 0);
      const maxV = Math.max(...vols, 0);
      setCeoChartSummary(
        "ceo-summary-finexp",
        `${estNote} Peak single-day finance volume: $${maxV.toLocaleString(undefined, { maximumFractionDigits: 0 })}.`.trim()
      );
    } else {
      setCeoChartSummary(
        "ceo-summary-finexp",
        estNote ? `${estNote} No daily finance volume points yet.` : "No financial exposure trend yet."
      );
    }

    const flow = cc.finance_flow_over_time || [];
    if (flow.length) {
      const busiest = flow.reduce((a, x) => ((x.count || 0) > (a.count || 0) ? x : a), flow[0]);
      setCeoChartSummary(
        "ceo-summary-flow",
        `Busiest time bucket: ${busiest.bucket} (${busiest.count || 0} transactions). Orange line = summed amounts.`
      );
    } else {
      setCeoChartSummary("ceo-summary-flow", "No funding-flow time buckets in range.");
    }

    const fsf = cc.finance_success_vs_failed || {};
    const succ = Number(fsf.success) || 0;
    const fail = Number(fsf.failed) || 0;
    const tot = succ + fail;
    if (tot > 0) {
      const pct = Math.round((succ / tot) * 100);
      setCeoChartSummary("ceo-summary-status", `${pct}% success-labeled finance events (${succ} / ${tot}).`);
    } else {
      setCeoChartSummary("ceo-summary-status", "No finance success vs. non-success split yet.");
    }

    const mix = cc.domain_event_mix || {};
    const labs = mix.labels || [];
    const vals = mix.values || [];
    if (labs.length && vals.some((v) => Number(v) > 0)) {
      let hi = 0;
      for (let i = 1; i < vals.length; i++) {
        if (Number(vals[i]) > Number(vals[hi])) hi = i;
      }
      setCeoChartSummary("ceo-summary-domain", `Dominant domain: ${labs[hi]} (${vals[hi]} events).`);
    } else {
      setCeoChartSummary("ceo-summary-domain", "No domain event mix to display.");
    }

    const rb = cc.risk_bands_portfolio || {};
    const rbKeys = Object.keys(rb);
    if (rbKeys.length) {
      let total = 0;
      let critN = 0;
      rbKeys.forEach((k) => {
        const v = Number(rb[k]) || 0;
        total += v;
        if (String(k).toUpperCase() === "CRITICAL") critN = v;
      });
      setCeoChartSummary("ceo-summary-riskbands", `${total} logs across bands; ${critN} CRITICAL.`);
    } else {
      setCeoChartSummary("ceo-summary-riskbands", "No portfolio severity band counts.");
    }

    const assets = ex.top_risky_assets || [];
    if (assets.length) {
      const top = assets[0];
      setCeoChartSummary(
        "ceo-summary-assets",
        `Top ranked: ${top.asset_name || top.asset_id} — avg ${fmtNum(top.avg_risk_score)} (${top.risk_level || "—"}).`
      );
    } else {
      setCeoChartSummary("ceo-summary-assets", "No asset-level risk ranking yet.");
    }

    const tu = ex.top_risky_users || [];
    if (tu.length) {
      const top = tu[0];
      setCeoChartSummary(
        "ceo-summary-topusers",
        `Highest avg user risk: User ${top.user_id} — avg ${fmtNum(top.avg_risk_score)} (${top.risk_level || "—"}).`
      );
    } else {
      setCeoChartSummary("ceo-summary-topusers", "No risky-user ranking yet.");
    }
  }

  function renderCeoDashboardCharts(dashboard) {
    if (!dashboard || typeof Chart === "undefined") return;
    destroyCeoCharts();
    const cc = dashboard.ceo_charts;
    const ex = dashboard.executive || {};
    if (cc) {
      const flow = cc.finance_flow_over_time || [];
      const labels = flow.map((x) => x.bucket);
      const counts = flow.map((x) => x.count);
      const amounts = flow.map((x) => x.amount_total || 0);

      const ctxFlow = el("ceoChartFinFlow");
      if (ctxFlow && labels.length) {
        window.__ceoChartFinFlow = new Chart(ctxFlow.getContext("2d"), {
          type: "bar",
          data: {
            labels,
            datasets: [
              {
                type: "bar",
                label: "Transactions / bucket",
                data: counts,
                backgroundColor: "rgba(34, 197, 94, 0.35)",
                borderColor: "#22c55e",
                borderWidth: 1,
                yAxisID: "y",
              },
              {
                type: "line",
                label: "Volume sum ($)",
                data: amounts,
                borderColor: "#f59e0b",
                backgroundColor: "rgba(245, 158, 11, 0.08)",
                fill: true,
                tension: 0.4,
                yAxisID: "y1",
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: "index", intersect: false },
            layout: { padding: { top: 4, bottom: 0, left: 0, right: 4 } },
            plugins: {
              legend: {
                position: "bottom",
                labels: { color: "#8b9aad", boxWidth: 10, font: { size: 10 } },
              },
            },
            scales: {
              x: { ticks: { color: "#8b9aad", maxRotation: 45 }, grid: { color: "#2a3544" } },
              y: {
                type: "linear",
                position: "left",
                ticks: { color: "#8b9aad" },
                grid: { color: "#2a3544" },
                beginAtZero: true,
              },
              y1: {
                type: "linear",
                position: "right",
                ticks: { color: "#fcd34d" },
                grid: { drawOnChartArea: false },
                beginAtZero: true,
              },
            },
          },
        });
      }

      const fsf = cc.finance_success_vs_failed || {};
      const ctxStatus = el("ceoChartFinStatus");
      if (ctxStatus && (fsf.success || fsf.failed)) {
        window.__ceoChartFinStatus = new Chart(ctxStatus.getContext("2d"), {
          type: "doughnut",
          data: {
            labels: ["Success", "Non-success"],
            datasets: [
              {
                data: [fsf.success || 0, fsf.failed || 0],
                backgroundColor: ["#22c55e", "rgba(239, 68, 68, 0.8)"],
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: { padding: { top: 2, bottom: 2, left: 2, right: 2 } },
            plugins: {
              legend: {
                position: "bottom",
                labels: { color: "#8b9aad", boxWidth: 10, font: { size: 10 } },
              },
            },
          },
        });
      }

      const mix = cc.domain_event_mix || {};
      const ctxDom = el("ceoChartDomain");
      if (ctxDom && mix.values && mix.values.some((v) => v > 0)) {
        window.__ceoChartDomain = new Chart(ctxDom.getContext("2d"), {
          type: "pie",
          data: {
            labels: mix.labels || [],
            datasets: [
              {
                data: mix.values || [],
                backgroundColor: ["#3b82f6", "#22c55e", "#a855f7"],
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: { padding: { top: 2, bottom: 2, left: 2, right: 2 } },
            plugins: {
              legend: {
                position: "bottom",
                labels: { color: "#8b9aad", boxWidth: 10, font: { size: 10 } },
              },
            },
          },
        });
      }

      const rb = cc.risk_bands_portfolio || {};
      const rbLabels = Object.keys(rb);
      const rbVals = rbLabels.map((k) => rb[k]);
      const ctxRisk = el("ceoChartRisk");
      if (ctxRisk && rbLabels.length) {
        window.__ceoChartRisk = new Chart(ctxRisk.getContext("2d"), {
          type: "bar",
          data: {
            labels: rbLabels,
            datasets: [
              {
                label: "Log count",
                data: rbVals,
                backgroundColor: rbLabels.map((lab) => {
                  const L = lab.toUpperCase();
                  if (L === "CRITICAL") return "rgba(239, 68, 68, 0.75)";
                  if (L === "HIGH") return "rgba(249, 115, 22, 0.7)";
                  if (L === "MEDIUM") return "rgba(234, 179, 8, 0.6)";
                  if (L === "LOW") return "rgba(34, 197, 94, 0.5)";
                  return "rgba(139, 154, 173, 0.45)";
                }),
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: { padding: { top: 4, bottom: 4, left: 0, right: 4 } },
            plugins: { legend: { display: false } },
            scales: {
              x: { ticks: { color: "#8b9aad", font: { size: 10 } }, grid: { color: "#2a3544" } },
              y: { ticks: { color: "#8b9aad", font: { size: 10 } }, grid: { color: "#2a3544" }, beginAtZero: true },
            },
          },
        });
      }
    }

    const deptRows = ex.department_risk || [];
    const ctxDept = el("ceoChartDeptBar");
    if (ctxDept && deptRows.length) {
      window.__ceoChartDeptBar = new Chart(ctxDept.getContext("2d"), {
        type: "bar",
        data: {
          labels: deptRows.map((d) => d.department),
          datasets: [
            {
              label: "Avg risk score",
              data: deptRows.map((d) => d.avg_risk_score),
              backgroundColor: ["#3b82f6", "#22c55e", "#a855f7"],
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          layout: { padding: { top: 4, bottom: 4, left: 0, right: 0 } },
          plugins: {
            legend: { display: false },
          },
          scales: {
            x: { ticks: { color: "#8b9aad", font: { size: 10 } }, grid: { color: "#2a3544" } },
            y: { ticks: { color: "#8b9aad", font: { size: 10 } }, grid: { color: "#2a3544" }, beginAtZero: true, suggestedMax: 1 },
          },
        },
      });
    }

    const rt = ex.risk_trend_daily || [];
    const ctxRt = el("ceoChartRiskTrend");
    if (ctxRt && rt.length) {
      window.__ceoChartRiskTrend = new Chart(ctxRt.getContext("2d"), {
        type: "line",
        data: {
          labels: rt.map((r) => r.date),
          datasets: [
            {
              label: "Avg risk",
              data: rt.map((r) => r.avg_risk_score),
              borderColor: "#38bdf8",
              tension: 0.4,
              yAxisID: "y",
            },
            {
              label: "Critical count",
              data: rt.map((r) => r.critical_count),
              borderColor: "#f87171",
              tension: 0.4,
              yAxisID: "y1",
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          layout: { padding: { top: 2, bottom: 0, left: 0, right: 6 } },
          plugins: {
            legend: {
              position: "bottom",
              labels: { color: "#8b9aad", boxWidth: 10, font: { size: 10 } },
            },
          },
          scales: {
            x: { ticks: { color: "#8b9aad", maxRotation: 45, font: { size: 9 } }, grid: { color: "#2a3544" } },
            y: {
              position: "left",
              ticks: { color: "#8b9aad", font: { size: 10 } },
              grid: { color: "#2a3544" },
              beginAtZero: true,
            },
            y1: {
              position: "right",
              ticks: { color: "#fca5a5", font: { size: 10 } },
              grid: { drawOnChartArea: false },
              beginAtZero: true,
            },
          },
        },
      });
    }

    const feTrend = (ex.financial_exposure && ex.financial_exposure.trend) || [];
    const ctxFe = el("ceoChartFinExpose");
    if (ctxFe && feTrend.length) {
      window.__ceoChartFinExpose = new Chart(ctxFe.getContext("2d"), {
        type: "line",
        data: {
          labels: feTrend.map((t) => t.date),
          datasets: [
            {
              label: "Daily finance volume ($)",
              data: feTrend.map((t) => t.volume),
              borderColor: "#fbbf24",
              backgroundColor: "rgba(251, 191, 36, 0.12)",
              fill: true,
              tension: 0.4,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          layout: { padding: { top: 4, bottom: 0, left: 0, right: 4 } },
          plugins: {
            legend: {
              position: "bottom",
              labels: { color: "#8b9aad", boxWidth: 10, font: { size: 10 } },
            },
          },
          scales: {
            x: { ticks: { color: "#8b9aad", maxRotation: 45, font: { size: 9 } }, grid: { color: "#2a3544" } },
            y: { ticks: { color: "#8b9aad", font: { size: 10 } }, grid: { color: "#2a3544" }, beginAtZero: true },
          },
        },
      });
    }

    const assets = ex.top_risky_assets || [];
    const ctxAb = el("ceoChartAssetsBar");
    if (ctxAb && assets.length) {
      const top = assets.slice(0, 10);
      window.__ceoChartAssetsBar = new Chart(ctxAb.getContext("2d"), {
        type: "bar",
        data: {
          labels: top.map((a) => String(a.asset_name || a.asset_id || "").substring(0, 16)),
          datasets: [{ label: "Avg risk", data: top.map((a) => a.avg_risk_score), backgroundColor: "#6366f1" }],
        },
        options: {
          indexAxis: "y",
          responsive: true,
          maintainAspectRatio: false,
          layout: { padding: { top: 2, bottom: 2, left: 0, right: 8 } },
          plugins: { legend: { display: false } },
          scales: {
            x: { min: 0, max: 1, ticks: { color: "#8b9aad", font: { size: 9 } }, grid: { color: "#2a3544" } },
            y: { ticks: { color: "#8b9aad", font: { size: 9 } }, grid: { color: "#2a3544" } },
          },
        },
      });
    }

    updateCeoChartSummaries(dashboard);

    const tu = ex.top_risky_users || [];
    const ctxTU = el("ceoChartTopUsers");
    if (ctxTU && tu.length) {
      const top = tu.slice(0, 10);
      window.__ceoChartTopUsers = new Chart(ctxTU.getContext("2d"), {
        type: "bar",
        data: {
          labels: top.map((u) => "User " + u.user_id),
          datasets: [
            {
              label: "Avg risk",
              data: top.map((u) => u.avg_risk_score),
              backgroundColor: "#7c3aed",
            },
          ],
        },
        options: {
          indexAxis: "y",
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (ctx) => {
                  const u = top[ctx.dataIndex] || {};
                  return `Avg risk ${fmtNum(u.avg_risk_score)} | events ${u.event_count ?? 0} | anomaly ${fmtNum(u.avg_anomaly_score)}`;
                },
              },
            },
          },
          scales: {
            x: { min: 0, max: 1, ticks: { color: "#8b9aad", font: { size: 9 } }, grid: { color: "#2a3544" } },
            y: { ticks: { color: "#8b9aad", font: { size: 9 } }, grid: { color: "#2a3544" } },
          },
        },
      });
    }

    const hm = ex.risk_heatmap || {};
    const ctxHM = el("ceoChartRiskHeatmap");
    if (ctxHM && hm.points && hm.points.length) {
      const ok = ensureMatrixRegistered();
      if (!ok) return;
      const assets = hm.assets || [];
      const depts = hm.departments || [];
      const pts = hm.points.map((p) => ({
        x: p.asset,
        y: p.department,
        v: Number(p.avg_risk_score || 0),
        n: Number(p.event_count || 0),
        risk_band: p.risk_band || "LOW",
        asset: p.asset,
        dept: p.department,
      }));
      const maxV = Math.max(1, ...pts.map((p) => Number(p.v || 0)));
      window.__ceoChartRiskHeatmap = new Chart(ctxHM.getContext("2d"), {
        type: "matrix",
        data: {
          datasets: [
            {
              data: pts,
              borderRadius: 4,
              borderColor: "rgba(42,53,68,0.9)",
              borderWidth: 1,
              backgroundColor: (ctx) => {
                const v = ctx.raw && ctx.raw.v ? ctx.raw.v : 0;
                const alpha = Math.max(0.12, Math.min(0.95, v / maxV));
                return `rgba(124,58,237,${alpha.toFixed(2)})`;
              },
              width: (ctx) => {
                const area = ctx.chart.chartArea;
                if (!area) return 18;
                return Math.max(16, Math.floor((area.right - area.left) / Math.max(1, assets.length)) - 6);
              },
              height: (ctx) => {
                const area = ctx.chart.chartArea;
                if (!area) return 18;
                return Math.max(16, Math.floor((area.bottom - area.top) / Math.max(1, depts.length)) - 6);
              },
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (ctx) => {
                  const r = ctx.raw || {};
                  return `${r.dept} • ${r.asset}: avg risk ${fmtNum(r.v)} (${r.n} events)`;
                },
              },
            },
          },
          scales: {
            x: { type: "category", labels: assets, ticks: { color: "#8b9aad", callback: (v) => (assets[v] ? String(assets[v]).slice(0, 10) : "") }, grid: { display: false } },
            y: { type: "category", labels: depts, offset: true, ticks: { color: "#8b9aad", callback: (v) => (depts[v] ? String(depts[v]) : "") }, grid: { display: false } },
          },
        },
      });
      const hs = el("ceo-summary-risk-heatmap");
      if (hs && pts.length) {
        const peak = pts.reduce((a, b) => (Number(b.v || 0) > Number(a.v || 0) ? b : a), pts[0]);
        hs.textContent = `Highest cell: ${peak.dept} × ${peak.asset} (avg risk ${fmtNum(peak.v)}, ${peak.n} events).`;
      }
    }
  }

  function renderChart(dashboard, role) {
    destroyCeoCharts();
    if (role === "ceo") {
      requestAnimationFrame(() => renderCeoDashboardCharts(dashboard));
      return;
    }
    const wrap = el("chart-container");
    const errBanner = el("error-banner");
    if (!wrap || typeof Chart === "undefined") {
      if (wrap) wrap.classList.add("hidden");
      if (errBanner) {
        errBanner.innerHTML =
          "Charts are unavailable because <strong>Chart.js failed to load</strong>. " +
          "If you're offline or your network blocks CDNs, allow `cdn.jsdelivr.net`/`unpkg.com` and refresh.";
        errBanner.classList.remove("hidden");
      }
      // Retry briefly in case Chart.js loads after DOMContentLoaded.
      if (!state.__chartRetry) state.__chartRetry = { n: 0, t: null };
      if (state.__chartRetry.n < 12) {
        state.__chartRetry.n += 1;
        clearTimeout(state.__chartRetry.t);
        state.__chartRetry.t = setTimeout(() => renderChart(dashboard, role), 250);
      }
      return;
    }
    if (state.__chartRetry) {
      clearTimeout(state.__chartRetry.t);
      state.__chartRetry = null;
    }
    wrap.classList.remove("hidden");
    const view = deriveViewType();
    if (view === "soc") return renderSocDashboardCharts(dashboard);
    if (view === "finance") return renderFinanceDashboardCharts(dashboard);
    if (view === "hr") return renderHrDashboardCharts(dashboard);
    wrap.classList.add("hidden");
  }

  function getFilteredLogs() {
    let rows = state.logs.slice();
    const q = state.filterText.trim().toLowerCase();
    if (q) {
      rows = rows.filter((r) => {
        const blob = JSON.stringify(r).toLowerCase();
        return blob.includes(q);
      });
    }
    if (state.filterSeverity) {
      rows = rows.filter((r) => (r.severity || "").toLowerCase() === state.filterSeverity);
    }
    if (state.filterType) {
      rows = rows.filter((r) => (r.log_type || "").toLowerCase() === state.filterType);
    }
    if (state.filterAsset) {
      const a = state.filterAsset;
      rows = rows.filter((r) => (r.asset_id === a) || (r.asset_name === a));
    }
    if (state.filterUser) {
      const u = state.filterUser;
      rows = rows.filter((r) => String(r.user_id || "") === u || String(r.username || "") === u);
    }
    if (state.filterRisk) {
      rows = rows.filter((r) => (r.risk_band || "").toUpperCase() === state.filterRisk);
    }
    if (state.filterStart) {
      const t0 = new Date(state.filterStart).getTime();
      rows = rows.filter((r) => (r.timestamp ? new Date(r.timestamp).getTime() : 0) >= t0);
    }
    if (state.filterEnd) {
      const t1 = new Date(state.filterEnd).getTime();
      rows = rows.filter((r) => (r.timestamp ? new Date(r.timestamp).getTime() : 0) <= t1);
    }

    const key = state.sortKey;
    const dir = state.sortDir;
    const numericKeys = new Set(["anomaly_score", "risk_score", "id"]);
    rows.sort((a, b) => {
      let va = a[key];
      let vb = b[key];
      if (key === "timestamp") {
        va = va ? new Date(va).getTime() : 0;
        vb = vb ? new Date(vb).getTime() : 0;
      } else if (numericKeys.has(key)) {
        va = va == null || va === "" ? Number.NEGATIVE_INFINITY : Number(va);
        vb = vb == null || vb === "" ? Number.NEGATIVE_INFINITY : Number(vb);
      } else if (typeof va === "string") va = va.toLowerCase();
      else if (typeof vb === "string") vb = vb.toLowerCase();
      if (va == null) va = "";
      if (vb == null) vb = "";
      if (va < vb) return -1 * dir;
      if (va > vb) return 1 * dir;
      return 0;
    });
    return rows;
  }

  function renderTable() {
    const tbody = el("log-tbody");
    const pager = el("pager-info");
    if (!tbody) return;

    const all = getFilteredLogs();
    const total = all.length;
    const pages = Math.max(1, Math.ceil(total / state.pageSize));
    if (state.page > pages) state.page = pages;
    const start = (state.page - 1) * state.pageSize;
    const slice = all.slice(start, start + state.pageSize);

    const totalUnfiltered = state.logs.length;
    if (pager) {
      if (total) {
        pager.textContent = `Showing ${start + 1}–${Math.min(start + slice.length, total)} of ${total} (loaded ${totalUnfiltered})`;
      } else {
        const bits = [];
        if (state.filterText.trim()) bits.push(`search “${state.filterText.trim()}”`);
        if (state.filterSeverity) bits.push(`severity=${state.filterSeverity}`);
        if (state.filterType) bits.push(`type=${state.filterType}`);
        if (state.filterRisk) bits.push(`risk=${state.filterRisk}`);
        const hint = bits.length ? `Active filters: ${bits.join(", ")}.` : "";
        pager.textContent =
          totalUnfiltered === 0
            ? "No logs returned for your role."
            : `No rows match filters (${hint} You have ${totalUnfiltered} logs — try Clear filters).`;
      }
    }

    if (!slice.length) {
      tbody.innerHTML = `<tr><td colspan="9" class="empty-state" style="padding:1.5rem;text-align:center">
          No rows to show. ${totalUnfiltered ? `<button type="button" class="btn btn-primary" id="empty-clear-filters">Clear filters</button>` : ""}
        </td></tr>`;
      const ec = el("empty-clear-filters");
      if (ec) ec.addEventListener("click", () => clearLogFilters());
      return;
    }

    const view = deriveViewType();
    const isCeo = state.role === "ceo";
    const headers = [
      "Time",
      ...(isCeo
        ? ["Type", "Event", "Severity", "Risk", "Anomaly", "Risk Score", "Asset", "Meta"]
        : view === "soc"
        ? ["Severity", "Event", "Asset", "Source IP", "Destination IP", "Status", "Rule", "Risk"]
        : view === "finance"
          ? ["User", "Action", "Asset", "Amount", "Status", "Risk", "Access", "Details"]
          : ["User", "Action", "Data Type", "Asset", "Status", "Risk", "Access", "Details"]),
    ];
    for (let i = 0; i < 9; i++) {
      const th = el(`logs-th-${i}`);
      if (th) th.textContent = headers[i] || "";
    }

    tbody.innerHTML = slice
      .map((row) => {
        const id = row.id;
        const risk = row.risk_level || "-";
        const rule = (row.metadata && (row.metadata.signature || row.metadata.rule || row.metadata.attack_type)) || "—";
        const finAccess = financeAccessLabel(row);
        const hrAccess = hrAccessLabel(row);
        const ceoMap = {
          timestamp: row.timestamp || "-",
          log_type: row.log_type || "-",
          event_type: row.event_type || "-",
          severity: row.severity || "-",
          risk_level: row.risk_level || "-",
          anomaly_score: row.anomaly_score == null ? "-" : fmtNum(row.anomaly_score),
          risk_score: row.risk_score == null ? "-" : fmtNum(row.risk_score),
          asset_name: row.asset_name || "-",
        };
        return `
        <tr data-id="${id}" class="log-row">
          ${
            isCeo
              ? `
            <td>${ceoMap.timestamp === "-" ? "-" : escapeHtml(fmtTs(ceoMap.timestamp))}</td>
            <td>${escapeHtml(ceoMap.log_type)}</td>
            <td>${escapeHtml(ceoMap.event_type)}</td>
            <td><span class="badge ${badgeClassSeverity(ceoMap.severity)}">${escapeHtml(ceoMap.severity)}</span></td>
            <td>${escapeHtml(ceoMap.risk_level)}</td>
            <td>${escapeHtml(ceoMap.anomaly_score)}</td>
            <td>${escapeHtml(ceoMap.risk_score)}</td>
            <td>${escapeHtml(ceoMap.asset_name)}</td>
            <td><button type="button" class="btn btn-ghost btn-detail" data-id="${id}">View</button></td>
          `
            : view === "soc"
              ? `
            <td>${fmtTs(row.timestamp)}</td>
            <td><span class="badge ${badgeClassSeverity(row.severity)}">${escapeHtml(row.severity || "—")}</span></td>
            <td>${escapeHtml(row.event_type || "—")}</td>
            <td>${escapeHtml(row.asset_name || row.asset_id || "—")}</td>
            <td>${escapeHtml(row.source_ip || "—")}</td>
            <td>${escapeHtml(row.destination_ip || "—")}</td>
            <td>${escapeHtml(normalizeStatusForSoc(row.status))}</td>
            <td>${escapeHtml(rule)}</td>
            <td>${escapeHtml(risk)}</td>
          `
              : view === "finance"
                ? `
            <td>${fmtTs(row.timestamp)}</td>
            <td>${escapeHtml(row.username || (row.user_id != null ? "User " + row.user_id : "—"))}</td>
            <td>${escapeHtml(row.action || row.event_type || "—")}</td>
            <td>${escapeHtml(row.asset_name || row.asset_id || "—")}</td>
            <td>${row.amount != null ? "$" + Number(row.amount).toLocaleString() : "—"}</td>
            <td>${escapeHtml(row.status || "—")}</td>
            <td>${escapeHtml(risk)}</td>
            <td><span class="badge ${finAccess === "unauthorized" ? "badge-risk-critical" : finAccess === "unusual" ? "badge-hr" : ""}">${escapeHtml(finAccess)}</span></td>
            <td><button type="button" class="btn btn-ghost btn-detail" data-id="${id}">View</button></td>
          `
                : `
            <td>${fmtTs(row.timestamp)}</td>
            <td>${escapeHtml(row.username || (row.user_id != null ? "User " + row.user_id : "—"))}</td>
            <td>${escapeHtml((row.metadata && row.metadata.action_context) || row.action || "—")}</td>
            <td>${escapeHtml((row.metadata && (row.metadata.data_type || row.metadata.resource)) || "—")}</td>
            <td>${escapeHtml(row.asset_name || row.asset_id || "—")}</td>
            <td>${escapeHtml(row.status || "—")}</td>
            <td>${escapeHtml(risk)}</td>
            <td><span class="badge ${hrAccess === "unauthorized" ? "badge-risk-critical" : hrAccess === "unusual" ? "badge-hr" : ""}">${escapeHtml(hrAccess)}</span></td>
            <td><button type="button" class="btn btn-ghost btn-detail" data-id="${id}">View</button></td>
          `
          }
        </tr>
      `;
      })
      .join("");

    tbody.querySelectorAll(".log-row").forEach((tr) => {
      tr.addEventListener("click", (ev) => {
        const btn = ev.target && ev.target.closest && ev.target.closest("button");
        if (btn) return;
        const id = Number(tr.getAttribute("data-id"));
        openLogModalById(id);
      });
    });
    tbody.querySelectorAll(".btn-detail").forEach((btn) => {
      btn.addEventListener("click", () => openLogModalById(Number(btn.getAttribute("data-id"))));
    });
  }

  function openLogModalById(id) {
    const row = state.logs.find((x) => Number(x.id) === Number(id));
    if (!row) return;
    const dlg = el("log-modal");
    const title = el("log-modal-title");
    const body = el("log-modal-body");
    if (!dlg || !body) return;
    const meta = JSON.stringify(row.metadata || {}, null, 2);
    const target = (row.metadata && (row.metadata.target_user_id || row.metadata.resource_id)) || null;
    if (title) title.textContent = `Log #${row.id} — ${row.log_type || "event"}`;
    body.innerHTML = `
      <div class="stat-grid" style="margin-bottom:0.75rem">
        <div class="stat"><div class="stat-value">${escapeHtml(row.risk_band || "—")}</div><div class="stat-label">Risk band</div></div>
        <div class="stat"><div class="stat-value">${fmtNum(row.anomaly_score)}</div><div class="stat-label">Anomaly score</div></div>
        <div class="stat"><div class="stat-value">${fmtNum(row.risk_score)}</div><div class="stat-label">Risk score</div></div>
        <div class="stat"><div class="stat-value">${escapeHtml(row.risk_level || "—")}</div><div class="stat-label">Risk level</div></div>
      </div>
      <p class="ceo-muted" style="margin:0 0 0.5rem"><strong>Event context:</strong> ${escapeHtml(row.event_type || row.action || "—")}</p>
      <p class="ceo-muted" style="margin:0 0 0.75rem"><strong>Target user id:</strong> ${escapeHtml(target == null ? "—" : target)}</p>
      <div class="table-wrap"><pre style="margin:0;padding:0.85rem;color:var(--muted);white-space:pre-wrap;word-break:break-word">${escapeHtml(meta)}</pre></div>
    `;
    if (typeof dlg.showModal === "function") dlg.showModal();
  }

  function wireSortHeaders() {
    document.querySelectorAll("[data-sort]").forEach((th) => {
      th.addEventListener("click", () => {
        const key = th.getAttribute("data-sort");
        if (state.sortKey === key) state.sortDir *= -1;
        else {
          state.sortKey = key;
          state.sortDir = key === "timestamp" ? -1 : 1;
        }
        state.page = 1;
        renderTable();
      });
    });
  }

  function wireFilters() {
    const search = el("filter-search");
    const sev = el("filter-severity");
    const lt = el("filter-type");
    const rk = el("filter-risk");
    const as = el("filter-asset");
    const us = el("filter-user");
    const st = el("filter-start");
    const en = el("filter-end");
    if (search) {
      search.addEventListener("input", () => {
        state.filterText = search.value;
        state.page = 1;
        renderTable();
      });
    }
    [sev, lt, rk, as, us, st, en].forEach((x) => {
      if (!x) return;
      x.addEventListener("change", () => {
        state.filterSeverity = sev ? sev.value : "";
        state.filterType = lt ? lt.value : "";
        state.filterRisk = rk ? rk.value : "";
        state.filterAsset = as ? as.value : "";
        state.filterUser = us ? us.value : "";
        state.filterStart = st ? st.value : "";
        state.filterEnd = en ? en.value : "";
        state.page = 1;
        renderTable();
      });
    });
  }

  function populateFilterOptions() {
    const as = el("filter-asset");
    const us = el("filter-user");
    if (as) {
      const seen = new Map();
      state.logs.forEach((l) => {
        const id = l.asset_id;
        if (!id) return;
        const label = l.asset_name || l.asset_id;
        if (!seen.has(id)) seen.set(id, label);
      });
      const opts = Array.from(seen.entries()).sort((a, b) => String(a[1]).localeCompare(String(b[1])));
      as.innerHTML = `<option value="">All assets</option>` + opts.map(([id, label]) => `<option value="${escapeHtml(id)}">${escapeHtml(label)}</option>`).join("");
    }
    if (us) {
      const seen = new Map();
      state.logs.forEach((l) => {
        if (l.user_id == null && !l.username) return;
        const key = l.username || String(l.user_id);
        if (!seen.has(key)) seen.set(key, l.username || `User ${l.user_id}`);
      });
      const opts = Array.from(seen.entries()).sort((a, b) => String(a[1]).localeCompare(String(b[1])));
      us.innerHTML = `<option value="">All users</option>` + opts.map(([k, label]) => `<option value="${escapeHtml(k)}">${escapeHtml(label)}</option>`).join("");
    }
  }

  async function loadAccessBanner() {
    const banner = el("access-banner");
    if (!banner) return;
    try {
      const data = await fetchJson("/api/v1/access/me");
      state.accessInfo = data;
      const grants = (data && data.approved_grants) || [];
      if (!grants.length) {
        banner.classList.add("hidden");
        return;
      }
      const bits = grants
        .slice(0, 3)
        .map((g) => `${escapeHtml(g.target_department)} until ${escapeHtml(fmtTs(g.expires_at))}`)
        .join(" • ");
      banner.innerHTML = `<strong>Temporary access active:</strong> ${bits}`;
      banner.classList.remove("hidden");
    } catch {
      banner.classList.add("hidden");
    }
  }

  function wireAccessRequestModal() {
    const btn = el("btn-request-access");
    const dlg = el("access-modal");
    const submit = el("access-submit");
    if (btn && dlg && typeof dlg.showModal === "function") {
      btn.addEventListener("click", () => {
        const status = el("access-modal-status");
        if (status) status.textContent = "";
        dlg.showModal();
      });
    }
    if (submit) {
      submit.addEventListener("click", async () => {
        const target = el("access-target");
        const dur = el("access-duration");
        const reason = el("access-reason");
        const status = el("access-modal-status");
        if (status) status.textContent = "";
        try {
          const res = await fetchPostJson("/api/v1/access/request", {
            target_department: target ? target.value : "",
            duration_hours: dur ? Number(dur.value || "8") : 8,
            reason: reason ? reason.value : "",
          });
          if (status) status.textContent = `Submitted (request #${res.request && res.request.id}). Await admin approval.`;
        } catch (e) {
          if (status) status.textContent = e.message || "Request failed.";
        }
      });
    }
  }

  function wirePager() {
    const prev = el("btn-prev");
    const next = el("btn-next");
    if (prev)
      prev.addEventListener("click", () => {
        state.page = Math.max(1, state.page - 1);
        renderTable();
      });
    if (next)
      next.addEventListener("click", () => {
        const all = getFilteredLogs();
        const pages = Math.max(1, Math.ceil(all.length / state.pageSize));
        state.page = Math.min(pages, state.page + 1);
        renderTable();
      });
  }

  function exportCsv() {
    const rows = getFilteredLogs();
    if (!rows.length) return;
    const keys = [
      "id",
      "timestamp",
      "log_type",
      "event_type",
      "severity",
      "risk_band",
      "anomaly_score",
      "risk_score",
      "asset_id",
      "asset_name",
      "status",
    ];
    const esc = (v) => {
      const s = v == null ? "" : String(v);
      if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
      return s;
    };
    const lines = [keys.join(",")].concat(
      rows.map((r) => keys.map((k) => esc(r[k])).join(","))
    );
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "locknlog-logs.csv";
    a.click();
    URL.revokeObjectURL(a.href);
  }

  async function load() {
    const errBanner = el("error-banner");
    const loading = el("loading-state");
    const main = el("main-content");
    if (errBanner) errBanner.classList.add("hidden");
    if (loading) loading.classList.remove("hidden");
    if (main) main.classList.add("hidden");

    state.dashboardError = null;

    try {
      let logsData;
      if (state.role === "ceo") {
        try {
          logsData = await fetchJson("/api/v1/ceo/logs");
        } catch (e) {
          if (e.status === 404) {
            logsData = await fetchJson("/api/v1/logs");
          } else {
            throw e;
          }
        }
      } else {
        logsData = await fetchJson("/api/v1/logs");
      }
      state.logs = Array.isArray(logsData.logs) ? logsData.logs : [];
      if (state.role === "ceo" && state.logs.length && !state.__ceoLogDebugged) {
        const log = state.logs[0];
        console.log(log);
        state.__ceoLogDebugged = true;
      }
      populateFilterOptions();
      void loadAccessBanner();

      let dashData = null;
      try {
        dashData = await fetchJson("/api/v1/dashboard");
      } catch (e) {
        state.dashboardError = e;
        dashData = null;
      }
      state.dashboard = dashData && !dashData.error ? dashData : null;

      renderOverviewStats(el("overview-stats"), state.dashboard, state.role, state.logs.length);

      if (errBanner && state.dashboardError && !state.dashboard) {
        errBanner.textContent =
          "Dashboard overview unavailable for this account (" +
          (state.dashboardError.message || "error") +
          "). Log explorer still works.";
        errBanner.classList.remove("hidden");
      }

      if (loading) loading.classList.add("hidden");
      if (main) main.classList.remove("hidden");

      if (state.role === "ceo") {
        renderCeoExecutivePanels(state.dashboard);
      }

      requestAnimationFrame(() => {
        renderChart(state.dashboard, state.role);
      });

      renderTable();

      // SOC real-time: refresh timelines every 5s (dashboard only; logs stay manual refresh)
      if (deriveViewType() === "soc" && (state.role === "soc" || state.role === "admin" || state.role === "ceo")) {
        if (window.__socAutoRefreshTimer) clearInterval(window.__socAutoRefreshTimer);
        window.__socAutoRefreshTimer = setInterval(async () => {
          try {
            const dd = await fetchJson("/api/v1/dashboard");
            state.dashboard = dd && !dd.error ? dd : state.dashboard;
            destroyCeoCharts();
            renderChart(state.dashboard, state.role);
          } catch {
            // ignore background polling errors
          }
        }, 5000);
      } else if (window.__socAutoRefreshTimer) {
        clearInterval(window.__socAutoRefreshTimer);
        window.__socAutoRefreshTimer = null;
      }
    } catch (e) {
      if (errBanner) {
        errBanner.textContent = "Failed to load logs: " + (e.message || e);
        errBanner.classList.remove("hidden");
      }
      if (loading) loading.classList.add("hidden");
      if (main) main.classList.remove("hidden");
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    setupChartDefaults();
    wireSortHeaders();
    wireFilters();
    wirePager();
    wireClearFilters();
    wireCeoTabs();
    wireCeoChat();
    wireAccessRequestModal();

    const inject = el("btn-inject-logs");
    if (inject) {
      inject.addEventListener("click", async () => {
        inject.disabled = true;
        inject.textContent = "Injecting...";
        try {
          await fetchPostJson("/api/v1/inject", {});
          await load();
        } catch (e) {
          alert("Injection failed: " + e.message);
        } finally {
          inject.disabled = false;
          inject.textContent = "Inject Logs";
        }
      });
    }

    let refreshTimer = null;
    const refreshRate = el("refresh-rate");
    if (refreshRate) {
      refreshRate.addEventListener("change", () => {
        const ms = parseInt(refreshRate.value);
        if (refreshTimer) clearInterval(refreshTimer);
        refreshTimer = null;
        if (ms > 0) {
          refreshTimer = setInterval(() => load(), ms);
        }
      });
    }

    const refresh = el("btn-refresh");
    if (refresh) refresh.addEventListener("click", () => load());
    const csv = el("btn-export-csv");
    if (csv) csv.addEventListener("click", exportCsv);
    load();
  });
})();
