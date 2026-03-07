// dashboard.js
// Handles chart rendering and live WebSocket updates for the monitoring dashboard.

const MAX_POINTS = 10; // 10 data points at 30s intervals = ~5 min window

let currentServerId = null;
let socket = null;
let alertCount = 0;

const charts = {};

// --- Utilities ---

function fmt(bytes) {
  if (bytes == null) return "—";
  const gb = bytes / 1e9;
  return gb >= 1 ? `${gb.toFixed(1)} GB` : `${(bytes / 1e6).toFixed(0)} MB`;
}

function fmtRate(bytes) {
  if (bytes == null || bytes === 0) return "0 KB/s";
  const kbps = bytes / 1024;
  return kbps >= 1024 ? `${(kbps / 1024).toFixed(1)} MB/s` : `${kbps.toFixed(0)} KB/s`;
}

function nowLabel() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function colorFor(pct) {
  if (pct >= 90) return "#ef4444";
  if (pct >= 70) return "#f59e0b";
  return "#10b981";
}

function thresholdClass(pct) {
  if (pct >= 90) return "stat-crit";
  if (pct >= 70) return "stat-warn";
  return "stat-ok";
}

function shiftData(chart, label, ...datasets) {
  chart.data.labels.push(label);
  if (chart.data.labels.length > MAX_POINTS) chart.data.labels.shift();

  datasets.forEach((val, i) => {
    chart.data.datasets[i].data.push(val);
    if (chart.data.datasets[i].data.length > MAX_POINTS) {
      chart.data.datasets[i].data.shift();
    }
  });
  chart.update("none");
}

// --- Chart setup ---

const lineDefaults = {
  type: "line",
  options: {
    animation: false,
    responsive: true,
    interaction: { intersect: false, mode: "index" },
    plugins: { legend: { display: false } },
    scales: {
      x: { ticks: { color: "#8892a4", maxRotation: 0 }, grid: { color: "#2e3250" } },
      y: {
        min: 0, max: 100,
        ticks: { color: "#8892a4", callback: v => v + "%" },
        grid: { color: "#2e3250" },
      },
    },
  },
};

function makeLineChart(id, color) {
  const ctx = document.getElementById(id).getContext("2d");
  return new Chart(ctx, {
    ...lineDefaults,
    data: {
      labels: [],
      datasets: [{
        data: [],
        borderColor: color,
        backgroundColor: color.replace(")", ", 0.1)").replace("rgb", "rgba"),
        borderWidth: 2,
        pointRadius: 2,
        fill: true,
        tension: 0.3,
      }],
    },
    options: JSON.parse(JSON.stringify(lineDefaults.options)),
  });
}

function makeNetChart() {
  const ctx = document.getElementById("chart-net").getContext("2d");
  return new Chart(ctx, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        {
          label: "Sent",
          data: [],
          borderColor: "#6366f1",
          backgroundColor: "rgba(99,102,241,0.1)",
          borderWidth: 2, pointRadius: 2, fill: true, tension: 0.3,
        },
        {
          label: "Received",
          data: [],
          borderColor: "#10b981",
          backgroundColor: "rgba(16,185,129,0.1)",
          borderWidth: 2, pointRadius: 2, fill: true, tension: 0.3,
        },
      ],
    },
    options: {
      animation: false,
      responsive: true,
      interaction: { intersect: false, mode: "index" },
      plugins: { legend: { labels: { color: "#8892a4" } } },
      scales: {
        x: { ticks: { color: "#8892a4", maxRotation: 0 }, grid: { color: "#2e3250" } },
        y: {
          min: 0,
          ticks: { color: "#8892a4", callback: v => fmtRate(v * 1024) },
          grid: { color: "#2e3250" },
        },
      },
    },
  });
}

function makeDiskChart() {
  const ctx = document.getElementById("chart-disk").getContext("2d");
  return new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: ["Used", "Free"],
      datasets: [{
        data: [0, 100],
        backgroundColor: ["#6366f1", "#2e3250"],
        borderWidth: 0,
        hoverOffset: 4,
      }],
    },
    options: {
      animation: false,
      responsive: true,
      cutout: "70%",
      plugins: { legend: { display: false } },
    },
  });
}

function initCharts() {
  charts.cpu  = makeLineChart("chart-cpu",  "#6366f1");
  charts.mem  = makeLineChart("chart-mem",  "#10b981");
  charts.disk = makeDiskChart();
  charts.net  = makeNetChart();
}

// --- Stat card updates ---

function updateCards(d) {
  // CPU
  const cpuEl = document.getElementById("stat-cpu");
  const cpuCard = document.getElementById("card-cpu");
  cpuEl.textContent = d.cpu_percent.toFixed(1) + "%";
  cpuCard.className = `card stat-card ${thresholdClass(d.cpu_percent)}`;
  document.getElementById("stat-cpu-cores").textContent = `${d.cpu_count ?? "—"} cores`;

  // Memory
  const memEl = document.getElementById("stat-mem");
  const memCard = document.getElementById("card-mem");
  memEl.textContent = d.memory_percent.toFixed(1) + "%";
  memCard.className = `card stat-card ${thresholdClass(d.memory_percent)}`;
  document.getElementById("stat-mem-used").textContent =
    `${fmt(d.memory_used)} / ${fmt(d.memory_total)}`;

  // Disk
  const diskEl = document.getElementById("stat-disk");
  const diskCard = document.getElementById("card-disk");
  diskEl.textContent = d.disk_percent.toFixed(1) + "%";
  diskCard.className = `card stat-card ${thresholdClass(d.disk_percent)}`;
  document.getElementById("stat-disk-used").textContent =
    `${fmt(d.disk_used)} / ${fmt(d.disk_total)}`;

  // Network
  document.getElementById("stat-net").textContent =
    `↑ ${fmtRate(d.net_bytes_sent)} ↓ ${fmtRate(d.net_bytes_recv)}`;
}

function updateCharts(d, label) {
  label = label || nowLabel();

  // CPU line
  shiftData(charts.cpu, label, d.cpu_percent);
  charts.cpu.data.datasets[0].borderColor = colorFor(d.cpu_percent);

  // Memory line
  shiftData(charts.mem, label, d.memory_percent);
  charts.mem.data.datasets[0].borderColor = colorFor(d.memory_percent);

  // Disk doughnut
  const used = d.disk_percent;
  const free = 100 - used;
  charts.disk.data.datasets[0].data = [used, free];
  charts.disk.data.datasets[0].backgroundColor[0] = colorFor(used);
  charts.disk.update("none");
  document.getElementById("doughnut-label").textContent = used.toFixed(0) + "%";

  // Network area
  const sentKb  = (d.net_bytes_sent  || 0) / 1024;
  const recvKb  = (d.net_bytes_recv  || 0) / 1024;
  shiftData(charts.net, label, sentKb, recvKb);
}

// --- Load historical data on server switch ---

async function loadHistory(serverId) {
  // Clear existing chart data
  [charts.cpu, charts.mem, charts.net].forEach(c => {
    c.data.labels = [];
    c.data.datasets.forEach(ds => (ds.data = []));
    c.update("none");
  });

  const from = new Date(Date.now() - 5 * 60 * 1000).toISOString();
  const res = await fetch(`/api/servers/${serverId}/metrics?from=${from}`);
  if (!res.ok) return;
  const history = await res.json();

  history.forEach(d => {
    const label = new Date(d.collected_at + "Z").toLocaleTimeString([], {
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
    updateCharts(d, label);
  });

  if (history.length > 0) {
    updateCards(history[history.length - 1]);
  }
}

// --- Alert feed ---

function addAlert(data) {
  alertCount++;
  document.getElementById("alert-count").textContent = alertCount;

  const list = document.getElementById("alert-list");
  const empty = list.querySelector(".alert-empty");
  if (empty) empty.remove();

  const li = document.createElement("li");
  li.className = `alert-item ${data.severity || "warning"}`;
  const time = new Date().toLocaleTimeString();
  li.innerHTML = `
    <div>
      <div class="alert-msg">${data.message}</div>
      <div class="alert-time">${time}</div>
    </div>`;
  list.prepend(li);

  // Keep list from growing forever in the UI
  while (list.children.length > 20) list.removeChild(list.lastChild);
}

// --- WebSocket ---

function connect() {
  socket = io({ transports: ["websocket"] });
  const badge = document.getElementById("connection-badge");

  socket.on("connect", () => {
    badge.textContent = "Connected";
    badge.className = "badge badge-connected";
    subscribeToServer(currentServerId);
  });

  socket.on("disconnect", () => {
    badge.textContent = "Disconnected";
    badge.className = "badge badge-error";
  });

  socket.on("connect_error", () => {
    badge.textContent = "Error";
    badge.className = "badge badge-error";
  });

  socket.on("metrics_update", (data) => {
    updateCards(data);
    updateCharts(data);
  });

  socket.on("alert_fired", (data) => {
    addAlert(data);
  });
}

function subscribeToServer(serverId) {
  if (!socket || !serverId) return;
  if (currentServerId && currentServerId !== serverId) {
    socket.emit("unsubscribe", { server_id: currentServerId });
  }
  socket.emit("subscribe", { server_id: serverId });
}

// --- Server switcher ---

document.getElementById("server-select").addEventListener("change", async (e) => {
  const newId = parseInt(e.target.value, 10);
  currentServerId = newId;
  await loadHistory(newId);
  subscribeToServer(newId);
  alertCount = 0;
  document.getElementById("alert-count").textContent = "0";
  document.getElementById("alert-list").innerHTML = '<li class="alert-empty">No alerts fired yet.</li>';
});

// --- Init ---

(async function init() {
  const select = document.getElementById("server-select");
  if (!select.options.length) return;

  currentServerId = parseInt(select.value, 10);
  initCharts();
  await loadHistory(currentServerId);
  connect();
})();
