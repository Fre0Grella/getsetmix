/* GetSetMix front-end */
"use strict";

const STR = {
  it: {
    paste: "Aggiungi", download: "Scarica", cancel: "Ferma",
    urlPh: "Incolla il link di una traccia o playlist",
    settings: "Impostazioni", save: "Salva", close: "Chiudi", search: "Cerca",
    secDownloads: "Download", secLibrary: "Libreria e Rekordbox",
    secInterface: "Interfaccia", secMaintenance: "Manutenzione",
    outputFormat: "Formato", concurrency: "Download paralleli",
    template: "Nome file", libraryRoot: "Cartella libreria",
    xmlPath: "XML inbox", playlist: "Playlist",
    collectionXml: "Export della collezione (opzionale)",
    collectionHint: "Con l'export della collezione impostato, i brani che hai già vengono segnati come duplicati e tolti dall'inbox.",
    rekordboxHint: "In Rekordbox imposta Preferenze › Avanzate › rekordbox xml su questo file, poi aggiorna l'albero xml dopo ogni batch.",
    browse: "Sfoglia", select: "Seleziona", fileName: "Nome file",
    pickerTitle: "Scegli un percorso",
    language: "Lingua", coverTitle: "Copertina", uploadCover: "Carica un'immagine",
    cleanInbox: "Pulisci inbox ora",
    cleanedInbox: n => `Rimossi ${n} brani già in collezione`,
    needCollectionXml: "Imposta prima l'export della collezione",
    purgeCompleted: "Togli le righe finite", purgeHistory: "Dimentica i link",
    colTrack: "Traccia", colAlbum: "Album", colGenre: "Genere", colTime: "Durata", colStatus: "Stato",
    emptyTitle: "La cassa è ancora vuota",
    emptyHint: "Incolla qui sotto un link di YouTube o SoundCloud. Una playlist diventa una riga per traccia.",
    footSource: "Codice sorgente",
    footDocs: "Guida",
    footMadeBy: "Fatto con ❤️ da FreoGrella",
    footDonate: "☕ Dona",
    shareHint: "Su Android, installa GetSetMix e condividi i link direttamente da YouTube o SoundCloud.",
    pasteAnywhere: "funziona ovunque nella pagina",
    theme: "Tema", themeSystem: "Auto", themeLight: "Chiaro", themeDark: "Scuro",
    themeHint: "Vale solo per questo dispositivo.", doneEdit: "Fatto",
    fetching: u => `Lettura di ${u}`,
    ready: "Pronto", queued: "In coda", processing: p => `${p}%`,
    tagging: "Scrittura tag", done: "Nella libreria", retry: "Riprova", remove: "Rimuovi",
    downloadOne: "Scarica questa", showPath: "Copia il percorso", changeCover: "Cambia copertina",
    downloading: "Download in corso", titlePh: "Titolo (obbligatorio)",
    artistPh: "Artista (obbligatorio)", albumPh: "Aggiungi album", genrePh: "Aggiungi genere",
    statsLine: (a, b, c) => `${a} negli ultimi 30 giorni · ${b} nell'anno · ${c} in totale`,
    notUrl: "Questo non sembra un link",
    duplicate: "Questo link è già stato scaricato",
    dupBadge: "Già presente?",
    dupConfirm: n => `${n} brano/i sembra già nella tua libreria. Scaricarli comunque?\n\n(OK = scarica comunque · Annulla = salta i duplicati)`,
    batchOf: (d, t) => `${d} di ${t}`,
    needMeta: "Servono titolo e artista",
    purged: n => `Eliminati ${n} elementi`, saved: "Impostazioni salvate",
    copyPath: "Percorso copiato", tokenPrompt: "Token di accesso:",
    coverSet: "Copertina aggiornata",
  },
  en: {
    paste: "Add", download: "Download", cancel: "Stop",
    urlPh: "Paste a track or playlist link",
    settings: "Settings", save: "Save", close: "Close", search: "Search",
    secDownloads: "Downloads", secLibrary: "Library and Rekordbox",
    secInterface: "Interface", secMaintenance: "Housekeeping",
    outputFormat: "Format", concurrency: "Parallel downloads",
    template: "File name", libraryRoot: "Library folder",
    xmlPath: "Inbox XML", playlist: "Playlist",
    collectionXml: "Collection export (optional)",
    collectionHint: "With your exported collection set, tracks you already own are flagged as duplicates and dropped from the inbox.",
    rekordboxHint: "In Rekordbox, point Preferences › Advanced › rekordbox xml at this file, then refresh the xml tree after each batch.",
    browse: "Browse", select: "Select", fileName: "File name",
    pickerTitle: "Choose a path",
    language: "Language", coverTitle: "Cover art", uploadCover: "Upload an image",
    cleanInbox: "Clean inbox now",
    cleanedInbox: n => `Removed ${n} tracks already in your collection`,
    needCollectionXml: "Set the collection export first",
    purgeCompleted: "Clear finished rows", purgeHistory: "Forget link history",
    colTrack: "Track", colAlbum: "Album", colGenre: "Genre", colTime: "Time", colStatus: "Status",
    emptyTitle: "Nothing in the crate yet",
    emptyHint: "Paste a YouTube or SoundCloud link below. A playlist becomes one row per track.",
    footSource: "Source code",
    footDocs: "Docs",
    footMadeBy: "Made with ❤️ by FreoGrella",
    footDonate: "☕ Donate",
    shareHint: "On Android, install GetSetMix and share links to it straight from YouTube or SoundCloud.",
    pasteAnywhere: "works anywhere on this page",
    theme: "Theme", themeSystem: "Auto", themeLight: "Light", themeDark: "Dark",
    themeHint: "Applies to this device only.", doneEdit: "Done",
    fetching: u => `Reading ${u}`,
    ready: "Ready", queued: "Queued", processing: p => `${p}%`,
    tagging: "Writing tags", done: "In your library", retry: "Retry", remove: "Remove",
    downloadOne: "Download this one", showPath: "Copy file path", changeCover: "Change cover",
    downloading: "Downloading", titlePh: "Title (required)",
    artistPh: "Artist (required)", albumPh: "Add album", genrePh: "Add genre",
    statsLine: (a, b, c) => `${a} in the last 30 days · ${b} this year · ${c} all time`,
    notUrl: "That doesn't look like a link",
    duplicate: "This link was downloaded before",
    dupBadge: "Already owned?",
    dupConfirm: n => `${n} track(s) look like they're already in your library. Download them anyway?\n\n(OK = download anyway · Cancel = skip the duplicates)`,
    batchOf: (d, t) => `${d} of ${t}`,
    needMeta: "Title and artist are required",
    purged: n => `Removed ${n} items`, saved: "Settings saved",
    copyPath: "Path copied", tokenPrompt: "Access token:",
    coverSet: "Cover updated",
  },
};

const GENRES = [
  "Afro House", "Amapiano", "Bass House", "Big Room", "Breakbeat", "Dance",
  "Deep House", "Disco", "Drum & Bass", "Dubstep", "EDM", "Electro", "Funk",
  "Future House", "Garage", "Hard Rock", "Hard Techno", "Hardcore", "Hardstyle",
  "Heavy Metal", "Hip-Hop", "House", "Indie Dance", "Italo Disco", "Jungle",
  "Latin", "Mainstage", "Melodic House & Techno", "Minimal", "Moombahton",
  "Pop", "Progressive House", "Psytrance", "R&B", "Reggaeton", "Rock",
  "Tech House", "Techno", "Trance", "Trap", "Tropical House", "UK Garage",
];

// Quick picks under an open row's genre field, after the ones this list already uses.
const GENRE_PICKS = ["House", "Tech House", "Techno", "Afro House", "Melodic House & Techno", "Drum & Bass"];

const $ = (sel) => document.querySelector(sel);
const list = $("#trackList");
// Phones: rows are compact until tapped open. Matches the CSS breakpoint.
const narrow = matchMedia("(max-width: 720px)");

let lang = "en";
let T = STR[lang];
let tracks = [];
let busy = false;
let batchTotal = 0;
let settingsCache = {};
let coverTrackId = null;
let pollTimer = null;
let highlightId = null; // newly added (e.g. shared) track to scroll to + flash
let openId = null; // the row expanded for editing on a phone
let genrePicks = GENRE_PICKS;
const dirtyFields = new Set(); // "id:field" being edited right now
const rowCache = new Map(); // id -> last-rendered row HTML, to skip untouched DOM

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
    const tok = prompt(T.tokenPrompt);
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

// ------------------------------------------------------------------ theme
// Per device, not a server setting: the phone can be dark while the desktop
// follows the system. The inline script in <head> applies it before paint.
const THEME_KEY = "gsm_theme";
const THEME_BAR = { light: "#fdfdff", dark: "#14161b" }; // --surface, for the status bar
const darkScheme = matchMedia("(prefers-color-scheme: dark)");
let themePref = "system";
try { themePref = localStorage.getItem(THEME_KEY) || "system"; } catch { /* storage blocked */ }

function applyTheme(pref) {
  themePref = pref === "light" || pref === "dark" ? pref : "system";
  const root = document.documentElement;
  if (themePref === "system") delete root.dataset.theme;
  else root.dataset.theme = themePref;
  const shown = themePref === "system" ? (darkScheme.matches ? "dark" : "light") : themePref;
  $('meta[name="theme-color"]').content = THEME_BAR[shown];
  document.querySelectorAll('input[name="theme"]').forEach((r) => { r.checked = r.value === themePref; });
}

function setTheme(pref) {
  try {
    if (pref === "system") localStorage.removeItem(THEME_KEY);
    else localStorage.setItem(THEME_KEY, pref);
  } catch { /* still applies for this visit */ }
  applyTheme(pref);
}

darkScheme.addEventListener("change", () => applyTheme(themePref));
document.querySelectorAll('input[name="theme"]').forEach((r) =>
  r.addEventListener("change", () => setTheme(r.value)));
applyTheme(themePref);

$("#footYear").textContent = new Date().getFullYear();

// ------------------------------------------------------------------- i18n
function applyLang(next) {
  lang = STR[next] ? next : "en";
  T = STR[lang];
  document.documentElement.lang = lang;
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const v = T[el.dataset.i18n];
    if (typeof v === "string") el.textContent = v;
  });
  document.querySelectorAll("[data-i18n-ph]").forEach((el) => {
    el.placeholder = T[el.dataset.i18nPh];
  });
  $("#btnSettings").title = T.settings;
  $("#btnSettings").setAttribute("aria-label", T.settings);
  rowCache.clear(); // rows embed translated labels
  render();
}

// ------------------------------------------------------------------ icons
const I = {
  dl: '<svg viewBox="0 0 24 24"><path d="M12 5v10m0 0l-4-4m4 4l4-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 19h12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
  x: '<svg viewBox="0 0 24 24"><path d="M7 7l10 10M17 7L7 17" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
  retry: '<svg viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" d="M20 11a8 8 0 1 0-2.34 6.06M20 5v6h-6"/></svg>',
  folder: '<svg viewBox="0 0 24 24"><path d="M4 7a2 2 0 0 1 2-2h3.5l2 2H18a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>',
  up: '<svg viewBox="0 0 24 24"><path d="M12 19V5m0 0l-6 6m6-6l6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  file: '<svg viewBox="0 0 24 24"><path d="M7 3h7l4 4v14H7z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>',
  cam: '<svg viewBox="0 0 24 24"><path d="M4 8.5A1.5 1.5 0 0 1 5.5 7h2l1.5-2h6l1.5 2h2A1.5 1.5 0 0 1 20 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17.5z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><circle cx="12" cy="13" r="3.2" fill="none" stroke="currentColor" stroke-width="2"/></svg>',
  check: '<svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
};

// ----------------------------------------------------------------- render
function fmtDur(sec) {
  sec = Math.round(sec || 0);
  if (!sec) return "";
  const m = Math.floor(sec / 60), s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

const EDITABLE = new Set(["staged", "fetch_error", "error"]);

// yt-dlp prefixes everything with "ERROR:"; the cell is narrow, the tooltip has it all.
const shortError = (e) => String(e || "").replace(/^ERROR:\s*/i, "");

// One status cell per state: a dot + label, then the actions that apply.
function stateHtml(t) {
  const act = (name, icon, label, cls = "") =>
    `<button class="icon-btn ${cls}" data-act="${name}" title="${label}" aria-label="${label}">${icon}</button>`;
  // An open row (phones) also gets a Done button that folds it back up.
  const done = t.id === openId
    ? `<button class="btn btn-quiet act-done" data-act="collapse">${I.check}<span>${T.doneEdit}</span></button>` : "";
  const cell = (cls, label, acts = "", title = "") =>
    `<div class="state ${cls}"><span class="state-label"${title ? ` title="${esc(title)}"` : ""}>${label}</span>
      <span class="row-acts">${acts}</span>${done}</div>`;
  switch (t.status) {
    case "queued":
      return cell("st-wait", T.queued);
    case "downloading":
      return cell("st-active", T.processing(Math.floor(t.progress || 0)));
    case "tagging":
      return cell("st-active", T.tagging);
    case "ingested":
      return cell("st-done", T.done, act("path", I.folder, T.showPath), t.file_path);
    case "error":
      return cell("st-error", esc(shortError(t.error)), act("retry", I.retry, T.retry, "go") + act("remove", I.x, T.remove), t.error);
    case "fetch_error":
      return cell("st-error", esc(shortError(t.error) || T.needMeta),
        act("download-one", I.dl, T.downloadOne, "go") + act("remove", I.x, T.remove), t.error);
    default: // staged
      return cell("st-ready", T.ready, act("download-one", I.dl, T.downloadOne, "go") + act("remove", I.x, T.remove));
  }
}

function rowHtml(t) {
  if (t.status === "fetching") {
    return `<article class="track is-fetching" data-id="${t.id}">
      <div class="skeleton"></div>
      <span class="fetch-label">${T.fetching(esc(t.title || t.url))}</span>
    </article>`;
  }
  const editable = EDITABLE.has(t.status);
  const dis = editable ? "" : "disabled";
  const open = t.id === openId;
  const sel = [
    t.status === "downloading" || t.status === "tagging" ? "is-selected" : "",
    open ? "is-open" : "",
  ].join(" ").trim();
  const chips = open && editable
    ? `<div class="genre-chips">${genrePicks.map((g) =>
        `<button type="button" class="chip" data-act="genre" data-genre="${esc(g)}" aria-pressed="${g === t.genre}">${esc(g)}</button>`
      ).join("")}</div>`
    : "";
  const dup = t.duplicate && t.status === "staged";
  const thumb = t.cover_path
    ? `/api/tracks/${t.id}/cover?v=${encodeURIComponent(t.updated_at || "")}`
    : (t.cover_url || t.thumbnail || "");
  const field = (name, cls, ph, extra = "") =>
    `<input class="f ${cls}${editable && !t[name] && (name === "title" || name === "artist") ? " missing" : ""}"
       data-field="${name}" value="${esc(t[name])}" placeholder="${ph}" aria-label="${ph}" ${extra} ${dis}>`;
  return `<article class="track ${sel}" data-id="${t.id}">
    <div class="thumb">
      ${thumb ? `<img src="${esc(thumb)}" alt="" loading="lazy" onerror="this.remove()">` : ""}
      ${editable ? `<button class="cover-btn" data-act="cover" title="${T.changeCover}" aria-label="${T.changeCover}">${I.cam}</button>` : ""}
    </div>
    <div class="who">
      ${field("title", "f-title", T.titlePh)}
      <div class="who-sub">
        ${field("artist", "f-artist", T.artistPh)}
        ${dup ? `<span class="dup" title="${esc(t.duplicate_reason)}">${T.dupBadge}</span>` : ""}
      </div>
    </div>
    <div class="c-album" data-label="${T.colAlbum}">${field("album", "f-album", T.albumPh)}</div>
    <div class="c-genre" data-label="${T.colGenre}">${field("genre", "f-genre", T.genrePh, 'list="genres"')}</div>
    <span class="dur">${fmtDur(t.duration)}</span>
    ${chips}
    ${stateHtml(t)}
    ${t.status === "downloading" ? `<div class="row-progress" style="width:${t.progress || 0}%"></div>` : ""}
  </article>`;
}

function nodeFromHtml(html) {
  const tpl = document.createElement("template");
  tpl.innerHTML = html;
  return tpl.content.firstElementChild;
}

function render() {
  const focused = document.activeElement;
  const focusField = focused && focused.dataset && focused.dataset.field ? focused.dataset.field : null;
  const focusId = focusField ? focused.closest(".track")?.dataset.id : null;
  const focusPos = focusField ? focused.selectionStart : 0;

  // Genres this list already uses come first, most used first.
  const used = new Map();
  for (const t of tracks) if (t.genre) used.set(t.genre, (used.get(t.genre) || 0) + 1);
  const top = [...used].sort((a, b) => b[1] - a[1]).map(([g]) => g);
  genrePicks = [...new Set([...top, ...GENRE_PICKS])].slice(0, 8);

  // Reconcile rows keyed by id instead of rebuilding the whole list every poll.
  // Wholesale innerHTML replacement tore down (and repainted) even the input the
  // user was editing — the genre field flickered teal->white each cycle. Reusing
  // untouched nodes, and never replacing the row currently being edited, kills it.
  const byId = new Map();
  for (const node of list.children) byId.set(node.dataset.id, node);

  let cursor = list.firstElementChild;
  for (const t of tracks) {
    const html = rowHtml(t);
    const existing = byId.get(t.id);
    let node;
    if (existing) {
      byId.delete(t.id);
      // Reuse the node unless its HTML actually changed. Never rebuild the row
      // being edited: its typed values are already in the DOM, and replacing it
      // would blur the field and re-blink the datalist popup.
      if (t.id !== focusId && rowCache.get(t.id) !== html) {
        node = nodeFromHtml(html);
        rowCache.set(t.id, html);
      } else {
        node = existing;
      }
    } else {
      node = nodeFromHtml(html);
      rowCache.set(t.id, html);
    }
    if (cursor === existing) {
      if (node !== existing) cursor.replaceWith(node); // swap in place, keep order
      cursor = node.nextElementSibling;
    } else {
      list.insertBefore(node, cursor); // new (or reordered) node goes before cursor
    }
  }
  for (const [id, node] of byId) { rowCache.delete(id); node.remove(); }

  $("#emptyState").classList.toggle("hidden", tracks.length > 0);
  $("#listHead").classList.toggle("hidden", tracks.length === 0);

  // Safety net: if a replace/insert stole focus, restore it. Guard against
  // re-focusing the already-focused input — focus() itself re-triggers the datalist.
  if (focusId && focusField) {
    const el = list.querySelector(`.track[data-id="${focusId}"] input[data-field="${focusField}"]`);
    if (el && document.activeElement !== el) {
      el.focus();
      try { el.setSelectionRange(focusPos, focusPos); } catch { /* noop */ }
    }
  }

  if (highlightId) {
    const row = list.querySelector(`.track[data-id="${highlightId}"]`);
    if (row) {
      row.scrollIntoView({ behavior: "smooth", block: "center" });
      row.classList.add("track--new");
      row.addEventListener("animationend", () => row.classList.remove("track--new"), { once: true });
      highlightId = null; // one-shot once the row exists
    }
  }

  // toolbar
  const staged = tracks.filter((t) => t.status === "staged").length;
  const badge = $("#stagedCount");
  badge.textContent = staged;
  badge.classList.toggle("hidden", staged === 0);
  $("#btnDownload").disabled = staged === 0 && !busy;
  $("#btnCancel").classList.toggle("hidden", !busy);
  $("#topStatus").textContent = busy ? T.downloading : "";

  // batch bar
  const active = tracks.filter((t) => ["queued", "downloading", "tagging"].includes(t.status));
  if (busy || active.length) {
    if (!batchTotal) batchTotal = active.length;
    batchTotal = Math.max(batchTotal, active.length);
    const finishedInBatch = batchTotal - active.length;
    let pct = batchTotal ? (finishedInBatch / batchTotal) * 100 : 0;
    const cur = active.find((t) => t.status === "downloading");
    if (cur && batchTotal) pct += (cur.progress || 0) / batchTotal;
    $("#batchBar").classList.remove("hidden");
    $("#batchFill").style.width = `${Math.min(100, pct).toFixed(1)}%`;
    $("#batchLabel").textContent = T.batchOf(Math.min(finishedInBatch + 1, batchTotal), batchTotal);
  } else {
    batchTotal = 0;
    $("#batchBar").classList.add("hidden");
  }
}

// ---------------------------------------------------------------- polling
async function poll() {
  try {
    const data = await api("/api/tracks");
    busy = data.busy;
    const editingIds = new Set([...dirtyFields].map((k) => k.split(":")[0]));
    // keep user-typed values: skip refresh of rows being edited
    tracks = data.tracks.map((nt) => {
      if (editingIds.has(nt.id)) {
        const old = tracks.find((o) => o.id === nt.id);
        if (old) return { ...nt, title: old.title, artist: old.artist, album: old.album, genre: old.genre };
      }
      return nt;
    });
    render();
    $("#healthDot").classList.remove("bad");
  } catch {
    $("#healthDot").classList.add("bad");
  }
  const fetching = tracks.some((t) => t.status === "fetching");
  schedulePoll(busy || fetching ? 1200 : 4000);
}

function schedulePoll(ms) {
  clearTimeout(pollTimer);
  pollTimer = setTimeout(poll, ms);
}

async function refreshStats() {
  try {
    const s = await api("/api/stats");
    $("#statsText").textContent = T.statsLine(s.songs_30d, s.songs_365d, s.songs_all_time);
  } catch { /* noop */ }
  setTimeout(refreshStats, 15000);
}

// Download-engine health: YouTube 403s without a JS runtime, so say it up front.
async function refreshEngine() {
  try {
    const { ytdlp } = await api("/api/status");
    const problems = ytdlp.problems || [];
    const banner = $("#engineBanner");
    banner.textContent = problems.join(" ");
    banner.classList.toggle("hidden", !problems.length);
    $("#healthDot").classList.toggle("bad", problems.length > 0);
    $("#healthDot").title = problems.length ? problems.join("\n") : "healthy";
  } catch { /* noop */ }
}

// ---------------------------------------------------------------- actions
function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add("hidden"), 2600);
}

async function addUrl(url) {
  if (!/^https?:\/\//i.test(url)) { toast(T.notUrl); return null; }
  try {
    const res = await api("/api/tracks", { method: "POST", body: JSON.stringify({ url }) });
    if (res.duplicate) toast(T.duplicate);
    if (res.ids && res.ids.length) highlightId = res.ids[0];
    schedulePoll(150);
    return res;
  } catch (e) { toast(e.message); return null; }
}

// The link field takes typed or pasted links; an empty field falls back to
// the clipboard so the button still works as a one-tap "paste".
async function addFromField() {
  const input = $("#urlInput");
  let text = input.value.trim();
  if (!text) {
    try { text = (await navigator.clipboard.readText()).trim(); } catch { /* blocked */ }
  }
  if (!text) { input.focus(); return; }
  // "youtu.be/abc" typed by hand: assume https rather than reject it.
  if (!/^https?:\/\//i.test(text) && /^[\w-]+(\.[\w-]+)+\/\S*$/.test(text)) text = `https://${text}`;
  if (await addUrl(text)) input.value = "";
}

const firstUrl = (text) => (text.match(/https?:\/\/\S+/i) || [])[0];

// Web Share Target landing (/share?…). Android share sheets from YouTube /
// SoundCloud drop the link inside the text/title field rather than a bare url,
// so pull the first http(s) URL out of whatever we were handed.
async function consumeShare() {
  if (location.pathname !== "/share") return;
  const p = new URLSearchParams(location.search);
  const blob = [p.get("url"), p.get("text"), p.get("title")].filter(Boolean).join(" ");
  const match = blob.match(/https?:\/\/\S+/i);
  history.replaceState({}, "", "/"); // strip params so a reload won't re-add
  if (match) await addUrl(match[0]);
}

async function startBatch(ids = null, force = false) {
  const sel = $("#batchConcurrency").value;
  const body = { ids, concurrency: sel ? Number(sel) : null, force };
  try {
    const res = await api("/api/batch/start", { method: "POST", body: JSON.stringify(body) });
    if (res.needs_confirm) {
      const list = res.duplicates
        .map((d) => `• ${d.artist ? d.artist + " – " : ""}${d.title}`).join("\n");
      if (confirm(`${T.dupConfirm(res.duplicates.length)}\n\n${list}`)) {
        return startBatch(ids, true);                       // download anyway
      }
      const dupIds = new Set(res.duplicates.map((d) => d.id));
      const base = ids || tracks.filter((t) => t.status === "staged").map((t) => t.id);
      const rest = base.filter((id) => !dupIds.has(id));     // skip the duplicates
      if (rest.length) return startBatch(rest, true);
      return;
    }
    batchTotal = res.count;
    schedulePoll(150);
  } catch (e) { toast(e.message); }
}

async function commitField(input) {
  const row = input.closest(".track");
  if (!row) return;
  const id = row.dataset.id;
  const field = input.dataset.field;
  dirtyFields.delete(`${id}:${field}`);
  const local = tracks.find((t) => t.id === id);
  if (local) local[field] = input.value;
  try {
    await api(`/api/tracks/${id}`, {
      method: "PATCH", body: JSON.stringify({ [field]: input.value }),
    });
    schedulePoll(200);
  } catch (e) { toast(e.message); }
}

list.addEventListener("input", (e) => {
  const input = e.target.closest("input[data-field]");
  if (!input) return;
  const id = input.closest(".track")?.dataset.id;
  dirtyFields.add(`${id}:${input.dataset.field}`);
  const local = tracks.find((t) => t.id === id);
  if (local) local[input.dataset.field] = input.value;
});
list.addEventListener("focusout", (e) => {
  const input = e.target.closest("input[data-field]");
  if (input) commitField(input);
});
list.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && e.target.matches("input[data-field]")) e.target.blur();
});

// Phones: a tap anywhere on a compact row opens it for editing.
function openRow(id) {
  openId = id;
  render();
  const row = list.querySelector(`.track[data-id="${id}"]`);
  if (row) requestAnimationFrame(() => row.scrollIntoView({ behavior: "smooth", block: "nearest" }));
}

list.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-act]");
  if (!btn) {
    const row = e.target.closest(".track");
    if (row && narrow.matches && row.dataset.id !== openId && !row.classList.contains("is-fetching")) {
      openRow(row.dataset.id);
    }
    return;
  }
  const row = btn.closest(".track");
  const id = row?.dataset.id;
  const act = btn.dataset.act;
  try {
    if (act === "collapse") {
      openId = null;
      render();
    } else if (act === "genre") {
      const input = row.querySelector('input[data-field="genre"]');
      input.value = input.value === btn.dataset.genre ? "" : btn.dataset.genre; // tap again to clear
      await commitField(input);
      render();
    } else if (act === "remove") {
      await api(`/api/tracks/${id}`, { method: "DELETE" });
      tracks = tracks.filter((t) => t.id !== id);
      if (openId === id) openId = null;
      render();
    } else if (act === "retry") {
      await api(`/api/tracks/${id}/retry`, { method: "POST" });
      schedulePoll(150);
    } else if (act === "download-one") {
      await startBatch([id]);
    } else if (act === "path") {
      const t = tracks.find((x) => x.id === id);
      if (t?.file_path) {
        try { await navigator.clipboard.writeText(t.file_path); toast(T.copyPath); }
        catch { prompt("", t.file_path); }
      }
    } else if (act === "cover") {
      openCoverModal(id);
    }
  } catch (err) { toast(err.message); }
});

// ------------------------------------------------------------- cover modal
function openCoverModal(id) {
  coverTrackId = id;
  const t = tracks.find((x) => x.id === id);
  $("#coverQuery").value = [t?.artist, t?.title].filter(Boolean).join(" ");
  $("#coverResults").innerHTML = "";
  $("#coverModal").classList.remove("hidden");
  if ($("#coverQuery").value) doCoverSearch();
}

async function doCoverSearch() {
  const q = $("#coverQuery").value.trim();
  if (!q) return;
  $("#coverResults").innerHTML = '<span class="dashes"><i></i><i></i><i></i></span>';
  try {
    const res = await api(`/api/cover-search?q=${encodeURIComponent(q)}`);
    $("#coverResults").innerHTML = res.results.map((r) =>
      `<button data-full="${esc(r.full)}" title="${esc(r.label)}"><img src="${esc(r.thumb)}" alt=""></button>`
    ).join("") || `<small>—</small>`;
  } catch (e) { $("#coverResults").innerHTML = `<small>${esc(e.message)}</small>`; }
}

$("#btnCoverSearch").addEventListener("click", doCoverSearch);
$("#coverQuery").addEventListener("keydown", (e) => { if (e.key === "Enter") doCoverSearch(); });

$("#coverResults").addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-full]");
  if (!btn || !coverTrackId) return;
  try {
    await api(`/api/tracks/${coverTrackId}`, {
      method: "PATCH", body: JSON.stringify({ cover_url: btn.dataset.full }),
    });
    $("#coverModal").classList.add("hidden");
    toast(T.coverSet);
    schedulePoll(150);
  } catch (err) { toast(err.message); }
});

$("#coverFile").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file || !coverTrackId) return;
  const fd = new FormData();
  fd.append("file", file);
  try {
    const res = await fetch(`/api/tracks/${coverTrackId}/cover`, {
      method: "POST", body: fd, headers: authHeaders(),
    });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    $("#coverModal").classList.add("hidden");
    toast(T.coverSet);
    schedulePoll(150);
  } catch (err) { toast(err.message); }
  e.target.value = "";
});

// --------------------------------------------------------- settings modal
async function openSettings() {
  // Open first, fill in when the values arrive: a slow fetch must not make
  // the panel pop up after the user has already pressed Escape.
  const panel = $("#settingsModal");
  const save = $("#btnSaveSettings");
  // Server settings can't be edited or saved until the current values are in.
  // The theme is local to this device, so it works straight away.
  const gated = panel.querySelectorAll("[data-server]");
  const gate = (on) => gated.forEach((el) => { el.inert = on; });
  save.disabled = true;
  gate(true);
  applyTheme(themePref);
  panel.classList.remove("hidden");
  try { settingsCache = await api("/api/settings"); } catch (e) { toast(e.message); return; }
  if (panel.classList.contains("hidden")) return;
  $("#setFormat").value = settingsCache.output_format;
  $("#setConcurrency").value = settingsCache.concurrency;
  $("#setTemplate").value = settingsCache.filename_template;
  $("#setLibrary").value = settingsCache.library_root;
  $("#setXml").value = settingsCache.xml_path;
  $("#setCollection").value = settingsCache.collection_xml_path || "";
  $("#setPlaylist").value = settingsCache.playlist_name;
  $("#setLanguage").value = settingsCache.language;
  save.disabled = false;
  gate(false);
}

$("#btnSaveSettings").addEventListener("click", async () => {
  try {
    const data = await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify({
        output_format: $("#setFormat").value,
        concurrency: Number($("#setConcurrency").value) || 2,
        filename_template: $("#setTemplate").value,
        library_root: $("#setLibrary").value,
        xml_path: $("#setXml").value,
        collection_xml_path: $("#setCollection").value.trim(),
        playlist_name: $("#setPlaylist").value,
        language: $("#setLanguage").value,
      }),
    });
    $("#settingsModal").classList.add("hidden");
    toast(T.saved);
    applyLang(data.language);
  } catch (e) { toast(e.message); }
});

$("#btnCleanInbox").addEventListener("click", async () => {
  const coll = $("#setCollection")?.value.trim();
  if (!coll) { toast(T.needCollectionXml); return; }
  try {
    const res = await api("/api/purge", { method: "POST", body: JSON.stringify({ scope: "inbox" }) });
    toast(T.cleanedInbox(res.purged));
  } catch (e) { toast(e.message); }
});
$("#btnPurgeCompleted").addEventListener("click", async () => {
  const res = await api("/api/purge", { method: "POST", body: JSON.stringify({ scope: "completed" }) });
  toast(T.purged(res.purged));
  schedulePoll(100);
});
$("#btnPurgeHistory").addEventListener("click", async () => {
  const res = await api("/api/purge", { method: "POST", body: JSON.stringify({ scope: "history" }) });
  toast(T.purged(res.purged));
});

// ------------------------------------------------------------ path picker
const PICK = {
  library:    { input: "#setLibrary",    mode: "dir",  ext: "" },
  xml:        { input: "#setXml",        mode: "file", ext: ".xml" },
  collection: { input: "#setCollection", mode: "file", ext: ".xml" },
};
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

async function openPicker(kind) {
  const conf = PICK[kind];
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
    res = await api(`/api/fs/list?path=${encodeURIComponent(path)}&ext=${encodeURIComponent(picker.conf.ext)}`);
  } catch (e) {
    if (path) { loadPicker(""); return; } // unreachable path -> fall back to roots
    toast(e.message);
    return;
  }
  picker.cur = res.path;
  $("#pickerPath").textContent = res.path || "—";
  const rows = [];
  if (res.parent !== null) {
    rows.push(`<button type="button" class="picker-row up" data-nav="${esc(res.parent)}">${I.up} ..</button>`);
  }
  rows.push(...res.dirs.map((d) =>
    `<button type="button" class="picker-row dir" data-nav="${esc(d.path)}">${I.folder} ${esc(d.name)}</button>`));
  if (picker.conf.mode === "file") {
    rows.push(...res.files.map((f) =>
      `<button type="button" class="picker-row file" data-file="${esc(f.name)}">${I.file} ${esc(f.name)}</button>`));
  }
  $("#pickerList").innerHTML = rows.join("") || "<small>—</small>";
}

$("#pickerList").addEventListener("click", (e) => {
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
  if (!value) return; // drive list has no selectable path
  $(picker.conf.input).value = value;
  $("#pickerModal").classList.add("hidden");
});

document.querySelectorAll("[data-pick]").forEach((btn) =>
  btn.addEventListener("click", (e) => { e.preventDefault(); openPicker(btn.dataset.pick); }));

// --------------------------------------------------------------- wire up
document.querySelectorAll(".modal").forEach((m) => {
  m.addEventListener("click", (e) => {
    if (e.target === m || e.target.closest("[data-close]")) m.classList.add("hidden");
  });
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") document.querySelectorAll(".modal").forEach((m) => m.classList.add("hidden"));
});

$("#addForm").addEventListener("submit", (e) => { e.preventDefault(); addFromField(); });
// Pasting a link into the field adds it straight away.
$("#urlInput").addEventListener("paste", (e) => {
  const url = firstUrl(e.clipboardData?.getData("text") || "");
  if (url) { e.preventDefault(); addUrl(url); }
});
// ...and so does pasting anywhere that isn't a text field.
document.addEventListener("paste", (e) => {
  if (e.target.closest("input, textarea, [contenteditable]")) return;
  const url = firstUrl(e.clipboardData?.getData("text") || "");
  if (url) { e.preventDefault(); addUrl(url); }
});
$("#btnDownload").addEventListener("click", () => startBatch(null));
$("#btnCancel").addEventListener("click", async () => {
  await api("/api/batch/cancel", { method: "POST" });
  schedulePoll(150);
});
$("#btnSettings").addEventListener("click", openSettings);

const dl = $("#genres");
dl.innerHTML = GENRES.map((g) => `<option value="${g}">`).join("");

// The list and the toast keep clear of the deck, whatever its height (batch
// bar, safe area). Ignore 0: the deck hides while a row field has the keyboard.
const dock = $(".dock");
new ResizeObserver(() => {
  if (dock.offsetHeight) document.documentElement.style.setProperty("--dock-h", `${dock.offsetHeight}px`);
}).observe(dock);

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => { /* PWA install optional */ });
}

(async function init() {
  try {
    const s = await api("/api/settings");
    applyLang(s.language);
    $("#batchConcurrency").options[0].text = `×${s.concurrency}`;
  } catch { applyLang("en"); }
  poll();
  refreshStats();
  refreshEngine();
  consumeShare();
})();
