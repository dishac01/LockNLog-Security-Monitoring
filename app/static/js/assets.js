/* Asset inventory UI: /api/v1/assets + /api/v1/assets/<id> */
(function () {
  "use strict";

  window.addEventListener("error", (ev) => {
    try {
      const msg = ev && ev.message ? ev.message : "Unexpected UI error";
      console.warn(msg);
    } catch {
      // ignore
    }
  });

  const state = {
    role: (window.__LOCKNLOG_ROLE__ || "").toLowerCase(),
    assets: [],
    sortKey: "risk_score",
    sortDir: -1,
    q: "",
    dept: "",
    chart: null,
    selectedId: null,
  };

  const el = (id) => document.getElementById(id);

  function fmtNum(n) {
    if (n == null || Number.isNaN(n)) return "—";
    return typeof n === "number" ? n.toFixed(3) : String(n);
  }

  function fmtTs(iso) {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
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

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function getFilteredAssets() {
    let rows = state.assets.slice();
    const q = state.q.trim().toLowerCase();
    if (q) {
      rows = rows.filter((a) => JSON.stringify(a).toLowerCase().includes(q));
    }
    if (state.dept) {
      rows = rows.filter((a) => String(a.department || "") === state.dept);
    }
    const key = state.sortKey;
    const dir = state.sortDir;
    rows.sort((a, b) => {
      let va = a[key];
      let vb = b[key];
      if (key === "last_activity") {
        va = va ? new Date(va).getTime() : 0;
        vb = vb ? new Date(vb).getTime() : 0;
      } else {
        va = va == null ? Number.NEGATIVE_INFINITY : Number(va);
        vb = vb == null ? Number.NEGATIVE_INFINITY : Number(vb);
      }
      if (va < vb) return -1 * dir;
      if (va > vb) return 1 * dir;
      return 0;
    });
    return rows;
  }

  function renderTable() {
    const tbody = el("asset-tbody");
    const pager = el("asset-pager");
    if (!tbody) return;
    const rows = getFilteredAssets();
    if (pager) pager.textContent = `${rows.length} assets visible`;
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="6" class="empty-state">No assets visible for your current access.</td></tr>`;
      return;
    }
    tbody.innerHTML = rows
      .map((a) => {
        const sel = state.selectedId === a.id ? ' style="background: rgba(124,58,237,0.10)"' : "";
        return `<tr data-id="${escapeHtml(a.id)}"${sel}>
          <td>${escapeHtml(a.name || a.id)}</td>
          <td>${escapeHtml(a.department || "—")}</td>
          <td>${escapeHtml(a.criticality ?? "—")}</td>
          <td>${escapeHtml(a.business_value ?? "—")}</td>
          <td>${fmtNum(a.risk_score)}</td>
          <td>${escapeHtml(fmtTs(a.last_activity))}</td>
        </tr>`;
      })
      .join("");

    tbody.querySelectorAll("tr[data-id]").forEach((tr) => {
      tr.addEventListener("click", () => {
        const id = tr.getAttribute("data-id");
        state.selectedId = id;
        renderTable();
        void loadAssetDetail(id);
      });
    });
  }

  function destroyChart() {
    if (state.chart) {
      state.chart.destroy();
      state.chart = null;
    }
  }

  function renderDetail(payload) {
    const hint = el("asset-detail-hint");
    const body = el("asset-detail-body");
    if (!body) return;
    if (hint) hint.classList.add("hidden");
    body.classList.remove("hidden");
    const asset = payload.asset || {};
    const topUsers = payload.top_users || [];
    const recent = payload.recent_logs || [];
    const trend = payload.risk_trend || [];

    body.innerHTML = `
      <div class="stat-grid" style="margin-bottom:0.75rem">
        <div class="stat"><div class="stat-value">${escapeHtml(asset.department || "—")}</div><div class="stat-label">Department</div></div>
        <div class="stat"><div class="stat-value">${escapeHtml(asset.criticality ?? "—")}</div><div class="stat-label">Criticality</div></div>
        <div class="stat"><div class="stat-value">${fmtNum(asset.risk_score)}</div><div class="stat-label">Risk score</div></div>
        <div class="stat"><div class="stat-value">${escapeHtml(fmtTs(asset.last_activity))}</div><div class="stat-label">Last activity</div></div>
      </div>
      <div class="ceo-chart-cell" style="margin-bottom:0.75rem">
        <h4 class="ceo-chart-title">Risk trend (hourly avg)</h4>
        <div class="ceo-chart-canvas-wrap"><canvas id="assetRiskTrend"></canvas></div>
      </div>
      <div class="card" style="margin-bottom:0.75rem">
        <div class="card-head"><h2>Top interacting users</h2></div>
        <div class="card-body">
          ${topUsers.length ? `<ul class="ceo-bullet">${topUsers.map((u) => `<li>User ${escapeHtml(u.user_id)} — ${escapeHtml(u.count)} events</li>`).join("")}</ul>` : `<p class="ceo-muted" style="margin:0">No user-linked logs for this asset yet.</p>`}
        </div>
      </div>
      <div class="card">
        <div class="card-head"><h2>Recent logs</h2></div>
        <div class="card-body">
          ${recent.length ? `<ul class="ceo-bullet">${recent.slice(0, 12).map((l) => `<li>${escapeHtml(fmtTs(l.timestamp))} — ${escapeHtml(l.log_type)} — ${escapeHtml(l.event_type)} — <strong>${escapeHtml(l.risk_band || "—")}</strong></li>`).join("")}</ul>` : `<p class="ceo-muted" style="margin:0">No recent logs for this asset.</p>`}
        </div>
      </div>
    `;

    destroyChart();
    if (typeof Chart !== "undefined") {
      const c = el("assetRiskTrend");
      if (c && trend.length) {
        state.chart = new Chart(c.getContext("2d"), {
          type: "line",
          data: {
            labels: trend.map((t) => t.bucket),
            datasets: [
              {
                label: "Avg risk",
                data: trend.map((t) => t.avg_risk_score),
                borderColor: "#7c3aed",
                backgroundColor: "rgba(124,58,237,0.10)",
                fill: true,
                tension: 0.2,
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { position: "bottom", labels: { color: "#8b9aad", boxWidth: 10, font: { size: 10 } } },
            },
            scales: {
              x: { ticks: { color: "#8b9aad", maxRotation: 45, font: { size: 9 } }, grid: { color: "#2a3544" } },
              y: { ticks: { color: "#8b9aad", font: { size: 10 } }, grid: { color: "#2a3544" }, beginAtZero: true, suggestedMax: 1 },
            },
          },
        });
      }
    } else {
      // Chart.js may load late due to CDN fallback; retry once.
      setTimeout(() => renderDetail(payload), 400);
    }
  }

  async function loadAssets() {
    const data = await fetchJson("/api/v1/assets");
    state.assets = Array.isArray(data.assets) ? data.assets : [];
    renderTable();
  }

  async function loadAssetDetail(id) {
    const payload = await fetchJson("/api/v1/assets/" + encodeURIComponent(id));
    renderDetail(payload);
  }

  document.addEventListener("DOMContentLoaded", () => {
    const search = el("asset-search");
    const dept = el("asset-dept");
    if (search) {
      search.addEventListener("input", () => {
        state.q = search.value;
        renderTable();
      });
    }
    if (dept) {
      dept.addEventListener("change", () => {
        state.dept = dept.value;
        renderTable();
      });
    }
    document.querySelectorAll("[data-sort]").forEach((th) => {
      th.addEventListener("click", () => {
        const key = th.getAttribute("data-sort");
        if (state.sortKey === key) state.sortDir *= -1;
        else {
          state.sortKey = key;
          state.sortDir = key === "risk_score" ? -1 : 1;
        }
        renderTable();
      });
    });
    const refresh = el("btn-refresh-assets");
    if (refresh) refresh.addEventListener("click", () => void loadAssets());
    void loadAssets();
  });
})();

