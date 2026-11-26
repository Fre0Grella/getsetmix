/* What every screen shares: the DOM shortcut, escaping and formatting,
   requests (the token and its prompt), the toast and the app's yes/no
   question, and the little state two screens read. */
import { serverError, T } from "./i18n.js";

export const $ = (sel) => document.querySelector(sel);

// Phones: rows are compact until tapped open. Matches the CSS breakpoint.
export const narrow = matchMedia("(max-width: 720px)");

// Rules the Library sheet applies as you type, from /api/library/rules; the
// server checks them again on save, so before they arrive nothing is refused.
export const libRules = { year: null, source: null };

// The one-tap genre picks: the server's, ranked by what the Downloads list
// uses (app.js writes them, the Library sheet reads them).
export const shared = { genrePicks: [] };

export function authHeaders() {
  const tok = localStorage.getItem("gsm_token");
  return tok ? { "X-Auth-Token": tok } : {};
}

// Every request goes through here: it adds the token and, on a 401, asks
// for it and tries again. One question at a time, shared by the requests
// that fail together (the covers of a screenful of rows); a dismissed
// question is not asked again until the page reloads, so polling never
// turns into a stream of prompts. The Response is the caller's, any status
// but 401; api() below is the JSON shortcut.
let tokenAsked = null;
export async function request(path, opts = {}) {
  const send = () => fetch(path, { ...opts, headers: { ...authHeaders(), ...(opts.headers || {}) } });
  const res = await send();
  if (res.status !== 401) return res;
  const asking = tokenAsked ??= Promise.resolve().then(() => {
    const tok = prompt(T.tokenPrompt);
    if (tok) localStorage.setItem("gsm_token", tok);
    return Boolean(tok);
  });
  if (!(await asking)) throw new Error("unauthorized");
  if (tokenAsked === asking) tokenAsked = null; // answered: a later 401 may ask again
  return send();
}

// The message of a failed response: the server's `detail`, else its status text.
export async function errorOf(res) {
  let detail = res.statusText;
  try { detail = (await res.json()).detail || detail; } catch { /* noop */ }
  detail = serverError(detail);
  const err = new Error(detail);
  err.status = res.status;
  return err;
}

export async function api(path, opts = {}) {
  const res = await request(path, {
    ...opts, headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
  });
  if (!res.ok) throw await errorOf(res);
  if (res.status === 204) return null;
  return res.json();
}

export function fmtDur(sec) {
  sec = Math.round(sec || 0);
  if (!sec) return "";
  const m = Math.floor(sec / 60), s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

export function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.remove("hidden", "toast--action");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add("hidden"), 2600);
}

// The app's own yes/no question (not the browser's confirm(), which looks
// foreign and can be turned off). Resolves true only on `yes`; Cancel, the
// A toast with one action (Undo); it shares toast()'s timer.
export function toastAction(msg, label, fn) {
  const el = $("#toast");
  el.innerHTML = `<span class="toast-msg">${esc(msg)}</span><button type="button" class="toast-act">${esc(label)}</button>`;
  el.classList.remove("hidden");
  el.classList.add("toast--action");
  clearTimeout(toast._t);
  el.querySelector(".toast-act").addEventListener("click", () => {
    clearTimeout(toast._t);
    el.classList.add("hidden");
    fn();
  }, { once: true });
  toast._t = setTimeout(() => el.classList.add("hidden"), 7000);
}

// backdrop and Escape all hide the modal, which answers false.
export function askConfirm(text, yes, no, { danger = false } = {}) {
  const modal = $("#confirmModal");
  const ok = $("#confirmYes");
  $("#confirmText").textContent = text;
  ok.textContent = yes;
  $("#confirmNo").textContent = no;
  ok.className = `btn ${danger ? "btn-danger" : "btn-primary"}`;
  modal.classList.remove("hidden");
  ok.focus();
  return new Promise((resolve) => {
    let answer = false;
    const onYes = () => { answer = true; modal.classList.add("hidden"); };
    const watch = new MutationObserver(() => {
      if (!modal.classList.contains("hidden")) return;
      watch.disconnect();
      ok.removeEventListener("click", onYes);
      resolve(answer);
    });
    ok.addEventListener("click", onYes);
    watch.observe(modal, { attributes: true, attributeFilter: ["class"] });
  });
}
