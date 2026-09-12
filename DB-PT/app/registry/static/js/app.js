// Personnel Registry front end.
// Plain ES module with no build step, so an update is just a git pull and restart.
// All user data is inserted with textContent (via h()), never innerHTML.

const STATUSES = [
  { value: "active", label: "Active" },
  { value: "leave", label: "On leave" },
  { value: "inactive", label: "Inactive" },
];
const STATUS_LABEL = Object.fromEntries(STATUSES.map((s) => [s.value, s.label]));
const STATUS_RANK = { active: 0, leave: 1, inactive: 2 };

const FIELD_TYPES = [
  { value: "text", label: "Short text" },
  { value: "textarea", label: "Long text" },
  { value: "number", label: "Number" },
  { value: "date", label: "Date" },
  { value: "select", label: "Dropdown" },
  { value: "checkbox", label: "Yes or no" },
  { value: "email", label: "Email address" },
  { value: "phone", label: "Phone number" },
  { value: "url", label: "Web link" },
];
const FIELD_TYPE_LABEL = Object.fromEntries(FIELD_TYPES.map((t) => [t.value, t.label]));

const SWATCHES = [
  ["#e8b84a", "Amber"],
  ["#ec8a4b", "Orange"],
  ["#ea6173", "Rose"],
  ["#cf7ae0", "Orchid"],
  ["#9587f5", "Violet"],
  ["#5aa6f2", "Blue"],
  ["#3fc1cf", "Cyan"],
  ["#52c98f", "Green"],
  ["#a9c952", "Lime"],
  ["#b9bcc4", "Silver"],
];

const ICONS = {
  plus: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 3.25v9.5M3.25 8h9.5"/></svg>',
  search: '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="7" cy="7" r="4.25"/><path d="m10.25 10.25 3 3"/></svg>',
  edit: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M10.5 3.5 12.5 5.5M3 13l.6-2.6 7.3-7.3a1.4 1.4 0 0 1 2 2L5.6 12.4z"/></svg>',
  download: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 2.75v7.5M4.75 7 8 10.25 11.25 7M3 13.25h10"/></svg>',
  close: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="m4 4 8 8M12 4l-8 8"/></svg>',
  chevron: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="m4.5 6.5 3.5 3.5 3.5-3.5"/></svg>',
};

// ---------------------------------------------------------------------------
// Small helpers

function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value == null || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key === "style") for (const [prop, v] of Object.entries(value)) el.style.setProperty(prop, v);
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2), value);
    else el.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of children.flat(Infinity)) {
    if (child == null || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

function icon(name) {
  const span = document.createElement("span");
  span.className = "icon";
  span.innerHTML = ICONS[name]; // static markup only
  return span;
}

let idCounter = 0;
const uid = (prefix = "el") => `${prefix}-${++idCounter}`;

const plural = (n, one, many = `${one}s`) => `${Number(n).toLocaleString()} ${n === 1 ? one : many}`;
const fullName = (p) => [p.first_name, p.last_name].filter(Boolean).join(" ");

function personInitials(first = "", last = "") {
  return `${[...first.trim()][0] || ""}${[...last.trim()][0] || ""}`.toUpperCase();
}

function userInitials(username = "") {
  const parts = username.split(/[._-]+/).filter(Boolean);
  const letters = parts.length > 1 ? parts[0][0] + parts[1][0] : username.slice(0, 2);
  return letters.toUpperCase();
}

// Black or white text, whichever reads better on a group colour.
function textOn(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || "");
  if (!m) return "#000";
  const [r, g, b] = [0, 2, 4].map((i) => {
    const c = parseInt(m[1].slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  const luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  return luminance > 0.18 ? "#000" : "#fff";
}

const dayFormat = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric" });
const stampFormat = new Intl.DateTimeFormat(undefined, {
  day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit",
});

function formatDay(value) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || "");
  return m ? dayFormat.format(new Date(+m[1], +m[2] - 1, +m[3])) : value || "";
}

function formatStamp(value) {
  if (!value) return "";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : stampFormat.format(d);
}

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

// ---------------------------------------------------------------------------
// API

class ApiError extends Error {
  constructor(status, detail) {
    const message = typeof detail === "string"
      ? detail
      : detail?.message || `The server returned an error (${status}).`;
    super(message);
    this.status = status;
    this.fields = detail && typeof detail === "object" && detail.fields ? detail.fields : {};
  }
}

async function api(path, { method = "GET", body } = {}) {
  const options = { method, credentials: "same-origin", headers: { Accept: "application/json" } };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path, options);
  } catch {
    throw new ApiError(0, "Can't reach the server. Check that the container is running.");
  }
  if (res.status === 401) {
    window.location.assign("/login");
    throw new ApiError(401, "Your session has ended. Sign in again.");
  }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, data?.detail);
  return data;
}

// ---------------------------------------------------------------------------
// State and routing

const state = {
  me: null,
  meta: null,
  groups: [],
  total: 0,
  unassigned: 0,
  fields: [],
  users: [],
  people: [],
  route: { name: "all" },
  filter: { q: "", status: "all" },
  sort: { key: "name", dir: 1 },
};

const refs = {
  box: document.querySelector(".box"),
  sidebar: document.getElementById("sidebar"),
  main: document.getElementById("main"),
  account: document.getElementById("account"),
  toasts: document.getElementById("toasts"),
  search: null,
  count: null,
  tableWrap: null,
};

function parseRoute() {
  const [name, id] = window.location.hash.replace(/^#\/?/, "").split("/");
  if (name === "group" && /^\d+$/.test(id || "")) return { name: "group", id: Number(id) };
  if (["unassigned", "fields", "users"].includes(name)) return { name };
  return { name: "all" };
}

const isPeopleRoute = (route) => ["all", "unassigned", "group"].includes(route.name);
const sameRoute = (a, b) => a.name === b.name && a.id === b.id;

function currentGroup() {
  return state.route.name === "group" ? state.groups.find((g) => g.id === state.route.id) || null : null;
}

function groupParam() {
  if (state.route.name === "group") return String(state.route.id);
  return state.route.name === "unassigned" ? "unassigned" : "all";
}

const groupById = (id) => state.groups.find((g) => g.id === id) || null;

function applicableFields(groupId, { tableOnly = false } = {}) {
  return state.fields.filter(
    (f) => (f.group_id === null || f.group_id === groupId) && (!tableOnly || f.show_in_table),
  );
}

async function loadGroups() {
  const data = await api("/api/groups");
  state.groups = data.groups;
  state.total = data.total;
  state.unassigned = data.unassigned;
}

async function loadFields() {
  state.fields = await api("/api/fields");
}

async function loadPeople() {
  state.people = await api(`/api/personnel?group=${encodeURIComponent(groupParam())}`);
}

async function loadUsers() {
  state.users = await api("/api/users");
}

let routeToken = 0;

async function showRoute() {
  const route = parseRoute();
  if (route.name === "group" && !groupById(route.id)) {
    history.replaceState(null, "", "#/all");
    return showRoute();
  }
  const token = ++routeToken;
  const changed = !sameRoute(route, state.route);
  state.route = route;
  if (changed) state.filter.q = "";
  applyViewFrame();
  renderSidebar();
  try {
    if (isPeopleRoute(route)) await loadPeople();
    else if (route.name === "users") await loadUsers();
  } catch (err) {
    if (token === routeToken) renderProblem(err);
    return;
  }
  if (token !== routeToken) return;
  renderMain();
  if (changed) refs.main.scrollTop = 0;
}

async function refreshPeople() {
  await Promise.all([loadGroups(), isPeopleRoute(state.route) ? loadPeople() : null]);
  renderSidebar();
  if (isPeopleRoute(state.route)) renderMain();
}

// ---------------------------------------------------------------------------
// Frame: sidebar, account menu, accent colour

function applyViewFrame() {
  const group = currentGroup();
  refs.box.dataset.view = state.route.name;
  refs.box.style.setProperty("--accent", group ? group.colour : "transparent");
  refs.box.style.setProperty("--on-accent", group ? textOn(group.colour) : "#000");
}

function navLink(href, label, count, { current = false, colour = null } = {}) {
  const link = h(
    "a",
    { class: "nav-item", href, "aria-current": current ? "page" : null },
    h("span", { class: "nav-name" }, label),
    count == null ? null : h("span", { class: "nav-count" }, Number(count).toLocaleString()),
  );
  if (colour) link.style.setProperty("--item-colour", colour);
  return h("li", {}, link);
}

function navSection(title, action, items) {
  return h(
    "section",
    { class: "nav-section" },
    h("div", { class: "nav-heading" }, h("span", {}, title), action),
    h("ul", { class: "nav-list" }, items),
  );
}

function renderSidebar() {
  const r = state.route;
  const groupItems = state.groups.map((g) =>
    navLink(`#/group/${g.id}`, g.name, g.member_count, {
      current: r.name === "group" && r.id === g.id,
      colour: g.colour,
    }),
  );
  refs.sidebar.replaceChildren(
    navSection("Directory", null, [
      navLink("#/all", "All personnel", state.total, { current: r.name === "all" }),
      navLink("#/unassigned", "Unassigned", state.unassigned, { current: r.name === "unassigned" }),
    ]),
    navSection(
      "Groups",
      h(
        "button",
        {
          class: "btn btn-ghost icon-btn",
          type: "button",
          title: "New group",
          "aria-label": "New group",
          onclick: () => openGroupDialog(null),
        },
        icon("plus"),
      ),
      groupItems.length ? groupItems : [h("li", { class: "nav-empty" }, "No groups yet.")],
    ),
    navSection("Settings", null, [
      navLink("#/fields", "Custom fields", state.fields.length, { current: r.name === "fields" }),
      navLink("#/users", "Users", null, { current: r.name === "users" }),
    ]),
  );
}

function renderAccount() {
  const menu = h(
    "details",
    { class: "menu-wrap" },
    h(
      "summary",
      { class: "btn btn-ghost", "aria-label": `Account: ${state.me.username}` },
      h("span", { class: "avatar", "aria-hidden": "true" }, userInitials(state.me.username)),
      h("span", {}, state.me.username),
      icon("chevron"),
    ),
    h(
      "div",
      { class: "menu" },
      h("button", { type: "button", onclick: () => { menu.open = false; openOwnPasswordDialog(); } }, "Change password"),
      h("button", { type: "button", onclick: signOut }, "Sign out"),
      state.meta ? h("div", { class: "menu-meta" }, `Version ${state.meta.version}, ${state.meta.database === "mariadb" ? "MariaDB" : "PostgreSQL"}`) : null,
    ),
  );
  refs.account.replaceChildren(menu);
}

async function signOut() {
  try {
    await api("/api/auth/logout", { method: "POST" });
  } finally {
    window.location.assign("/login");
  }
}

// ---------------------------------------------------------------------------
// Main views

function renderMain() {
  applyViewFrame();
  refs.main.setAttribute("aria-labelledby", "view-title");
  if (state.route.name === "fields") return renderFieldsView();
  if (state.route.name === "users") return renderUsersView();
  return renderPeopleView();
}

function renderProblem(err) {
  refs.main.replaceChildren(
    h(
      "div",
      { class: "empty" },
      h("h2", { id: "view-title" }, "This view didn't load"),
      h("p", {}, err.message),
      h("div", { class: "empty-actions" }, h("button", { class: "btn", type: "button", onclick: showRoute }, "Try again")),
    ),
  );
}

function viewHead({ title, code, description, actions = [] }) {
  return h(
    "header",
    { class: "view-head" },
    h(
      "div",
      { class: "view-heading" },
      h(
        "div",
        { class: "view-title-row" },
        h("h1", { class: "view-title", id: "view-title" }, title),
        code ? h("span", { class: "view-code" }, code) : null,
      ),
      description ? h("p", { class: "view-desc" }, description) : null,
    ),
    actions.length ? h("div", { class: "view-actions" }, actions) : null,
  );
}

// ---- people ----------------------------------------------------------------

function renderPeopleView() {
  const group = currentGroup();
  const r = state.route;
  const title = group ? group.name : r.name === "unassigned" ? "Unassigned" : "All personnel";
  const description = group
    ? group.description
    : r.name === "unassigned"
      ? "People who aren't in a group yet."
      : "Everyone in the registry, across every group.";

  const actions = [
    group ? h("button", { class: "btn", type: "button", onclick: () => openGroupDialog(group) }, icon("edit"), "Edit group") : null,
    h("button", { class: "btn", type: "button", onclick: exportCsv }, icon("download"), "Export CSV"),
    h("button", { class: "btn btn-primary", type: "button", onclick: () => openPersonDrawer(null) }, icon("plus"), "Add person"),
  ].filter(Boolean);

  refs.search = h("input", {
    class: "input",
    type: "search",
    placeholder: "Search names, IDs, titles and details",
    "aria-label": "Search personnel",
    value: state.filter.q,
    oninput: (event) => {
      state.filter.q = event.target.value;
      renderTable();
    },
  });

  const statusFilter = h(
    "div",
    { class: "segmented", role: "group", "aria-label": "Filter by status" },
    [{ value: "all", label: "All" }, ...STATUSES].map((s) =>
      h(
        "button",
        {
          type: "button",
          "aria-pressed": String(state.filter.status === s.value),
          onclick: (event) => {
            state.filter.status = s.value;
            for (const b of event.currentTarget.parentElement.children) {
              b.setAttribute("aria-pressed", String(b === event.currentTarget));
            }
            renderTable();
          },
        },
        s.label,
      ),
    ),
  );

  refs.count = h("span", { class: "result-count", "aria-live": "polite" });
  refs.tableWrap = h("div", { class: "table-wrap" });

  refs.main.replaceChildren(
    viewHead({ title, code: group?.code, description, actions }),
    h("div", { class: "toolbar" }, h("label", { class: "search" }, icon("search"), refs.search), statusFilter, refs.count),
    refs.tableWrap,
  );
  renderTable();
}

function filteredPeople() {
  const terms = state.filter.q.toLowerCase().split(/\s+/).filter(Boolean);
  return state.people.filter((p) => {
    if (state.filter.status !== "all" && p.status !== state.filter.status) return false;
    if (!terms.length) return true;
    const haystack = [
      p.identifier, p.first_name, p.last_name, p.preferred_name, p.job_title, p.role,
      p.email, p.phone, groupById(p.group_id)?.name,
      ...Object.values(p.extra || {}).filter((v) => typeof v !== "boolean"),
    ]
      .filter((v) => v != null && v !== "")
      .join(" ")
      .toLowerCase();
    return terms.every((t) => haystack.includes(t));
  });
}

function peopleColumns() {
  const group = currentGroup();
  const columns = [
    { key: "identifier", label: "ID", className: "cell-id", sortValue: (p) => p.identifier, render: (p) => p.identifier || "" },
    { key: "name", label: "Name", sortValue: (p) => `${p.last_name} ${p.first_name}`, render: nameCell },
    { key: "job_title", label: "Job title", sortValue: (p) => p.job_title, render: (p) => truncated(p.job_title) },
    { key: "role", label: "Role", sortValue: (p) => p.role, render: (p) => truncated(p.role) },
  ];
  if (state.route.name === "all") {
    columns.push({
      key: "group",
      label: "Group",
      sortValue: (p) => groupById(p.group_id)?.name,
      render: (p) => groupById(p.group_id)?.name || h("span", { class: "faint" }, "Unassigned"),
    });
  }
  for (const field of applicableFields(group ? group.id : null, { tableOnly: true })) {
    columns.push({
      key: `extra.${field.key}`,
      label: field.label,
      sortValue: (p) => p.extra?.[field.key],
      render: (p) => extraCell(field, p.extra?.[field.key]),
    });
  }
  columns.push({
    key: "status",
    label: "Status",
    sortValue: (p) => STATUS_RANK[p.status],
    render: (p) => h("span", { class: "status", dataset: { status: p.status } }, STATUS_LABEL[p.status] || p.status),
  });
  return columns;
}

function truncated(value) {
  return value ? h("span", { class: "truncate", title: value }, value) : "";
}

function nameCell(person) {
  return h(
    "span",
    {},
    h("button", { class: "name-link", type: "button", onclick: () => openPersonDrawer(person) }, fullName(person)),
    person.preferred_name ? h("span", { class: "pref" }, `“${person.preferred_name}”`) : null,
  );
}

function formatExtra(field, value) {
  if (value === undefined || value === null || value === "") return "";
  if (field.field_type === "checkbox") return value ? "Yes" : "No";
  if (field.field_type === "date") return formatDay(value);
  if (field.field_type === "number" && typeof value === "number") return value.toLocaleString();
  return String(value);
}

function extraCell(field, value) {
  if (field.field_type === "url" && typeof value === "string" && /^https?:\/\//i.test(value)) {
    const label = value.replace(/^https?:\/\//i, "").replace(/\/$/, "");
    return h("a", { class: "cell-link truncate", href: value, target: "_blank", rel: "noopener noreferrer", onclick: (e) => e.stopPropagation() }, label);
  }
  if (field.field_type === "email" && value) {
    return h("a", { class: "cell-link", href: `mailto:${value}`, onclick: (e) => e.stopPropagation() }, value);
  }
  return truncated(formatExtra(field, value));
}

function sortPeople(people, columns) {
  const column = columns.find((c) => c.key === state.sort.key) || columns.find((c) => c.key === "name");
  const dir = column.key === state.sort.key ? state.sort.dir : 1;
  const isEmpty = (v) => v === undefined || v === null || v === "";
  return [...people].sort((a, b) => {
    const va = column.sortValue(a);
    const vb = column.sortValue(b);
    if (isEmpty(va) || isEmpty(vb)) return isEmpty(va) === isEmpty(vb) ? 0 : isEmpty(va) ? 1 : -1;
    let result;
    if (typeof va === "number" && typeof vb === "number") result = va - vb;
    else if (typeof va === "boolean" || typeof vb === "boolean") result = Number(vb) - Number(va);
    else result = collator.compare(String(va), String(vb));
    return result * dir || collator.compare(`${a.last_name} ${a.first_name}`, `${b.last_name} ${b.first_name}`);
  });
}

function renderTable() {
  const group = currentGroup();
  const total = state.people.length;
  const columns = peopleColumns();
  const people = sortPeople(filteredPeople(), columns);
  refs.count.textContent = people.length === total ? plural(total, "person", "people") : `${people.length.toLocaleString()} of ${plural(total, "person", "people")}`;

  if (!total) {
    refs.tableWrap.replaceChildren(emptyPeople(group));
    return;
  }
  if (!people.length) {
    refs.tableWrap.replaceChildren(
      h(
        "div",
        { class: "empty" },
        h("h2", {}, "No one matches"),
        h("p", {}, "Nobody in this view matches your search and status filter."),
        h("div", { class: "empty-actions" }, h("button", { class: "btn", type: "button", onclick: clearFilters }, "Clear filters")),
      ),
    );
    return;
  }

  const thead = h(
    "thead",
    {},
    h(
      "tr",
      {},
      columns.map((c) => {
        const active = state.sort.key === c.key;
        return h(
          "th",
          { scope: "col", "aria-sort": active ? (state.sort.dir > 0 ? "ascending" : "descending") : null },
          h(
            "button",
            {
              class: "sort",
              type: "button",
              onclick: () => {
                state.sort = { key: c.key, dir: active ? -state.sort.dir : 1 };
                renderTable();
              },
            },
            c.label,
            active ? h("span", { "aria-hidden": "true" }, state.sort.dir > 0 ? "↑" : "↓") : null,
          ),
        );
      }),
    ),
  );

  const notched = state.route.name === "all";
  const tbody = h(
    "tbody",
    {},
    people.map((person) => {
      const row = h(
        "tr",
        {
          onclick: (event) => {
            if (!event.target.closest("button, a")) openPersonDrawer(person);
          },
        },
        columns.map((c) => h("td", { class: c.className || null }, c.render(person))),
      );
      if (notched && person.group_id) row.style.setProperty("--row-colour", groupById(person.group_id)?.colour || "transparent");
      return row;
    }),
  );

  refs.tableWrap.replaceChildren(h("table", { class: `grid clickable${notched ? " notched" : ""}` }, thead, tbody));
}

function emptyPeople(group) {
  if (group) {
    return h(
      "div",
      { class: "empty" },
      h("h2", {}, `No one in ${group.name} yet`),
      h("p", {}, "Add a person here, or open an existing record and move them into this group."),
      h("div", { class: "empty-actions" }, h("button", { class: "btn btn-primary", type: "button", onclick: () => openPersonDrawer(null) }, icon("plus"), "Add person")),
    );
  }
  if (state.route.name === "unassigned") {
    return h("div", { class: "empty" }, h("h2", {}, "Everyone is in a group"), h("p", {}, "People without a group will be listed here."));
  }
  return h(
    "div",
    { class: "empty" },
    h("h2", {}, "The registry is empty"),
    h("p", {}, state.groups.length ? "Add your first person to get started." : "Create groups for your teams or departments, then add people to them."),
    h(
      "div",
      { class: "empty-actions" },
      state.groups.length ? null : h("button", { class: "btn", type: "button", onclick: () => openGroupDialog(null) }, "New group"),
      h("button", { class: "btn btn-primary", type: "button", onclick: () => openPersonDrawer(null) }, icon("plus"), "Add person"),
    ),
  );
}

function clearFilters() {
  state.filter = { q: "", status: "all" };
  renderPeopleView();
}

function exportCsv() {
  const params = new URLSearchParams({ group: groupParam(), status: state.filter.status });
  if (state.filter.q.trim()) params.set("q", state.filter.q.trim());
  const link = h("a", { href: `/api/personnel/export.csv?${params}`, download: "" });
  document.body.append(link);
  link.click();
  link.remove();
}

// ---- custom fields view ------------------------------------------------------

function scopeLabel(groupId) {
  const group = groupById(groupId);
  const el = h("span", { class: "scope" }, group ? group.name : "All groups");
  if (group) el.style.setProperty("--scope-colour", group.colour);
  return el;
}

function renderFieldsView() {
  const head = viewHead({
    title: "Custom fields",
    description: "Record extra details about people. A field can apply to everyone, or only to one group.",
    actions: [h("button", { class: "btn btn-primary", type: "button", onclick: () => openFieldDialog(null) }, icon("plus"), "Add field")],
  });

  if (!state.fields.length) {
    refs.main.replaceChildren(
      head,
      h(
        "div",
        { class: "table-wrap" },
        h(
          "div",
          { class: "empty" },
          h("h2", {}, "No custom fields yet"),
          h("p", {}, "Add fields such as clearance level, employee number or emergency contact. They appear in every person's record."),
          h("div", { class: "empty-actions" }, h("button", { class: "btn btn-primary", type: "button", onclick: () => openFieldDialog(null) }, icon("plus"), "Add field")),
        ),
      ),
    );
    return;
  }

  const header = ["Field", "Type", "Applies to", "Required", "Table column", "Order"];
  const table = h(
    "table",
    { class: "grid clickable" },
    h("thead", {}, h("tr", {}, header.map((label) => h("th", { scope: "col" }, h("span", { class: "th-label" }, label))))),
    h(
      "tbody",
      {},
      state.fields.map((f) =>
        h(
          "tr",
          { onclick: () => openFieldDialog(f) },
          h("td", {}, h("button", { class: "name-link", type: "button", onclick: (e) => { e.stopPropagation(); openFieldDialog(f); } }, f.label), " ", h("code", {}, f.key)),
          h("td", {}, FIELD_TYPE_LABEL[f.field_type] || f.field_type, f.field_type === "select" ? h("span", { class: "faint" }, ` (${plural((f.options || []).length, "option")})`) : null),
          h("td", {}, scopeLabel(f.group_id)),
          h("td", {}, f.required ? "Yes" : h("span", { class: "faint" }, "No")),
          h("td", {}, f.show_in_table ? "Shown" : h("span", { class: "faint" }, "Hidden")),
          h("td", { class: "faint" }, String(f.sort_order)),
        ),
      ),
    ),
  );
  refs.main.replaceChildren(head, h("div", { class: "table-wrap" }, table));
}

// ---- users view --------------------------------------------------------------

function renderUsersView() {
  const head = viewHead({
    title: "Users",
    description: "Accounts that can sign in. Every user can view and change all records.",
    actions: [h("button", { class: "btn btn-primary", type: "button", onclick: openAddUserDialog }, icon("plus"), "Add user")],
  });
  const header = ["Username", "Last signed in", "Created", ""];
  const table = h(
    "table",
    { class: "grid" },
    h("thead", {}, h("tr", {}, header.map((label) => h("th", { scope: "col" }, h("span", { class: "th-label" }, label))))),
    h(
      "tbody",
      {},
      state.users.map((u) => {
        const isMe = u.id === state.me.id;
        return h(
          "tr",
          {},
          h("td", {}, h("span", { class: "cell-user" }, h("span", { class: "avatar", "aria-hidden": "true" }, userInitials(u.username)), u.username, isMe ? h("span", { class: "tag" }, "You") : null)),
          h("td", {}, u.last_login_at ? formatStamp(u.last_login_at) : h("span", { class: "faint" }, "Never")),
          h("td", {}, formatStamp(u.created_at)),
          h(
            "td",
            { class: "cell-actions" },
            isMe
              ? h("button", { class: "btn btn-small", type: "button", onclick: openOwnPasswordDialog }, "Change password")
              : [
                h("button", { class: "btn btn-small", type: "button", onclick: () => openResetPasswordDialog(u) }, "Reset password"),
                h("button", { class: "btn btn-small btn-danger", type: "button", onclick: () => deleteUser(u) }, "Delete"),
              ],
          ),
        );
      }),
    ),
  );
  refs.main.replaceChildren(head, h("div", { class: "table-wrap" }, table));
}

// ---------------------------------------------------------------------------
// Form building blocks

function inputField({ name, label, type = "text", value, required = false, span = 1, hint, options, attrs = {} }) {
  const id = uid("field");
  const errorId = `${id}-error`;
  const wrapClass = `field${span === 2 ? " span-2" : ""}`;
  const error = h("p", { class: "field-error", id: errorId, hidden: true });
  const hintEl = hint ? h("p", { class: "field-hint" }, hint) : null;

  if (type === "checkbox") {
    return h(
      "div",
      { class: wrapClass, dataset: { field: name } },
      h("label", { class: "check" }, h("input", { type: "checkbox", id, name, checked: Boolean(value), ...attrs }), h("span", {}, label)),
      hintEl,
      error,
    );
  }

  let control;
  if (type === "textarea") {
    control = h("textarea", { class: "input", id, name, required, rows: 3, ...attrs }, value ?? "");
  } else if (type === "select") {
    control = h(
      "select",
      { class: "input", id, name, required, ...attrs },
      options.map(([optionValue, optionLabel]) =>
        h("option", { value: optionValue, selected: String(optionValue) === String(value ?? "") }, optionLabel),
      ),
    );
  } else {
    control = h("input", { class: "input", id, name, type, value: value ?? "", required, ...attrs });
  }

  return h(
    "div",
    { class: wrapClass, dataset: { field: name } },
    h("label", { for: id }, label, required ? h("span", { class: "req", "aria-hidden": "true" }, " *") : null),
    control,
    hintEl,
    error,
  );
}

function customFieldInput(field, value) {
  const common = { name: `extra.${field.key}`, label: field.label, required: field.required, value };
  switch (field.field_type) {
    case "textarea":
      return inputField({ ...common, type: "textarea", span: 2 });
    case "number":
      return inputField({ ...common, type: "number", attrs: { step: "any" } });
    case "date":
      return inputField({ ...common, type: "date" });
    case "email":
      return inputField({ ...common, type: "email", attrs: { autocomplete: "off" } });
    case "phone":
      return inputField({ ...common, type: "tel", attrs: { autocomplete: "off" } });
    case "url":
      return inputField({ ...common, type: "url", attrs: { placeholder: "https://" } });
    case "checkbox":
      return inputField({ ...common, type: "checkbox", required: false, value: value === true });
    case "select": {
      const choices = (field.options || []).map((o) => [o, o]);
      if (value && !field.options?.includes(value)) choices.push([value, `${value} (no longer an option)`]);
      return inputField({ ...common, type: "select", options: [["", "Not set"], ...choices] });
    }
    default:
      return inputField({ ...common, type: "text", attrs: { autocomplete: "off" } });
  }
}

function clearErrors(form, banner) {
  banner.hidden = true;
  banner.textContent = "";
  for (const wrap of form.querySelectorAll(".field.invalid")) {
    wrap.classList.remove("invalid");
    const control = wrap.querySelector("input, select, textarea");
    control?.removeAttribute("aria-invalid");
    control?.removeAttribute("aria-describedby");
    const error = wrap.querySelector(".field-error");
    if (error) {
      error.hidden = true;
      error.textContent = "";
    }
  }
}

function showErrors(form, banner, err) {
  const fields = err instanceof ApiError ? err.fields : {};
  const unplaced = [];
  let first = null;
  for (const [key, message] of Object.entries(fields)) {
    const wrap = form.querySelector(`[data-field="${CSS.escape(key)}"]`);
    if (!wrap) {
      unplaced.push(message);
      continue;
    }
    wrap.classList.add("invalid");
    const error = wrap.querySelector(".field-error");
    error.textContent = message;
    error.hidden = false;
    const control = wrap.querySelector("input, select, textarea");
    if (control) {
      control.setAttribute("aria-invalid", "true");
      control.setAttribute("aria-describedby", error.id);
      first ??= control;
    }
  }
  if (!first || unplaced.length) {
    banner.textContent = [err.message || "Something went wrong.", ...unplaced].join(" ");
    banner.hidden = false;
    banner.scrollIntoView({ block: "nearest" });
  }
  first?.focus();
}

// Reports every empty required field at once, before the server is asked.
function checkRequired(form) {
  const fields = {};
  for (const control of form.querySelectorAll("input[required], select[required], textarea[required]")) {
    const wrap = control.closest("[data-field]");
    if (!wrap || wrap.closest("[hidden]") || control.value.trim()) continue;
    fields[wrap.dataset.field] = "This field is required.";
  }
  if (Object.keys(fields).length) {
    throw new ApiError(422, { message: "Some fields need attention.", fields });
  }
}

function formDialog({ title, subtitle, head, accent, className = "modal", content, submitLabel, onSubmit, dangerAction }) {
  const titleId = uid("title");
  const banner = h("p", { class: "form-banner", role: "alert", hidden: true });
  const submit = h("button", { class: "btn btn-primary", type: "submit" }, submitLabel);
  const form = h("form", { class: "dialog-form", novalidate: true });
  const dialog = h("dialog", { class: `${className}${accent ? " has-accent" : ""}`, "aria-labelledby": titleId }, form);
  const closeButton = h("button", { class: "btn btn-ghost icon-btn dialog-close", type: "button", "aria-label": "Close", onclick: () => dialog.close() }, icon("close"));

  form.append(
    head ? head(titleId, closeButton) : h(
      "div",
      { class: "dialog-head" },
      h("h2", { class: "dialog-title", id: titleId }, title),
      subtitle ? h("p", { class: "dialog-sub" }, subtitle) : null,
      closeButton,
    ),
    h("div", { class: "dialog-body" }, banner, content),
    h(
      "div",
      { class: "dialog-foot" },
      dangerAction || null,
      h("span", { class: "spacer" }),
      h("button", { class: "btn", type: "button", onclick: () => dialog.close() }, "Cancel"),
      submit,
    ),
  );

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearErrors(form, banner);
    submit.disabled = true;
    try {
      checkRequired(form);
      await onSubmit(form, dialog);
    } catch (err) {
      showErrors(form, banner, err);
    } finally {
      submit.disabled = false;
    }
  });

  if (accent) dialog.style.setProperty("--accent", accent);
  dialog.addEventListener("close", () => dialog.remove());
  document.body.append(dialog);
  dialog.showModal();
  return { dialog, form, banner };
}

function confirmDialog({ title, body, confirmLabel, danger = false }) {
  return new Promise((resolve) => {
    let confirmed = false;
    const titleId = uid("title");
    const dialog = h(
      "dialog",
      { class: "modal", role: "alertdialog", "aria-labelledby": titleId },
      h("div", { class: "dialog-head" }, h("h2", { class: "dialog-title", id: titleId }, title)),
      h("div", { class: "dialog-body" }, body),
      h(
        "div",
        { class: "dialog-foot" },
        h("span", { class: "spacer" }),
        h("button", { class: "btn", type: "button", autofocus: true, onclick: () => dialog.close() }, "Cancel"),
        h(
          "button",
          { class: `btn ${danger ? "btn-danger-solid" : "btn-primary"}`, type: "button", onclick: () => { confirmed = true; dialog.close(); } },
          confirmLabel,
        ),
      ),
    );
    dialog.addEventListener("close", () => {
      dialog.remove();
      resolve(confirmed);
    });
    document.body.append(dialog);
    dialog.showModal();
  });
}

function toast(message, kind = "ok") {
  const host = refs.toasts;
  const el = h("div", { class: `toast${kind === "error" ? " toast-error" : ""}`, role: kind === "error" ? "alert" : "status" }, message);
  host.append(el);
  if (typeof host.showPopover === "function") {
    try { host.hidePopover(); } catch { /* not open */ }
    host.showPopover(); // re-open so it stacks above any open dialog
  }
  window.setTimeout(() => {
    el.remove();
    if (!host.children.length && typeof host.hidePopover === "function") {
      try { host.hidePopover(); } catch { /* already closed */ }
    }
  }, kind === "error" ? 6000 : 3200);
}

// ---------------------------------------------------------------------------
// Person record

function openPersonDrawer(person) {
  const isNew = !person;
  const draftExtra = { ...(person?.extra || {}) };
  const defaults = {
    identifier: "", first_name: "", last_name: "", preferred_name: "", job_title: "", role: "",
    email: "", phone: "", status: "active", start_date: "", notes: "",
    group_id: state.route.name === "group" ? state.route.id : null,
  };
  const record = { ...defaults, ...(person || {}) };

  const monogram = h("div", { class: "monogram", "aria-hidden": "true" });
  const idLine = h("div", { class: "badge-id" });
  const nameLine = h("h2", { class: "badge-name" });
  const titleLine = h("p", { class: "badge-title" });
  const groupLine = h("div", { class: "badge-group" });

  const groupOptions = [["", "Unassigned"], ...state.groups.map((g) => [g.id, g.name])];
  const extraSection = h("section", { class: "form-section" });

  const content = [
    h(
      "section",
      { class: "form-section" },
      h("h3", {}, "Identity"),
      h(
        "div",
        { class: "form-grid" },
        inputField({ name: "first_name", label: "First name", required: true, value: record.first_name, attrs: { maxlength: 100, autocomplete: "off" } }),
        inputField({ name: "last_name", label: "Last name", required: true, value: record.last_name, attrs: { maxlength: 100, autocomplete: "off" } }),
        inputField({ name: "preferred_name", label: "Preferred name", value: record.preferred_name, attrs: { maxlength: 100, autocomplete: "off" } }),
        inputField({ name: "identifier", label: "Personnel ID", value: record.identifier, hint: "Must be unique if set.", attrs: { maxlength: 64, autocomplete: "off" } }),
      ),
    ),
    h(
      "section",
      { class: "form-section" },
      h("h3", {}, "Position"),
      h(
        "div",
        { class: "form-grid" },
        inputField({ name: "job_title", label: "Job title", value: record.job_title, attrs: { maxlength: 150, autocomplete: "off" } }),
        inputField({ name: "role", label: "Role", value: record.role, attrs: { maxlength: 150, autocomplete: "off" } }),
        inputField({ name: "group_id", label: "Group", type: "select", value: record.group_id ?? "", options: groupOptions }),
        inputField({ name: "status", label: "Status", type: "select", value: record.status, options: STATUSES.map((s) => [s.value, s.label]) }),
        inputField({ name: "start_date", label: "Start date", type: "date", value: record.start_date }),
      ),
    ),
    h(
      "section",
      { class: "form-section" },
      h("h3", {}, "Contact"),
      h(
        "div",
        { class: "form-grid" },
        inputField({ name: "email", label: "Email", type: "email", value: record.email, attrs: { maxlength: 255, autocomplete: "off" } }),
        inputField({ name: "phone", label: "Phone", type: "tel", value: record.phone, attrs: { maxlength: 50, autocomplete: "off" } }),
      ),
    ),
    extraSection,
    h(
      "section",
      { class: "form-section" },
      h("h3", {}, "Notes"),
      inputField({ name: "notes", label: "Notes", type: "textarea", value: record.notes, span: 2, attrs: { rows: 4, maxlength: 20000 } }),
    ),
    isNew ? null : h("p", { class: "record-meta" }, `Added ${formatStamp(record.created_at)}. Last changed ${formatStamp(record.updated_at)}.`),
  ];

  const deleteButton = isNew
    ? null
    : h("button", { class: "btn btn-danger", type: "button", onclick: () => deletePerson(person, dialog) }, "Delete person");

  const { dialog, form } = formDialog({
    className: "drawer",
    accent: "transparent",
    content,
    submitLabel: isNew ? "Add person" : "Save changes",
    dangerAction: deleteButton,
    head: (titleId, closeButton) => {
      nameLine.id = titleId;
      return h("div", { class: "badge" }, monogram, h("div", {}, idLine, nameLine, titleLine, groupLine), closeButton);
    },
    onSubmit: async (formEl, dlg) => {
      const payload = { extra: {} };
      for (const el of formEl.elements) {
        if (!el.name) continue;
        const value = el.type === "checkbox" ? el.checked : el.value;
        if (el.name.startsWith("extra.")) payload.extra[el.name.slice(6)] = value;
        else payload[el.name] = value;
      }
      payload.group_id = payload.group_id ? Number(payload.group_id) : null;
      const saved = isNew
        ? await api("/api/personnel", { method: "POST", body: payload })
        : await api(`/api/personnel/${person.id}`, { method: "PUT", body: payload });
      dlg.close();
      toast(isNew ? `${fullName(saved)} added` : "Changes saved");
      await refreshPeople();
    },
  });

  function selectedGroupId() {
    const value = form.elements.group_id.value;
    return value ? Number(value) : null;
  }

  function renderExtraSection() {
    for (const el of extraSection.querySelectorAll("[name^='extra.']")) {
      draftExtra[el.name.slice(6)] = el.type === "checkbox" ? el.checked : el.value;
    }
    const fields = applicableFields(selectedGroupId());
    if (!fields.length) {
      extraSection.hidden = !state.fields.length ? false : true;
      extraSection.replaceChildren(
        h("h3", {}, "Additional details"),
        h(
          "p",
          { class: "field-hint" },
          "No custom fields yet. ",
          h("a", { href: "#/fields", class: "cell-link", onclick: () => dialog.close() }, "Add custom fields"),
          " to record more about each person.",
        ),
      );
      return;
    }
    extraSection.hidden = false;
    extraSection.replaceChildren(
      h("h3", {}, "Additional details"),
      h("div", { class: "form-grid" }, fields.map((f) => customFieldInput(f, draftExtra[f.key]))),
    );
  }

  function updateBadge() {
    const first = form.elements.first_name.value.trim();
    const last = form.elements.last_name.value.trim();
    const group = groupById(selectedGroupId());
    monogram.textContent = personInitials(first, last) || "?";
    nameLine.textContent = [first, last].filter(Boolean).join(" ") || (isNew ? "New person" : "Unnamed");
    idLine.textContent = form.elements.identifier.value.trim() || "No ID assigned";
    titleLine.textContent = form.elements.job_title.value.trim();
    groupLine.textContent = group ? group.name : "Unassigned";
    dialog.style.setProperty("--accent", group ? group.colour : "var(--line-strong)");
  }

  form.elements.group_id.addEventListener("change", () => {
    renderExtraSection();
    updateBadge();
  });
  form.addEventListener("input", updateBadge);
  renderExtraSection();
  updateBadge();
  if (isNew) form.elements.first_name.focus();
}

async function deletePerson(person, drawer) {
  const ok = await confirmDialog({
    title: `Delete ${fullName(person)}?`,
    body: h("p", {}, "This removes their record and every detail stored with it. It can't be undone."),
    confirmLabel: "Delete person",
    danger: true,
  });
  if (!ok) return;
  try {
    await api(`/api/personnel/${person.id}`, { method: "DELETE" });
    drawer.close();
    toast("Person deleted");
    await refreshPeople();
  } catch (err) {
    toast(err.message, "error");
  }
}

// ---------------------------------------------------------------------------
// Groups

function openGroupDialog(group) {
  const isNew = !group;
  const startColour = (group?.colour || SWATCHES[state.groups.length % SWATCHES.length][0]).toLowerCase();
  const presetMatch = SWATCHES.some(([hex]) => hex === startColour);

  const colourValue = h("input", { type: "hidden", name: "colour", value: startColour });
  const customInput = h("input", { type: "color", value: startColour, "aria-label": "Custom colour" });
  const customSwatch = h("label", { class: `swatch swatch-custom${presetMatch ? "" : " is-active"}`, title: "Custom colour" }, customInput);
  customSwatch.style.setProperty("--swatch", startColour);

  const swatches = h(
    "div",
    { class: "swatches", role: "radiogroup", "aria-label": "Group colour" },
    SWATCHES.map(([hex, name]) => {
      const label = h("label", { class: "swatch", title: name }, h("input", { type: "radio", name: "swatch", value: hex, checked: hex === startColour, "aria-label": name }));
      label.style.setProperty("--swatch", hex);
      return label;
    }),
    customSwatch,
  );

  const content = h(
    "div",
    { class: "form-grid" },
    inputField({ name: "name", label: "Name", required: true, value: group?.name, span: 2, attrs: { maxlength: 100, autocomplete: "off" } }),
    inputField({ name: "code", label: "Short code", value: group?.code, hint: "Shown beside the name, for example OPS.", attrs: { maxlength: 16, autocomplete: "off" } }),
    inputField({ name: "sort_order", label: "Menu position", type: "number", value: group?.sort_order ?? 0, hint: "Lower numbers are listed first.", attrs: { step: 1 } }),
    h("div", { class: "field span-2", dataset: { field: "colour" } }, h("span", { class: "field-label" }, "Colour"), swatches, colourValue, h("p", { class: "field-error", id: uid("err"), hidden: true })),
    inputField({ name: "description", label: "Description", type: "textarea", value: group?.description, span: 2, attrs: { maxlength: 2000, rows: 3 } }),
  );

  let dialogRef = null;
  const { dialog } = formDialog({
    title: isNew ? "New group" : "Edit group",
    subtitle: isNew ? "Groups appear in the menu and can have their own custom fields." : null,
    accent: startColour,
    content,
    submitLabel: isNew ? "Create group" : "Save changes",
    dangerAction: isNew ? null : h("button", { class: "btn btn-danger", type: "button", onclick: () => deleteGroup(group, dialogRef) }, "Delete group"),
    onSubmit: async (form, dlg) => {
      const payload = {
        name: form.elements.name.value,
        code: form.elements.code.value,
        colour: form.elements.colour.value,
        description: form.elements.description.value,
        sort_order: Number.parseInt(form.elements.sort_order.value, 10) || 0,
      };
      const saved = await api(isNew ? "/api/groups" : `/api/groups/${group.id}`, { method: isNew ? "POST" : "PUT", body: payload });
      dlg.close();
      await loadGroups();
      toast(isNew ? "Group created" : "Changes saved");
      if (isNew) {
        window.location.hash = `#/group/${saved.id}`;
      } else {
        renderSidebar();
        if (isPeopleRoute(state.route)) renderMain();
      }
    },
  });
  dialogRef = dialog;

  function setColour(hex) {
    colourValue.value = hex;
    dialog.style.setProperty("--accent", hex);
  }

  swatches.addEventListener("change", (event) => {
    if (event.target.name !== "swatch") return;
    customSwatch.classList.remove("is-active");
    customInput.value = event.target.value;
    setColour(event.target.value);
  });

  customInput.addEventListener("input", () => {
    for (const radio of swatches.querySelectorAll("input[type=radio]")) radio.checked = false;
    customSwatch.classList.add("is-active");
    customSwatch.style.setProperty("--swatch", customInput.value);
    setColour(customInput.value);
  });
}

async function deleteGroup(group, groupDialog) {
  const others = state.groups.filter((g) => g.id !== group.id);
  const fieldCount = state.fields.filter((f) => f.group_id === group.id).length;
  const reassign = h(
    "select",
    { class: "input", id: uid("reassign") },
    h("option", { value: "" }, "Leave them unassigned"),
    others.map((g) => h("option", { value: g.id }, `Move them to ${g.name}`)),
  );

  const body = [
    h("p", {}, group.member_count ? `${group.name} has ${plural(group.member_count, "person", "people")} in it.` : `${group.name} has no one in it.`),
    group.member_count ? h("div", { class: "field" }, h("label", { for: reassign.id }, "What happens to its members"), reassign) : null,
    fieldCount ? h("p", {}, `Its ${plural(fieldCount, "custom field")} and the values stored in them will also be deleted.`) : null,
    h("p", { class: "muted" }, "This can't be undone."),
  ];

  const ok = await confirmDialog({ title: `Delete ${group.name}?`, body, confirmLabel: "Delete group", danger: true });
  if (!ok) return;
  try {
    const query = reassign.value ? `?reassign_to=${encodeURIComponent(reassign.value)}` : "";
    await api(`/api/groups/${group.id}${query}`, { method: "DELETE" });
    groupDialog?.close();
    await Promise.all([loadGroups(), loadFields()]);
    toast("Group deleted");
    if (state.route.name === "group" && state.route.id === group.id) {
      window.location.hash = "#/all";
    } else {
      await showRoute();
    }
  } catch (err) {
    toast(err.message, "error");
  }
}

// ---------------------------------------------------------------------------
// Custom fields

function openFieldDialog(field) {
  const isNew = !field;
  const typeField = inputField({ name: "field_type", label: "Type", type: "select", value: field?.field_type || "text", options: FIELD_TYPES.map((t) => [t.value, t.label]) });
  const optionsField = inputField({
    name: "options", label: "Options", type: "textarea", span: 2,
    value: (field?.options || []).join("\n"), hint: "One option per line, in the order they should appear.", attrs: { rows: 5 },
  });
  const requiredField = inputField({ name: "required", label: "Required", type: "checkbox", value: field?.required, hint: "Records can't be saved without it." });

  const content = h(
    "div",
    { class: "form-grid" },
    inputField({ name: "label", label: "Label", required: true, value: field?.label, span: 2, attrs: { maxlength: 100, autocomplete: "off" } }),
    typeField,
    inputField({
      name: "group_id", label: "Applies to", type: "select", value: field?.group_id ?? "",
      options: [["", "All groups"], ...state.groups.map((g) => [g.id, g.name])],
    }),
    optionsField,
    requiredField,
    inputField({ name: "show_in_table", label: "Show as a table column", type: "checkbox", value: field?.show_in_table }),
    inputField({ name: "sort_order", label: "Order in forms", type: "number", value: field?.sort_order ?? 0, hint: "Lower numbers are listed first.", attrs: { step: 1 } }),
    isNew ? null : h("p", { class: "field-hint span-2" }, "Stored as ", h("code", {}, field.key), ". Renaming the label keeps existing values."),
  );

  let dialogRef = null;
  const { dialog, form } = formDialog({
    title: isNew ? "Add field" : "Edit field",
    content,
    submitLabel: isNew ? "Add field" : "Save changes",
    dangerAction: isNew ? null : h("button", { class: "btn btn-danger", type: "button", onclick: () => deleteField(field, dialogRef) }, "Delete field"),
    onSubmit: async (formEl, dlg) => {
      const type = formEl.elements.field_type.value;
      const payload = {
        label: formEl.elements.label.value,
        field_type: type,
        options: type === "select" ? formEl.elements.options.value.split("\n") : null,
        group_id: formEl.elements.group_id.value ? Number(formEl.elements.group_id.value) : null,
        required: formEl.elements.required.checked,
        show_in_table: formEl.elements.show_in_table.checked,
        sort_order: Number.parseInt(formEl.elements.sort_order.value, 10) || 0,
      };
      await api(isNew ? "/api/fields" : `/api/fields/${field.id}`, { method: isNew ? "POST" : "PUT", body: payload });
      dlg.close();
      await loadFields();
      toast(isNew ? "Field added" : "Changes saved");
      renderSidebar();
      renderMain();
    },
  });
  dialogRef = dialog;

  function syncType() {
    const type = form.elements.field_type.value;
    optionsField.hidden = type !== "select";
    requiredField.hidden = type === "checkbox";
  }
  form.elements.field_type.addEventListener("change", syncType);
  syncType();
}

async function deleteField(field, fieldDialog) {
  const ok = await confirmDialog({
    title: `Delete ${field.label}?`,
    body: h("p", {}, "The field is removed from every record, along with the values stored in it. This can't be undone."),
    confirmLabel: "Delete field",
    danger: true,
  });
  if (!ok) return;
  try {
    await api(`/api/fields/${field.id}`, { method: "DELETE" });
    fieldDialog?.close();
    await loadFields();
    toast("Field deleted");
    renderSidebar();
    renderMain();
  } catch (err) {
    toast(err.message, "error");
  }
}

// ---------------------------------------------------------------------------
// Users and passwords

function passwordPair(name, label) {
  return [
    inputField({ name, label, type: "password", required: true, hint: "At least 10 characters.", attrs: { autocomplete: "new-password", minlength: 10 } }),
    inputField({ name: `${name}_confirm`, label: "Type it again", type: "password", required: true, attrs: { autocomplete: "new-password" } }),
  ];
}

function checkPair(form, name) {
  if (form.elements[name].value !== form.elements[`${name}_confirm`].value) {
    throw new ApiError(422, { message: "The passwords don't match.", fields: { [`${name}_confirm`]: "This doesn't match the password above." } });
  }
}

function openAddUserDialog() {
  formDialog({
    title: "Add user",
    subtitle: "They can sign in straight away and change their own password.",
    content: h(
      "div",
      { class: "form-grid" },
      inputField({ name: "username", label: "Username", required: true, span: 2, hint: "Lowercase letters, numbers, dots, dashes or underscores.", attrs: { maxlength: 64, autocomplete: "off", autocapitalize: "none", spellcheck: "false" } }),
      passwordPair("password", "Password"),
    ),
    submitLabel: "Add user",
    onSubmit: async (form, dlg) => {
      checkPair(form, "password");
      await api("/api/users", { method: "POST", body: { username: form.elements.username.value, password: form.elements.password.value } });
      dlg.close();
      toast("User added");
      if (state.route.name === "users") await showRoute();
    },
  });
}

function openResetPasswordDialog(user) {
  formDialog({
    title: `Reset password for ${user.username}`,
    subtitle: "Their other signed-in sessions will end.",
    content: h("div", { class: "form-grid" }, passwordPair("password", "New password")),
    submitLabel: "Reset password",
    onSubmit: async (form, dlg) => {
      checkPair(form, "password");
      await api(`/api/users/${user.id}/password`, { method: "PUT", body: { password: form.elements.password.value } });
      dlg.close();
      toast("Password reset");
    },
  });
}

function openOwnPasswordDialog() {
  formDialog({
    title: "Change password",
    subtitle: "You'll stay signed in here. Other sessions will end.",
    content: h(
      "div",
      { class: "form-grid" },
      inputField({ name: "current_password", label: "Current password", type: "password", required: true, span: 2, attrs: { autocomplete: "current-password" } }),
      passwordPair("new_password", "New password"),
    ),
    submitLabel: "Change password",
    onSubmit: async (form, dlg) => {
      checkPair(form, "new_password");
      await api("/api/auth/password", {
        method: "POST",
        body: { current_password: form.elements.current_password.value, new_password: form.elements.new_password.value },
      });
      dlg.close();
      toast("Password changed");
    },
  });
}

async function deleteUser(user) {
  const ok = await confirmDialog({
    title: `Delete ${user.username}?`,
    body: h("p", {}, "They won't be able to sign in any more. Personnel records aren't affected."),
    confirmLabel: "Delete user",
    danger: true,
  });
  if (!ok) return;
  try {
    await api(`/api/users/${user.id}`, { method: "DELETE" });
    toast("User deleted");
    await showRoute();
  } catch (err) {
    toast(err.message, "error");
  }
}

// ---------------------------------------------------------------------------
// Start

document.addEventListener("click", (event) => {
  for (const menu of document.querySelectorAll("details.menu-wrap[open]")) {
    if (!menu.contains(event.target)) menu.open = false;
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    for (const menu of document.querySelectorAll("details.menu-wrap[open]")) menu.open = false;
  }
  const typing = event.target instanceof HTMLElement && event.target.closest("input, textarea, select, [contenteditable]");
  if (event.key === "/" && !typing && !event.ctrlKey && !event.metaKey && !event.altKey && !document.querySelector("dialog[open]") && refs.search?.isConnected) {
    event.preventDefault();
    refs.search.focus();
  }
});

window.addEventListener("hashchange", showRoute);

(async function start() {
  try {
    const [me, meta] = await Promise.all([api("/api/auth/me"), api("/api/meta"), loadGroups(), loadFields()]);
    state.me = me;
    state.meta = meta;
    renderAccount();
    await showRoute();
  } catch (err) {
    if (err.status !== 401) renderProblem(err);
  }
})();
