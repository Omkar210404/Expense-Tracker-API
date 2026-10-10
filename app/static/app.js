/* Expense Tracker web app.
 *
 * Plain JavaScript, no framework and no build step. It talks to the same JSON
 * API that is documented at /docs.
 *
 * Text that came from a user (notes, category names, emails) is only ever put
 * on the page as text, through textContent or text nodes, and never parsed as
 * HTML. That is what stops a note such as "<script>" from running.
 */
"use strict";

const TOKEN_KEY = "expense-tracker-token";
const PAGE_SIZE = 15;
const PAYMENT_METHODS = {
  cash: "Cash",
  card: "Card",
  upi: "UPI",
  bank_transfer: "Bank transfer",
  wallet: "Wallet",
  other: "Other",
};

const state = {
  token: sessionStorage.getItem(TOKEN_KEY),
  user: null,
  categories: [],
  tab: "overview",
  month: currentMonth(),
  page: 1,
  editing: null, // the expense being edited, or null when adding
  authMode: "login",
};

// ---------- small helpers ----------------------------------------------------

const $ = (id) => document.getElementById(id);

/** Create an element. Children that are strings become text nodes. */
function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key === "tip") node.dataset.tip = value;
    else if (key === "onclick") node.addEventListener("click", value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children) {
    if (child === undefined || child === null || child === false) continue;
    node.append(child);
  }
  return node;
}

function money(value) {
  return Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function compactMoney(value) {
  const number = Number(value);
  if (Math.abs(number) < 1000) return number.toLocaleString(undefined, { maximumFractionDigits: 0 });
  return new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(number);
}

function pad(number) {
  return String(number).padStart(2, "0");
}

function localToday() {
  const now = new Date();
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

function currentMonth() {
  return localToday().slice(0, 7);
}

function addMonths(month, count) {
  const [year, monthNumber] = month.split("-").map(Number);
  const index = year * 12 + (monthNumber - 1) + count;
  return `${Math.floor(index / 12)}-${pad((index % 12) + 1)}`;
}

/** First and last day of a month, as ISO dates. */
function monthRange(month) {
  const [year, monthNumber] = month.split("-").map(Number);
  const lastDay = new Date(year, monthNumber, 0).getDate();
  return [`${month}-01`, `${month}-${pad(lastDay)}`];
}

function monthName(month, style = "long") {
  const [year, monthNumber] = month.split("-").map(Number);
  const options = style === "long" ? { month: "long", year: "numeric" } : { month: style };
  return new Date(year, monthNumber - 1, 1).toLocaleDateString(undefined, options);
}

function prettyDate(isoDate) {
  const [year, monthNumber, day] = isoDate.split("-").map(Number);
  return new Date(year, monthNumber - 1, day).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function plural(count, word) {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

let toastTimer;
function toast(message, isError = false) {
  const node = $("toast");
  node.textContent = message;
  node.classList.toggle("error", isError);
  node.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { node.hidden = true; }, isError ? 5000 : 2500);
}

function showError(node, message) {
  node.textContent = message;
  node.hidden = !message;
}

// ---------- talking to the API -------------------------------------------------

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

/** Turn the API's error body into one readable message. */
function errorMessage(body, status) {
  const error = body && body.error;
  if (!error) return `Something went wrong (HTTP ${status}).`;
  if (error.details && error.details.length) {
    return error.details
      .map((detail) => {
        const field = detail.field.replace(/^(body|query|path)\.?/, "").replace(/_/g, " ");
        return field ? `${field}: ${detail.message}` : detail.message;
      })
      .join("\n");
  }
  return error.message;
}

async function api(path, { method = "GET", json, form, raw = false } = {}) {
  const headers = {};
  let body;
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  } else if (form !== undefined) {
    body = new URLSearchParams(form);
  }

  let response;
  try {
    response = await fetch(path, { method, headers, body });
  } catch {
    throw new ApiError("Could not reach the server.", 0);
  }

  if (response.status === 401 && state.token && !path.startsWith("/auth/login")) {
    logout();
    toast("Your session has ended. Please log in again.", true);
    throw new ApiError("Session ended", 401);
  }
  if (response.status === 204) return null;
  if (raw && response.ok) return response;

  const data = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(errorMessage(data, response.status), response.status);
  return data;
}

function query(params) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, value);
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

/** Run an action started by the user and show a toast if it fails. */
async function attempt(action) {
  try {
    await action();
  } catch (error) {
    if (error.status !== 401) toast(error.message, true);
  }
}

// ---------- logging in and out -------------------------------------------------

function setAuthMode(mode) {
  state.authMode = mode;
  const registering = mode === "register";
  $("auth-tab-login").setAttribute("aria-selected", String(!registering));
  $("auth-tab-register").setAttribute("aria-selected", String(registering));
  $("auth-submit").textContent = registering ? "Create account" : "Log in";
  $("auth-password").autocomplete = registering ? "new-password" : "current-password";
  $("auth-hint").hidden = !registering;
  showError($("auth-error"), "");
}

async function submitAuth(event) {
  event.preventDefault();
  const email = $("auth-email").value.trim();
  const password = $("auth-password").value;
  if (!email || !password) {
    showError($("auth-error"), "Enter your email and password.");
    return;
  }
  $("auth-submit").disabled = true;
  try {
    if (state.authMode === "register") {
      await api("/auth/register", { method: "POST", json: { email, password } });
    }
    const token = await api("/auth/login", { method: "POST", form: { username: email, password } });
    state.token = token.access_token;
    // sessionStorage: the token is forgotten when the tab is closed.
    sessionStorage.setItem(TOKEN_KEY, state.token);
    $("auth-password").value = "";
    await start();
  } catch (error) {
    showError($("auth-error"), error.message);
  } finally {
    $("auth-submit").disabled = false;
  }
}

function logout() {
  state.token = null;
  state.user = null;
  state.categories = [];
  sessionStorage.removeItem(TOKEN_KEY);
  if ($("expense-dialog").open) $("expense-dialog").close();
  $("app-view").hidden = true;
  $("auth-view").hidden = false;
  setAuthMode("login");
}

async function start() {
  if (!state.token) {
    $("auth-view").hidden = false;
    return;
  }
  try {
    [state.user, state.categories] = await Promise.all([api("/auth/me"), api("/categories")]);
  } catch (error) {
    if (error.status !== 401) {
      $("auth-view").hidden = false;
      showError($("auth-error"), error.message);
    }
    return;
  }
  $("user-email").textContent = state.user.email;
  $("auth-view").hidden = true;
  $("app-view").hidden = false;
  fillFilterSelects();
  showTab("overview");
}

// ---------- tabs and the month picker ---------------------------------------------

const TAB_TITLES = { expenses: "All expenses", categories: "Categories" };

function showTab(tab) {
  state.tab = tab;
  for (const button of document.querySelectorAll(".tabs button")) {
    button.classList.toggle("active", button.dataset.tab === tab);
  }
  for (const section of document.querySelectorAll(".tab")) {
    section.hidden = section.id !== `tab-${tab}`;
  }
  // The month applies to the overview and the budgets only.
  const usesMonth = tab === "overview" || tab === "budgets";
  $("month-nav").hidden = !usesMonth;
  $("section-title").hidden = usesMonth;
  $("section-title").textContent = TAB_TITLES[tab] || "";
  refresh();
}

function setMonth(month) {
  state.month = month;
  refresh();
}

function refresh() {
  $("month-label").textContent = monthName(state.month);
  $("month-today").hidden = state.month === currentMonth();
  const loaders = { overview: loadOverview, expenses: loadExpenses, budgets: loadBudgets, categories: loadCategories };
  return attempt(loaders[state.tab]);
}

// ---------- overview -----------------------------------------------------------

async function loadOverview() {
  const month = state.month;
  const previous = addMonths(month, -1);
  const [first, last] = monthRange(month);

  const [status, byCategory, twoMonths, trends, recent] = await Promise.all([
    api(`/budgets/status${query({ month })}`),
    api(`/summary/categories${query({ date_from: first, date_to: last })}`),
    api(`/summary/monthly${query({ from: previous, to: month })}`),
    api("/summary/trends?months=6"),
    api(`/expenses${query({ date_from: first, date_to: last, page_size: 5 })}`),
  ]);
  if (month !== state.month || state.tab !== "overview") return; // the user moved on

  renderTiles(month, previous, status, byCategory, twoMonths);
  renderBudgetMeters($("overview-budgets"), status);
  renderCategoryBars(byCategory);
  renderTrend(trends);
  renderRecent(recent.items);
}

function renderTiles(month, previous, status, byCategory, twoMonths) {
  // Spent
  $("tile-spent-label").textContent = `Spent in ${monthName(month)}`;
  $("tile-spent").textContent = money(status.total_spent);
  const categoryCount = byCategory.categories.length;
  $("tile-spent-sub").textContent = byCategory.count
    ? `${plural(byCategory.count, "expense")} in ${categoryCount} ${categoryCount === 1 ? "category" : "categories"}`
    : "No expenses yet";

  // Budget left
  const leftSub = $("tile-left-sub");
  leftSub.replaceChildren();
  if (!status.items.length) {
    $("tile-left-label").textContent = "Budget left";
    $("tile-left").textContent = "–";
    leftSub.textContent = "No budgets set for this month";
  } else {
    const remaining = Number(status.totals.remaining);
    const used = status.totals.percent_used;
    $("tile-left-label").textContent = remaining < 0 ? "Over budget by" : "Budget left";
    $("tile-left").textContent = money(Math.abs(remaining));
    const level = remaining < 0 ? "critical" : used >= 80 ? "warning" : "good";
    const label = remaining < 0 ? "Over budget" : used >= 80 ? "Nearly used up" : "On track";
    leftSub.append(
      el("span", { class: `status ${level}`, text: label }),
      ` · ${used}% of ${money(status.totals.budget)} used`,
    );
  }

  // Compared with the month before
  const totals = Object.fromEntries(twoMonths.months.map((row) => [row.month, Number(row.total)]));
  const now = totals[month] || 0;
  const before = totals[previous] || 0;
  const change = now - before;
  const previousName = monthName(previous, "long").split(" ")[0];
  $("tile-delta-label").textContent = `Compared with ${previousName}`;
  if (change === 0) {
    $("tile-delta").textContent = "No change";
  } else {
    $("tile-delta").textContent = `${change > 0 ? "▲" : "▼"} ${money(Math.abs(change))}`;
  }
  if (before === 0) {
    $("tile-delta-sub").textContent = `Nothing was spent in ${previousName}`;
  } else if (change === 0) {
    $("tile-delta-sub").textContent = `The same as ${previousName}`;
  } else {
    const percent = Math.abs((change / before) * 100).toFixed(1);
    $("tile-delta-sub").textContent = `${percent}% ${change > 0 ? "more" : "less"} than ${previousName} (${money(before)})`;
  }
}

/** One budget as a meter. The fill colour and the label both carry the state. */
function meterRow(item) {
  const percent = item.percent_used;
  const remaining = Number(item.remaining);
  const level = item.over_budget ? "critical" : percent >= 80 ? "warning" : "";
  const label = item.over_budget ? `Over by ${money(Math.abs(remaining))}` : `${money(remaining)} left`;

  const fill = el("span");
  fill.style.width = `${Math.min(percent, 100)}%`;
  return el(
    "div",
    { class: "meter-row", tip: `${item.category_name}\n${money(item.spent)} of ${money(item.budget)} (${percent}%)` },
    el(
      "div",
      { class: "meter-top" },
      el("span", { class: "meter-name", text: item.category_name }),
      el("span", { class: "meter-figures", text: `${money(item.spent)} of ${money(item.budget)}` }),
    ),
    el("div", { class: `meter ${level}`, role: "img", "aria-label": `${percent}% of the budget used` }, fill),
    el("span", { class: `status ${level || "good"}`, text: label }),
  );
}

function renderBudgetMeters(container, status) {
  container.replaceChildren();
  if (!status.items.length) {
    container.append(el("div", { class: "empty", text: "No budgets for this month yet." }));
  }
  for (const item of status.items) container.append(meterRow(item));
  if (Number(status.unbudgeted_spent) > 0) {
    container.append(
      el("p", {
        class: "muted",
        text: `${money(status.unbudgeted_spent)} was spent in categories without a budget.`,
      }),
    );
  }
}

function renderCategoryBars(summary) {
  const container = $("overview-categories");
  container.replaceChildren();
  if (!summary.categories.length) {
    container.append(el("div", { class: "empty", text: "Nothing spent this month." }));
    return;
  }
  const largest = Number(summary.categories[0].total);
  const bars = el("div", { class: "bars" });
  for (const row of summary.categories) {
    const fill = el("div", { class: "bar-fill" });
    fill.style.width = `${(Number(row.total) / largest) * 100}%`;
    bars.append(
      el(
        "div",
        {
          class: "bar-row",
          tip: `${row.category_name}\n${money(row.total)} · ${row.share}% of the month\n${plural(row.count, "expense")}`,
        },
        el("span", { class: "bar-label", text: row.category_name }),
        el("div", { class: "bar-track" }, fill),
        el("span", { class: "bar-value", text: money(row.total) }),
      ),
    );
  }
  container.append(bars);
}

function renderTrend(trends) {
  const container = $("overview-trend");
  container.replaceChildren();
  const largest = Math.max(...trends.months.map((row) => Number(row.total)));
  const columns = el("div", { class: "columns" });
  const labels = el("div", { class: "column-labels" });
  const tallest = 150; // pixels; leaves room for the value above the column

  trends.months.forEach((row, index) => {
    const isCurrent = index === trends.months.length - 1;
    const total = Number(row.total);
    const change = Number(row.change);
    const fill = el("div", { class: "column-fill" });
    fill.style.height = `${largest ? Math.round((total / largest) * tallest) : 0}px`;
    const changeText = change === 0 ? "No change" : `${change > 0 ? "+" : "−"}${money(Math.abs(change))}`;
    columns.append(
      el(
        "div",
        {
          class: `column${isCurrent ? " current" : ""}`,
          tip: `${monthName(row.month)}\n${money(total)} · ${plural(row.count, "expense")}\n${changeText} on the month before`,
        },
        el("span", { class: "column-value", text: compactMoney(total) }),
        fill,
      ),
    );
    labels.append(el("span", { class: isCurrent ? "current" : "", text: monthName(row.month, "short") }));
  });

  container.append(columns, labels);
  container.append(
    el("p", { class: "muted", text: `Average ${money(trends.average_monthly_total)} a month over these six months.` }),
  );
}

function expenseListRow(expense) {
  return el(
    "div",
    { class: "list-row" },
    el(
      "div",
      { class: "list-main" },
      el("div", { class: "list-title", text: expense.note || expense.category_name }),
      el("div", {
        class: "list-sub",
        text: `${prettyDate(expense.date)} · ${expense.category_name} · ${PAYMENT_METHODS[expense.payment_method]}`,
      }),
    ),
    el("div", { class: "list-amount", text: money(expense.amount) }),
  );
}

function renderRecent(items) {
  const container = $("overview-recent");
  container.replaceChildren();
  if (!items.length) {
    container.append(el("div", { class: "empty", text: "No expenses this month. Use “Add expense” to record one." }));
    return;
  }
  for (const expense of items) container.append(expenseListRow(expense));
}

// ---------- expenses -------------------------------------------------------------

function fillSelect(select, options, selected) {
  select.replaceChildren();
  for (const [value, label] of options) {
    select.append(el("option", { value, text: label, selected: String(value) === String(selected) }));
  }
}

function categoryOptions() {
  return state.categories.map((category) => [category.id, category.name]);
}

function fillFilterSelects() {
  fillSelect($("f-category"), [["", "All categories"], ...categoryOptions()], $("f-category").value);
  fillSelect($("f-method"), [["", "Any"], ...Object.entries(PAYMENT_METHODS)], $("f-method").value);
}

function currentFilters() {
  return {
    q: $("f-q").value.trim(),
    category_id: $("f-category").value,
    payment_method: $("f-method").value,
    date_from: $("f-from").value,
    date_to: $("f-to").value,
  };
}

async function loadExpenses() {
  const data = await api(`/expenses${query({ ...currentFilters(), page: state.page, page_size: PAGE_SIZE })}`);
  if (state.page > 1 && !data.items.length && data.total) {
    // The last row of the last page was deleted: step back.
    state.page = data.pages;
    return loadExpenses();
  }

  const rows = $("expense-rows");
  rows.replaceChildren();
  for (const expense of data.items) {
    rows.append(
      el(
        "tr",
        {},
        el("td", { text: prettyDate(expense.date) }),
        el("td", { class: "note", text: expense.note || "–", tip: expense.note }),
        el("td", { text: expense.category_name }),
        el("td", { text: PAYMENT_METHODS[expense.payment_method] }),
        el("td", { class: "num", text: money(expense.amount) }),
        el(
          "td",
          { class: "actions" },
          el("button", { type: "button", class: "ghost small", text: "Edit", onclick: () => openExpenseDialog(expense) }),
          " ",
          el("button", {
            type: "button",
            class: "ghost small danger",
            text: "Delete",
            onclick: () => deleteExpense(expense),
          }),
        ),
      ),
    );
  }

  $("expense-table").hidden = !data.items.length;
  $("expense-empty").hidden = Boolean(data.items.length);
  const firstShown = data.total ? (data.page - 1) * PAGE_SIZE + 1 : 0;
  const lastShown = firstShown ? firstShown + data.items.length - 1 : 0;
  $("pager-info").textContent = data.total ? `${firstShown}–${lastShown} of ${data.total}` : "";
  $("pager-prev").disabled = data.page <= 1;
  $("pager-next").disabled = data.page >= data.pages;
}

function deleteExpense(expense) {
  const what = `${money(expense.amount)} · ${expense.note || expense.category_name} · ${prettyDate(expense.date)}`;
  if (!window.confirm(`Delete this expense?\n\n${what}`)) return;
  attempt(async () => {
    await api(`/expenses/${expense.id}`, { method: "DELETE" });
    toast("Expense deleted");
    await refresh();
  });
}

async function downloadCsv() {
  const response = await api(`/expenses/export${query(currentFilters())}`, { raw: true });
  const url = URL.createObjectURL(await response.blob());
  const link = el("a", { href: url, download: "expenses.csv" });
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function openExpenseDialog(expense = null) {
  if (!state.categories.length) {
    toast("Add a category first.", true);
    return;
  }
  state.editing = expense;
  $("expense-dialog-title").textContent = expense ? "Edit expense" : "Add expense";
  $("e-amount").value = expense ? expense.amount : "";
  fillSelect($("e-category"), categoryOptions(), expense ? expense.category_id : state.categories[0].id);
  fillSelect($("e-method"), Object.entries(PAYMENT_METHODS), expense ? expense.payment_method : "upi");
  $("e-date").value = expense ? expense.date : localToday();
  $("e-note").value = expense ? expense.note || "" : "";
  showError($("expense-error"), "");
  $("expense-dialog").showModal();
  $("e-amount").focus();
}

async function saveExpense(event) {
  event.preventDefault();
  const amount = $("e-amount").value.trim().replace(/,/g, "");
  if (!amount) {
    showError($("expense-error"), "Enter an amount.");
    return;
  }
  const body = {
    amount,
    category_id: Number($("e-category").value),
    date: $("e-date").value,
    note: $("e-note").value.trim() || null,
    payment_method: $("e-method").value,
  };
  $("expense-save").disabled = true;
  try {
    if (state.editing) {
      await api(`/expenses/${state.editing.id}`, { method: "PATCH", json: body });
    } else {
      await api("/expenses", { method: "POST", json: body });
    }
    $("expense-dialog").close();
    toast(state.editing ? "Expense updated" : "Expense added");
    await refresh();
  } catch (error) {
    showError($("expense-error"), error.message);
  } finally {
    $("expense-save").disabled = false;
  }
}

// ---------- budgets --------------------------------------------------------------

async function loadBudgets() {
  const month = state.month;
  const status = await api(`/budgets/status${query({ month })}`);
  if (month !== state.month || state.tab !== "budgets") return;

  $("budgets-title").textContent = `Budgets for ${monthName(month)}`;
  $("budgets-total").textContent = status.items.length
    ? `${money(status.totals.spent)} of ${money(status.totals.budget)} used`
    : "";

  const budgeted = Object.fromEntries(status.items.map((item) => [item.category_id, item]));
  const unbudgeted = Object.fromEntries(status.unbudgeted.map((item) => [item.category_id, item.spent]));
  const container = $("budget-rows");
  container.replaceChildren();

  for (const category of state.categories) {
    const item = budgeted[category.id];
    const input = el("input", {
      type: "text",
      inputmode: "decimal",
      placeholder: "No budget",
      value: item ? item.budget : "",
      "aria-label": `Budget for ${category.name}`,
    });
    const info = item
      ? meterRow(item)
      : el(
          "div",
          { class: "budget-info" },
          el("span", { class: "meter-name", text: category.name }),
          el("span", {
            class: "muted",
            text: unbudgeted[category.id] ? `${money(unbudgeted[category.id])} spent, no budget` : "No budget",
          }),
        );
    const save = el("button", {
      type: "button",
      text: "Save",
      onclick: () => attempt(() => saveBudget(category, item, input.value)),
    });
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") save.click();
    });
    container.append(el("div", { class: "budget-row" }, info, input, save));
  }
  if (!state.categories.length) {
    container.append(el("div", { class: "empty", text: "Add a category first." }));
  }
}

async function saveBudget(category, existing, text) {
  const amount = text.trim().replace(/,/g, "");
  if (!amount && !existing) return;
  if (!amount) {
    await api(`/budgets/${existing.budget_id}`, { method: "DELETE" });
    toast(`Budget for ${category.name} removed`);
  } else if (existing) {
    await api(`/budgets/${existing.budget_id}`, { method: "PATCH", json: { amount } });
    toast(`Budget for ${category.name} updated`);
  } else {
    await api("/budgets", { method: "POST", json: { category_id: category.id, month: state.month, amount } });
    toast(`Budget for ${category.name} set`);
  }
  await loadBudgets();
}

// ---------- categories -----------------------------------------------------------

async function loadCategories() {
  state.categories = await api("/categories");
  fillFilterSelects();
  const container = $("category-rows");
  container.replaceChildren();
  for (const category of state.categories) {
    container.append(
      el(
        "div",
        { class: "list-row" },
        el("div", { class: "list-main" }, el("div", { class: "list-title", text: category.name })),
        el("button", { type: "button", class: "ghost small", text: "Rename", onclick: () => renameCategory(category) }),
        el("button", {
          type: "button",
          class: "ghost small danger",
          text: "Delete",
          onclick: () => deleteCategory(category),
        }),
      ),
    );
  }
  if (!state.categories.length) {
    container.append(el("div", { class: "empty", text: "No categories yet." }));
  }
}

async function addCategory(event) {
  event.preventDefault();
  const name = $("category-name").value.trim();
  if (!name) return;
  await attempt(async () => {
    await api("/categories", { method: "POST", json: { name } });
    $("category-name").value = "";
    toast("Category added");
    await loadCategories();
  });
}

function renameCategory(category) {
  const name = window.prompt("New name for this category", category.name);
  if (name === null || !name.trim() || name.trim() === category.name) return;
  attempt(async () => {
    await api(`/categories/${category.id}`, { method: "PATCH", json: { name: name.trim() } });
    toast("Category renamed");
    await loadCategories();
  });
}

function deleteCategory(category) {
  if (!window.confirm(`Delete the category “${category.name}”? Its budgets are deleted with it.`)) return;
  attempt(async () => {
    await api(`/categories/${category.id}`, { method: "DELETE" });
    toast("Category deleted");
    await loadCategories();
  });
}

// ---------- tooltip ---------------------------------------------------------------

function setUpTooltip() {
  const tooltip = $("tooltip");
  const place = (event) => {
    const margin = 14;
    const box = tooltip.getBoundingClientRect();
    let left = event.clientX + margin;
    let top = event.clientY + margin;
    if (left + box.width > window.innerWidth - 8) left = event.clientX - box.width - margin;
    if (top + box.height > window.innerHeight - 8) top = event.clientY - box.height - margin;
    tooltip.style.left = `${Math.max(8, left)}px`;
    tooltip.style.top = `${Math.max(8, top)}px`;
  };
  document.addEventListener("mousemove", (event) => {
    const target = event.target.closest("[data-tip]");
    if (!target) {
      tooltip.hidden = true;
      return;
    }
    tooltip.textContent = target.dataset.tip;
    tooltip.hidden = false;
    place(event);
  });
  document.addEventListener("mouseleave", () => { tooltip.hidden = true; });
}

// ---------- wiring ----------------------------------------------------------------

function setUp() {
  $("auth-tab-login").addEventListener("click", () => setAuthMode("login"));
  $("auth-tab-register").addEventListener("click", () => setAuthMode("register"));
  $("auth-form").addEventListener("submit", submitAuth);
  $("logout").addEventListener("click", logout);

  for (const button of document.querySelectorAll(".tabs button")) {
    button.addEventListener("click", () => showTab(button.dataset.tab));
  }
  for (const button of document.querySelectorAll("[data-goto]")) {
    button.addEventListener("click", () => showTab(button.dataset.goto));
  }

  $("month-prev").addEventListener("click", () => setMonth(addMonths(state.month, -1)));
  $("month-next").addEventListener("click", () => setMonth(addMonths(state.month, 1)));
  $("month-today").addEventListener("click", () => setMonth(currentMonth()));

  $("add-expense").addEventListener("click", () => openExpenseDialog());
  $("expense-cancel").addEventListener("click", () => $("expense-dialog").close());
  $("expense-form").addEventListener("submit", saveExpense);

  let searchTimer;
  const filtersChanged = () => {
    state.page = 1;
    attempt(loadExpenses);
  };
  $("filters").addEventListener("submit", (event) => event.preventDefault());
  $("f-q").addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(filtersChanged, 250);
  });
  for (const id of ["f-category", "f-method", "f-from", "f-to"]) {
    $(id).addEventListener("change", filtersChanged);
  }
  $("f-clear").addEventListener("click", () => {
    for (const id of ["f-q", "f-category", "f-method", "f-from", "f-to"]) $(id).value = "";
    filtersChanged();
  });
  $("export-csv").addEventListener("click", () => attempt(downloadCsv));
  $("pager-prev").addEventListener("click", () => {
    state.page -= 1;
    attempt(loadExpenses);
  });
  $("pager-next").addEventListener("click", () => {
    state.page += 1;
    attempt(loadExpenses);
  });

  $("category-form").addEventListener("submit", addCategory);

  setUpTooltip();
  setAuthMode("login");
  start();
}

setUp();
