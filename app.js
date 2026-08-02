"use strict";

const state = {
  meta: {},
  actual: {},
  vintages: {},
  manifest: { sources: [] },
  variableNames: [],
  currentVariable: null,
  activeVintages: new Set(),
  chart: null,
  toastTimer: null,
};

const elements = {};

document.addEventListener("DOMContentLoaded", boot);

async function boot() {
  cacheElements();
  try {
    await loadData();
    setupInterface();
    render();
  } catch (error) {
    showFatalError(error);
    console.error(error);
  }
}

function cacheElements() {
  [
    "releaseReport", "releaseDate", "varSelect", "vintageToggles", "btnAll", "btnNone", "btnReset",
    "btnCsv", "btnDownload", "btnShare", "mainChart", "chartSubtitle",
    "dataTableContainer", "methodologyText", "sourceList", "toast",
  ].forEach((id) => { elements[id] = document.getElementById(id); });
}

async function loadData() {
  const [forecastResponse, manifestResponse] = await Promise.all([
    fetch("forecasts.json", { cache: "no-cache" }),
    fetch("data/source_manifest.json", { cache: "no-cache" }),
  ]);
  if (!forecastResponse.ok) throw new Error(`No se pudo cargar forecasts.json (HTTP ${forecastResponse.status}).`);
  if (!manifestResponse.ok) throw new Error(`No se pudo cargar source_manifest.json (HTTP ${manifestResponse.status}).`);

  const dataset = await forecastResponse.json();
  state.manifest = await manifestResponse.json();
  state.meta = dataset.meta || {};
  state.actual = normalizeSeriesByVariable(dataset.actual || {});
  state.vintages = {};
  Object.entries(dataset.vintages || {}).forEach(([name, vintage]) => {
    state.vintages[name] = {
      color: vintage.color,
      projStart: Number(vintage.projStart),
      data: normalizeSeriesByVariable(vintage.data),
    };
  });
  state.variableNames = Object.keys(state.actual);
  if (!state.variableNames.length || !Object.keys(state.vintages).length) {
    throw new Error("La fuente canónica no contiene variables o vintages.");
  }
}

function normalizeSeriesByVariable(source) {
  return Object.fromEntries(Object.entries(source).map(([variable, series]) => [
    variable,
    Object.fromEntries(Object.entries(series).map(([year, value]) => [Number(year), value])),
  ]));
}

function setupInterface() {
  const urlState = readUrlState();
  const allVintageNames = Object.keys(state.vintages);
  const defaultVariable = state.variableNames.includes("Real GDP (%)")
    ? "Real GDP (%)"
    : state.variableNames[0];

  state.currentVariable = state.variableNames.includes(urlState.variable) ? urlState.variable : defaultVariable;
  state.activeVintages = urlState.vintages
    ? new Set(urlState.vintages.filter((name) => allVintageNames.includes(name)))
    : new Set(allVintageNames);

  elements.releaseReport.textContent = state.meta.latestReport || "Último Staff Report";
  elements.releaseDate.textContent = `Actualizado: ${formatMonth(state.meta.updatedAt)} · histórico hasta ${state.meta.actualThrough}`;
  elements.methodologyText.textContent = state.meta.actualMethodology || "";

  state.variableNames.forEach((variable) => {
    const option = document.createElement("option");
    option.value = variable;
    option.textContent = getVariableMeta(variable).label || variable;
    elements.varSelect.append(option);
  });
  elements.varSelect.value = state.currentVariable;
  elements.varSelect.addEventListener("change", () => {
    state.currentVariable = elements.varSelect.value;
    writeUrlState();
    render();
  });

  Object.entries(state.vintages).forEach(([name, vintage]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "vintage-button";
    button.dataset.vintage = name;
    button.textContent = name;
    button.style.color = vintage.color;
    button.addEventListener("click", () => {
      if (state.activeVintages.has(name)) state.activeVintages.delete(name);
      else state.activeVintages.add(name);
      syncVintageButtons();
      writeUrlState();
      render();
    });
    elements.vintageToggles.append(button);
  });

  elements.btnAll.addEventListener("click", () => setAllVintages(true));
  elements.btnNone.addEventListener("click", () => setAllVintages(false));
  elements.btnReset.addEventListener("click", resetState);
  elements.btnDownload.addEventListener("click", downloadPng);
  elements.btnCsv.addEventListener("click", downloadCsv);
  elements.btnShare.addEventListener("click", copyShareLink);
  syncVintageButtons();
  renderSources();
}

function getVariableMeta(variable = state.currentVariable) {
  return state.meta.variables?.[variable] || { label: variable, unit: "", decimals: 1 };
}

function readUrlState() {
  const hash = window.location.hash.replace(/^#/, "");
  if (!hash) return {};
  const params = new URLSearchParams(hash);
  return {
    variable: params.get("var"),
    vintages: params.has("vintages") ? params.get("vintages").split(",").filter(Boolean) : null,
  };
}

function writeUrlState() {
  const params = new URLSearchParams();
  params.set("var", state.currentVariable);
  params.set("vintages", [...state.activeVintages].join(","));
  history.replaceState(null, "", `#${params.toString()}`);
}

function resetState() {
  state.currentVariable = state.variableNames.includes("Real GDP (%)")
    ? "Real GDP (%)"
    : state.variableNames[0];
  state.activeVintages = new Set(Object.keys(state.vintages));
  elements.varSelect.value = state.currentVariable;
  syncVintageButtons();
  writeUrlState();
  render();
}

function setAllVintages(enabled) {
  state.activeVintages = enabled ? new Set(Object.keys(state.vintages)) : new Set();
  syncVintageButtons();
  writeUrlState();
  render();
}

function syncVintageButtons() {
  elements.vintageToggles.querySelectorAll(".vintage-button").forEach((button) => {
    const name = button.dataset.vintage;
    const active = state.activeVintages.has(name);
    const color = state.vintages[name].color;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", String(active));
    button.style.backgroundColor = active ? color : "#ffffff";
    button.style.color = active ? "#ffffff" : color;
  });
}

function render() {
  const actualSeries = state.actual[state.currentVariable] || {};
  const years = collectYears(actualSeries);
  renderChart(actualSeries, years);
  renderDataTable(actualSeries, years);

  const variableMeta = getVariableMeta();
  elements.chartSubtitle.textContent = `${variableMeta.label} · ${variableMeta.unit} · vintages seleccionados: ${state.activeVintages.size}`;
  elements.mainChart.setAttribute(
    "aria-label",
    `${variableMeta.label}: serie histórica/estimada y ${state.activeVintages.size} vintages de pronóstico.`,
  );
}

function collectYears(actualSeries) {
  const years = new Set(Object.keys(actualSeries).map(Number));
  Object.entries(state.vintages).forEach(([name, vintage]) => {
    if (!state.activeVintages.has(name)) return;
    Object.keys(vintage.data[state.currentVariable] || {}).forEach((year) => years.add(Number(year)));
  });
  return [...years].sort((a, b) => a - b);
}

function lastYear(series) {
  const years = Object.keys(series).map(Number).filter((year) => Number.isFinite(series[year]));
  return years.length ? Math.max(...years) : null;
}

function renderChart(actualSeries, years) {
  if (state.chart) state.chart.destroy();
  const datasets = [{
    label: state.meta.actualLabel || "Histórico / estimado",
    data: years.map((year) => actualSeries[year] ?? null),
    borderColor: "#071b2a",
    backgroundColor: "#071b2a",
    borderWidth: 3,
    pointRadius: 4,
    pointHoverRadius: 6,
    tension: 0.15,
    spanGaps: false,
    order: 0,
  }];

  Object.entries(state.vintages).forEach(([name, vintage]) => {
    if (!state.activeVintages.has(name)) return;
    const forecastSeries = vintage.data[state.currentVariable];
    if (!forecastSeries) return;
    const connectYear = vintage.projStart - 1;
    datasets.push({
      label: `Pron. ${name}`,
      data: years.map((year) => {
        if (year === connectYear && Number.isFinite(actualSeries[year])) return actualSeries[year];
        return forecastSeries[year] ?? null;
      }),
      borderColor: vintage.color,
      backgroundColor: vintage.color,
      borderWidth: name === state.meta.latestVintage ? 2.7 : 1.8,
      borderDash: name === state.meta.latestVintage ? [8, 4] : [5, 4],
      pointRadius: name === state.meta.latestVintage ? 3 : 2,
      pointHoverRadius: 6,
      tension: 0.15,
      spanGaps: false,
      order: 1,
    });
  });

  const actualYear = lastYear(actualSeries);
  const annotations = {};
  if (actualYear !== null && years.at(-1) > actualYear) {
    annotations.forecastZone = {
      type: "box",
      xMin: String(actualYear),
      xMax: String(years.at(-1)),
      backgroundColor: "rgba(23, 93, 141, 0.065)",
      borderWidth: 0,
      drawTime: "beforeDatasetsDraw",
    };
    annotations.lastActual = {
      type: "line",
      xMin: String(actualYear),
      xMax: String(actualYear),
      borderColor: "rgba(63, 82, 100, 0.72)",
      borderWidth: 1,
      borderDash: [4, 4],
      label: {
        display: true,
        content: `Último histórico/estimado (${actualYear})`,
        position: "start",
        backgroundColor: "rgba(11, 37, 58, 0.9)",
        color: "#ffffff",
        font: { size: 10, weight: "600" },
        padding: 5,
      },
    };
  }

  const meta = getVariableMeta();
  state.chart = new Chart(elements.mainChart.getContext("2d"), {
    type: "line",
    data: { labels: years.map(String), datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 280 },
      interaction: { mode: "index", intersect: false },
      plugins: {
        title: { display: true, text: `${meta.label} (${meta.unit})`, color: "#0b253a", font: { size: 16, weight: "700" }, padding: { bottom: 16 } },
        legend: { position: "bottom", labels: { usePointStyle: true, pointStyle: "line", padding: 15, color: "#3f5264", font: { size: 11 } } },
        tooltip: {
          backgroundColor: "rgba(7, 27, 42, 0.96)",
          padding: 12,
          cornerRadius: 9,
          filter: (context) => context.raw !== null && context.raw !== undefined,
          callbacks: { label: (context) => `  ${context.dataset.label}: ${formatValue(context.raw, meta)}` },
        },
        annotation: { annotations },
      },
      scales: {
        x: { grid: { color: "rgba(7,27,42,0.055)" }, ticks: { color: "#66788a", maxRotation: 0, autoSkipPadding: 10 } },
        y: { grid: { color: "rgba(7,27,42,0.075)" }, ticks: { color: "#66788a", callback: (value) => formatCompact(value, meta) }, title: { display: true, text: meta.unit, color: "#66788a" } },
      },
    },
  });
}

function renderDataTable(actualSeries, years) {
  const meta = getVariableMeta();
  const table = document.createElement("table");
  const head = document.createElement("thead");
  const headerRow = document.createElement("tr");
  ["Serie", ...years].forEach((label) => {
    const th = document.createElement("th");
    th.textContent = label;
    headerRow.append(th);
  });
  head.append(headerRow);
  table.append(head);

  const body = document.createElement("tbody");
  body.append(buildDataRow(state.meta.actualLabel || "Histórico / estimado", years, actualSeries, meta, "#071b2a", true));
  Object.entries(state.vintages).forEach(([name, vintage]) => {
    if (!state.activeVintages.has(name) || !vintage.data[state.currentVariable]) return;
    body.append(buildDataRow(`Pron. ${name}`, years, vintage.data[state.currentVariable], meta, vintage.color, false));
  });
  table.append(body);

  elements.dataTableContainer.replaceChildren(table);
  if (state.activeVintages.size === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-cell";
    empty.textContent = "No hay vintages seleccionados; se mantiene visible la serie histórica/estimada.";
    elements.dataTableContainer.append(empty);
  }
}

function buildDataRow(label, years, series, meta, color, isActual) {
  const row = document.createElement("tr");
  if (isActual) row.className = "actual-row";
  const labelCell = document.createElement("td");
  labelCell.textContent = label;
  labelCell.style.color = color;
  row.append(labelCell);
  years.forEach((year) => {
    const cell = document.createElement("td");
    const value = series[year];
    cell.textContent = Number.isFinite(value) ? formatValue(value, meta, false) : "";
    if (year > state.meta.actualThrough) cell.classList.add("forecast-zone-cell");
    row.append(cell);
  });
  return row;
}

function renderSources() {
  const fragment = document.createDocumentFragment();
  state.manifest.sources.forEach((source) => {
    const link = document.createElement("a");
    link.className = "source-item";
    link.href = source.file;
    link.target = "_blank";
    link.rel = "noopener";
    const title = document.createElement("strong");
    title.textContent = source.report;
    const subtitle = document.createElement("span");
    subtitle.textContent = `${source.vintage} · ${source.publicationDate}`;
    link.append(title, subtitle);
    fragment.append(link);
  });
  elements.sourceList.replaceChildren(fragment);
}

function formatValue(value, meta = getVariableMeta(), includeUnit = true) {
  if (!Number.isFinite(Number(value))) return "—";
  const decimals = Number(meta.decimals ?? 1);
  const formatted = Number(value).toLocaleString("es-EC", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  return includeUnit && meta.unit ? `${formatted} ${meta.unit}` : formatted;
}

function formatCompact(value, meta = getVariableMeta()) {
  const decimals = Math.abs(Number(value)) >= 1000 ? 0 : Number(meta.decimals ?? 1);
  return Number(value).toLocaleString("es-EC", { maximumFractionDigits: decimals });
}

function formatMonth(isoDate) {
  if (!isoDate) return "fecha no disponible";
  const date = new Date(`${isoDate}T00:00:00Z`);
  return new Intl.DateTimeFormat("es-EC", { month: "long", year: "numeric", timeZone: "UTC" }).format(date);
}

function downloadPng() {
  if (!state.chart) return;
  const link = document.createElement("a");
  const safeName = state.currentVariable.replace(/[^a-z0-9]+/gi, "_").replace(/^_|_$/g, "");
  link.href = state.chart.toBase64Image("image/png", 1);
  link.download = `IMF_Ecuador_${safeName}.png`;
  link.click();
  showToast("PNG generado.");
}

function downloadCsv() {
  const years = collectYears(state.actual[state.currentVariable]);
  const rows = [["Serie", ...years]];
  rows.push([state.meta.actualLabel || "Histórico / estimado", ...years.map((year) => state.actual[state.currentVariable][year] ?? "")]);
  Object.entries(state.vintages).forEach(([name, vintage]) => {
    if (!state.activeVintages.has(name)) return;
    const series = vintage.data[state.currentVariable] || {};
    rows.push([`Pron. ${name}`, ...years.map((year) => series[year] ?? "")]);
  });
  const csv = rows.map((row) => row.map(csvEscape).join(",")).join("\r\n");
  const blob = new Blob(["\ufeff", csv], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `IMF_Ecuador_${state.currentVariable.replace(/[^a-z0-9]+/gi, "_")}.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
  showToast("CSV generado.");
}

function csvEscape(value) {
  const text = String(value ?? "");
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

async function copyShareLink() {
  writeUrlState();
  try {
    await navigator.clipboard.writeText(window.location.href);
    showToast("Enlace copiado al portapapeles.");
  } catch {
    window.prompt("Copia este enlace:", window.location.href);
  }
}

function showToast(message) {
  window.clearTimeout(state.toastTimer);
  elements.toast.textContent = message;
  elements.toast.classList.add("is-visible");
  state.toastTimer = window.setTimeout(() => elements.toast.classList.remove("is-visible"), 2200);
}

function showFatalError(error) {
  const main = document.getElementById("main");
  const box = document.createElement("div");
  box.className = "fatal-error";
  box.innerHTML = `<strong>No se pudo iniciar la aplicación.</strong><br>${error.message}<br><small>Usa un servidor local, por ejemplo <code>python -m http.server</code>; los navegadores bloquean fetch bajo file://.</small>`;
  main.replaceChildren(box);
}
