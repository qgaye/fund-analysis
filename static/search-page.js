const searchForm = document.querySelector("#search-page-form");
const searchInput = document.querySelector("#search-page-input");
const searchFeedback = document.querySelector("#search-page-feedback");
const searchResultsSection = document.querySelector("#search-page-results");
const searchResultList = document.querySelector("#search-page-result-list");
const searchResultCount = document.querySelector("#search-page-count");
const searchHistorySection = document.querySelector("#search-page-history");
const searchHistoryList = document.querySelector("#search-page-history-list");
const searchHistoryCount = document.querySelector("#search-page-history-count");
const searchHistoryClear = document.querySelector("#search-page-history-clear");

const SEARCH_HISTORY_COOKIE = "fund_search_history";
const SEARCH_HISTORY_MAX = 12;

let searchResults = [];
let activeResultIndex = -1;
let searchTimer = null;
let searchRequestId = 0;

function isFundCode(value) {
  return /^\d{6}$/.test(String(value || "").trim());
}

function setFeedback(message = "", isError = false) {
  searchFeedback.textContent = message;
  searchFeedback.classList.toggle("error", isError);
}

function openFund(code) {
  if (!isFundCode(code)) return;
  window.location.assign(`/?code=${encodeURIComponent(code)}`);
}

function readSearchHistory() {
  const match = document.cookie
    .split("; ")
    .find((item) => item.startsWith(`${SEARCH_HISTORY_COOKIE}=`));
  if (!match) return [];
  try {
    const parsed = JSON.parse(
      decodeURIComponent(match.split("=").slice(1).join("=")),
    );
    return Array.isArray(parsed)
      ? parsed
          .filter((item) => item && isFundCode(item.code))
          .slice(0, SEARCH_HISTORY_MAX)
      : [];
  } catch (error) {
    return [];
  }
}

function renderSearchHistory() {
  const items = readSearchHistory();
  searchHistoryList.replaceChildren();
  searchHistorySection.hidden = items.length === 0;
  searchHistoryCount.textContent = `${items.length} RECORDS`;
  items.forEach((item, index) => {
    const link = document.createElement("a");
    link.className = "search-page-history-item";
    link.href = `/?code=${encodeURIComponent(item.code)}`;
    link.title = item.name ? `${item.name}（${item.code}）` : item.code;

    const order = document.createElement("span");
    order.textContent = String(index + 1).padStart(2, "0");
    const identity = document.createElement("span");
    const name = document.createElement("strong");
    name.textContent = item.name || "未命名基金";
    const code = document.createElement("small");
    code.textContent = item.code;
    identity.append(name, code);
    const arrow = document.createElement("b");
    arrow.setAttribute("aria-hidden", "true");
    arrow.textContent = "↗";
    link.append(order, identity, arrow);
    searchHistoryList.append(link);
  });
}

function hideResults() {
  searchResults = [];
  activeResultIndex = -1;
  searchResultsSection.hidden = true;
  searchInput.setAttribute("aria-expanded", "false");
  searchInput.removeAttribute("aria-activedescendant");
}

function setActiveResult(index) {
  const options = [...searchResultList.querySelectorAll("[role='option']")];
  if (!options.length) return;
  activeResultIndex = (index + options.length) % options.length;
  options.forEach((option, optionIndex) => {
    const active = optionIndex === activeResultIndex;
    option.classList.toggle("active", active);
    option.setAttribute("aria-selected", String(active));
  });
  const activeOption = options[activeResultIndex];
  searchInput.setAttribute("aria-activedescendant", activeOption.id);
  activeOption.scrollIntoView({ block: "nearest" });
}

function renderResults(items, total) {
  searchResults = items;
  activeResultIndex = -1;
  searchResultList.replaceChildren();
  searchResultCount.textContent = total > items.length
    ? `显示 ${items.length} / ${total}`
    : `${total} 条匹配`;

  if (!items.length) {
    const empty = document.createElement("p");
    empty.className = "fund-search-no-result";
    empty.textContent = "没有找到匹配基金";
    searchResultList.append(empty);
  } else {
    items.forEach((item, index) => {
      const option = document.createElement("a");
      option.id = `search-page-option-${index}`;
      option.className = "fund-search-suggestion";
      option.href = `/?code=${encodeURIComponent(item.代码)}`;
      option.setAttribute("role", "option");
      option.setAttribute("aria-selected", "false");

      const order = document.createElement("span");
      order.textContent = String(index + 1).padStart(2, "0");
      const identity = document.createElement("span");
      const name = document.createElement("strong");
      name.textContent = item.名称 || "未命名基金";
      const meta = document.createElement("small");
      meta.textContent = `${item.代码} · ${item.类型 || "类型未知"}`;
      identity.append(name, meta);
      const arrow = document.createElement("i");
      arrow.textContent = "↗";
      option.append(order, identity, arrow);
      option.addEventListener("mouseenter", () => setActiveResult(index));
      searchResultList.append(option);
    });
  }

  searchResultsSection.hidden = false;
  searchInput.setAttribute("aria-expanded", "true");
}

async function performSearch(query) {
  const normalized = query.trim();
  if (normalized.length < 2) {
    hideResults();
    setFeedback("");
    return [];
  }

  const requestId = ++searchRequestId;
  setFeedback("正在搜索…");
  try {
    const params = new URLSearchParams({ q: normalized, limit: "20" });
    const response = await fetch(`/api/funds/search?${params}`);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || `查询失败（HTTP ${response.status}）`);
    }
    if (requestId !== searchRequestId) return [];
    const items = Array.isArray(payload.基金) ? payload.基金 : [];
    const total = Number(payload.匹配总数) || items.length;
    renderResults(items, total);
    setFeedback(items.length ? "" : "换一个名称片段或输入六位基金代码");
    return items;
  } catch (error) {
    if (requestId !== searchRequestId) return [];
    hideResults();
    setFeedback(error.message || "本地基金目录搜索失败", true);
    return [];
  }
}

searchInput.addEventListener("input", () => {
  clearTimeout(searchTimer);
  const query = searchInput.value.trim();
  if (query.length < 2) {
    searchRequestId += 1;
    hideResults();
    setFeedback("");
    return;
  }
  searchTimer = window.setTimeout(() => performSearch(query), 180);
});

searchInput.addEventListener("keydown", (event) => {
  if (event.key === "ArrowDown") {
    event.preventDefault();
    setActiveResult(activeResultIndex + 1);
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    setActiveResult(activeResultIndex - 1);
  } else if (event.key === "Enter" && activeResultIndex >= 0) {
    event.preventDefault();
    openFund(searchResults[activeResultIndex]?.代码);
  } else if (event.key === "Escape") {
    hideResults();
  }
});

searchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearTimeout(searchTimer);
  const query = searchInput.value.trim();
  if (isFundCode(query)) {
    openFund(query);
    return;
  }
  if (query.length < 2) {
    setFeedback("请输入基金代码、名称或拼音", true);
    searchInput.focus();
    return;
  }
  const items = await performSearch(query);
  if (items.length) openFund(items[0].代码);
});

searchHistoryClear.addEventListener("click", () => {
  document.cookie = `${SEARCH_HISTORY_COOKIE}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/; SameSite=Lax`;
  renderSearchHistory();
});

const initialQuery = new URLSearchParams(window.location.search).get("q")?.trim() || "";
if (initialQuery) {
  searchInput.value = initialQuery;
  performSearch(initialQuery);
}
renderSearchHistory();
window.addEventListener("pageshow", renderSearchHistory);
requestAnimationFrame(() => searchInput.focus());
