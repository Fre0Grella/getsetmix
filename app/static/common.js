/* Shared front-end plumbing: fetch + auth, escaping, toasts, theme, the
   server-side path picker, and check rendering. Loaded by both the main UI
   and the setup wizard so neither has its own copy. */
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);

// ------------------------------------------------------------------ fetch
function authHeaders() {
  const tok = localStorage.getItem("gsm_token");
  return tok ? { "X-Auth-Token": tok } : {};
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: { "Content-Type": "application/json", ...authHeaders(), ...(opts.headers || {}) },
  });
  if (res.status === 401) {
    const tok = prompt((window.T && T.tokenPrompt) || "Access token:");
    if (tok) { localStorage.setItem("gsm_token", tok); return api(path, opts); }
    throw new Error("unauthorized");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch { /* noop */ }
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

function toast(msg) {
  const el = $("#toast");
  if (!el) return;
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add("hidden"), 2600);
}

// ------------------------------------------------------------------ theme
// "auto" leaves the attribute off so prefers-color-scheme decides; an explicit
// choice stamps it so the toggle wins in both directions.
function applyTheme(theme) {
  const root = document.documentElement;
  if (theme === "dark" || theme === "light") root.dataset.theme = theme;
  else delete root.dataset.theme;
  const dark = theme === "dark" ||
    (theme !== "light" && matchMedia("(prefers-color-scheme: dark)").matches);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = dark ? "#0c111c" : "#f1f3f7";
}

// ------------------------------------------------------------ check lists
const CHECK_MARK = { ok: "✓", warn: "!", error: "✕" };

function checksHtml(checks) {
  if (!checks || !checks.length) return "";
  return checks.map((c) => `
    <div class="check is-${esc(c.level)}">
      <span class="mark">${CHECK_MARK[c.level] || "•"}</span>
      <div>
        <div class="title">${esc(c.title)}</div>
        ${c.detail ? `<div class="detail">${esc(c.detail)}</div>` : ""}
        ${c.fix ? `<div class="fix">${esc(c.fix)}</div>` : ""}
      </div>
    </div>`).join("");
}

// ------------------------------------------------------------ path picker
// Lists the *server's* filesystem — worth saying out loud in the UI, because a
// containerised server showing /app and /data is otherwise just confusing.
let picker = null; // { conf, cur }

function dirOf(p) {
  const i = Math.max(p.lastIndexOf("/"), p.lastIndexOf("\\"));
  return i > 0 ? p.slice(0, i) : "";
}
function baseOf(p) {
  const i = Math.max(p.lastIndexOf("/"), p.lastIndexOf("\\"));
  return i >= 0 ? p.slice(i + 1) : p;
}
function joinPath(dir, name) {
  const sep = dir.includes("\\") ? "\\" : "/";
  return dir.endsWith(sep) ? dir + name : dir + sep + name;
}

async function openPicker(conf) {
  picker = { conf, cur: "" };
  const val = $(conf.input).value.trim();
  $("#pickerNameRow").classList.toggle("hidden", conf.mode !== "file");
  $("#pickerName").value = conf.mode === "file" ? baseOf(val) : "";
  $("#pickerModal").classList.remove("hidden");
  await loadPicker(conf.mode === "file" ? dirOf(val) : val);
}

async function loadPicker(path) {
  let res;
  try {
    res = await api(`/api/fs/list?path=${encodeURIComponent(path)}&ext=${encodeURIComponent(picker.conf.ext || "")}`);
  } catch (e) {
    if (path) { loadPicker(""); return; } // unreachable path -> fall back to roots
    toast(e.message);
    return;
  }
  picker.cur = res.path;
  $("#pickerPath").textContent = res.path || "—";
  const rows = [];
  if (res.parent !== null) {
    rows.push(`<button type="button" class="picker-row up" data-nav="${esc(res.parent)}">⬆️ ..</button>`);
  }
  rows.push(...res.dirs.map((d) =>
    `<button type="button" class="picker-row dir" data-nav="${esc(d.path)}">📁 ${esc(d.name)}</button>`));
  if (picker.conf.mode === "file") {
    rows.push(...res.files.map((f) =>
      `<button type="button" class="picker-row file" data-file="${esc(f.name)}">📄 ${esc(f.name)}</button>`));
  }
  $("#pickerList").innerHTML = rows.join("") || "<small>—</small>";
}

function wirePicker(pickMap) {
  const list = $("#pickerList");
  if (!list) return;
  list.addEventListener("click", (e) => {
    const nav = e.target.closest("[data-nav]");
    if (nav) { loadPicker(nav.dataset.nav); return; }
    const file = e.target.closest("[data-file]");
    if (file) $("#pickerName").value = file.dataset.file;
  });
  $("#btnPickerSelect").addEventListener("click", () => {
    if (!picker) return;
    let value = picker.cur;
    if (picker.conf.mode === "file") {
      const name = $("#pickerName").value.trim();
      if (!name || !value) return;
      value = joinPath(value, name);
    }
    if (!value) return; // the drive list has no selectable path
    const input = $(picker.conf.input);
    input.value = value;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    $("#pickerModal").classList.add("hidden");
  });
  document.querySelectorAll("[data-pick]").forEach((btn) =>
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const conf = pickMap[btn.dataset.pick];
      if (conf) openPicker(conf);
    }));
}

function wireModals() {
  document.querySelectorAll(".modal").forEach((m) => {
    m.addEventListener("click", (e) => {
      if (e.target === m || e.target.closest("[data-close]")) m.classList.add("hidden");
    });
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") document.querySelectorAll(".modal").forEach((m) => m.classList.add("hidden"));
  });
}
