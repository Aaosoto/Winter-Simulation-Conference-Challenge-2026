const CSV_FILES = {
  port: "Port_Waiting_Statistics.csv",
  route: "Service_Route_Utilization.csv",
  waitingMatrix: "Average_Origin_Waiting_TEU_By_OD.csv",
  transitionMatrix: "Average_In_Transit_TEU_By_OD.csv",
  completedMatrix: "Cumulative_Completed_TEU_By_OD.csv",
  vessel: "Average_Vessel_State_Counts.csv",
  attPeriod: "ATT_By_Statistics_Interval.csv"
};
const OPTIONAL_CSV_KEYS = new Set();
const BASELINE_ATT_FILENAMES = [
  "Baseline_ATT_By_Statistics_Interval.csv",
  "ATT_By_Period_For_baseline.csv"
];
const BASELINE_ATT_URLS = [
  `../Output/${encodeURIComponent(BASELINE_ATT_FILENAMES[0])}`,
  `../baseline_output/${encodeURIComponent(BASELINE_ATT_FILENAMES[0])}`
];

const PORT_LOCATIONS = {
  "Shanghai": [31.2304, 121.4737],
  "Singapore": [1.3521, 103.8198],
  "Shenzhen": [22.5431, 114.0579],
  "Qingdao": [36.0671, 120.3826],
  "Busan": [35.1796, 129.0756],
  "Tianjin": [39.3434, 117.3616],
  "Xiamen": [24.4798, 118.0894],
  "Kaohsiung": [22.6273, 120.3014],
  "Laem Chabang": [13.0827, 100.8832],
  "Ho Chi Minh City": [10.8231, 106.6297],
  "Jakarta": [-6.2088, 106.8456],
  "Colombo": [6.9271, 79.8612],
  "Jebel Ali": [24.9857, 55.0272],
  "Rotterdam": [51.9244, 4.4777],
  "Hamburg": [53.5511, 9.9937],
  "Piraeus": [37.9429, 23.6469],
  "Los Angeles": [33.7405, -118.2728],
  "New Jersey": [40.7357, -74.1724],
  "Tanger Med": [35.8919, -5.5008],
  "Cartagena": [10.3910, -75.4794]
};

let dashboardData = null;
let flowSort = "teu";
let flowAsc = false;
let portWaitingView = "bar";
let vesselWaitingView = "bar";
let heatmapView = "waiting";

document.addEventListener("DOMContentLoaded", () => {
  bindNavigation();
  bindActions();
  loadFromCsvFolder();
});

async function loadFromCsvFolder() {
  try {
    const loaded = {};
    for (const [key, filename] of Object.entries(CSV_FILES)) {
      const response = await fetch(`../Output/${encodeURIComponent(filename)}`);
      if (!response.ok) {
        if (OPTIONAL_CSV_KEYS.has(key)) {
          loaded[key] = [];
          continue;
        }
        throw new Error(`Unable to load ${filename}`);
      }
      loaded[key] = parseCsv(await response.text());
    }
    loaded.baselineAttPeriod = await loadBaselineAttFromUrls();
    if (!loaded.baselineAttPeriod) {
      throw new Error("Unable to load baseline ATT");
    }

    applyLoadedCsv(loaded, "Loaded from ../Output");
  } catch (error) {
    document.getElementById("fallbackNotice").classList.add("visible");
    renderEmptyState();
  }
}

function bindNavigation() {
  document.querySelectorAll(".tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach(item => item.classList.remove("active"));
      document.querySelectorAll(".page").forEach(item => item.classList.remove("active"));

      tab.classList.add("active");
      document.getElementById(tab.dataset.page).classList.add("active");
      setTimeout(resizePlots, 100);
    });
  });
}

function bindActions() {
  const folderInput = document.getElementById("folderInput");
  folderInput.addEventListener("click", () => {
    // Allow re-selecting the same Output folder to trigger a fresh reload.
    folderInput.value = "";
  });
  folderInput.addEventListener("change", handleFolderSelection);
  document.getElementById("openPortBtn").addEventListener("click", openSelectedPort);
  document.getElementById("flowSearch").addEventListener("input", renderFlowTable);
  document.getElementById("closeModalBtn").addEventListener("click", closeModal);
  document.getElementById("heatmapInsightBtn").addEventListener("click", showHeatmapInsight);
  document.getElementById("completionInsightBtn").addEventListener("click", showCompletionInsight);
  document.getElementById("bottleneckInsightBtn").addEventListener("click", showBottleneckInsight);
  bindViewToggle("[data-port-waiting-view]", value => {
    portWaitingView = value;
    renderPortWaitingChart();
  });
  bindViewToggle("[data-vessel-waiting-view]", value => {
    vesselWaitingView = value;
    renderVesselWaitingChart();
  });
  bindViewToggle("[data-heatmap-view]", value => {
    heatmapView = value;
    renderHeatmap();
  });
  document.querySelectorAll("th[data-sort]").forEach(header => {
    header.addEventListener("click", () => sortFlows(header.dataset.sort));
  });
}

function bindViewToggle(selector, onChange) {
  document.querySelectorAll(selector).forEach(button => {
    button.addEventListener("click", () => {
      document.querySelectorAll(selector).forEach(item => item.classList.remove("active"));
      button.classList.add("active");
      onChange(button.dataset.portWaitingView || button.dataset.vesselWaitingView || button.dataset.heatmapView);
    });
  });
}

async function handleFolderSelection(event) {
  const files = [...event.target.files];
  const loaded = {};

  try {
    for (const [key, filename] of Object.entries(CSV_FILES)) {
      const file = findCsvFile(files, filename);
      if (!file) {
        if (OPTIONAL_CSV_KEYS.has(key)) {
          loaded[key] = [];
          continue;
        }
        showModal("Missing CSV", `Could not find ${filename} in the selected folder.`);
        return;
      }
      loaded[key] = parseCsv(await file.text());
    }

    const baselineFile = findCsvFile(files, BASELINE_ATT_FILENAMES);
    loaded.baselineAttPeriod = baselineFile
      ? parseCsv(await baselineFile.text())
      : await loadBaselineAttFromUrls();

    if (!loaded.baselineAttPeriod) {
      showModal(
        "Missing Baseline ATT",
        `Could not find ${BASELINE_ATT_FILENAMES[0]} in the selected folder, and could not load it from Output or baseline_output.`
      );
      return;
    }

    applyLoadedCsv(loaded, "Loaded from selected Output folder");
  } catch (error) {
    showModal("Invalid Output", `Could not parse the selected Output folder: ${error.message}`);
  }
}

function findCsvFile(files, names) {
  const expectedNames = Array.isArray(names) ? names : [names];
  return files.find(file =>
    expectedNames.some(name => file.name.toLowerCase() === name.toLowerCase())
  );
}

async function loadBaselineAttFromUrls() {
  for (const url of BASELINE_ATT_URLS) {
    try {
      const response = await fetch(url, { cache: "no-store" });
      if (response.ok) {
        return parseCsv(await response.text());
      }
    } catch (error) {
      // Direct file:// access can block fetch(). In that case, folder upload can
      // still provide the baseline file through the user's explicit selection.
    }
  }
  return null;
}

function applyLoadedCsv(csv, sourceLabel) {
  dashboardData = normalizeData(csv);
  dashboardData.rawAttPeriod = csv.attPeriod || null;
  document.getElementById("fallbackNotice").classList.remove("visible");
  renderDashboard();
  requestAnimationFrame(resizePlots);
}

function normalizeData(csv) {
  const portStats = csv.port
    .filter(row => row.Port && row.Port !== "TOTAL")
    .map(row => ({
      port: row.Port,
      originWaiting: parseNumber(row["Origin Waiting TEU"]),
      transshipmentWaiting: parseNumber(row["Transshipment Waiting TEU"]),
      waitingTEU: parseNumber(row["Total Waiting TEU"]),
      vesselsWaiting: parseNumber(row["Vessels Waiting"]),
      congestionScore: 0,
      congestionLevel: "Stable"
    }))
    .sort((a, b) => b.waitingTEU - a.waitingTEU);

  assignPercentileCongestionLevels(portStats);

  const routeStats = csv.route
    .filter(row => row.Route)
    .map(row => ({
      route: row.Route,
      name: row.Name || "",
      capacity: parseNumber(row["Avg Capacity TEU"]),
      carried: parseNumber(row["Avg Carried TEU"]),
      utilization: parseNumber(row.Utilization)
    }));

  const vesselState = csv.vessel
    .filter(row => row.Metric && row.Metric !== "TOTAL average active/port vessels")
    .map(row => ({
      state: row.Metric.replace("Average vessels ", "").replace(" at port", ""),
      value: parseNumber(row["Average Count"])
    }));

  const waitingMatrix = parseMatrix(csv.waitingMatrix);
  const transitionMatrix = parseMatrix(csv.transitionMatrix);
  const completedMatrix = parseMatrix(csv.completedMatrix);
  const networkLinks = buildNetworkLinks(waitingMatrix, 30);
  const attPeriods = parseAttPeriods(csv.attPeriod);
  const baselineAttPeriods = parseAttPeriods(csv.baselineAttPeriod);
  const resiliencePeriods = calculateResiliencePeriods(
    baselineAttPeriods,
    attPeriods
  );

  return {
    portStats,
    routeStats,
    vesselState,
    waitingMatrix,
    transitionMatrix,
    completedMatrix,
    networkLinks,
    attPeriods,
    baselineAttPeriods,
    resiliencePeriods
  };
}

function parseAttPeriods(rows) {
  if (!rows || rows.length === 0) return [];

  const sample = rows[0];
  const keys = Object.keys(sample);
  const keyMap = {};
  for (const k of keys) {
    const normalized = k.trim().toLowerCase();
    if (normalized.includes('periodindex')) keyMap.periodIndex = k;
    if (normalized.includes('startday')) keyMap.startDay = k;
    if (normalized.includes('endday')) keyMap.endDay = k;
    if (normalized.includes('averagetransporttime')) keyMap.averageTransportTime = k;
  }

  keyMap.periodIndex = keyMap.periodIndex || keys.find(k => /^\s*period\s*index\s*$/i.test(k));
  keyMap.startDay = keyMap.startDay || keys.find(k => /^\s*start\s*day\s*$/i.test(k));
  keyMap.endDay = keyMap.endDay || keys.find(k => /^\s*end\s*day\s*$/i.test(k));
  keyMap.averageTransportTime = keyMap.averageTransportTime || keys.find(
    k => /^\s*average\s*transport\s*time\s*$/i.test(k)
  );

  const periods = [];
  for (const row of rows) {
    const indexRaw = keyMap.periodIndex ? row[keyMap.periodIndex] : row.PeriodIndex || row.periodIndex;
    if (indexRaw == null || indexRaw === '') continue;

    const periodIndex = parseNumber(indexRaw);
    const start = keyMap.startDay ? parseNumber(row[keyMap.startDay]) : parseNumber(row.StartDay || row.startDay);
    const end = keyMap.endDay ? parseNumber(row[keyMap.endDay]) : parseNumber(row.EndDay || row.endDay);
    const averageTransportTime = keyMap.averageTransportTime
      ? parseNumber(row[keyMap.averageTransportTime])
      : parseNumber(
        row.AverageTransportTime
        || row.averageTransportTime
      );

    if (Number.isFinite(periodIndex) && Number.isFinite(start) && Number.isFinite(end) && Number.isFinite(averageTransportTime)) {
      periods.push({
        periodIndex,
        startDay: start,
        endDay: end,
        averageTransportTime
      });
    }
  }

  const sorted = periods.sort((a, b) => a.periodIndex - b.periodIndex);
  console.debug(`Parsed ${sorted.length} KPI periods`);
  return sorted;
}

function calculateResiliencePeriods(baselinePeriods, disruptionPeriods) {
  const disruptionByIndex = new Map(
    disruptionPeriods.map(period => [period.periodIndex, period])
  );
  const periods = [];
  let cumulativeLoss = 0;

  for (const baseline of baselinePeriods) {
    const disruption = disruptionByIndex.get(baseline.periodIndex);
    if (!disruption) {
      console.warn(`Missing disruption ATT period ${baseline.periodIndex}`);
      continue;
    }
    if (
      baseline.startDay !== disruption.startDay
      || baseline.endDay !== disruption.endDay
    ) {
      console.warn(
        `Skipping ATT period ${baseline.periodIndex}: baseline and disruption day ranges differ`
      );
      continue;
    }

    const baselineAtt = baseline.averageTransportTime;
    const disruptionAtt = disruption.averageTransportTime;
    const attRatio = disruptionAtt <= 0
      ? (baselineAtt <= 0 ? 1 : 0)
      : baselineAtt / disruptionAtt;
    const performanceLoss = 1 - attRatio;
    const periodDays = baseline.endDay - baseline.startDay + 1;
    const periodResilienceLoss = performanceLoss * periodDays;
    cumulativeLoss += periodResilienceLoss;

    periods.push({
      periodIndex: baseline.periodIndex,
      startDay: baseline.startDay,
      endDay: baseline.endDay,
      baselineAtt,
      disruptionAtt,
      attRatio,
      performanceLoss,
      periodResilienceLoss,
      cumulativeLoss
    });
  }

  return periods;
}

function parseMatrix(rows) {
  if (rows.length === 0) {
    return { origins: [], destinations: [], values: [] };
  }

  const firstColumn = Object.keys(rows[0])[0];
  const destinations = Object.keys(rows[0]).filter(key => key !== firstColumn);
  const origins = rows.map(row => row[firstColumn]).filter(Boolean);
  const values = rows
    .filter(row => row[firstColumn])
    .map(row => destinations.map(destination => {
      const value = row[destination];
      return value === "-" || value === "" ? 0 : parseNumber(value);
    }));

  return { origins, destinations, values };
}

function buildNetworkLinks(matrix, limit) {
  const links = [];

  matrix.origins.forEach((origin, rowIndex) => {
    matrix.destinations.forEach((destination, columnIndex) => {
      const teu = matrix.values[rowIndex][columnIndex];
      if (teu > 0) {
        links.push({
          from: origin,
          to: destination,
          teu,
          waitingShare: 0,
          level: "Stable"
        });
      }
    });
  });

  const totalWaitingTeu = links.reduce((sum, link) => sum + link.teu, 0);
  const displayedLinks = links.sort((a, b) => b.teu - a.teu).slice(0, limit);
  assignFlowLevels(displayedLinks, totalWaitingTeu);
  return displayedLinks;
}

function renderDashboard() {
  renderSummaryCards();
  renderPortControls();
  renderPortWaitingChart();
  renderVesselWaitingChart();
  renderRouteBar();
  renderFlowTable();
  renderVesselCharts();
  renderHeatmap();
  renderAttPeriodChart();
  renderResilienceLossChart();
}

function renderEmptyState() {
  const emptyLayout = { margin: { l: 20, r: 20, t: 20, b: 20 }, annotations: [{ text: "Load CSV output to render this chart", showarrow: false }] };
    ["portBar", "vesselWaitingChart", "routeBar", "vesselPie", "vesselTimeline", "heatmap", "attPeriodTrend", "resilienceLossChart"].forEach(id => {
    Plotly.newPlot(id, [], emptyLayout, { displayModeBar: false, responsive: true });
  });
}

function renderSummaryCards() {
  const totalRow = dashboardData.portStats.reduce((acc, item) => ({
    waitingTEU: acc.waitingTEU + item.waitingTEU
  }), { waitingTEU: 0 });

  const routeTotal = dashboardData.routeStats.find(route => route.route === "TOTAL");
  const vesselsWaiting = dashboardData.vesselState.find(item => item.state === "waiting for berth");
  const mainRisk = dashboardData.portStats.reduce(
    (highest, port) => !highest || port.congestionScore > highest.congestionScore ? port : highest,
    null
  );
  const finalResilience = dashboardData.resiliencePeriods.length
    ? dashboardData.resiliencePeriods[dashboardData.resiliencePeriods.length - 1]
    : null;

  document.getElementById("mainRiskPort").textContent = mainRisk ? mainRisk.port : "-";
  document.getElementById("mainRiskDetail").textContent = mainRisk
    ? `50% waiting cargo + 50% vessels waiting`
    : "Highest congestion score";
  document.getElementById("totalWaitingTeu").textContent = formatCompact(totalRow.waitingTEU);
  document.getElementById("totalVesselsWaiting").textContent = vesselsWaiting
    ? vesselsWaiting.value.toFixed(2)
    : "-";
  document.getElementById("networkUtilization").textContent = routeTotal ? `${routeTotal.utilization.toFixed(2)}%` : "-";
  document.getElementById("cumulativeResilienceLoss").textContent = finalResilience
    ? finalResilience.cumulativeLoss.toFixed(2)
    : "-";
  document.getElementById("cumulativeResilienceLossDetail").textContent =
    "Lower is better";
}

function renderPortControls() {
  const select = document.getElementById("portSelect");
  select.innerHTML = dashboardData.portStats.map(port => `<option>${escapeHtml(port.port)}</option>`).join("");
  select.onchange = () => updateSelectedPort(select.value);

  if (dashboardData.portStats.length > 0) {
    updateSelectedPort(dashboardData.portStats[0].port);
  }
}

function updateSelectedPort(name) {
  const port = dashboardData.portStats.find(item => item.port === name);
  if (!port) {
    return;
  }

  const level = classifyPort(port);
  document.getElementById("selectedPortName").textContent = port.port;
  document.getElementById("selectedTEU").textContent = formatNumber(port.waitingTEU);
  document.getElementById("selectedVessels").textContent = port.vesselsWaiting.toFixed(2);

  const badge = document.getElementById("selectedBadge");
  badge.textContent = level;
  badge.className = `badge ${levelClass(level)}`;

  document.getElementById("selectedInterpretation").textContent =
    `${port.port} has ${formatNumber(port.waitingTEU)} TEU of waiting cargo and ${port.vesselsWaiting.toFixed(2)} vessels waiting. Status: ${level}, based on percentile rank within the current scenario.`;
  document.getElementById("portSelect").value = port.port;
}

function renderPortWaitingChart() {
  if (portWaitingView === "map") {
    renderPortMap("portBar", "waitingTEU", "Combined waiting cargo", "#ea580c", "TEU");
    return;
  }

  const topPorts = dashboardData.portStats.slice(0, 12).reverse();
  const totalWaiting = topPorts.map(port => port.waitingTEU);

  Plotly.newPlot("portBar", [
    {
      type: "bar",
      orientation: "h",
      name: "Origin waiting cargo (TEU)",
      y: topPorts.map(port => port.port),
      x: topPorts.map(port => port.originWaiting),
      customdata: totalWaiting,
      marker: { color: "#f97316" },
      hovertemplate: "%{y}<br>Origin waiting cargo: %{x:,} TEU<br>Total waiting cargo: %{customdata:,} TEU<extra></extra>"
    },
    {
      type: "bar",
      orientation: "h",
      name: "Transshipment waiting cargo (TEU)",
      y: topPorts.map(port => port.port),
      x: topPorts.map(port => port.transshipmentWaiting),
      customdata: totalWaiting,
      marker: { color: "#0f766e" },
      hovertemplate: "%{y}<br>Transshipment waiting cargo: %{x:,} TEU<br>Total waiting cargo: %{customdata:,} TEU<extra></extra>"
    }
  ], {
    barmode: "stack",
    margin: { l: 120, r: 20, t: 38, b: 45 },
    xaxis: { title: "Waiting Cargo (TEU)" },
    legend: { orientation: "h", x: 0, y: 1.14, yanchor: "bottom" },
    height: 380,
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff"
  }, { displayModeBar: false, responsive: true });

  document.getElementById("portBar").on("plotly_click", event => updateSelectedPort(event.points[0].y));
}

function renderVesselWaitingChart() {
  if (vesselWaitingView === "map") {
    renderPortMap("vesselWaitingChart", "vesselsWaiting", "Vessels waiting", "#0369a1", "vessels");
    return;
  }

  const ports = dashboardData.portStats
    .slice()
    .sort((a, b) => b.vesselsWaiting - a.vesselsWaiting)
    .slice(0, 12)
    .reverse();

  Plotly.newPlot("vesselWaitingChart", [{
    type: "bar",
    orientation: "h",
    y: ports.map(port => port.port),
    x: ports.map(port => port.vesselsWaiting),
    marker: { color: ports.map(port => levelColor(classifyPort(port))) },
    text: ports.map(port => port.vesselsWaiting.toFixed(2)),
    hovertemplate: "%{y}<br>Vessels waiting: %{x:.2f}<extra></extra>"
  }], {
    margin: { l: 120, r: 20, t: 10, b: 45 },
    xaxis: { title: "Average vessels waiting" },
    height: 380,
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff"
  }, { displayModeBar: false, responsive: true });

  document.getElementById("vesselWaitingChart").on("plotly_click", event => updateSelectedPort(event.points[0].y));
}

function renderPortMap(targetId, metric, label, color, unit) {
  const ports = dashboardData.portStats
    .map(port => {
      const location = PORT_LOCATIONS[port.port];
      return location ? { ...port, latitude: location[0], longitude: location[1] } : null;
    })
    .filter(Boolean);
  const maxValue = Math.max(...ports.map(port => port[metric]), 1);

  Plotly.newPlot(targetId, [{
    type: "scattergeo",
    mode: "markers",
    lat: ports.map(port => port.latitude),
    lon: ports.map(port => port.longitude),
    text: ports.map(port => port.port),
    customdata: ports.map(port => port[metric]),
    marker: {
      size: ports.map(port => 8 + 36 * Math.sqrt(Math.max(port[metric], 0) / maxValue)),
      color,
      opacity: .74,
      line: { color: "#172033", width: 1 }
    },
    hovertemplate: `%{text}<br>${label}: %{customdata:,.2f} ${unit}<extra></extra>`
  }], {
    margin: { l: 10, r: 10, t: 10, b: 10 },
    height: 380,
    geo: {
      projection: { type: "natural earth" },
      showland: true,
      landcolor: "#f1f5f9",
      showocean: true,
      oceancolor: "#e0f2fe",
      showcountries: true,
      countrycolor: "#cbd5e1",
      coastlinecolor: "#94a3b8"
    },
    paper_bgcolor: "#ffffff"
  }, { displayModeBar: false, responsive: true });

  document.getElementById(targetId).on("plotly_click", event => updateSelectedPort(event.points[0].text));
}

function renderRouteBar() {
  const routes = dashboardData.routeStats.filter(route => route.route !== "TOTAL");
  const utilizationAxis = calculateUtilizationAxis(routes);

  Plotly.newPlot("routeBar", [{
    type: "bar",
    x: routes.map(route => route.route),
    y: routes.map(route => route.utilization),
    text: routes.map(route => `${route.utilization.toFixed(2)}%`),
    marker: { color: routes.map(route => utilizationColor(route.utilization)) },
    customdata: routes.map(route => [route.name, route.capacity, route.carried]),
    hovertemplate: "%{x} %{customdata[0]}<br>Utilization: %{y:.2f}%<br>Capacity: %{customdata[1]:,}<br>Carried: %{customdata[2]:,}<extra></extra>"
  }], {
    margin: { l: 55, r: 20, t: 10, b: 60 },
    yaxis: {
      range: [0, utilizationAxis.max],
      dtick: utilizationAxis.tick,
      tick0: 0,
      title: "Utilization %",
      gridcolor: "#e2e8f0"
    },
    height: 380,
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff"
  }, { displayModeBar: false, responsive: true });

  document.getElementById("routeBar").on("plotly_click", event => {
    const route = routes.find(item => item.route === event.points[0].x);
    showModal(
      `${route.route} ${route.name}`,
      `Average capacity: ${formatNumber(route.capacity)} TEU. Average carried: ${formatNumber(route.carried)} TEU. Utilization: ${route.utilization.toFixed(2)}%.`
    );
  });
}

function calculateUtilizationAxis(routes) {
  const values = routes
    .map(route => route.utilization)
    .filter(value => Number.isFinite(value) && value >= 0);
  const maxValue = values.length ? Math.max(...values) : 0;

  if (maxValue <= 0) {
    return { max: 1, tick: 0.2 };
  }

  const paddedMax = maxValue * 1.18;
  const tick = niceAxisStep(paddedMax / 5);
  return {
    max: Math.max(tick, Math.ceil(paddedMax / tick) * tick),
    tick
  };
}

function niceAxisStep(rawStep) {
  if (!Number.isFinite(rawStep) || rawStep <= 0) {
    return 1;
  }

  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const normalized = rawStep / magnitude;
  let niceNormalized = 10;

  if (normalized <= 1) {
    niceNormalized = 1;
  } else if (normalized <= 2) {
    niceNormalized = 2;
  } else if (normalized <= 2.5) {
    niceNormalized = 2.5;
  } else if (normalized <= 5) {
    niceNormalized = 5;
  }

  return niceNormalized * magnitude;
}

function renderFlowTable() {
  if (!dashboardData) {
    return;
  }

  const query = document.getElementById("flowSearch").value.toLowerCase();
  const rows = dashboardData.networkLinks
    .filter(link => `${link.from} ${link.to} ${link.level}`.toLowerCase().includes(query))
    .sort((a, b) => {
      const left = a[flowSort];
      const right = b[flowSort];
      const result = left > right ? 1 : -1;
      return result * (flowAsc ? 1 : -1);
    });

  document.getElementById("flowTable").innerHTML = rows.map(link => `
    <tr>
      <td>${escapeHtml(link.from)}</td>
      <td>${escapeHtml(link.to)}</td>
      <td class="num">${formatNumber(link.teu)}</td>
      <td><span class="badge ${levelClass(link.level)}">${link.level}</span></td>
    </tr>
  `).join("");
}

function renderVesselCharts() {
  const states = dashboardData.vesselState;

  Plotly.newPlot("vesselPie", [{
    type: "pie",
    labels: states.map(item => toTitleCase(item.state)),
    values: states.map(item => item.value),
    hole: .38,
    textinfo: "percent",
    textposition: "inside",
    hovertemplate: "%{label}: %{value:.2f}<extra></extra>"
  }], {
    margin: { l: 10, r: 10, t: 10, b: 70 },
    height: 320,
    showlegend: true,
    legend: { orientation: "h", x: .5, xanchor: "center", y: -.12, yanchor: "top" },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff"
  }, { displayModeBar: false, responsive: true });

  Plotly.newPlot("vesselTimeline", [{
    type: "bar",
    orientation: "h",
    y: states.map(item => toTitleCase(item.state)),
    x: states.map(item => item.value),
    text: states.map(item => item.value.toFixed(2)),
    textposition: "inside",
    marker: { color: ["#64748b", "#ef4444", "#0284c7"] },
    hovertemplate: "%{y}: %{x:.2f}<extra></extra>"
  }], {
    margin: { l: 135, r: 20, t: 20, b: 45 },
    height: 320,
    xaxis: { title: "Average count", gridcolor: "#e2e8f0" },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff"
  }, { displayModeBar: false, responsive: true });
}

function renderHeatmap() {
  const configs = {
    waiting: {
      matrix: dashboardData.waitingMatrix,
      description: "Waiting cargo (TEU) by origin-destination pair.",
      colorScale: "YlOrRd",
      suffix: " TEU"
    },
    transition: {
      matrix: dashboardData.transitionMatrix,
      description: "Average in-transition TEU by origin-destination pair.",
      colorScale: "YlOrRd",
      suffix: " TEU"
    },
    completed: {
      matrix: dashboardData.completedMatrix,
      description: "Completed TEU by origin-destination pair.",
      colorScale: "YlOrRd",
      suffix: " TEU"
    }
  };
  const config = configs[heatmapView] || configs.waiting;
  const matrix = config.matrix;
  document.getElementById("heatmapDescription").textContent = config.description;

  Plotly.newPlot("heatmap", [{
    type: "heatmap",
    x: matrix.destinations,
    y: matrix.origins,
    z: matrix.values,
    colorscale: config.colorScale,
    reversescale: true,
    colorbar: { thickness: 14, len: .78, x: 1.03, y: .52 },
    hovertemplate: `Origin %{y}<br>Destination %{x}<br>Value: %{z:,.1f}${config.suffix}<extra></extra>`
  }], {
    margin: { l: 120, r: 85, t: 20, b: 115 },
    height: 430,
    xaxis: { automargin: true, tickangle: -35, tickfont: { size: 12 } },
    yaxis: { automargin: true, tickfont: { size: 12 } },
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff"
  }, { displayModeBar: false, responsive: true });
}

function renderAttPeriodChart() {
  const periods = (dashboardData && dashboardData.attPeriods) || [];
  const baselinePeriods = (dashboardData && dashboardData.baselineAttPeriods) || [];
  const attValues = periods
    .concat(baselinePeriods)
    .map(period => period.averageTransportTime)
    .filter(Number.isFinite);
  const attMin = attValues.length ? Math.min(...attValues) : 0;
  const attMax = attValues.length ? Math.max(...attValues) : 1;
  const attRange = Math.max(attMax - attMin, 10);
  const attPadding = Math.max(5, attRange * 0.30);
  const yMin = Math.max(0, attMin - attPadding);
  const yMax = attMax + attPadding;

  Plotly.newPlot("attPeriodTrend", [
    {
      type: "scatter",
      mode: "lines+markers",
      name: "Disruption ATT",
      x: periods.map(period => period.endDay),
      y: periods.map(period => period.averageTransportTime),
      line: { color: "#f59e0b", width: 3 },
      marker: { size: 5, color: "#b45309" },
      hovertemplate: "Day %{x}<br>Disruption ATT: %{y:.2f} days<extra></extra>"
    },
    {
      type: "scatter",
      mode: "lines+markers",
      name: "Baseline ATT",
      x: baselinePeriods.map(period => period.endDay),
      y: baselinePeriods.map(period => period.averageTransportTime),
      line: { color: "#2563eb", width: 3, dash: "dash" },
      marker: { size: 5, color: "#1d4ed8" },
      hovertemplate: "Day %{x}<br>Baseline ATT: %{y:.2f} days<extra></extra>"
    }
  ], {
    margin: { l: 70, r: 30, t: 20, b: 60 },
    xaxis: { title: "Simulation day", gridcolor: "#e2e8f0" },
    yaxis: {
      title: "Average transport time (days)",
      range: [yMin, yMax],
      gridcolor: "#e2e8f0"
    },
    height: 420,
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    legend: { orientation: "h", y: 1.12 }
  }, { displayModeBar: true, responsive: true });
}

function renderResilienceLossChart() {
  const periods = (dashboardData && dashboardData.resiliencePeriods) || [];
  const days = periods.map(period => period.endDay);
  const qValues = periods.map(period => period.attRatio);
  const normalPerformance = periods.map(() => 1);
  const finiteQValues = qValues.filter(Number.isFinite);
  const qMin = finiteQValues.length ? Math.min(...finiteQValues, 1) : 0;
  const qMax = finiteQValues.length ? Math.max(...finiteQValues, 1) : 1;
  const qPadding = Math.max(0.05, (qMax - qMin) * 0.15);
  const yMin = Math.max(0, qMin - qPadding);
  const yMax = qMax + qPadding;

  Plotly.newPlot("resilienceLossChart", [
    {
      type: "scatter",
      mode: "lines+markers",
      name: "Performance Q(t)",
      x: days,
      y: qValues,
      line: { color: "#dc2626", width: 3, shape: "spline" },
      marker: { size: 6, color: "#dc2626" },
      hovertemplate: "Day %{x}<br>Q(t): %{y:.3f}<extra></extra>"
    },
    {
      type: "scatter",
      mode: "lines",
      name: "Normal Performance",
      x: days,
      y: normalPerformance,
      line: { color: "#172033", width: 2, dash: "dash" },
      fill: "tonexty",
      fillcolor: "rgba(148, 163, 184, 0.30)",
      hoverinfo: "skip"
    }
  ], {
    margin: { l: 70, r: 30, t: 20, b: 60 },
    xaxis: { title: "Simulation day", gridcolor: "#e2e8f0" },
    yaxis: {
      title: "Performance, Q(t)",
      range: [yMin, yMax],
      gridcolor: "#e2e8f0"
    },
    height: 420,
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    legend: { orientation: "h", y: 1.12 }
  }, { displayModeBar: true, responsive: true });
}

function sortFlows(key) {
  flowAsc = flowSort === key ? !flowAsc : false;
  flowSort = key;
  renderFlowTable();
}

function openSelectedPort() {
  const portName = document.getElementById("portSelect").value;
  const port = dashboardData.portStats.find(item => item.port === portName);
  if (!port) {
    return;
  }

  showModal(
    `${port.port} Detailed Status`,
    `Origin waiting cargo: ${formatNumber(port.originWaiting)} TEU. Transshipment waiting cargo: ${formatNumber(port.transshipmentWaiting)} TEU. Total waiting cargo: ${formatNumber(port.waitingTEU)} TEU. Vessels waiting: ${port.vesselsWaiting.toFixed(2)}. Congestion score percentile class: ${port.congestionLevel}.`
  );
}

function showHeatmapInsight() {
  const views = {
    waiting: { matrix: dashboardData.waitingMatrix, label: "waiting cargo", suffix: " TEU" },
    transition: { matrix: dashboardData.transitionMatrix, label: "average in-transition TEU", suffix: " TEU" },
    completed: { matrix: dashboardData.completedMatrix, label: "completed TEU", suffix: " TEU" },
  };
  const view = views[heatmapView] || views.waiting;
  const top = findMatrixMaximum(view.matrix);
  showModal(
    "OD Heatmap",
    top
      ? `The highest ${view.label} OD pair is ${top.from} to ${top.to}, with ${top.value.toFixed(0)}${view.suffix}.`
      : "No positive OD flow is available in the selected matrix."
  );
}

function showCompletionInsight() {
  const waiting = sumMatrix(dashboardData.waitingMatrix);
  const transition = sumMatrix(dashboardData.transitionMatrix);
  const completed = sumMatrix(dashboardData.completedMatrix);
  showModal(
    "Cargo Flow Summary",
    `Average waiting cargo: ${formatNumber(waiting)} TEU. Average in-transition cargo: ${formatNumber(transition)} TEU. Cumulative completed cargo: ${formatNumber(completed)} TEU.`
  );
}

function findMatrixMaximum(matrix) {
  let maximum = null;
  matrix.values.forEach((row, rowIndex) => {
    row.forEach((value, columnIndex) => {
      if (value > 0 && (!maximum || value > maximum.value)) {
        maximum = {
          from: matrix.origins[rowIndex],
          to: matrix.destinations[columnIndex],
          value
        };
      }
    });
  });
  return maximum;
}

function showBottleneckInsight() {
  const port = dashboardData.portStats.reduce(
    (highest, item) => !highest || item.congestionScore > highest.congestionScore ? item : highest,
    null
  );
  showModal(
    "Bottleneck Detection",
    port
      ? `${port.port} is the main risk port by the combined congestion score: 50% normalized waiting cargo and 50% normalized vessels waiting. It has ${formatNumber(port.waitingTEU)} TEU of waiting cargo and ${port.vesselsWaiting.toFixed(2)} vessels waiting.`
      : "No port statistics are loaded."
  );
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let insideQuotes = false;

  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    const next = text[i + 1];

    if (char === '"' && insideQuotes && next === '"') {
      field += '"';
      i++;
    } else if (char === '"') {
      insideQuotes = !insideQuotes;
    } else if (char === "," && !insideQuotes) {
      row.push(field);
      field = "";
    } else if ((char === "\n" || char === "\r") && !insideQuotes) {
      if (char === "\r" && next === "\n") {
        i++;
      }
      row.push(field);
      if (row.some(value => value !== "")) {
        rows.push(row);
      }
      row = [];
      field = "";
    } else {
      field += char;
    }
  }

  row.push(field);
  if (row.some(value => value !== "")) {
    rows.push(row);
  }

  if (rows.length === 0) {
    return [];
  }

  const headers = rows[0];
  return rows.slice(1).map(values => {
    const record = {};
    headers.forEach((header, index) => {
      record[header] = values[index] || "";
    });
    return record;
  });
}

function parseNumber(value) {
  if (value == null || value === "" || value === "-") {
    return 0;
  }

  return Number(String(value).replace(/[%,"\s]/g, ""));
}

function sumMatrix(matrix) {
  return matrix.values.flat().reduce((sum, value) => sum + value, 0);
}

function classifyPort(port) {
  return port.congestionLevel || "Stable";
}

function assignPercentileCongestionLevels(portStats) {
  if (portStats.length === 0) {
    return;
  }

  const maxWaitingTeu = Math.max(...portStats.map(port => port.waitingTEU), 0);
  const maxVesselsWaiting = Math.max(...portStats.map(port => port.vesselsWaiting), 0);

  const rankedPorts = portStats
    .map(port => {
      const waitingScore = maxWaitingTeu > 0 ? port.waitingTEU / maxWaitingTeu : 0;
      const vesselScore = maxVesselsWaiting > 0 ? port.vesselsWaiting / maxVesselsWaiting : 0;
      port.congestionScore = waitingScore * 0.5 + vesselScore * 0.5;
      return port;
    })
    .sort((a, b) => b.congestionScore - a.congestionScore);

  const highCount = Math.max(1, Math.ceil(rankedPorts.length * 0.10));
  const mediumCount = Math.max(1, Math.ceil(rankedPorts.length * 0.30));

  rankedPorts.forEach((port, index) => {
    if (index < highCount) {
      port.congestionLevel = "High";
    } else if (index < mediumCount) {
      port.congestionLevel = "Medium";
    } else {
      port.congestionLevel = "Stable";
    }
  });
}

function assignFlowLevels(links, totalWaitingTeu) {
  if (links.length === 0) {
    return;
  }

  const rankedLinks = links.slice().sort((a, b) => b.teu - a.teu);
  const highCount = Math.max(1, Math.ceil(rankedLinks.length * 0.10));
  const mediumCount = Math.max(highCount + 1, Math.ceil(rankedLinks.length * 0.30));

  rankedLinks.forEach((link, index) => {
    link.waitingShare = totalWaitingTeu > 0 ? link.teu / totalWaitingTeu : 0;

    if (index < highCount || link.waitingShare >= 0.05) {
      link.level = "High";
    } else if (index < mediumCount || link.waitingShare >= 0.01) {
      link.level = "Medium";
    } else {
      link.level = "Stable";
    }
  });
}

function levelClass(level) {
  if (level === "Critical") {
    return "critical";
  }
  if (level === "High") {
    return "high";
  }
  if (level === "Medium") {
    return "medium";
  }
  return "low";
}

function levelColor(level) {
  if (level === "Critical") {
    return "#ef4444";
  }
  if (level === "High") {
    return "#f59e0b";
  }
  if (level === "Medium") {
    return "#eab308";
  }
  return "#22c55e";
}

function utilizationColor(value) {
  if (value >= 85) {
    return "#ef4444";
  }
  if (value >= 65) {
    return "#f59e0b";
  }
  if (value >= 35) {
    return "#eab308";
  }
  return "#475569";
}

function formatNumber(value) {
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function formatCompact(value) {
  return Intl.NumberFormat(undefined, {
    notation: "compact",
    maximumFractionDigits: 1
  }).format(value);
}

function toTitleCase(value) {
  return value.replace(/\w\S*/g, word => word.charAt(0).toUpperCase() + word.slice(1));
}

function showModal(title, text) {
  document.getElementById("modalTitle").textContent = title;
  document.getElementById("modalText").textContent = text;
  document.getElementById("modal").classList.add("visible");
}

function closeModal() {
  document.getElementById("modal").classList.remove("visible");
}

function resizePlots() {
  ["portBar", "routeBar", "vesselPie", "vesselTimeline", "heatmap", "attPeriodTrend", "resilienceLossChart"].forEach(id => {
    const element = document.getElementById(id);
    if (element) {
      Plotly.Plots.resize(element);
    }
  });
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
