const form = document.querySelector("#fund-form");
const codeInput = document.querySelector("#fund-code");
const inputHelp = document.querySelector("#input-help");
const loadingState = document.querySelector("#loading-state");
const errorState = document.querySelector("#error-state");
const errorMessage = document.querySelector("#error-message");
const results = document.querySelector("#results");
const refreshButton = document.querySelector("#refresh-button");

let currentCode = "";
let currentHoldings = null;
let currentHoldingType = "股票";
let currentBondStructureView = "品种";
let currentNavHistory = {};
let currentNavRange = "1y";
let currentNavMetric = "累计收益率";
let currentCustomRange = { start: "", end: "" };
let currentInvestmentMode = "single";
let currentDividends = [];
let navPlotPoints = [];
let currentPeriodicUnit = "year";
let currentPerformance = {};
let currentTrackBenchmark = null;
let currentTrackBenchmarkKey = "";
let trackBenchmarkRequestId = 0;
let benchmarkPlotPoints = [];
const trackBenchmarkCache = new Map();

const palette = [
  "#d33b28",
  "#e07e2e",
  "#d7a928",
  "#8e9f36",
  "#14745a",
  "#337f86",
  "#4e6a98",
  "#765c87",
  "#9a5264",
  "#5f645c",
];

const navMetricConfig = {
  累计收益率: {
    valueKey: "累计收益率",
    subtitle: "所选区间首日归零的收益走势",
    note: "区间收益将所选区间首个可用点视为 0%，用于观察这段持有期内的涨跌；“成立以来”仅作为长期研究选项。",
    tooltipLabel: "区间收益",
    unit: "%",
  },
  阶段收益: {
    valueKey: "累计收益率",
    subtitle: "近 1 天 / 1 月 / 3 月 / 6 月 / 今年以来 / 1 年 / 3 年及成立以来的阶段涨幅",
    note: "阶段涨幅按相同起止日比较基金与所选赛道，并以百分点显示领先或落后。",
    tooltipLabel: "阶段涨幅",
    unit: "%",
  },
  累计净值: {
    valueKey: "累计净值",
    subtitle: "将历史现金分红加回后的净值走势",
    note: "累计净值将历史现金分红加回，减少除息断层；首末变化不等同于分红再投资收益率。",
    tooltipLabel: "累计净值",
    unit: "元",
  },
  单位净值: {
    valueKey: "单位净值",
    subtitle: "每份基金的实际净值，保留分红除息变化",
    note: "橙色虚线标记分红除息日；单位净值下跳通常是现金分红，不代表同等幅度亏损。",
    tooltipLabel: "单位净值",
    unit: "元",
  },
  分红记录: {
    valueKey: "每份分红",
    subtitle: "现金分红事件与每份分红金额",
    note: "分红会使单位净值在除息日相应下降，本身不是额外收益；累计净值用于观察将历史现金分红加回后的走势。",
    tooltipLabel: "分红记录",
    unit: "元",
  },
  周期收益: {
    valueKey: "累计净值",
    subtitle: "各自然年 / 季度 / 月内的独立涨跌幅",
    note: "基金按累计净值计算并与所选赛道采用相同起止日；每格展示自然年 / 季度 / 月内的基金、赛道和相对涨幅。",
    tooltipLabel: "周期涨幅",
    unit: "%",
  },
  回撤修复: {
    valueKey: "累计收益率",
    subtitle: "区间收益曲线中的最大回撤与修复阶段",
    note: "基金最大回撤按区间收益指数计算，绿色标出回撤段、红色标出修复段；蓝色虚线同步展示所选赛道，悬浮可比较双方回撤。",
    tooltipLabel: "区间收益",
    unit: "%",
  },
};

function text(selector, value, fallback = "暂无数据") {
  const element = document.querySelector(selector);
  element.textContent =
    value === null || value === undefined || value === "" ? fallback : value;
}

function formatNumber(value, digits = 4) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  return Number(value).toLocaleString("zh-CN", {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  });
}

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  const numeric = Number(value);
  return `${numeric > 0 ? "+" : ""}${numeric.toFixed(2)}%`;
}

function formatCurrency(value, signed = false) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  const numeric = Number(value);
  const absolute = Math.abs(numeric).toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  if (!signed) return `¥${absolute}`;
  if (numeric > 0) return `+¥${absolute}`;
  if (numeric < 0) return `-¥${absolute}`;
  return "¥0.00";
}

function movementClass(value) {
  const numeric = Number(value);
  if (numeric > 0) return "positive-text";
  if (numeric < 0) return "negative-text";
  return "";
}

function setView(view) {
  loadingState.hidden = view !== "loading";
  errorState.hidden = view !== "error";
  results.hidden = view !== "results";
}

function validateCode(value) {
  return /^\d{6}$/.test(value);
}

function showInputError(message) {
  inputHelp.textContent = message;
  inputHelp.classList.add("invalid");
  codeInput.setAttribute("aria-invalid", "true");
}

function clearInputError() {
  inputHelp.textContent = "输入完整的六位基金代码";
  inputHelp.classList.remove("invalid");
  codeInput.removeAttribute("aria-invalid");
}

function benchmarkReturnBetween(start, end, previousEndPoint = false) {
  const rows = currentTrackBenchmark?.明细 ?? [];
  if (rows.length < 2 || !start || !end) return null;
  const endIndex = rows.findLastIndex((row) => row.日期 <= end);
  if (endIndex < 1) return null;
  let startIndex = previousEndPoint
    ? endIndex - 1
    : rows.findLastIndex((row) => row.日期 <= start);
  if (startIndex < 0) {
    startIndex = rows.findIndex((row) => row.日期 >= start);
  }
  if (startIndex < 0 || startIndex >= endIndex) return null;
  const startValue = Number(rows[startIndex].指数值);
  const endValue = Number(rows[endIndex].指数值);
  if (
    !Number.isFinite(startValue) ||
    !Number.isFinite(endValue) ||
    startValue <= 0
  ) {
    return null;
  }
  return (endValue / startValue - 1) * 100;
}

function shiftIsoDate(isoDate, { days = 0, months = 0, years = 0 }) {
  const value = new Date(`${isoDate}T12:00:00Z`);
  if (years || months) {
    const targetDay = value.getUTCDate();
    value.setUTCDate(1);
    value.setUTCFullYear(value.getUTCFullYear() + years);
    value.setUTCMonth(value.getUTCMonth() + months);
    const lastDay = new Date(
      Date.UTC(value.getUTCFullYear(), value.getUTCMonth() + 1, 0),
    ).getUTCDate();
    value.setUTCDate(Math.min(targetDay, lastDay));
  }
  if (days) value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString().slice(0, 10);
}

function benchmarkStageReturn(key) {
  const navRows = currentNavHistory?.累计净值?.明细 ?? [];
  const end = navRows.at(-1)?.日期;
  if (!end) return null;
  if (key === "日涨幅") {
    return benchmarkReturnBetween(end, end, true);
  }
  const startByKey = {
    近1月: shiftIsoDate(end, { months: -1 }),
    近3月: shiftIsoDate(end, { months: -3 }),
    近6月: shiftIsoDate(end, { months: -6 }),
    今年以来: `${end.slice(0, 4)}-01-01`,
    近1年: shiftIsoDate(end, { years: -1 }),
    近3年: shiftIsoDate(end, { years: -3 }),
    成立以来: navRows[0]?.日期,
  };
  return benchmarkReturnBetween(startByKey[key], end);
}

function renderPerformance(performance) {
  currentPerformance = performance ?? {};
  const chart = document.querySelector("#performance-chart");
  const periods = [
    { label: "近1天", key: "日涨幅" },
    { label: "近1月", key: "近1月" },
    { label: "近3月", key: "近3月" },
    { label: "近6月", key: "近6月" },
    { label: "今年以来", key: "今年以来" },
    { label: "近1年", key: "近1年" },
    { label: "近3年", key: "近3年" },
    { label: "成立以来", key: "成立以来" },
  ];
  chart.replaceChildren();
  text(
    "#stage-benchmark-heading",
    currentTrackBenchmark?.简称
      ? `${currentTrackBenchmark.简称}涨幅`
      : "赛道涨幅",
  );

  periods.forEach(({ label: period, key }, index) => {
    const rawValue = currentPerformance[key];
    const numeric = Number(rawValue);
    const valid = Number.isFinite(numeric);
    const item = document.createElement("div");
    const direction =
      !valid || numeric === 0 ? "neutral" : numeric > 0 ? "positive" : "negative";
    item.className = `stage-performance-row ${direction}`;
    item.style.animationDelay = `${index * 55}ms`;

    const label = document.createElement("span");
    label.textContent = period;

    const value = document.createElement("strong");
    value.textContent = valid ? formatPercent(numeric) : "—";
    value.className = valid ? movementClass(numeric) : "";

    const benchmarkReturn = benchmarkStageReturn(key);
    const benchmarkValue = document.createElement("strong");
    benchmarkValue.className = `benchmark-value ${
      Number.isFinite(benchmarkReturn)
        ? movementClass(benchmarkReturn)
        : ""
    }`;
    benchmarkValue.textContent = Number.isFinite(benchmarkReturn)
      ? formatPercent(benchmarkReturn)
      : "—";

    const relativeReturn = Number.isFinite(numeric) &&
      Number.isFinite(benchmarkReturn)
      ? numeric - benchmarkReturn
      : null;
    const relativeValue = document.createElement("strong");
    relativeValue.className = `relative-value ${
      Number.isFinite(relativeReturn) ? movementClass(relativeReturn) : ""
    }`;
    relativeValue.textContent = Number.isFinite(relativeReturn)
      ? `${relativeReturn > 0 ? "+" : ""}${relativeReturn.toFixed(2)}pp`
      : "—";

    item.append(label, value, benchmarkValue, relativeValue);
    chart.append(item);
  });
}

function computePeriodicReturns(unit) {
  const rows = (currentNavHistory?.累计净值?.明细 ?? [])
    .map((row) => ({
      日期: row.日期,
      value: Number(row.累计净值),
    }))
    .filter((row) => row.日期 && Number.isFinite(row.value))
    .sort((a, b) => a.日期.localeCompare(b.日期));
  if (rows.length < 2) return [];

  const keyOf = (isoDate) => {
    if (unit === "year") return isoDate.slice(0, 4);
    if (unit === "quarter") {
      const year = isoDate.slice(0, 4);
      const quarter = Math.ceil(Number(isoDate.slice(5, 7)) / 3);
      return `${year}-Q${quarter}`;
    }
    return isoDate.slice(0, 7);
  };

  // 每个自然周期保留首末净值点。
  const buckets = new Map();
  rows.forEach((row) => {
    const key = keyOf(row.日期);
    const bucket = buckets.get(key);
    if (!bucket) {
      buckets.set(key, { key, first: row, last: row });
    } else {
      bucket.last = row;
    }
  });

  const ordered = [...buckets.values()].sort((a, b) =>
    a.key.localeCompare(b.key),
  );
  return ordered.map((bucket, index) => {
    // 以上一周期期末净值为基准，衔接跨期涨跌；首个周期回退到本周期期初。
    const base =
      index > 0 ? ordered[index - 1].last.value : bucket.first.value;
    const change =
      Number.isFinite(base) && base !== 0
        ? (bucket.last.value / base - 1) * 100
        : null;
    return {
      key: bucket.key,
      label:
        unit === "year"
          ? `${bucket.key}年`
          : unit === "quarter"
            ? `${bucket.key.slice(0, 4)} Q${bucket.key.at(-1)}`
          : `${bucket.key.slice(0, 4)}/${bucket.key.slice(5, 7)}`,
      change,
      partial: index === 0,
      startDate:
        index > 0
          ? ordered[index - 1].last.日期
          : bucket.first.日期,
      endDate: bucket.last.日期,
    };
  });
}

function renderPeriodicReturns(unit = currentPeriodicUnit) {
  currentPeriodicUnit = unit;
  const grid = document.querySelector("#periodic-returns-grid");
  const empty = document.querySelector("#periodic-returns-empty");
  grid.replaceChildren();

  document.querySelectorAll("[data-periodic-unit]").forEach((button) => {
    const active = button.dataset.periodicUnit === unit;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  text(
    "#periodic-returns-subtitle",
    unit === "year"
      ? "各自然年内的基金、赛道与相对涨跌幅"
      : unit === "quarter"
        ? "各自然季度内的基金、赛道与相对涨跌幅"
        : "各自然月内的基金、赛道与相对涨跌幅",
  );

  let entries = computePeriodicReturns(unit);
  if (unit === "month") entries = entries.slice(-24);

  if (!entries.length) {
    empty.hidden = false;
    return;
  }
  empty.hidden = true;

  entries
    .slice()
    .reverse()
    .forEach((entry, index) => {
      const numeric = entry.change;
      const valid = Number.isFinite(numeric);
      const direction =
        !valid || numeric === 0
          ? "neutral"
          : numeric > 0
            ? "positive"
            : "negative";
      const item = document.createElement("div");
      item.className = `periodic-stat ${direction}`;
      item.style.animationDelay = `${Math.min(index * 40, 480)}ms`;

      const label = document.createElement("span");
      label.textContent = entry.label;

      const value = document.createElement("strong");
      value.textContent = valid ? formatPercent(numeric) : "—";
      value.className = valid ? movementClass(numeric) : "";

      const fundLabel = document.createElement("small");
      fundLabel.textContent = "基金";
      const primary = document.createElement("div");
      primary.className = "periodic-primary";
      primary.append(fundLabel, value);

      const benchmarkReturn = benchmarkReturnBetween(
        entry.startDate,
        entry.endDate,
      );
      const benchmarkValue = document.createElement("b");
      benchmarkValue.className = Number.isFinite(benchmarkReturn)
        ? movementClass(benchmarkReturn)
        : "";
      benchmarkValue.textContent = Number.isFinite(benchmarkReturn)
        ? formatPercent(benchmarkReturn)
        : "—";
      const benchmarkLabel = document.createElement("small");
      benchmarkLabel.textContent =
        currentTrackBenchmark?.简称 ?? "赛道";
      const secondary = document.createElement("div");
      secondary.className = "periodic-secondary";
      secondary.append(benchmarkLabel, benchmarkValue);

      const relativeReturn = valid && Number.isFinite(benchmarkReturn)
        ? numeric - benchmarkReturn
        : null;
      const relative = document.createElement("em");
      relative.className = Number.isFinite(relativeReturn)
        ? movementClass(relativeReturn)
        : "";
      relative.textContent = Number.isFinite(relativeReturn)
        ? `${relativeReturn >= 0 ? "领先" : "落后"} ${Math.abs(
            relativeReturn,
          ).toFixed(2)}pp`
        : "相对赛道 —";

      const marker = document.createElement("i");
      marker.setAttribute("aria-hidden", "true");

      item.append(label, primary, secondary, relative, marker);
      if (entry.partial) {
        item.title = `${entry.label}为区间起点，涨跌幅以本期首个净值为基准。`;
      }
      grid.append(item);
    });
}

function svgNode(name, attributes = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attributes).forEach(([key, value]) => {
    node.setAttribute(key, value);
  });
  return node;
}

function formatChartDate(value, includeYear = true) {
  const date = new Date(`${value}T00:00:00`);
  return new Intl.DateTimeFormat("zh-CN", {
    year: includeYear ? "numeric" : undefined,
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function filterNavRows(rows, range) {
  if (!rows.length || range === "all") return rows;
  const latest = new Date(
    `${rows[rows.length - 1].日期}T00:00:00`,
  );
  const cutoff = new Date(latest);
  if (range === "1m") cutoff.setMonth(cutoff.getMonth() - 1);
  if (range === "3m") cutoff.setMonth(cutoff.getMonth() - 3);
  if (range === "6m") cutoff.setMonth(cutoff.getMonth() - 6);
  if (range === "1y") cutoff.setFullYear(cutoff.getFullYear() - 1);
  if (range === "3y") cutoff.setFullYear(cutoff.getFullYear() - 3);
  if (range === "5y") cutoff.setFullYear(cutoff.getFullYear() - 5);
  return rows.filter(
    (point) => new Date(`${point.日期}T00:00:00`) >= cutoff,
  );
}

function filterCustomRows(rows) {
  if (!currentCustomRange.start || !currentCustomRange.end) return [];
  return rows.filter(
    (point) =>
      point.日期 >= currentCustomRange.start &&
      point.日期 <= currentCustomRange.end,
  );
}

function customReturnRows() {
  const returnRanges = currentNavHistory?.累计收益率?.区间 ?? {};
  const totalReturnRows =
    ["1m", "3m", "6m", "1y", "3y", "5y", "all"]
      .map((range) => returnRanges[range] ?? [])
      .find(
        (rows) =>
          rows.length >= 2 &&
          rows[0].日期 <= currentCustomRange.start &&
          rows.at(-1).日期 >= currentCustomRange.end,
      ) ?? returnRanges.all ?? [];
  const selectedReturns = filterCustomRows(totalReturnRows);
  if (selectedReturns.length >= 2) {
    const baseReturn = Number(selectedReturns[0].累计收益率);
    const baseIndex = 1 + baseReturn / 100;
    if (Number.isFinite(baseIndex) && baseIndex > 0) {
      return selectedReturns.map((row) => ({
        日期: row.日期,
        累计收益率:
          ((1 + Number(row.累计收益率) / 100) / baseIndex - 1) * 100,
      }));
    }
  }

  const cumulativeRows = filterCustomRows(
    currentNavHistory?.累计净值?.明细 ?? [],
  );
  if (cumulativeRows.length < 2) return [];
  const baseNav = Number(cumulativeRows[0].累计净值);
  if (!Number.isFinite(baseNav) || baseNav <= 0) return [];
  return cumulativeRows.map((row) => ({
    日期: row.日期,
    累计收益率: (Number(row.累计净值) / baseNav - 1) * 100,
  }));
}

function daysBetween(start, end) {
  const startTime = new Date(`${start}T00:00:00Z`).getTime();
  const endTime = new Date(`${end}T00:00:00Z`).getTime();
  return Math.max(0, Math.round((endTime - startTime) / 86400000));
}

function computeDrawdownAnalysis(range) {
  let returnRows =
    range === "custom"
      ? customReturnRows()
      : currentNavHistory?.累计收益率?.区间?.[range] ?? [];

  // 上游偶尔缺少某个收益区间，用单位净值首日归零作为降级数据源。
  if (returnRows.length < 2) {
    const unitRows = currentNavHistory?.单位净值?.明细 ?? [];
    const filtered =
      range === "custom"
        ? filterCustomRows(unitRows)
        : filterNavRows(unitRows, range);
    const baseNav = Number(filtered[0]?.单位净值);
    returnRows =
      Number.isFinite(baseNav) && baseNav > 0
        ? filtered.map((row) => ({
            日期: row.日期,
            累计收益率: (Number(row.单位净值) / baseNav - 1) * 100,
          }))
        : [];
  }

  const selected = returnRows
    .map((row) => ({
      日期: row.日期,
      累计收益率: Number(row.累计收益率),
    }))
    .filter(
      (row) => row.日期 && Number.isFinite(row.累计收益率),
    )
    .sort((a, b) => a.日期.localeCompare(b.日期));

  if (!selected.length) {
    return {
      rows: [],
      maxDrawdown: 0,
      peakIndex: null,
      troughIndex: null,
      recoveryIndex: null,
      recoveryDays: null,
      elapsedRecoveryDays: null,
    };
  }

  let runningPeak = 1 + selected[0].累计收益率 / 100;
  let runningPeakIndex = 0;
  let maxDrawdown = 0;
  let maxPeakIndex = 0;
  let troughIndex = 0;
  let maxPeakValue = runningPeak;

  const rows = selected.map((row, index) => {
    const returnIndex = 1 + row.累计收益率 / 100;
    if (returnIndex > runningPeak) {
      runningPeak = returnIndex;
      runningPeakIndex = index;
    }
    const drawdown =
      runningPeak > 0 ? (returnIndex / runningPeak - 1) * 100 : 0;
    if (drawdown < maxDrawdown) {
      maxDrawdown = drawdown;
      maxPeakIndex = runningPeakIndex;
      troughIndex = index;
      maxPeakValue = runningPeak;
    }
    return {
      ...row,
      收益指数: returnIndex,
      回撤: drawdown,
    };
  });

  let recoveryIndex = null;
  if (maxDrawdown < -0.000001) {
    recoveryIndex = rows.findIndex(
      (row, index) =>
        index > troughIndex && row.收益指数 >= maxPeakValue * (1 - 1e-10),
    );
    if (recoveryIndex < 0) recoveryIndex = null;
  }

  const recoveryDays =
    recoveryIndex === null
      ? null
      : daysBetween(rows[troughIndex].日期, rows[recoveryIndex].日期);
  const elapsedRecoveryDays =
    maxDrawdown < -0.000001 && recoveryIndex === null
      ? daysBetween(rows[troughIndex].日期, rows.at(-1).日期)
      : null;

  return {
    rows,
    maxDrawdown,
    peakIndex: maxPeakIndex,
    troughIndex,
    recoveryIndex,
    recoveryDays,
    elapsedRecoveryDays,
  };
}

function computeDrawdownRows(range) {
  return computeDrawdownAnalysis(range).rows;
}

function navRowsFor(metric, range) {
  if (metric === "分红记录") {
    const rows = currentDividends.map((row) => ({
      ...row,
      日期: row.除息日,
    }));
    return range === "custom"
      ? filterCustomRows(rows)
      : filterNavRows(rows, range);
  }
  if (metric === "回撤修复") {
    return computeDrawdownRows(range);
  }
  if (range === "custom") {
    return metric === "累计收益率"
      ? customReturnRows()
      : filterCustomRows(currentNavHistory?.[metric]?.明细 ?? []);
  }
  if (metric === "累计收益率") {
    return currentNavHistory?.累计收益率?.区间?.[range] ?? [];
  }
  return filterNavRows(currentNavHistory?.[metric]?.明细 ?? [], range);
}

function renderDividendHistory(rows) {
  const list = document.querySelector("#dividend-history-list");
  const empty = document.querySelector("#no-dividend-history");
  const validAmounts = rows
    .map((row) => Number(row.每份分红))
    .filter(Number.isFinite);
  const totalPerShare = validAmounts.reduce(
    (sum, amount) => sum + amount,
    0,
  );
  const latest = rows.at(-1);

  list.replaceChildren();
  empty.hidden = Boolean(rows.length);
  rows
    .slice()
    .reverse()
    .forEach((row, index) => {
      const item = document.createElement("div");
      item.className = "dividend-history-row";
      item.style.setProperty(
        "--dividend-delay",
        `${Math.min(index * 45, 360)}ms`,
      );

      const date = document.createElement("time");
      date.dateTime = row.除息日;
      date.textContent = formatChartDate(row.除息日);

      const amount = document.createElement("strong");
      amount.textContent = Number.isFinite(Number(row.每份分红))
        ? `${formatNumber(row.每份分红, 4)} 元`
        : "金额暂无";

      const description = document.createElement("span");
      description.textContent = row.说明 ?? "现金分红";
      item.append(date, amount, description);
      list.append(item);
    });

  text("#nav-range-change-label", "分红次数");
  text("#nav-range-high-label", "累计每份分红");
  text("#nav-range-low-label", "最近每份分红");
  text("#nav-range-dates-label", "除息日期范围");
  document.querySelector("#nav-range-change").className = "";
  text("#nav-range-change", `${rows.length} 次`);
  text(
    "#nav-range-high",
    validAmounts.length ? `${formatNumber(totalPerShare, 4)} 元` : null,
  );
  text(
    "#nav-range-low",
    latest && Number.isFinite(Number(latest.每份分红))
      ? `${formatNumber(latest.每份分红, 4)} 元`
      : null,
  );
  text(
    "#nav-range-dates",
    rows.length
      ? `${formatChartDate(rows[0].除息日)} — ${formatChartDate(
          rows.at(-1).除息日,
        )}`
      : null,
  );
}

function localIsoDate(value) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function initializeCustomRange() {
  const sourceRows =
    currentNavHistory?.累计收益率?.区间?.all?.length
      ? currentNavHistory.累计收益率.区间.all
      : currentNavHistory?.累计净值?.明细 ?? [];
  const startInput = document.querySelector("#custom-range-start");
  const endInput = document.querySelector("#custom-range-end");
  if (sourceRows.length < 2) {
    currentCustomRange = { start: "", end: "" };
    startInput.value = "";
    endInput.value = "";
    startInput.removeAttribute("min");
    startInput.removeAttribute("max");
    endInput.removeAttribute("min");
    endInput.removeAttribute("max");
    text("#custom-range-available", "暂无可用日期范围");
    return;
  }

  const firstDate = sourceRows[0].日期;
  const lastDate = sourceRows.at(-1).日期;
  const defaultStart = new Date(`${lastDate}T00:00:00`);
  defaultStart.setFullYear(defaultStart.getFullYear() - 1);
  currentCustomRange = {
    start: localIsoDate(defaultStart) < firstDate
      ? firstDate
      : localIsoDate(defaultStart),
    end: lastDate,
  };
  [startInput, endInput].forEach((input) => {
    input.min = firstDate;
    input.max = lastDate;
  });
  startInput.value = currentCustomRange.start;
  endInput.value = currentCustomRange.end;
  text(
    "#custom-range-available",
    `可用 ${formatChartDate(firstDate)} — ${formatChartDate(lastDate)}`,
  );
}

function showCustomRangeError(message = "") {
  const error = document.querySelector("#custom-range-error");
  error.hidden = !message;
  error.textContent = message;
}

function benchmarkRowsForChart(fundRows) {
  const source = currentTrackBenchmark?.明细 ?? [];
  if (fundRows.length < 2 || source.length < 2) return [];
  const start = fundRows[0].日期;
  const end = fundRows.at(-1).日期;
  const usable = source.filter((row) => row.日期 <= end);
  const baseRow =
    usable.filter((row) => row.日期 <= start).at(-1) ??
    usable.find((row) => row.日期 >= start);
  const baseValue = Number(baseRow?.指数值);
  if (!baseRow || !Number.isFinite(baseValue) || baseValue <= 0) return [];

  const rows = usable
    .filter((row) => row.日期 >= start && row.日期 <= end)
    .map((row) => ({
      日期: row.日期,
      累计收益率: (Number(row.指数值) / baseValue - 1) * 100,
    }))
    .filter((row) => Number.isFinite(row.累计收益率));
  if (baseRow.日期 < start) {
    rows.unshift({ 日期: start, 累计收益率: 0 });
  }
  return rows;
}

function addDrawdownDepth(rows) {
  let peak = -Infinity;
  return rows.map((row) => {
    const returnIndex = 1 + Number(row.累计收益率) / 100;
    peak = Math.max(peak, returnIndex);
    return {
      ...row,
      回撤: peak > 0 ? (returnIndex / peak - 1) * 100 : 0,
    };
  });
}

function formatNavValue(value, metric = currentNavMetric, axis = false) {
  if (metric === "累计收益率" || metric === "回撤修复") {
    return axis ? `${Number(value).toFixed(2)}%` : formatPercent(value);
  }
  return formatNumber(value, 4);
}

function buildYAxisTicks(minValue, maxValue, includeZero = false) {
  const ticks = Array.from({ length: 5 }, (_, index) => {
    const ratio = index / 4;
    return maxValue - ratio * (maxValue - minValue);
  });
  if (includeZero) ticks.push(0);

  return ticks
    .sort((a, b) => b - a)
    .filter(
      (value, index, values) =>
        index === 0 ||
        Math.abs(value - values[index - 1]) >
          Math.max(Math.abs(maxValue - minValue) * 0.000001, 1e-9),
    );
}

function renderNavChart(
  range = currentNavRange,
  metric = currentNavMetric,
) {
  currentNavRange = range;
  currentNavMetric = metric;
  const config = navMetricConfig[metric];
  const customPanel = document.querySelector("#nav-custom-range");
  const svg = document.querySelector("#nav-history-chart");
  const chartShell = document.querySelector("#nav-chart-shell");
  const dividendPanel = document.querySelector("#dividend-history-panel");
  const periodicPanel = document.querySelector("#periodic-returns-panel");
  const stagePanel = document.querySelector("#stage-performance-panel");
  const noData = document.querySelector("#no-nav-history");
  const tooltip = document.querySelector("#nav-chart-tooltip");
  const summary = document.querySelector(".nav-history-summary");
  const isDrawdownView = metric === "回撤修复";
  const isPerformanceView = metric === "累计收益率";
  const isBenchmarkCurveView = isPerformanceView || isDrawdownView;
  const drawdownAnalysis = isDrawdownView
    ? computeDrawdownAnalysis(range)
    : null;
  const rows = drawdownAnalysis?.rows ?? navRowsFor(metric, range);
  const values = rows
    .map((row) => Number(row[config.valueKey]))
    .filter(Number.isFinite);
  svg.replaceChildren();
  svg.classList.toggle("drawdown-view", isDrawdownView);
  tooltip.hidden = true;
  navPlotPoints = [];
  benchmarkPlotPoints = [];
  const isDividendView = metric === "分红记录";
  const isPeriodicView = metric === "周期收益";
  const isStageView = metric === "阶段收益";
  customPanel.hidden = range !== "custom" || isPeriodicView || isStageView;
  chartShell.hidden = isDividendView || isPeriodicView || isStageView;
  dividendPanel.hidden = !isDividendView;
  periodicPanel.hidden = !isPeriodicView;
  stagePanel.hidden = !isStageView;
  summary.hidden = isPeriodicView || isStageView;
  summary.classList.toggle("drawdown-summary", isDrawdownView);
  document.querySelector("#nav-range-switcher").hidden =
    isPeriodicView || isStageView;
  document.querySelector("#track-benchmark-control").hidden = false;
  document.querySelector("#nav-chart-legend").hidden =
    !isBenchmarkCurveView;

  document.querySelectorAll("[data-nav-range]").forEach((button) => {
    const active = button.dataset.navRange === range;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll("[data-nav-metric]").forEach((button) => {
    const active = button.dataset.navMetric === metric;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  text(
    "#nav-chart-subtitle",
    range === "custom" && !isPeriodicView && !isStageView
      ? `自定义区间 · ${config.subtitle}`
      : config.subtitle,
  );
  text("#nav-chart-note", config.note);
  if (isStageView) {
    noData.hidden = true;
    renderPerformance(currentPerformance);
    return;
  }
  if (isPeriodicView) {
    noData.hidden = true;
    renderPeriodicReturns(currentPeriodicUnit);
    return;
  }
  if (isDividendView) {
    noData.hidden = true;
    if (range === "custom") showCustomRangeError();
    renderDividendHistory(rows);
    return;
  }
  text(
    "#nav-range-change-label",
    isDrawdownView
      ? "最大回撤比例"
      : isPerformanceView
        ? "基金涨幅"
        : "首末变化",
  );
  text(
    "#nav-range-dates-label",
    isDrawdownView ? "回撤修复阶段" : "覆盖日期",
  );
  text(
    "#nav-range-high-label",
    isDrawdownView
      ? "最大回撤修复天数"
      : isPerformanceView
        ? "赛道涨幅"
        : "区间最高",
  );
  text(
    "#nav-range-low-label",
    isDrawdownView
      ? "最大回撤阶段"
      : isPerformanceView
        ? "相对赛道"
        : "区间最低",
  );

  if (rows.length < 2 || values.length < 2) {
    noData.hidden = false;
    if (range === "custom") {
      showCustomRangeError(
        "所选日期内不足两个有效净值点，请扩大时间范围。",
      );
    }
    text("#nav-range-change", "—");
    text("#nav-range-high", "—");
    text("#nav-range-low", "—");
    text("#nav-range-dates", "—");
    return;
  }

  noData.hidden = true;
  if (range === "custom") showCustomRangeError();
  const width = 1000;
  const height = 360;
  const margin = { top: 24, right: 22, bottom: 46, left: 68 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const startTime = new Date(`${rows[0].日期}T00:00:00`).getTime();
  const endTime = new Date(`${rows[rows.length - 1].日期}T00:00:00`).getTime();
  const isPercentageChart =
    metric === "累计收益率" || metric === "回撤修复";
  const rawBenchmarkRows = isBenchmarkCurveView
    ? benchmarkRowsForChart(rows)
    : [];
  const benchmarkRows = isDrawdownView
    ? addDrawdownDepth(rawBenchmarkRows)
    : rawBenchmarkRows;
  const benchmarkValues = benchmarkRows.map((row) => row.累计收益率);
  let minValue = Math.min(...values);
  let maxValue = Math.max(...values);
  if (benchmarkValues.length) {
    minValue = Math.min(minValue, ...benchmarkValues);
    maxValue = Math.max(maxValue, ...benchmarkValues);
  }
  if (isPercentageChart) {
    minValue = Math.min(minValue, 0);
    maxValue = Math.max(maxValue, 0);
  }
  const valueSpan = maxValue - minValue || Math.max(maxValue * 0.02, 0.02);
  minValue = isPercentageChart && minValue === 0
    ? 0
    : minValue - valueSpan * 0.1;
  maxValue = isPercentageChart && maxValue === 0
    ? 0
    : maxValue + valueSpan * 0.1;

  const xFor = (date) =>
    margin.left +
    ((new Date(`${date}T00:00:00`).getTime() - startTime) /
      Math.max(endTime - startTime, 1)) *
      plotWidth;
  const yFor = (value) =>
    margin.top +
    ((maxValue - Number(value)) / Math.max(maxValue - minValue, 0.0001)) *
      plotHeight;

  const defs = svgNode("defs");
  const gradient = svgNode("linearGradient", {
    id: "nav-area-gradient",
    x1: "0",
    y1: "0",
    x2: "0",
    y2: "1",
  });
  gradient.append(
    svgNode("stop", {
      offset: "0%",
      "stop-color": "#d33b28",
      "stop-opacity": "0.24",
    }),
    svgNode("stop", {
      offset: "100%",
      "stop-color": "#d33b28",
      "stop-opacity": "0",
    }),
  );
  defs.append(gradient);
  svg.append(defs);

  if (
    isDrawdownView &&
    drawdownAnalysis?.peakIndex !== null &&
    drawdownAnalysis?.troughIndex !== null &&
    drawdownAnalysis.maxDrawdown < -0.000001
  ) {
    const peakDate = rows[drawdownAnalysis.peakIndex].日期;
    const troughDate = rows[drawdownAnalysis.troughIndex].日期;
    const repairEndIndex =
      drawdownAnalysis.recoveryIndex ?? rows.length - 1;
    const repairEndDate = rows[repairEndIndex].日期;
    const phaseBands = svgNode("g", {
      class: "drawdown-phase-bands",
      "aria-hidden": "true",
    });
    const declineStart = xFor(peakDate);
    const declineEnd = xFor(troughDate);
    const repairStart = declineEnd;
    const repairEnd = xFor(repairEndDate);
    phaseBands.append(
      svgNode("rect", {
        x: declineStart,
        y: margin.top,
        width: Math.max(declineEnd - declineStart, 1),
        height: plotHeight,
        class: "drawdown-decline-band",
      }),
      svgNode("rect", {
        x: repairStart,
        y: margin.top,
        width: Math.max(repairEnd - repairStart, 1),
        height: plotHeight,
        class: "drawdown-recovery-band",
      }),
    );
    svg.append(phaseBands);
  }

  const grid = svgNode("g", { class: "nav-grid" });
  const yAxisTicks = buildYAxisTicks(
    minValue,
    maxValue,
    isPercentageChart,
  );
  yAxisTicks.forEach((labelValue) => {
    const y = yFor(labelValue);
    const isZeroTick = isPercentageChart && Math.abs(labelValue) < 1e-9;
    grid.append(
      svgNode("line", {
        x1: margin.left,
        y1: y,
        x2: width - margin.right,
        y2: y,
        class: isZeroTick ? "zero-line" : "",
      }),
    );
    const label = svgNode("text", {
      x: margin.left - 12,
      y: y + 4,
      "text-anchor": "end",
      class: isZeroTick ? "zero-label" : "",
    });
    label.textContent = isZeroTick
      ? "0.00%"
      : formatNavValue(labelValue, metric, true);
    grid.append(label);
  });
  for (let index = 0; index < 5; index += 1) {
    const ratio = index / 4;
    const time = startTime + ratio * (endTime - startTime);
    const x = margin.left + ratio * plotWidth;
    grid.append(
      svgNode("line", {
        x1: x,
        y1: margin.top,
        x2: x,
        y2: height - margin.bottom,
      }),
    );
    const label = svgNode("text", {
      x,
      y: height - 16,
      "text-anchor": index === 0 ? "start" : index === 4 ? "end" : "middle",
    });
    label.textContent = formatChartDate(
      new Date(time).toISOString().slice(0, 10),
      range !== "1m",
    );
    grid.append(label);
  }
  svg.append(grid);

  navPlotPoints = rows.map((row) => ({
    ...row,
    x: xFor(row.日期),
    y: yFor(row[config.valueKey]),
    value: Number(row[config.valueKey]),
  }));
  const linePath = navPlotPoints
    .map((point, index) => `${index ? "L" : "M"}${point.x.toFixed(2)},${point.y.toFixed(2)}`)
    .join(" ");
  const areaPath = `${linePath} L${navPlotPoints.at(-1).x.toFixed(2)},${(
    height - margin.bottom
  ).toFixed(2)} L${navPlotPoints[0].x.toFixed(2)},${(
    height - margin.bottom
  ).toFixed(2)} Z`;
  svg.append(
    svgNode("path", { d: areaPath, class: "nav-area" }),
    svgNode("path", { d: linePath, class: "nav-line" }),
  );

  if (benchmarkRows.length >= 2) {
    benchmarkPlotPoints = benchmarkRows.map((row) => ({
      ...row,
      x: xFor(row.日期),
      y: yFor(row.累计收益率),
      value: Number(row.累计收益率),
    }));
    const benchmarkPath = benchmarkPlotPoints
      .map(
        (point, index) =>
          `${index ? "L" : "M"}${point.x.toFixed(2)},${point.y.toFixed(2)}`,
      )
      .join(" ");
    svg.append(
      svgNode("path", {
        d: benchmarkPath,
        class: "benchmark-line",
      }),
    );
  }

  if (
    isDrawdownView &&
    drawdownAnalysis?.peakIndex !== null &&
    drawdownAnalysis?.troughIndex !== null &&
    drawdownAnalysis.maxDrawdown < -0.000001
  ) {
    const {
      peakIndex,
      troughIndex,
      recoveryIndex,
      recoveryDays,
      elapsedRecoveryDays,
      maxDrawdown,
    } = drawdownAnalysis;
    const repairEndIndex = recoveryIndex ?? navPlotPoints.length - 1;
    const stages = svgNode("g", { class: "drawdown-stages" });
    const segmentPath = (startIndex, endIndex) =>
      navPlotPoints
        .slice(startIndex, endIndex + 1)
        .map(
          (point, index) =>
            `${index ? "L" : "M"}${point.x.toFixed(2)},${point.y.toFixed(2)}`,
        )
        .join(" ");
    stages.append(
      svgNode("path", {
        d: segmentPath(peakIndex, troughIndex),
        class: "drawdown-decline-line",
      }),
      svgNode("path", {
        d: segmentPath(troughIndex, repairEndIndex),
        class: recoveryIndex === null
          ? "drawdown-recovery-line pending"
          : "drawdown-recovery-line",
      }),
    );

    const addMarker = (point, className, label, position = "above") => {
      const marker = svgNode("g", { class: `drawdown-marker ${className}` });
      const labelWidth = Math.max(92, label.length * 12 + 24);
      const labelX = Math.min(
        width - margin.right - labelWidth,
        Math.max(margin.left, point.x - labelWidth / 2),
      );
      const labelY =
        position === "below"
          ? Math.min(height - margin.bottom - 30, point.y + 20)
          : Math.max(margin.top + 4, point.y - 38);
      marker.append(
        svgNode("line", {
          x1: point.x,
          y1: point.y,
          x2: point.x,
          y2: position === "below" ? labelY : labelY + 26,
        }),
        svgNode("rect", {
          x: labelX,
          y: labelY,
          width: labelWidth,
          height: 26,
          rx: 3,
        }),
      );
      const labelNode = svgNode("text", {
        x: labelX + labelWidth / 2,
        y: labelY + 17,
        "text-anchor": "middle",
      });
      labelNode.textContent = label;
      marker.append(
        svgNode("circle", { cx: point.x, cy: point.y, r: 5 }),
        labelNode,
      );
      stages.append(marker);
    };

    addMarker(
      navPlotPoints[troughIndex],
      "maximum",
      `最大回撤 ${Math.abs(maxDrawdown).toFixed(2)}%`,
      "below",
    );
    addMarker(
      navPlotPoints[repairEndIndex],
      recoveryIndex === null ? "repair pending" : "repair",
      recoveryIndex === null
        ? `修复中 · 已 ${elapsedRecoveryDays} 天`
        : `${recoveryDays} 天修复`,
      "above",
    );
    svg.append(stages);
  }

  if (metric === "单位净值") {
    const dividends = currentDividends.filter(
      (dividend) =>
        dividend.除息日 >= rows[0].日期 &&
        dividend.除息日 <= rows.at(-1).日期,
    );
    const dividendGroup = svgNode("g", { class: "nav-dividends" });
    dividends.forEach((dividend) => {
      const time = new Date(`${dividend.除息日}T00:00:00`).getTime();
      const nearest = navPlotPoints.reduce((best, point) => {
        const pointTime = new Date(`${point.日期}T00:00:00`).getTime();
        const bestTime = new Date(`${best.日期}T00:00:00`).getTime();
        return Math.abs(pointTime - time) < Math.abs(bestTime - time)
          ? point
          : best;
      });
      const marker = svgNode("g");
      const title = svgNode("title");
      title.textContent = `${formatChartDate(dividend.除息日)} 分红：每份 ${
        dividend.每份分红 === null
          ? "—"
          : formatNumber(dividend.每份分红, 4)
      } 元`;
      marker.append(
        title,
        svgNode("line", {
          x1: nearest.x,
          y1: nearest.y,
          x2: nearest.x,
          y2: height - margin.bottom,
        }),
        svgNode("circle", {
          cx: nearest.x,
          cy: nearest.y,
          r: "3.5",
        }),
      );
      dividendGroup.append(marker);
    });
    svg.append(dividendGroup);
  }

  const crosshair = svgNode("g", {
    id: "nav-crosshair",
    class: "nav-crosshair",
    visibility: "hidden",
  });
  crosshair.append(
    svgNode("line", {
      x1: "0",
      y1: margin.top,
      x2: "0",
      y2: height - margin.bottom,
    }),
    svgNode("circle", { cx: "0", cy: "0", r: "5" }),
    svgNode("circle", {
      cx: "0",
      cy: "0",
      r: "4.5",
      class: "benchmark-crosshair-point",
      visibility: "hidden",
    }),
  );
  svg.append(crosshair);

  const firstValue = Number(rows[0][config.valueKey]);
  const lastValue = Number(rows.at(-1)[config.valueKey]);
  const changeElement = document.querySelector("#nav-range-change");
  if (isDrawdownView) {
    const {
      maxDrawdown,
      peakIndex,
      troughIndex,
      recoveryIndex,
      recoveryDays,
      elapsedRecoveryDays,
    } = drawdownAnalysis;
    const hasDrawdown = maxDrawdown < -0.000001;
    changeElement.textContent = `${Math.abs(maxDrawdown).toFixed(2)}%`;
    changeElement.className = hasDrawdown ? "drawdown-value" : "";
    text(
      "#nav-range-high",
      hasDrawdown
        ? recoveryIndex === null
          ? `修复中 · 已 ${elapsedRecoveryDays} 天`
          : `${recoveryDays} 天`
        : "0 天",
    );
    text(
      "#nav-range-low",
      hasDrawdown
        ? `${formatChartDate(rows[peakIndex].日期)} — ${formatChartDate(
            rows[troughIndex].日期,
          )}`
        : "区间内无回撤",
    );
    text(
      "#nav-range-dates",
      hasDrawdown
        ? `${formatChartDate(rows[troughIndex].日期)} — ${
            recoveryIndex === null
              ? "至今（修复中）"
              : formatChartDate(rows[recoveryIndex].日期)
          }`
        : "持续创新高",
    );
    svg.setAttribute(
      "aria-label",
      `${formatChartDate(rows[0].日期)}至${formatChartDate(
        rows.at(-1).日期,
      )}的区间收益曲线，最大回撤${Math.abs(maxDrawdown).toFixed(2)}%，${
        hasDrawdown
          ? recoveryIndex === null
            ? `尚未修复，已历时${elapsedRecoveryDays}天`
            : `历时${recoveryDays}天修复`
          : "区间内无回撤"
      }`,
    );
    return;
  }
  const periodChange =
    metric === "累计收益率"
      ? lastValue - firstValue
      : ((lastValue / firstValue) - 1) * 100;
  changeElement.textContent = formatPercent(periodChange);
  changeElement.className = movementClass(periodChange);
  if (isPerformanceView) {
    const benchmarkChange = benchmarkPlotPoints.length
      ? benchmarkPlotPoints.at(-1).value
      : null;
    const relativeChange = Number.isFinite(benchmarkChange)
      ? periodChange - benchmarkChange
      : null;
    const benchmarkElement = document.querySelector("#nav-range-high");
    const relativeElement = document.querySelector("#nav-range-low");
    benchmarkElement.textContent = Number.isFinite(benchmarkChange)
      ? formatPercent(benchmarkChange)
      : "—";
    benchmarkElement.className = Number.isFinite(benchmarkChange)
      ? movementClass(benchmarkChange)
      : "";
    relativeElement.textContent = Number.isFinite(relativeChange)
      ? `${relativeChange > 0 ? "+" : ""}${relativeChange.toFixed(2)} 个百分点`
      : "—";
    relativeElement.className = Number.isFinite(relativeChange)
      ? movementClass(relativeChange)
      : "";
  } else {
    text("#nav-range-high", formatNavValue(Math.max(...values), metric));
    text("#nav-range-low", formatNavValue(Math.min(...values), metric));
  }
  text(
    "#nav-range-dates",
    `${formatChartDate(rows[0].日期)} — ${formatChartDate(rows.at(-1).日期)}`,
  );
  svg.setAttribute(
    "aria-label",
    `${formatChartDate(rows[0].日期)}至${formatChartDate(
      rows.at(-1).日期,
    )}的${config.tooltipLabel}曲线，基金涨幅${formatPercent(periodChange)}${
      benchmarkPlotPoints.length
        ? `，${currentTrackBenchmark.简称}涨幅${formatPercent(
            benchmarkPlotPoints.at(-1).value,
          )}`
        : ""
    }`,
  );
}

async function loadTrackBenchmark(key, reason = "") {
  currentTrackBenchmarkKey = key;
  const requestId = ++trackBenchmarkRequestId;
  const select = document.querySelector("#track-benchmark-select");
  const status = document.querySelector("#track-benchmark-status");
  select.value = key;
  select.disabled = true;
  status.textContent = "正在加载赛道基准…";

  try {
    let payload = trackBenchmarkCache.get(key);
    if (!payload) {
      const response = await fetch(`/api/benchmarks/${key}`);
      payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "赛道基准加载失败");
      }
      trackBenchmarkCache.set(key, payload);
    }
    if (requestId !== trackBenchmarkRequestId) return;
    currentTrackBenchmark = payload;
    document.querySelector("#benchmark-legend-label").textContent =
      payload.简称 ?? payload.名称;
    status.textContent = reason || payload.说明 || "赛道基准已加载";
  } catch (error) {
    if (requestId !== trackBenchmarkRequestId) return;
    currentTrackBenchmark = null;
    document.querySelector("#benchmark-legend-label").textContent = "赛道基准";
    status.textContent = error.message || "赛道基准暂不可用";
  } finally {
    if (requestId === trackBenchmarkRequestId) {
      select.disabled = false;
      renderNavChart(currentNavRange, currentNavMetric);
    }
  }
}

function initializeTrackBenchmark(recommendation = {}) {
  const key = recommendation.key || "hs300";
  currentTrackBenchmark = null;
  loadTrackBenchmark(key, recommendation.理由 || "");
}

function firstNavOnOrAfter(rows, requestedDate) {
  let low = 0;
  let high = rows.length - 1;
  let match = null;
  while (low <= high) {
    const middle = Math.floor((low + high) / 2);
    if (rows[middle].日期 >= requestedDate) {
      match = rows[middle];
      high = middle - 1;
    } else {
      low = middle + 1;
    }
  }
  return match;
}

function buildInvestmentSchedule(start, end, frequency) {
  const startDate = new Date(`${start}T00:00:00`);
  const endDate = new Date(`${end}T00:00:00`);
  if (
    Number.isNaN(startDate.getTime()) ||
    Number.isNaN(endDate.getTime()) ||
    startDate > endDate
  ) {
    return [];
  }

  const dates = [];
  if (frequency === "weekly") {
    const cursor = new Date(startDate);
    while (cursor <= endDate && dates.length < 2000) {
      dates.push(localIsoDate(cursor));
      cursor.setDate(cursor.getDate() + 7);
    }
    return dates;
  }

  const preferredDay = startDate.getDate();
  for (let index = 0; index < 1200; index += 1) {
    const scheduled = new Date(
      startDate.getFullYear(),
      startDate.getMonth() + index,
      1,
    );
    const lastDay = new Date(
      scheduled.getFullYear(),
      scheduled.getMonth() + 1,
      0,
    ).getDate();
    scheduled.setDate(Math.min(preferredDay, lastDay));
    if (scheduled > endDate) break;
    dates.push(localIsoDate(scheduled));
  }
  return dates;
}

function selectInvestmentMode(mode, recalculate = true) {
  currentInvestmentMode = mode;
  const recurring = mode === "recurring";
  document.querySelectorAll("[data-simulator-mode]").forEach((button) => {
    const active = button.dataset.simulatorMode === mode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  document.querySelector("#investment-frequency-field").hidden = !recurring;
  text(
    "#investment-date-label",
    recurring ? "定投开始日期" : "买入日期",
  );
  text(
    "#investment-amount-label",
    recurring ? "每期投入金额" : "买入金额",
  );
  text(
    "#investment-count-label",
    recurring ? "定投次数" : "买入次数",
  );
  text(
    "#holding-simulator-submit",
    recurring ? "计算定投结果" : "计算持有结果",
  );
  text(
    "#simulator-description",
    recurring
      ? "从选定日期开始按周或按月投入固定金额，持续至最新净值日。"
      : "假设在选定日期一次性买入并持有至最新净值日，查看更贴近个人持有期的收益。",
  );
  if (recalculate) calculateHoldingSimulation();
}

function calculateHoldingSimulation() {
  const rows = currentNavHistory?.单位净值?.明细 ?? [];
  const dateInput = document.querySelector("#holding-start-date");
  const amountInput = document.querySelector("#holding-amount");
  const frequency = document.querySelector("#investment-frequency").value;
  const note = document.querySelector("#holding-simulator-note");
  const amount = Number(amountInput.value);
  const requestedDate = dateInput.value;

  const resetResults = (message) => {
    text("#holding-invested", "—");
    text("#investment-count", "—");
    text("#holding-return", "—");
    text("#holding-profit", "—");
    text("#holding-end-value", "—");
    text("#holding-period", "—");
    note.textContent = message;
  };

  if (rows.length < 2) {
    resetResults("该基金暂无足够的成立以来收益数据，无法进行模拟。");
    return;
  }
  if (!requestedDate || !Number.isFinite(amount) || amount < 100) {
    resetResults(
      `请选择有效开始日期，并输入不少于 100 元的${
        currentInvestmentMode === "recurring" ? "每期投入金额" : "买入金额"
      }。`,
    );
    return;
  }

  const end = rows.at(-1);
  if (requestedDate < rows[0].日期) {
    resetResults(`开始日期不能早于首个净值日期 ${rows[0].日期}。`);
    return;
  }
  if (requestedDate > end.日期) {
    resetResults(`开始日期不能晚于最新净值日期 ${end.日期}。`);
    return;
  }

  const endNav = Number(end.单位净值);
  if (!Number.isFinite(endNav) || endNav <= 0) {
    resetResults("单位净值序列存在异常，暂时无法进行模拟。");
    return;
  }

  const scheduledDates =
    currentInvestmentMode === "recurring"
      ? buildInvestmentSchedule(requestedDate, end.日期, frequency)
      : [requestedDate];
  const orders = scheduledDates
    .map((scheduledDate) => {
      const navRow = firstNavOnOrAfter(rows, scheduledDate);
      const nav = Number(navRow?.单位净值);
      if (!navRow || !Number.isFinite(nav) || nav <= 0) return null;
      return {
        scheduledDate,
        actualDate: navRow.日期,
        units: amount / nav,
      };
    })
    .filter(Boolean);
  if (!orders.length) {
    resetResults("所选区间内没有可用于投入的净值数据。");
    return;
  }

  const totalUnits = orders.reduce((sum, order) => sum + order.units, 0);
  const cashDividends = orders.reduce((cash, order) => {
    const dividendPerShare = currentDividends
      .filter(
        (dividend) =>
          dividend.除息日 > order.actualDate &&
          dividend.除息日 <= end.日期 &&
          Number.isFinite(Number(dividend.每份分红)),
      )
      .reduce((sum, dividend) => sum + Number(dividend.每份分红), 0);
    return cash + order.units * dividendPerShare;
  }, 0);
  const totalInvested = amount * orders.length;
  const endValue = totalUnits * endNav + cashDividends;
  const holdingReturn = (endValue / totalInvested - 1) * 100;
  const profit = endValue - totalInvested;
  const actualStart = orders[0].actualDate;
  const shiftedOrders = orders.filter(
    (order) => order.scheduledDate !== order.actualDate,
  ).length;
  const returnElement = document.querySelector("#holding-return");
  const profitElement = document.querySelector("#holding-profit");
  text("#holding-invested", formatCurrency(totalInvested));
  text("#investment-count", `${orders.length} 次`);
  returnElement.textContent = formatPercent(holdingReturn);
  returnElement.className = movementClass(holdingReturn);
  profitElement.textContent = formatCurrency(profit, true);
  profitElement.className = movementClass(profit);
  text("#holding-end-value", formatCurrency(endValue));
  text(
    "#holding-period",
    `${formatChartDate(actualStart)} — ${formatChartDate(end.日期)}`,
  );
  if (currentInvestmentMode === "recurring") {
    const frequencyLabel = frequency === "weekly" ? "每周" : "每月";
    note.textContent = `${frequencyLabel}投入，共 ${orders.length} 期${
      shiftedOrders ? `，其中 ${shiftedOrders} 期顺延至下一有效净值日` : ""
    }；期间现金分红约 ${formatCurrency(cashDividends)}，不计申购、赎回费用。`;
  } else {
    note.textContent =
      actualStart === requestedDate
        ? `按单位净值估算，期间现金分红约 ${formatCurrency(cashDividends)}；不计申购、赎回费用。`
        : `所选日期无净值数据，已从下一可用日期 ${formatChartDate(actualStart)} 起算；期间现金分红约 ${formatCurrency(cashDividends)}，不计交易费用。`;
  }
}

function renderHoldingSimulator() {
  const rows = currentNavHistory?.单位净值?.明细 ?? [];
  const dateInput = document.querySelector("#holding-start-date");
  selectInvestmentMode(currentInvestmentMode, false);
  if (rows.length < 2) {
    dateInput.value = "";
    dateInput.removeAttribute("min");
    dateInput.removeAttribute("max");
    calculateHoldingSimulation();
    return;
  }

  const firstDate = rows[0].日期;
  const endDate = rows.at(-1).日期;
  const defaultDate = new Date(`${endDate}T00:00:00`);
  defaultDate.setFullYear(defaultDate.getFullYear() - 1);
  const defaultValue = localIsoDate(defaultDate);
  dateInput.min = firstDate;
  dateInput.max = endDate;
  dateInput.value = defaultValue < firstDate ? firstDate : defaultValue;
  calculateHoldingSimulation();
}

function renderNavHistory(history) {
  currentNavHistory = history ?? {};
  currentDividends = history?.分红事件 ?? [];
  currentNavMetric = history?.默认指标 ?? "累计收益率";
  initializeCustomRange();
  renderNavChart(currentNavRange, currentNavMetric);
  renderHoldingSimulator();
}

function buildTreemapLayout(items, bounds = { x: 0, y: 0, width: 100, height: 100 }) {
  if (!items.length) return [];
  if (items.length === 1) {
    return [{ ...items[0], ...bounds }];
  }

  const total = items.reduce((sum, item) => sum + item.weight, 0);
  let firstTotal = 0;
  let splitIndex = 1;
  for (let index = 0; index < items.length - 1; index += 1) {
    const nextTotal = firstTotal + items[index].weight;
    if (Math.abs(total / 2 - nextTotal) <= Math.abs(total / 2 - firstTotal)) {
      firstTotal = nextTotal;
      splitIndex = index + 1;
    } else {
      break;
    }
  }

  const first = items.slice(0, splitIndex);
  const second = items.slice(splitIndex);
  const ratio = firstTotal / total;

  if (bounds.width >= bounds.height) {
    const firstWidth = bounds.width * ratio;
    return [
      ...buildTreemapLayout(first, { ...bounds, width: firstWidth }),
      ...buildTreemapLayout(second, {
        x: bounds.x + firstWidth,
        y: bounds.y,
        width: bounds.width - firstWidth,
        height: bounds.height,
      }),
    ];
  }

  const firstHeight = bounds.height * ratio;
  return [
    ...buildTreemapLayout(first, { ...bounds, height: firstHeight }),
    ...buildTreemapLayout(second, {
      x: bounds.x,
      y: bounds.y + firstHeight,
      width: bounds.width,
      height: bounds.height - firstHeight,
    }),
  ];
}

function renderTreemap(
  container,
  items,
  ariaLabel,
  weightScope = "基金净值",
) {
  container.replaceChildren();
  const normalized = items
    .map((item, index) => ({
      ...item,
      index,
      weight: Math.max(Number(item.weight) || 0, 0),
    }))
    .filter((item) => item.weight > 0)
    .sort((a, b) => b.weight - a.weight);

  if (!normalized.length) {
    container.hidden = true;
    return 0;
  }

  container.hidden = false;
  const total = normalized.reduce((sum, item) => sum + item.weight, 0);
  const layout = buildTreemapLayout(normalized);
  layout.forEach((item, index) => {
    const cell = document.createElement("div");
    const area = item.width * item.height;
    const colorIndex = index % palette.length;
    cell.className = "treemap-cell";
    if (area < 900) cell.classList.add("compact");
    if (area < 330) cell.classList.add("micro");
    cell.style.left = `${item.x}%`;
    cell.style.top = `${item.y}%`;
    cell.style.width = `${item.width}%`;
    cell.style.height = `${item.height}%`;
    cell.style.background = palette[colorIndex];
    cell.style.color = [1, 2, 3].includes(colorIndex)
      ? "var(--ink)"
      : "var(--paper-light)";
    cell.style.setProperty("--cell-delay", `${Math.min(index * 45, 360)}ms`);
    cell.tabIndex = 0;
    cell.title = `${item.name}${item.code ? ` · ${item.code}` : ""}：占${weightScope} ${item.weight.toFixed(2)}%`;

    const name = document.createElement("span");
    name.className = "treemap-name";
    name.textContent = item.name;
    const weight = document.createElement("strong");
    weight.textContent = `${formatNumber(item.weight, 2)}%`;
    cell.append(name, weight);
    if (item.code) {
      const code = document.createElement("small");
      code.textContent = item.code;
      cell.append(code);
    }
    container.append(cell);
  });

  container.setAttribute(
    "aria-label",
    `${ariaLabel}，共 ${normalized.length} 项，合计占${weightScope} ${total.toFixed(2)}%`,
  );
  return total;
}

function renderSectorMatrix(holdingGroup, type) {
  const container = document.querySelector("#sector-treemap");
  const empty = document.querySelector("#sector-empty");
  const note = document.querySelector("#sector-note");
  const viewTabs = document.querySelector("#structure-view-tabs");
  let group = {};
  let rows = [];
  let nameKey = "行业类别";
  let chartLabel = "股票行业配置矩阵图";
  const weightScope =
    type === "穿透" ? "目标 ETF 净值" : "基金净值";

  viewTabs.replaceChildren();
  if (type === "债券") {
    const bondGroup = currentHoldings?.债券持仓 ?? {};
    const views = {
      品种: {
        group: bondGroup.品种结构 ?? {},
        nameKey: "债券品种",
        eyebrow: "BOND TYPE",
        title: "债券品种结构",
        totalLabel: "完整组合占净值",
      },
      信用属性: {
        group: {
          ...(bondGroup.品种结构?.信用属性 ?? {}),
          报告期: bondGroup.品种结构?.报告期,
        },
        nameKey: "信用属性",
        eyebrow: "CREDIT PROFILE",
        title: "利率债 / 信用债",
        totalLabel: "归并结构占净值",
      },
      剩余期限: {
        group: bondGroup.期限结构 ?? {},
        nameKey: "期限分类",
        eyebrow: "MATURITY",
        title: "披露债券剩余期限",
        totalLabel: "披露债券占净值",
      },
    };
    const availableViews = Object.entries(views).filter(
      ([, config]) => (config.group.明细 ?? []).length,
    );
    if (
      !(views[currentBondStructureView]?.group?.明细 ?? []).length &&
      availableViews.length
    ) {
      currentBondStructureView = availableViews[0][0];
    }
    const view = views[currentBondStructureView] ?? views.品种;
    group = view.group;
    rows = group.明细 ?? [];
    nameKey = view.nameKey;
    chartLabel = `${view.title}矩阵图`;
    text("#structure-map-label", view.eyebrow);
    text("#structure-map-title", view.title);
    text("#sector-total-share-label", view.totalLabel);
    viewTabs.hidden = availableViews.length < 2;
    availableViews.forEach(([viewName]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "structure-view-tab";
      button.textContent = viewName;
      const active = viewName === currentBondStructureView;
      button.classList.toggle("active", active);
      button.setAttribute("role", "tab");
      button.setAttribute("aria-selected", String(active));
      button.addEventListener("click", () => {
        currentBondStructureView = viewName;
        renderSectorMatrix(holdingGroup, type);
      });
      viewTabs.append(button);
    });
  } else {
    group =
      type === "穿透"
        ? holdingGroup?.板块配置 ?? {}
        : currentHoldings?.板块配置 ?? {};
    rows = group.明细 ?? [];
    viewTabs.hidden = true;
    text("#structure-map-label", "SECTOR MAP");
    text("#structure-map-title", "行业 / 板块矩阵");
    text(
      "#sector-total-share-label",
      type === "穿透" ? "ETF行业内部占比" : "股票行业占净值",
    );
  }

  const total = renderTreemap(
    container,
    rows.map((row) => ({
      name: row[nameKey] ?? "未分类",
      weight: row.占净值比例,
    })),
    chartLabel,
    weightScope,
  );
  text("#sector-total-share", `${formatNumber(total, 1)}%`);

  empty.hidden = Boolean(rows.length);
  if (!rows.length) {
    empty.textContent =
      group.说明 ??
      (type === "债券"
        ? "最新季报暂未提供可解析的债券结构。"
        : type === "穿透"
        ? "AKShare 暂未返回目标 ETF 的行业配置。"
        : "AKShare 暂无该基金的股票行业配置。");
  }
  note.textContent = rows.length
    ? `${group.报告期 ?? "最新报告期"} · ${group.口径 ?? "股票行业配置"}${
        group.说明 ? ` · ${group.说明}` : ""
      }`
    : type === "债券"
      ? "债券结构暂不可用，不根据名称猜测品种或期限。"
      : type === "穿透"
        ? "目标 ETF 暂无可用行业配置。"
        : "仅展示官方披露数据，不根据证券名称推测行业。";
}

function renderAssetAllocation(allocation) {
  const bar = document.querySelector("#asset-allocation-bar");
  const stats = document.querySelector("#asset-allocation-stats");
  const details = allocation?.明细 ?? [];
  const categoryColors = {
    股票: "#d33b28",
    债券: "#14745a",
    基金: "#d7a928",
    其他: "#73776f",
  };

  bar.replaceChildren();
  stats.replaceChildren();
  text("#asset-allocation-period", allocation?.报告期, "暂无报告期");

  if (!details.length) {
    bar.classList.add("empty");
    bar.setAttribute("aria-label", "暂无可用的基金资产分布");
    const empty = document.createElement("span");
    empty.className = "asset-allocation-empty";
    empty.textContent = "最新季报暂未提供可解析的资产分布";
    bar.append(empty);
    text(
      "#asset-allocation-note",
      allocation?.说明,
      "资产分布暂不可用，持仓明细仍按基金净值口径展示。",
    );
    return;
  }

  bar.classList.remove("empty");
  const ariaParts = [];
  details.forEach((item) => {
    const category = item.资产类别 ?? "其他";
    const share = Math.max(Number(item.占比) || 0, 0);
    const color = categoryColors[category] ?? categoryColors.其他;
    ariaParts.push(`${category} ${share.toFixed(2)}%`);

    if (share > 0) {
      const segment = document.createElement("div");
      segment.className = "asset-allocation-segment";
      segment.style.width = `${share}%`;
      segment.style.background = color;
      segment.title = `${category}：${share.toFixed(2)}%`;
      if (share >= 9) {
        const segmentLabel = document.createElement("span");
        segmentLabel.textContent = category;
        segment.append(segmentLabel);
      }
      bar.append(segment);
    }

    const card = document.createElement("div");
    card.className = "asset-allocation-stat";
    card.style.setProperty("--asset-color", color);
    const label = document.createElement("span");
    label.textContent = category;
    const value = document.createElement("strong");
    value.textContent = `${formatNumber(share, 2)}%`;
    card.append(label, value);
    stats.append(card);
  });
  bar.setAttribute("aria-label", `基金资产分布：${ariaParts.join("，")}`);
  text(
    "#asset-allocation-note",
    `${allocation?.说明 ?? "来自最新季度报告。"}${
      allocation?.公告日期 ? ` · 公告于 ${allocation.公告日期}` : ""
    }`,
  );
}

function renderHoldingGroup(group, type) {
  const rows = group?.明细 ?? [];
  const tableBody = document.querySelector("#holdings-table");
  const noHoldings = document.querySelector("#no-holdings");
  const holdingTreemap = document.querySelector("#holding-treemap");
  const quantityHeading = document.querySelector("#quantity-heading");
  const weightHeading = document.querySelector("#holding-weight-heading");
  const isBond = type === "债券";
  const isPenetration = type === "穿透";
  const penetration = currentHoldings?.ETF穿透 ?? {};
  const target = penetration.目标ETF ?? {};
  const context = document.querySelector("#holdings-context");

  text("#holdings-period", group?.报告期, "暂无报告期");
  text("#holdings-count", rows.length, "0");
  text(
    "#security-map-title",
    isPenetration
      ? "目标 ETF 穿透矩阵"
      : penetration.可用 && type === "股票"
        ? "直接股票持仓矩阵"
        : `${type}持仓矩阵`,
  );
  text(
    "#top-holdings-share-label",
    isPenetration ? "ETF内部列示占比" : "已列示占净值",
  );
  text(
    "#security-map-note",
    isPenetration
      ? "矩形面积为目标 ETF 内部权重，尚未乘以联接基金持有目标 ETF 的比例。"
      : isBond
        ? "矩形面积按最新报告披露的各只债券占基金净值比例分配。"
        : penetration.可用 && type === "股票"
          ? "矩形面积按各项占联接基金净值比例分配，标签显示实际比例。"
          : "矩形面积按各项占基金净值比例分配，标签显示实际比例。",
  );
  if (isPenetration) {
    context.hidden = false;
    context.textContent = `穿透目标：${target.名称 ?? "目标 ETF"} · ${target.代码 ?? "代码未知"}`;
  } else if (penetration.可用 && type === "股票") {
    context.hidden = false;
    context.textContent = "以下为联接基金直接持有的股票，不包含目标 ETF 内部持仓。";
  } else {
    context.hidden = true;
    context.textContent = "";
  }
  tableBody.replaceChildren();
  quantityHeading.hidden = isBond;
  weightHeading.textContent = isPenetration ? "ETF内部占比" : "占净值";
  renderSectorMatrix(group, type);

  if (!rows.length) {
    noHoldings.hidden = false;
    holdingTreemap.replaceChildren();
    holdingTreemap.hidden = true;
    text("#top-holdings-share", "0%");
    return;
  }

  noHoldings.hidden = true;
  const maxWeight = Math.max(
    ...rows.map((row) => Number(row.占净值比例) || 0),
    1,
  );

  rows.forEach((row) => {
    const tr = document.createElement("tr");

    const rank = document.createElement("td");
    rank.className = "holding-rank";
    rank.textContent = String(row.持仓排名 ?? "—").padStart(2, "0");

    const security = document.createElement("td");
    const name = document.createElement("span");
    name.className = "security-name";
    name.textContent = isBond
      ? row.债券名称 ?? "未知债券"
      : row.股票名称 ?? "未知股票";
    const code = document.createElement("span");
    code.className = "security-code";
    code.textContent = isBond
      ? [
          row.债券代码,
          row.债券类型,
          row.到期日 ? `到期 ${row.到期日}` : null,
        ]
          .filter(Boolean)
          .join(" · ") || "—"
      : row.股票代码 ?? "—";
    security.append(name, code);

    const weight = document.createElement("td");
    weight.className = "weight-cell";
    const weightValue = document.createElement("span");
    weightValue.className = "weight-value";
    weightValue.textContent = `${formatNumber(row.占净值比例, 2)}%`;
    const track = document.createElement("span");
    track.className = "weight-track";
    const fill = document.createElement("i");
    fill.style.width = `${Math.min(((Number(row.占净值比例) || 0) / maxWeight) * 100, 100)}%`;
    track.append(fill);
    weight.append(weightValue, track);

    const shares = document.createElement("td");
    shares.hidden = isBond;
    shares.textContent = `${formatNumber(row.持股数, 2)} 万股`;

    const marketValue = document.createElement("td");
    marketValue.textContent = `${formatNumber(row.持仓市值, 2)} 万元`;

    tr.append(rank, security, weight, shares, marketValue);
    tableBody.append(tr);
  });

  const total = renderTreemap(
    holdingTreemap,
    rows.map((row) => ({
      name: isBond
        ? row.债券名称 ?? "未知债券"
        : row.股票名称 ?? "未知股票",
      code: isBond ? row.债券代码 : row.股票代码,
      weight: row.占净值比例,
    })),
    isPenetration ? "目标 ETF 穿透持仓矩阵图" : `${type}持仓矩阵图`,
    isPenetration ? "目标 ETF 净值" : "基金净值",
  );
  text("#top-holdings-share", `${formatNumber(total, 1)}%`);
}

function holdingGroupConfig(type) {
  const penetrationAvailable = Boolean(currentHoldings?.ETF穿透?.可用);
  const configs = {
    穿透: {
      key: "ETF穿透",
      label: "ETF穿透",
    },
    股票: {
      key: "股票持仓",
      label: penetrationAvailable ? "直接股票" : "股票持仓",
    },
    债券: {
      key: "债券持仓",
      label: "债券持仓",
    },
  };
  return configs[type];
}

function selectHoldingType(type) {
  currentHoldingType = type;
  if (type === "债券") {
    currentBondStructureView = "品种";
  }
  document.querySelectorAll(".holding-tab").forEach((button) => {
    const active = button.dataset.holdingType === type;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  const config = holdingGroupConfig(type);
  renderHoldingGroup(currentHoldings?.[config.key], type);
}

function renderHoldings(holdings) {
  currentHoldings = holdings ?? {};
  renderAssetAllocation(currentHoldings.资产分布);
  const tabs = document.querySelector("#holdings-tabs");
  const groups = ["穿透", "股票", "债券"].filter(
    (type) => {
      const config = holdingGroupConfig(type);
      return (currentHoldings?.[config.key]?.明细 ?? []).length;
    },
  );

  tabs.replaceChildren();
  tabs.hidden = groups.length < 2;

  groups.forEach((type) => {
    const config = holdingGroupConfig(type);
    const button = document.createElement("button");
    const count = currentHoldings[config.key]?.明细?.length ?? 0;
    button.type = "button";
    button.className = "holding-tab";
    button.dataset.holdingType = type;
    button.setAttribute("role", "tab");
    button.textContent = `${config.label} ${count}`;
    button.addEventListener("click", () => selectHoldingType(type));
    tabs.append(button);
  });

  currentHoldingType =
    groups.includes("穿透")
      ? "穿透"
      : groups.includes("股票")
        ? "股票"
        : groups.includes("债券")
          ? "债券"
          : "股票";

  if (!groups.length) {
    renderHoldingGroup(
      {
        报告期: currentHoldings?.报告期,
        明细: currentHoldings?.明细 ?? [],
      },
      currentHoldingType,
    );
    return;
  }
  selectHoldingType(currentHoldingType);
}

function renderWarnings(warnings) {
  const panel = document.querySelector("#warnings-panel");
  const list = document.querySelector("#warnings-list");
  list.replaceChildren();
  panel.hidden = !warnings?.length;
  (warnings ?? []).forEach((warning) => {
    const item = document.createElement("li");
    item.textContent = warning;
    list.append(item);
  });
}

function renderFundProfile(basic) {
  const scale = basic.基金规模 ?? {};
  const holders = basic.持有人结构 ?? {};
  const purchaseFee = basic.买入费率 ?? {};
  const feeRows = purchaseFee.明细 ?? [];

  text("#founded-date", basic.成立日期 ?? basic.成立日);
  text("#fund-age", basic.成立时间);
  text("#fund-scale", scale.最新净资产);
  text("#profile-summary-age", basic.成立时间);
  text("#profile-summary-manager", basic.管理人);
  const managementRate = Number(
    String(basic.管理费率 ?? "").match(/[\d.]+/)?.[0],
  );
  const custodyRate = Number(
    String(basic.托管费率 ?? "").match(/[\d.]+/)?.[0],
  );
  const hasManagementRate = Number.isFinite(managementRate);
  const hasCustodyRate = Number.isFinite(custodyRate);
  const totalOperatingRate =
    (hasManagementRate ? managementRate : 0) +
    (hasCustodyRate ? custodyRate : 0);
  text(
    "#profile-summary-cost",
    hasManagementRate || hasCustodyRate
      ? `约 ${formatNumber(totalOperatingRate, 3)}% / 年`
      : null,
  );
  document.querySelector("#profile-summary-cost").title =
    `管理费 ${basic.管理费率 ?? "—"} + 托管费 ${basic.托管费率 ?? "—"}`;
  text(
    "#fund-scale-date",
    scale.净资产截止日 ? `截至 ${scale.净资产截止日}` : null,
    "报告期暂无",
  );
  text("#fund-shares", scale.最新份额);
  text("#founded-scale", scale.成立份额);

  const institution = Number(holders.机构持有比例);
  const individual = Number(holders.个人持有比例);
  const hasHolderData =
    Number.isFinite(institution) && Number.isFinite(individual);
  text(
    "#holder-period",
    holders.报告期 ? `报告期 ${holders.报告期}` : null,
    "报告期暂无",
  );
  text(
    "#institution-share",
    hasHolderData ? `${formatNumber(institution, 2)}%` : null,
  );
  text(
    "#individual-share",
    hasHolderData ? `${formatNumber(individual, 2)}%` : null,
  );
  document.querySelector("#institution-bar").style.width = hasHolderData
    ? `${Math.max(institution, 0)}%`
    : "0";
  document.querySelector("#individual-bar").style.width = hasHolderData
    ? `${Math.max(individual, 0)}%`
    : "0";
  document.querySelector("#holder-bar").classList.toggle(
    "empty",
    !hasHolderData,
  );
  document
    .querySelector("#holder-bar")
    .setAttribute(
      "aria-label",
      hasHolderData
        ? `机构持有 ${institution.toFixed(2)}%，个人持有 ${individual.toFixed(2)}%`
        : "暂无基金持有人结构",
    );
  text(
    "#holder-note",
    hasHolderData
      ? `报告总份额 ${formatNumber(holders.总份额, 2)}${
          holders.总份额单位 ?? "亿份"
        } · 内部持有 ${formatNumber(holders.内部持有比例, 2)}% · ${
          holders.说明 ?? "内部持有为补充披露。"
        }`
      : holders.说明,
    "暂未取得该基金最新持有人结构。",
  );

  const feeList = document.querySelector("#purchase-fee-list");
  feeList.replaceChildren();
  text("#purchase-fee-method", purchaseFee.收费方式, "费率暂无");
  if (!feeRows.length) {
    const empty = document.createElement("p");
    empty.className = "purchase-fee-empty";
    empty.textContent = "该基金暂无可用的申购费率表。";
    feeList.append(empty);
    text("#purchase-fee-lead-label", "最低金额档买入费率");
    text("#purchase-fee-lead", null);
    text(
      "#purchase-fee-note",
      purchaseFee.说明,
      "部分不开放申购或无申购费的基金可能不提供分档费率。",
    );
    return;
  }

  const leadFee =
    feeRows[0].天天基金优惠费率 ?? feeRows[0].原费率 ?? "—";
  text(
    "#purchase-fee-lead-label",
    feeRows[0].天天基金优惠费率
      ? "最低金额档 · 天天基金优惠"
      : "最低金额档买入费率",
  );
  text("#purchase-fee-lead", leadFee);
  feeRows.forEach((row) => {
    const item = document.createElement("div");
    item.className = "purchase-fee-row";
    const condition = document.createElement("span");
    condition.textContent = row.适用条件 ?? "默认金额档";
    const rates = document.createElement("div");
    const original = document.createElement("strong");
    original.textContent = row.原费率 ?? "—";
    rates.append(original);
    if (row.天天基金优惠费率) {
      const discount = document.createElement("b");
      discount.textContent = `${row.天天基金优惠费率} 渠道优惠`;
      rates.append(discount);
    }
    item.append(condition, rates);
    feeList.append(item);
  });
  text("#purchase-fee-note", purchaseFee.说明);
}

function renderShareClassAdvice(advice) {
  const card = document.querySelector("#share-class-card");
  if (!advice || !advice.可用) {
    card.hidden = true;
    return;
  }
  card.hidden = false;

  const a = advice.A类 ?? {};
  const c = advice.C类 ?? {};
  text(
    "#share-class-current",
    advice.当前份额 ? `当前查看 ${advice.当前份额} 类` : "—",
  );

  const threshold = advice.临界持有天数;
  text("#share-class-threshold", threshold ? `${threshold} 天` : "长期持有");
  text("#share-class-summary", advice.建议);

  const aRate =
    a.申购费率 != null ? `申购费 ${a.申购费率}%` : "申购费未知";
  text("#share-class-a", `${a.名称 ?? "—"}（${a.代码 ?? "—"}） · ${aRate}`);
  const cRate =
    c.年销售服务费率 != null
      ? `销售服务费 ${c.年销售服务费率}%/年`
      : "销售服务费未知";
  text("#share-class-c", `${c.名称 ?? "—"}（${c.代码 ?? "—"}） · ${cRate}`);

  text("#share-class-note", advice.说明);
}

function renderFund(data) {
  const basic = data.基础资料 ?? {};
  const performance = data.历史业绩 ?? {};
  const source = data.数据来源 ?? {};

  document.querySelector(".compact-profile").open = false;
  document.querySelector(".holding-simulator").open = false;

  text("#fund-name", basic.名称);
  text("#fund-code-badge", basic.代码);
  text("#fund-type", basic.类型);
  text("#fund-date", basic.成立日 ? `成立于 ${basic.成立日}` : "成立日暂无");
  text(
    "#query-time",
    source.查询时间
      ? `查询于 ${new Date(source.查询时间).toLocaleString("zh-CN", {
          hour12: false,
        })}`
      : "查询时间未知",
  );

  text("#manager", basic.管理人);
  text("#custodian", basic.托管人);
  text("#management-fee", basic.管理费率);
  text("#custodian-fee", basic.托管费率);
  renderShareClassAdvice(basic.AC份额建议);
  text("#benchmark", basic.业绩比较基准);
  document.querySelector("#benchmark").title =
    basic.业绩比较基准 ?? "业绩比较基准暂无";
  text("#data-source", `净值及业绩：${source.净值及业绩 ?? "AKShare"}`);

  renderFundProfile(basic);
  renderPerformance(performance);
  renderNavHistory(data.净值曲线);
  initializeTrackBenchmark(data.赛道基准建议);
  renderHoldings(data.基金持仓);
  renderWarnings(data.提示);
}

async function queryFund(code, refresh = false) {
  if (!validateCode(code)) {
    showInputError("请输入完整的六位数字基金代码。");
    codeInput.focus();
    return;
  }

  clearInputError();
  currentCode = code;
  codeInput.value = code;
  setView("loading");

  try {
    const params = new URLSearchParams({ holdings_limit: "20" });
    if (refresh) params.set("refresh", "true");
    const response = await fetch(`/api/funds/${code}?${params}`);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || `查询失败（HTTP ${response.status}）`);
    }

    renderFund(payload);
    setView("results");
    history.replaceState(null, "", `/?code=${code}`);
    results.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    errorMessage.textContent = error.message || "未知错误，请稍后重试。";
    setView("error");
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  queryFund(codeInput.value.trim());
});

codeInput.addEventListener("input", () => {
  codeInput.value = codeInput.value.replace(/\D/g, "").slice(0, 6);
  if (codeInput.value.length === 6) clearInputError();
});

document.querySelectorAll("[data-code]").forEach((button) => {
  button.addEventListener("click", () => queryFund(button.dataset.code));
});

refreshButton.addEventListener("click", () => {
  if (currentCode) queryFund(currentCode, true);
});

document.querySelectorAll("[data-nav-range]").forEach((button) => {
  button.addEventListener("click", () => {
    showCustomRangeError();
    renderNavChart(button.dataset.navRange);
  });
});

document.querySelectorAll("[data-nav-metric]").forEach((button) => {
  button.addEventListener("click", () =>
    renderNavChart(currentNavRange, button.dataset.navMetric),
  );
});

document.querySelectorAll("[data-periodic-unit]").forEach((button) => {
  button.addEventListener("click", () =>
    renderPeriodicReturns(button.dataset.periodicUnit),
  );
});

document
  .querySelector("#track-benchmark-select")
  .addEventListener("change", (event) => {
    loadTrackBenchmark(event.target.value);
  });

document
  .querySelector("#nav-custom-range")
  .addEventListener("submit", (event) => {
    event.preventDefault();
    const start = document.querySelector("#custom-range-start").value;
    const end = document.querySelector("#custom-range-end").value;
    if (!start || !end) {
      showCustomRangeError("请选择完整的开始和结束日期。");
      return;
    }
    if (start > end) {
      showCustomRangeError("开始日期不能晚于结束日期。");
      return;
    }
    currentCustomRange = { start, end };
    renderNavChart("custom", currentNavMetric);
  });

document
  .querySelector("#holding-simulator-form")
  .addEventListener("submit", (event) => {
    event.preventDefault();
    calculateHoldingSimulation();
  });

document.querySelectorAll("[data-simulator-mode]").forEach((button) => {
  button.addEventListener("click", () =>
    selectInvestmentMode(button.dataset.simulatorMode),
  );
});

const navChart = document.querySelector("#nav-history-chart");
const navTooltip = document.querySelector("#nav-chart-tooltip");
navChart.addEventListener("pointermove", (event) => {
  if (!navPlotPoints.length) return;
  const bounds = navChart.getBoundingClientRect();
  const chartX = ((event.clientX - bounds.left) / bounds.width) * 1000;
  const nearest = navPlotPoints.reduce((best, point) =>
    Math.abs(point.x - chartX) < Math.abs(best.x - chartX) ? point : best,
  );
  const crosshair = document.querySelector("#nav-crosshair");
  const [line, circle, benchmarkCircle] = crosshair.children;
  line.setAttribute("x1", nearest.x);
  line.setAttribute("x2", nearest.x);
  circle.setAttribute("cx", nearest.x);
  circle.setAttribute("cy", nearest.y);
  const nearestBenchmark = benchmarkPlotPoints.length
    ? benchmarkPlotPoints.reduce((best, point) =>
        Math.abs(point.x - nearest.x) < Math.abs(best.x - nearest.x)
          ? point
          : best,
      )
    : null;
  if (benchmarkCircle) {
    benchmarkCircle.setAttribute(
      "visibility",
      nearestBenchmark ? "visible" : "hidden",
    );
    if (nearestBenchmark) {
      benchmarkCircle.setAttribute("cx", nearestBenchmark.x);
      benchmarkCircle.setAttribute("cy", nearestBenchmark.y);
    }
  }
  crosshair.setAttribute("visibility", "visible");

  navTooltip.querySelector("span").textContent = formatChartDate(nearest.日期);
  navTooltip.querySelector("strong").textContent =
    currentNavMetric === "回撤修复"
      ? `基金回撤 ${formatPercent(nearest.回撤)}${
          nearestBenchmark
            ? ` · ${currentTrackBenchmark?.简称 ?? "赛道"}回撤 ${formatPercent(
                nearestBenchmark.回撤,
              )}`
            : ""
        }`
      : currentNavMetric === "累计收益率" && nearestBenchmark
        ? `基金 ${formatPercent(nearest.value)} · ${
            currentTrackBenchmark?.简称 ?? "赛道"
          } ${formatPercent(nearestBenchmark.value)}`
      : `${navMetricConfig[currentNavMetric].tooltipLabel} ${formatNavValue(
          nearest.value,
          currentNavMetric,
        )}`;
  navTooltip.style.left = `${(nearest.x / 1000) * bounds.width}px`;
  navTooltip.style.top = `${(nearest.y / 360) * bounds.height}px`;
  navTooltip.classList.toggle("align-right", nearest.x > 820);
  navTooltip.hidden = false;
});

navChart.addEventListener("pointerleave", () => {
  navTooltip.hidden = true;
  document
    .querySelector("#nav-crosshair")
    ?.setAttribute("visibility", "hidden");
});

const initialCode = new URLSearchParams(location.search).get("code");
if (initialCode && validateCode(initialCode)) {
  codeInput.value = initialCode;
  queryFund(initialCode);
}
