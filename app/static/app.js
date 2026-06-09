/* GetSetMix front-end */
"use strict";

const STR = {
  it: {
    paste: "Incolla link", download: "Scarica", cancel: "Annulla scaricamento",
    settings: "Impostazioni", save: "Salva", search: "Cerca",
    outputFormat: "Formato di uscita (globale)",
    concurrency: "Download paralleli (default globale)",
    template: "Template nome file", libraryRoot: "Cartella libreria",
    xmlPath: "Percorso XML Rekordbox", playlist: "Playlist di destinazione",
    language: "Lingua", coverTitle: "Copertina", uploadCover: "Carica immagine…",
    purgeCompleted: "Svuota elenco completati", purgeHistory: "Cancella cronologia URL",
    rekordboxHint: "Dopo l’ingestione, apri Rekordbox e ricarica la sorgente XML per vedere le nuove tracce nella playlist Inbox.",
    emptyHint: "Copia il link di una traccia o di una playlist, poi premi “Incolla link”.",
    fetching: u => `Reperimento info per ${u}`,
    queued: "In coda", processing: p => `Elaborazione ${p}%`,
    tagging: "Scrittura tag…", done: "Finito", retry: "Riprova", remove: "Rimuovi",
    downloading: "downloading…", titlePh: "Titolo (obbligatorio)",
    artistPh: "Artista (obbligatorio)", albumPh: "<vuoto>", genrePh: "<vuoto>",
    statsLine: (a, b, c) => `Ultimi 30 giorni: ${a} · Ultimi 365 giorni: ${b} · Totale: ${c}`,
    clipboardFail: "Impossibile leggere gli appunti — incolla il link qui:",
    notUrl: "Il testo copiato non è un URL valido",
    duplicate: "Nota: URL già scaricato in passato",
    batchOf: (d, t) => `${d} di ${t}`,
    needMeta: "Titolo e artista sono obbligatori",
    purged: n => `Eliminati ${n} elementi`, saved: "Impostazioni salvate",
    copyPath: "Percorso copiato", tokenPrompt: "Token di accesso:",
    coverSet: "Copertina aggiornata",
  },
  en: {
    paste: "Paste link", download: "Download", cancel: "Cancel download",
    settings: "Settings", save: "Save", search: "Search",
    outputFormat: "Output format (global)",
    concurrency: "Parallel downloads (global default)",
    template: "Filename template", libraryRoot: "Library folder",
    xmlPath: "Rekordbox XML path", playlist: "Target playlist",
    language: "Language", coverTitle: "Cover art", uploadCover: "Upload image…",
    purgeCompleted: "Clear completed list", purgeHistory: "Purge URL history",
    rekordboxHint: "After ingestion, open Rekordbox and reload the XML source to see new tracks in the Inbox playlist.",
    emptyHint: "Copy a track or playlist link, then press “Paste link”.",
    fetching: u => `Fetching info for ${u}`,
    queued: "Queued", processing: p => `Processing ${p}%`,
    tagging: "Writing tags…", done: "Done", retry: "Retry", remove: "Remove",
    downloading: "downloading…", titlePh: "Title (required)",
    artistPh: "Artist (required)", albumPh: "<empty>", genrePh: "<empty>",
    statsLine: (a, b, c) => `Last 30 days: ${a} · Last 365 days: ${b} · All time: ${c}`,
    clipboardFail: "Couldn't read the clipboard — paste the link here:",
    notUrl: "Clipboard text is not a valid URL",
    duplicate: "Note: this URL was downloaded before",
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

const $ = (sel) => document.querySelector(sel);
const list = $("#trackList");

let lang = "it";
let T = STR[lang];
let tracks = [];
let busy = false;
let batchTotal = 0;
let settingsCache = {};
let coverTrackId = null;
let pollTimer = null;
const dirtyFields = new Set(); // "id:field" being edited right now

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

// ------------------------------------------------------------------- i18n
function applyLang(next) {
  lang = STR[next] ? next : "it";
  T = STR[lang];
  document.documentElement.lang = lang;
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const v = T[el.dataset.i18n];
    if (typeof v === "string") el.textContent = v;
  });
  $("#btnPaste").title = T.paste;
  $("#btnSettings").title = T.settings;
  render();
}

// ------------------------------------------------------------------ icons
const I = {
  mic: '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M12 14a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2z"/></svg>',
  user: '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M12 12a4 4 0 1 0-4-4 4 4 0 0 0 4 4zm0 2c-3.3 0-8 1.7-8 5v2h16v-2c0-3.3-4.7-5-8-5z"/></svg>',
  note: '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M12 3v10.55A4 4 0 1 0 14 17V7h4V3h-6z"/></svg>',
  disc: '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm0 13a3 3 0 1 1 3-3 3 3 0 0 1-3 3z"/></svg>',
  dl: '<svg viewBox="0 0 24 24"><path d="M12 5v10m0 0l-4-4m4 4l4-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 19h12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
  x: '<svg viewBox="0 0 24 24"><path d="M7 7l10 10M17 7L7 17" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
  retry: '<svg viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" d="M20 11a8 8 0 1 0-2.34 6.06M20 5v6h-6"/></svg>',
  zoom: '<svg viewBox="0 0 24 24"><circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M15.5 15.5L21 21" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
  cam: '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M9 3l-1.5 2H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-3.5L15 3H9zm3 5.5A4.5 4.5 0 1 1 7.5 13 4.5 4.5 0 0 1 12 8.5zm0 2A2.5 2.5 0 1 0 14.5 13 2.5 2.5 0 0 0 12 10.5z"/></svg>',
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

function stateHtml(t) {
  switch (t.status) {
    case "queued":
      return `<div class="state"><span>${T.queued}</span></div>`;
    case "downloading":
      return `<div class="state"><span class="pct">${T.processing(Math.floor(t.progress || 0))}</span></div>`;
    case "tagging":
      return `<div class="state"><span>${T.tagging}</span></div>`;
    case "ingested":
      return `<div class="state is-done"><span>${T.done}</span>
        <button class="icon-btn" data-act="path" title="${esc(t.file_path)}">${I.zoom}</button></div>`;
    case "error":
      return `<div class="state is-error"><span class="err-text" title="${esc(t.error)}">${esc(t.error)}</span>
        <button class="icon-btn" data-act="retry" title="${T.retry}">${I.retry}</button>
        <button class="icon-btn" data-act="remove" title="${T.remove}">${I.x}</button></div>`;
    default: // staged / fetch_error
      return `<div class="state ${t.status === "fetch_error" ? "is-error" : ""}">
        ${t.status === "fetch_error" ? `<span class="err-text" title="${esc(t.error)}">${esc(t.error || T.needMeta)}</span>` : ""}
        <button class="icon-btn dl" data-act="download-one" title="${T.download}">${I.dl}</button>
        <button class="icon-btn" data-act="remove" title="${T.remove}">${I.x}</button></div>`;
  }
}

function rowHtml(t) {
  if (t.status === "fetching") {
    return `<article class="track is-fetching" data-id="${t.id}">
      <span class="dashes"><i></i><i></i><i></i></span>
      <span class="fetch-label">${T.fetching(esc(t.title || t.url))}</span>
    </article>`;
  }
  const editable = EDITABLE.has(t.status);
  const dis = editable ? "" : "disabled";
  const sel = t.status === "downloading" || t.status === "tagging" ? "is-selected" : "";
  const err = t.status === "error" || t.status === "fetch_error" ? "is-error" : "";
  const thumb = t.cover_path
    ? `/api/tracks/${t.id}/cover?v=${encodeURIComponent(t.updated_at || "")}`
    : (t.cover_url || t.thumbnail || "/static/assets/icon.png");
  return `<article class="track ${sel} ${err}" data-id="${t.id}">
    <div class="thumb">
      <img src="${esc(thumb)}" alt="" loading="lazy"
           onerror="this.src='/static/assets/icon.png'">
      ${t.duration ? `<span class="dur">${fmtDur(t.duration)}</span>` : ""}
      ${editable ? `<button class="cover-btn" data-act="cover" title="${T.coverTitle}">${I.cam}</button>` : ""}
    </div>
    <div class="meta">
      <div class="meta-line">${I.mic}
        <input class="f-title" data-field="title" value="${esc(t.title)}"
               placeholder="${T.titlePh}" ${dis}>
        ${!t.title && editable ? `<span class="req-flag">*</span>` : ""}
      </div>
      <div class="meta-line">${I.user}
        <input data-field="artist" value="${esc(t.artist)}"
               placeholder="${T.artistPh}" ${dis}>
        ${!t.artist && editable ? `<span class="req-flag">*</span>` : ""}
      </div>
    </div>
    <div class="side">
      <div class="meta-line">${I.disc}
        <input data-field="album" value="${esc(t.album)}" placeholder="${T.albumPh}" ${dis}>
      </div>
      <div class="meta-line">${I.note}
        <input class="f-genre" data-field="genre" list="genres"
               value="${esc(t.genre)}" placeholder="${T.genrePh}" ${dis}>
      </div>
    </div>
    ${stateHtml(t)}
    ${t.status === "downloading" ? `<div class="row-progress" style="width:${t.progress || 0}%"></div>` : ""}
  </article>`;
}

function render() {
  const focused = document.activeElement;
  const focusKey = focused && focused.dataset && focused.dataset.field
    ? `${focused.closest(".track")?.dataset.id}:${focused.dataset.field}` : null;
  const focusPos = focusKey ? focused.selectionStart : 0;

  list.innerHTML = tracks.map(rowHtml).join("");
  $("#emptyState").classList.toggle("hidden", tracks.length > 0);

  if (focusKey) {
    const [id, field] = focusKey.split(":");
    const el = list.querySelector(`.track[data-id="${id}"] input[data-field="${field}"]`);
    if (el) { el.focus(); try { el.setSelectionRange(focusPos, focusPos); } catch { /* noop */ } }
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

// ---------------------------------------------------------------- actions
function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add("hidden"), 2600);
}

async function pasteLink() {
  let text = "";
  try { text = (await navigator.clipboard.readText()).trim(); } catch { /* blocked */ }
  if (!text) text = (prompt(T.clipboardFail) || "").trim();
  if (!text) return;
  if (!/^https?:\/\//i.test(text)) { toast(T.notUrl); return; }
  try {
    const res = await api("/api/tracks", { method: "POST", body: JSON.stringify({ url: text }) });
    if (res.duplicate) toast(T.duplicate);
    schedulePoll(150);
  } catch (e) { toast(e.message); }
}

async function startBatch(ids = null) {
  const sel = $("#batchConcurrency").value;
  const body = { ids, concurrency: sel ? Number(sel) : null };
  try {
    const res = await api("/api/batch/start", { method: "POST", body: JSON.stringify(body) });
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

list.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-act]");
  if (!btn) return;
  const row = btn.closest(".track");
  const id = row?.dataset.id;
  const act = btn.dataset.act;
  try {
    if (act === "remove") {
      await api(`/api/tracks/${id}`, { method: "DELETE" });
      tracks = tracks.filter((t) => t.id !== id);
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
  settingsCache = await api("/api/settings");
  $("#setFormat").value = settingsCache.output_format;
  $("#setConcurrency").value = settingsCache.concurrency;
  $("#setTemplate").value = settingsCache.filename_template;
  $("#setLibrary").value = settingsCache.library_root;
  $("#setXml").value = settingsCache.xml_path;
  $("#setPlaylist").value = settingsCache.playlist_name;
  $("#setLanguage").value = settingsCache.language;
  $("#settingsModal").classList.remove("hidden");
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
        playlist_name: $("#setPlaylist").value,
        language: $("#setLanguage").value,
      }),
    });
    $("#settingsModal").classList.add("hidden");
    toast(T.saved);
    applyLang(data.language);
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

// --------------------------------------------------------------- wire up
document.querySelectorAll(".modal").forEach((m) => {
  m.addEventListener("click", (e) => {
    if (e.target === m || e.target.closest("[data-close]")) m.classList.add("hidden");
  });
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") document.querySelectorAll(".modal").forEach((m) => m.classList.add("hidden"));
});

$("#btnPaste").addEventListener("click", pasteLink);
$("#btnDownload").addEventListener("click", () => startBatch(null));
$("#btnCancel").addEventListener("click", async () => {
  await api("/api/batch/cancel", { method: "POST" });
  schedulePoll(150);
});
$("#btnSettings").addEventListener("click", openSettings);

const dl = $("#genres");
dl.innerHTML = GENRES.map((g) => `<option value="${g}">`).join("");

(async function init() {
  try {
    const s = await api("/api/settings");
    applyLang(s.language);
    $("#batchConcurrency").options[0].text = `×${s.concurrency}`;
  } catch { applyLang("it"); }
  poll();
  refreshStats();
})();
