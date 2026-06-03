/* Admin requests UI: /api/v1/admin/requests */
(function () {
  "use strict";

  const state = { rows: [], q: "", status: "", logs: [] };
  const el = (id) => document.getElementById(id);

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function fmtTs(iso) {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  }

  async function fetchJson(url, opts) {
    const res = await fetch(url, Object.assign({ credentials: "same-origin" }, opts || {}));
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

  function getFiltered() {
    let rows = state.rows.slice();
    const q = state.q.trim().toLowerCase();
    if (q) rows = rows.filter((r) => JSON.stringify(r).toLowerCase().includes(q));
    if (state.status) rows = rows.filter((r) => String(r.status || "") === state.status);
    return rows;
  }

  function render() {
    const tbody = el("req-tbody");
    if (!tbody) return;
    const rows = getFiltered();
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="8" class="empty-state">No requests to show.</td></tr>`;
      return;
    }
    tbody.innerHTML = rows
      .map((r) => {
        const pending = String(r.status) === "pending";
        const approveBtn = pending
          ? `<button class="btn btn-primary btn-approve" data-id="${r.id}">Approve</button>`
          : "";
        const denyBtn = pending ? `<button class="btn btn-ghost btn-deny" data-id="${r.id}">Deny</button>` : "";
        const actions = pending ? `${approveBtn} ${denyBtn}` : "—";
        return `<tr>
          <td>${escapeHtml(fmtTs(r.requested_at))}</td>
          <td>${escapeHtml(r.requester_username || r.requester_user_id)}</td>
          <td>${escapeHtml(r.requester_department || "—")}</td>
          <td>${escapeHtml(r.target_department || "—")}</td>
          <td style="max-width:420px">${escapeHtml(r.reason || "")}</td>
          <td>${escapeHtml(r.status || "")}</td>
          <td>${escapeHtml(fmtTs(r.expires_at))}</td>
          <td>${actions}</td>
        </tr>`;
      })
      .join("");

    tbody.querySelectorAll(".btn-approve").forEach((b) => {
      b.addEventListener("click", async () => {
        const id = b.getAttribute("data-id");
        const hours = Number(prompt("Approve duration (hours):", "8") || "8");
        await fetchJson(`/api/v1/admin/requests/${id}/approve`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ duration_hours: hours }),
        });
        await load();
      });
    });
    tbody.querySelectorAll(".btn-deny").forEach((b) => {
      b.addEventListener("click", async () => {
        const id = b.getAttribute("data-id");
        await fetchJson(`/api/v1/admin/requests/${id}/deny`, { method: "POST" });
        await load();
      });
    });
  }

  async function load() {
    const data = await fetchJson("/api/v1/admin/requests");
    state.rows = Array.isArray(data.requests) ? data.requests : [];
    render();
    await renderAdminCharts();
  }

  function destroyAdminCharts() {
    if (window.adminRiskTrendChart) window.adminRiskTrendChart.destroy();
    if (window.adminSeverityChart) window.adminSeverityChart.destroy();
    if (window.adminRiskDistChart) window.adminRiskDistChart.destroy();
    if (window.adminDeptChart) window.adminDeptChart.destroy();
    window.adminRiskTrendChart = null;
    window.adminSeverityChart = null;
    window.adminRiskDistChart = null;
    window.adminDeptChart = null;
  }

  function groupByHour(logs) {
    const m = new Map();
    logs.forEach((log) => {
      const ts = log.timestamp ? new Date(log.timestamp) : null;
      if (!ts || Number.isNaN(ts.getTime())) return;
      const key = `${ts.getFullYear()}-${String(ts.getMonth() + 1).padStart(2, "0")}-${String(ts.getDate()).padStart(2, "0")} ${String(
        ts.getHours()
      ).padStart(2, "0")}:00`;
      if (!m.has(key)) m.set(key, []);
      m.get(key).push(log);
    });
    const labels = Array.from(m.keys()).sort();
    const values = labels.map((k) => {
      const rows = m.get(k) || [];
      const nums = rows.map((r) => Number(r.risk_score || 0));
      return nums.length ? nums.reduce((a, b) => a + b, 0) / nums.length : 0;
    });
    return { labels, values };
  }

  async function renderAdminCharts() {
    if (typeof Chart === "undefined") return;
    destroyAdminCharts();

    const msg = el("admin-chart-msg");
    const adminData = await fetchJson("/api/v1/logs");
    console.log(adminData);
    const logs = Array.isArray(adminData.logs) ? adminData.logs : [];
    state.logs = logs;
    if (!logs.length) {
      if (msg) msg.textContent = "No data available";
      return;
    }
    if (msg) msg.textContent = `Loaded ${logs.length} logs`;

    const trend = groupByHour(logs);
    const c1 = el("adminRiskTrendChart");
    if (c1 && trend.labels.length) {
      const gradient = c1.getContext("2d").createLinearGradient(0, 0, 0, 220);
      gradient.addColorStop(0, "rgba(124,58,237,0.45)");
      gradient.addColorStop(1, "rgba(124,58,237,0.02)");
      window.adminRiskTrendChart = new Chart(c1.getContext("2d"), {
        type: "line",
        data: {
          labels: trend.labels,
          datasets: [{ label: "Avg risk_score", data: trend.values, borderColor: "#7c3aed", backgroundColor: gradient, tension: 0.4, fill: true }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            x: { ticks: { autoSkip: true, color: "#8b9aad" }, grid: { color: "rgba(139,154,173,0.08)" } },
            y: { min: 0, max: 1, ticks: { color: "#8b9aad" }, grid: { color: "rgba(139,154,173,0.08)" } },
          },
        },
      });
    }

    const sev = { low: 0, medium: 0, high: 0, critical: 0 };
    logs.forEach((log) => {
      const s = String(log.severity || "").toLowerCase();
      if (Object.prototype.hasOwnProperty.call(sev, s)) sev[s] += 1;
    });
    const c2 = el("adminSeverityChart");
    if (c2) {
      window.adminSeverityChart = new Chart(c2.getContext("2d"), {
        type: "bar",
        data: {
          labels: ["low", "medium", "high", "critical"],
          datasets: [
            { data: [sev.low, sev.medium, sev.high, sev.critical], backgroundColor: ["#22c55e", "#facc15", "#f97316", "#ef4444"], borderRadius: 8 },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { ticks: { color: "#8b9aad" }, grid: { color: "rgba(139,154,173,0.08)" } },
            y: { ticks: { color: "#8b9aad" }, grid: { color: "rgba(139,154,173,0.08)" }, beginAtZero: true },
          },
        },
      });
    }

    const rd = { LOW: 0, MEDIUM: 0, HIGH: 0, CRITICAL: 0 };
    logs.forEach((log) => {
      const b = String(log.risk_band || "").toUpperCase();
      if (Object.prototype.hasOwnProperty.call(rd, b)) rd[b] += 1;
    });
    const c3 = el("adminRiskDistChart");
    if (c3) {
      window.adminRiskDistChart = new Chart(c3.getContext("2d"), {
        type: "doughnut",
        data: {
          labels: ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
          datasets: [{ data: [rd.LOW, rd.MEDIUM, rd.HIGH, rd.CRITICAL], backgroundColor: ["#22c55e", "#facc15", "#f97316", "#ef4444"], borderWidth: 0 }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { position: "right", labels: { color: "#8b9aad" } } },
          cutout: "60%",
        },
      });
    }

    const deptMap = {};
    logs.forEach((log) => {
      const d = log.asset_department || log.department || (log.asset && log.asset.department) || "Unknown";
      if (!deptMap[d]) deptMap[d] = 0;
      deptMap[d] += 1;
    });
    const c4 = el("adminDeptChart");
    if (c4) {
      const labels = Object.keys(deptMap);
      const values = Object.values(deptMap);
      window.adminDeptChart = new Chart(c4.getContext("2d"), {
        type: "pie",
        data: {
          labels: labels,
          datasets: [{ data: values, backgroundColor: ["#3b82f6", "#10b981", "#f59e0b", "#6366f1", "#ec4899"], borderWidth: 0 }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { position: "right", labels: { color: "#8b9aad" } } },
        },
      });
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const s = el("req-search");
    const st = el("req-status");
    if (s) {
      s.addEventListener("input", () => {
        state.q = s.value;
        render();
      });
    }
    if (st) {
      st.addEventListener("change", () => {
        state.status = st.value;
        render();
      });
    }
    const refresh = el("btn-refresh-reqs");
    if (refresh) refresh.addEventListener("click", () => void load());
    void load();
  });
})();

