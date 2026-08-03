const watchlistListEl = document.querySelector("#watchlist-list");
const watchlistEmptyEl = document.querySelector("#watchlist-empty");
const watchlistTagFiltersEl = document.querySelector("#watchlist-tag-filters");
const watchlistFeedbackEl = document.querySelector("#watchlist-feedback");
const watchlistTotalEl = document.querySelector("#watchlist-total");
const watchlistRefreshButton = document.querySelector("#watchlist-refresh");

let watchlistData = { 基金: [], 总数: 0, 标签建议: [] };
let watchlistActiveTag = "全部";

const WATCHLIST_TAG_TONES = new Map([
  ["全部", "all"],
  ["持有中", "holding"],
  ["债基", "bond"],
  ["固收+", "bond"],
  ["偏股", "equity"],
  ["股票", "equity"],
  ["指数", "index"],
  ["成长", "growth"],
  ["价值", "value"],
  ["红利", "dividend"],
  ["低波", "low-risk"],
  ["货币", "cash"],
  ["QDII", "global"],
  ["FOF", "global"],
]);

function watchlistTagTone(tag) {
  const value = String(tag || "");
  const knownTone = WATCHLIST_TAG_TONES.get(value);
  if (knownTone) return knownTone;
  let hash = 0;
  for (const character of value) hash = (hash * 31 + character.codePointAt(0)) >>> 0;
  return `custom-${hash % 4}`;
}

function applyWatchlistTagTone(element, tag) {
  element.dataset.tagTone = watchlistTagTone(tag);
}

function setWatchlistFeedback(message = "", isError = false) {
  watchlistFeedbackEl.textContent = message;
  watchlistFeedbackEl.classList.toggle("error", isError);
}

async function readApiPayload(response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || `请求失败（HTTP ${response.status}）`);
  }
  return payload;
}

function applyWatchlistPayload(payload) {
  watchlistData = {
    基金: Array.isArray(payload?.基金) ? payload.基金 : [],
    总数: Number(payload?.总数) || 0,
    标签建议: Array.isArray(payload?.标签建议) ? payload.标签建议 : [],
  };
  watchlistTotalEl.textContent = `${watchlistData.总数} FUNDS`;
  renderWatchlist();
}

async function loadWatchlist() {
  watchlistRefreshButton.disabled = true;
  setWatchlistFeedback("正在读取本地组合…");
  try {
    const payload = await readApiPayload(await fetch("/api/watchlist"));
    applyWatchlistPayload(payload);
    setWatchlistFeedback("已与本地文件同步");
  } catch (error) {
    setWatchlistFeedback(error.message || "收藏读取失败", true);
  } finally {
    watchlistRefreshButton.disabled = false;
  }
}

async function saveWatchlistItem(item, tags) {
  return readApiPayload(
    await fetch(`/api/watchlist/${item.code}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: item.name || "",
        fund_type: item.fund_type || "",
        tags,
      }),
    }),
  );
}

async function removeWatchlistItem(code) {
  return readApiPayload(
    await fetch(`/api/watchlist/${code}`, { method: "DELETE" }),
  );
}

function renderWatchlistTagFilters(items) {
  const counts = new Map();
  items.forEach((item) => {
    (item.tags || []).forEach((tag) => {
      counts.set(tag, (counts.get(tag) || 0) + 1);
    });
  });

  if (watchlistActiveTag !== "全部" && !counts.has(watchlistActiveTag)) {
    watchlistActiveTag = "全部";
  }

  watchlistTagFiltersEl.replaceChildren();
  [["全部", items.length], ...counts.entries()].forEach(([tag, count]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "watchlist-tag-filter";
    applyWatchlistTagTone(button, tag);
    button.classList.toggle("active", tag === watchlistActiveTag);
    button.setAttribute("aria-pressed", String(tag === watchlistActiveTag));

    const name = document.createElement("span");
    name.textContent = tag;
    const total = document.createElement("small");
    total.textContent = String(count).padStart(2, "0");
    button.append(name, total);
    button.addEventListener("click", () => {
      watchlistActiveTag = tag;
      renderWatchlist();
    });
    watchlistTagFiltersEl.append(button);
  });
}

function createWatchlistEditor(item, card) {
  const form = document.createElement("form");
  form.className = "watchlist-editor";
  form.hidden = true;
  let selectedTags = [...new Set((item.tags || []).filter(Boolean))].slice(0, 12);
  let customTagMode = false;

  const heading = document.createElement("div");
  heading.className = "watchlist-editor-heading";
  const headingText = document.createElement("strong");
  headingText.textContent = "管理标签";
  const headingNote = document.createElement("small");
  headingNote.textContent = "最多 12 个";
  heading.append(headingText, headingNote);

  const selected = document.createElement("div");
  selected.className = "watchlist-editor-tags";

  const suggestions = document.createElement("div");
  suggestions.className = "watchlist-tag-suggestions";

  const inputRow = document.createElement("div");
  inputRow.className = "watchlist-tag-input-row";
  inputRow.hidden = true;
  const tagField = document.createElement("label");
  tagField.textContent = "添加自定义标签";
  const tagInput = document.createElement("input");
  tagInput.type = "text";
  tagInput.maxLength = 24;
  tagInput.placeholder = "例如：核心观察";
  tagField.append(tagInput);
  const addButton = document.createElement("button");
  addButton.type = "button";
  addButton.textContent = "添加";
  inputRow.append(tagField, addButton);

  const actions = document.createElement("div");
  actions.className = "watchlist-editor-actions";
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.textContent = "取消";
  const save = document.createElement("button");
  save.type = "submit";
  save.textContent = "保存标签";
  actions.append(cancel, save);
  form.append(heading, selected, suggestions, inputRow, actions);

  const hasTag = (tag) =>
    selectedTags.some(
      (current) => current.toLocaleLowerCase() === tag.toLocaleLowerCase(),
    );

  function renderTagEditor() {
    selected.replaceChildren();
    if (!selectedTags.length) {
      const empty = document.createElement("span");
      empty.className = "watchlist-tags-empty";
      empty.textContent = "尚未添加标签，保存后会自动补充基金类型标签";
      selected.append(empty);
    } else {
      selectedTags.forEach((tag) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "watchlist-tag removable";
        applyWatchlistTagTone(chip, tag);
        chip.setAttribute("aria-label", `移除标签 ${tag}`);
        chip.textContent = `${tag} ×`;
        chip.addEventListener("click", () => {
          selectedTags = selectedTags.filter((current) => current !== tag);
          renderTagEditor();
        });
        selected.append(chip);
      });
    }

    suggestions.replaceChildren();
    const label = document.createElement("span");
    label.textContent = "从已有标签选择";
    suggestions.append(label);
    (watchlistData.标签建议 || []).forEach((tag) => {
      const choice = document.createElement("button");
      choice.type = "button";
      choice.className = "watchlist-tag-choice";
      applyWatchlistTagTone(choice, tag);
      choice.textContent = tag;
      choice.disabled = hasTag(tag) || selectedTags.length >= 12;
      choice.addEventListener("click", () => {
        if (selectedTags.length < 12 && !hasTag(tag)) selectedTags.push(tag);
        renderTagEditor();
      });
      suggestions.append(choice);
    });

    const custom = document.createElement("button");
    custom.type = "button";
    custom.className = "watchlist-tag-choice custom";
    custom.textContent = customTagMode ? "收起自定义" : "+ 自定义";
    custom.disabled = selectedTags.length >= 12;
    custom.setAttribute("aria-expanded", String(customTagMode));
    custom.addEventListener("click", () => {
      customTagMode = !customTagMode;
      renderTagEditor();
      if (customTagMode) tagInput.focus();
    });
    suggestions.append(custom);
    inputRow.hidden = !customTagMode || selectedTags.length >= 12;
  }

  function addCustomTag() {
    const tag = tagInput.value.trim().replace(/\s+/g, " ");
    if (!tag || selectedTags.length >= 12 || hasTag(tag)) return;
    selectedTags.push(tag);
    tagInput.value = "";
    customTagMode = false;
    renderTagEditor();
  }

  addButton.addEventListener("click", addCustomTag);
  tagInput.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    addCustomTag();
  });
  renderTagEditor();

  cancel.addEventListener("click", () => {
    form.hidden = true;
    card.classList.remove("editing");
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    save.disabled = true;
    save.textContent = "保存中…";
    try {
      applyWatchlistPayload(await saveWatchlistItem(item, selectedTags));
      setWatchlistFeedback("标签已写入本地文件");
    } catch (error) {
      setWatchlistFeedback(error.message || "保存失败", true);
      save.disabled = false;
      save.textContent = "保存标签";
    }
  });

  return { form, tagInput };
}

function createWatchlistCard(item, index) {
  const card = document.createElement("article");
  card.className = "watchlist-card";

  const main = document.createElement("a");
  main.className = "watchlist-card-main";
  main.href = `/?code=${encodeURIComponent(item.code)}`;
  main.title = `打开 ${item.name || item.code}`;

  const order = document.createElement("span");
  order.className = "watchlist-order";
  order.textContent = String(index + 1).padStart(2, "0");

  const identity = document.createElement("span");
  identity.className = "watchlist-identity";
  const displayName = document.createElement("strong");
  displayName.textContent = item.name || "未命名基金";
  const metadata = document.createElement("small");
  metadata.textContent = `${item.code} · ${item.fund_type || "类型未知"}`;
  identity.append(displayName, metadata);

  const tags = document.createElement("span");
  tags.className = "watchlist-tags";
  (item.tags || []).forEach((tag) => {
    const chip = document.createElement("span");
    chip.className = "watchlist-tag";
    applyWatchlistTagTone(chip, tag);
    chip.textContent = tag;
    tags.append(chip);
  });
  main.append(order, identity, tags);

  const controls = document.createElement("div");
  controls.className = "watchlist-card-controls";
  const edit = document.createElement("button");
  edit.type = "button";
  edit.textContent = "标签";
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "danger";
  remove.textContent = "移除";
  controls.append(edit, remove);

  const { form: editor, tagInput } = createWatchlistEditor(item, card);
  edit.addEventListener("click", () => {
    const opening = editor.hidden;
    document.querySelectorAll(".watchlist-editor").forEach((form) => {
      form.hidden = true;
      form.closest(".watchlist-card")?.classList.remove("editing");
    });
    editor.hidden = !opening;
    card.classList.toggle("editing", opening);
    if (opening) tagInput.focus();
  });

  remove.addEventListener("click", async () => {
    remove.disabled = true;
    remove.textContent = "移除中…";
    try {
      applyWatchlistPayload(await removeWatchlistItem(item.code));
      setWatchlistFeedback(`已移除 ${item.name || item.code}`);
    } catch (error) {
      setWatchlistFeedback(error.message || "移除失败", true);
      remove.disabled = false;
      remove.textContent = "移除";
    }
  });

  card.append(main, controls, editor);
  return card;
}

function renderWatchlist() {
  const items = watchlistData.基金 || [];
  renderWatchlistTagFilters(items);
  const visibleItems =
    watchlistActiveTag === "全部"
      ? items
      : items.filter((item) => (item.tags || []).includes(watchlistActiveTag));

  watchlistListEl.replaceChildren();
  visibleItems.forEach((item, index) => {
    watchlistListEl.append(createWatchlistCard(item, index));
  });
  watchlistEmptyEl.hidden = items.length > 0;
  watchlistListEl.hidden = items.length === 0;
}

watchlistRefreshButton.addEventListener("click", loadWatchlist);
loadWatchlist();
