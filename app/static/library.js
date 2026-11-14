/* GetSetMix: the Library view (docs/design/library.md 4.5): the list, and
   the trash (delete with an Undo toast, Restore, Empty trash).
   Loaded after app.js and uses its helpers: api(), esc(), fmtDur(), toast(), T, STR. */
"use strict";

Object.assign(STR.en, {
  viewSwitch: "View", viewDownloads: "Downloads", viewLibrary: "Library",
  libSearchPh: "Search title, artist, album, genre or file",
  libCount: (n) => (n === 1 ? "1 track" : `${n.toLocaleString("en")} tracks`),
  libIndexing: (d, t) => `Indexing the library: ${d.toLocaleString("en")} of ${t.toLocaleString("en")} files`,
  libUnavailable: "The library folder can't be read right now: a drive may be unplugged or a network share may have dropped. Nothing is marked as removed until it is back.",
  libEmptyTitle: "No tracks in the library yet",
  libEmptyHint: "Audio files in the library folder show up here, and so does every download.",
  libNoMatch: "No track matches",
  libNoMatchHint: "Try fewer words, or another spelling.",
  libDamaged: "Read-only: this file could not be read as audio",
  libTrash: "Trash", libTrashN: (n) => (n ? `Trash · ${n.toLocaleString("en")}` : "Trash"),
  libEmptyTrash: "Empty trash",
  libTrashNote: (d) => (d > 0
    ? `Deleted tracks stay here for ${d} ${d === 1 ? "day" : "days"}, then they are removed for good.`
    : "Deleted tracks stay here until you empty the trash."),
  libTrashEmptyTitle: "The trash is empty",
  libTrashEmptyHint: "Tracks you delete wait here, so a wrong tap can always be undone.",
  libDelete: "Delete", libRestore: "Restore", libUndo: "Undo",
  libDeleted: (t) => `Deleted “${t}”`,
  libRestored: (t) => `Restored “${t}”`,
  libRestoreTaken: "Another file now has this track's name: move or rename it first.",
  libEmptyConfirm: (n) => (n === 1
    ? "Remove 1 track for good? This can't be undone."
    : `Remove ${n.toLocaleString("en")} tracks for good? This can't be undone.`),
  libEmptied: (n) => (n === 1 ? "1 track removed for good" : `${n.toLocaleString("en")} tracks removed for good`),
});
Object.assign(STR.it, {
  viewSwitch: "Vista", viewDownloads: "Download", viewLibrary: "Libreria",
  libSearchPh: "Cerca titolo, artista, album, genere o file",
  libCount: (n) => (n === 1 ? "1 brano" : `${n.toLocaleString("it")} brani`),
  libIndexing: (d, t) => `Indicizzazione della libreria: ${d.toLocaleString("it")} file su ${t.toLocaleString("it")}`,
  libUnavailable: "La cartella della libreria ora non è leggibile: forse un disco è scollegato o una condivisione di rete è caduta. Nulla viene segnato come rimosso finché non torna.",
  libEmptyTitle: "Ancora nessun brano nella libreria",
  libEmptyHint: "Qui compaiono i file audio della cartella della libreria, e ogni download.",
  libNoMatch: "Nessun brano corrisponde",
  libNoMatchHint: "Prova con meno parole, o un'altra grafia.",
  libDamaged: "Sola lettura: questo file non si legge come audio",
  libTrash: "Cestino", libTrashN: (n) => (n ? `Cestino · ${n.toLocaleString("it")}` : "Cestino"),
  libEmptyTrash: "Svuota il cestino",
  libTrashNote: (d) => (d > 0
    ? `I brani eliminati restano qui ${d} ${d === 1 ? "giorno" : "giorni"}, poi vengono cancellati per sempre.`
    : "I brani eliminati restano qui finché non svuoti il cestino."),
  libTrashEmptyTitle: "Il cestino è vuoto",
  libTrashEmptyHint: "I brani che elimini aspettano qui, così un tocco sbagliato si può sempre annullare.",
  libDelete: "Elimina", libRestore: "Ripristina", libUndo: "Annulla",
  libDeleted: (t) => `Eliminato “${t}”`,
  libRestored: (t) => `Ripristinato “${t}”`,
  libRestoreTaken: "Un altro file ora ha il nome di questo brano: spostalo o rinominalo prima.",
  libEmptyConfirm: (n) => (n === 1
    ? "Cancellare per sempre 1 brano? Non si può annullare."
    : `Cancellare per sempre ${n.toLocaleString("it")} brani? Non si può annullare.`),
  libEmptied: (n) => (n === 1 ? "1 brano cancellato per sempre" : `${n.toLocaleString("it")} brani cancellati per sempre`),
});

const Lib = {
  view: "downloads",
  q: "",
  items: [],
  next: null,
  total: 0,
  rev: null,
  loading: false,
  seq: 0,            // the newest request; older answers are dropped
  statusTimer: null,
  searchTimer: null,
  trash: false,      // showing the trash instead of the library
  trashCount: 0,
  trashDays: null,   // the setting, for the note above the trash
};

const libList = $("#libList");
const TRASH = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7h14M10 7V5h4v2M7 7l1 12h8l1-12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const NOTE = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 17.5V6l10-2v11.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><circle cx="6.5" cy="17.5" r="2.5" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="16.5" cy="15.5" r="2.5" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>';

function libName(path) {
  const base = path.slice(path.lastIndexOf("/") + 1);
  const dot = base.lastIndexOf(".");
  return dot > 0 ? base.slice(0, dot) : base;
}

// What a toast calls a track: its title, or its file name.
function libLabel(t) {
  return t && t.title.trim() ? t.title.trim() : libName(t ? t.path : "");
}

function libRowHtml(t) {
  const title = t.title.trim() ? esc(t.title) : `<span class="lib-file">${esc(libName(t.path))}</span>`;
  const act = Lib.trash
    ? `<button type="button" class="btn btn-quiet lib-act lib-restore" data-act="restore">${esc(T.libRestore)}</button>`
    : `<button type="button" class="icon-btn lib-act lib-del" data-act="delete" title="${esc(T.libDelete)}" aria-label="${esc(T.libDelete)}">${TRASH}</button>`;
  const damaged = t.audio_id.startsWith("f1_");
  return `<article class="lib-row" data-id="${t.id}"${damaged ? ` title="${esc(T.libDamaged)}"` : ""}>
    <div class="lib-art${t.has_cover ? " has-cover" : ""}">${NOTE}</div>
    <div class="lib-who">
      <span class="lib-title">${title}</span>
      <span class="lib-artist">${esc(t.artist)}</span>
    </div>
    <span class="lib-genre">${t.genre ? `<span class="lib-chip">${esc(t.genre)}</span>` : ""}</span>
    <span class="lib-dur">${fmtDur(t.duration)}</span>
    ${act}
  </article>`;
}

// Texts set from code, so they follow a language change on the next status tick.
function libTexts() {
  $(".view-switch").setAttribute("aria-label", T.viewSwitch);
  $("#libEmptyTitle").textContent = Lib.q ? T.libNoMatch : Lib.trash ? T.libTrashEmptyTitle : T.libEmptyTitle;
  $("#libEmptyHint").textContent = Lib.q ? T.libNoMatchHint : Lib.trash ? T.libTrashEmptyHint : T.libEmptyHint;
  $("#libCount").textContent = Lib.rev === null ? "" : T.libCount(Lib.total);
  $("#libTrashLabel").textContent = T.libTrashN(Lib.trashCount);
  const note = $("#libTrashNote");
  note.classList.toggle("hidden", !Lib.trash || Lib.trashDays === null);
  if (Lib.trashDays !== null) note.textContent = T.libTrashNote(Lib.trashDays);
  $("#libEmptyTrash").disabled = !Lib.trashCount;
}

function libRender() {
  libList.innerHTML = Lib.items.map(libRowHtml).join("");
  const empty = !Lib.items.length && !Lib.loading;
  $("#libEmpty").classList.toggle("hidden", !empty);
  $("#libHead").classList.toggle("hidden", !Lib.items.length);
  libTexts();
}

// The first page again (as many rows as are shown, so a reload keeps the place).
async function libLoad(keep = false) {
  const seq = ++Lib.seq;
  const limit = keep ? Math.min(500, Math.max(100, Lib.items.length)) : 100;
  const params = new URLSearchParams({ limit });
  if (Lib.q) params.set("q", Lib.q);
  if (Lib.trash) params.set("state", "trashed");
  Lib.loading = true;
  try {
    const page = await api(`/api/library?${params}`);
    if (seq !== Lib.seq) return;
    Object.assign(Lib, { items: page.items, next: page.next, total: page.total, rev: page.rev });
  } catch (e) {
    if (seq === Lib.seq) toast(e.message);
  } finally {
    if (seq === Lib.seq) { Lib.loading = false; libRender(); }
  }
}

async function libMore() {
  if (!Lib.next || Lib.loading) return;
  const seq = Lib.seq;
  const params = new URLSearchParams({ limit: 100, cursor: Lib.next });
  if (Lib.q) params.set("q", Lib.q);
  if (Lib.trash) params.set("state", "trashed");
  Lib.loading = true;
  try {
    const page = await api(`/api/library?${params}`);
    if (seq !== Lib.seq) return;
    Lib.items = Lib.items.concat(page.items);
    Lib.next = page.next;
    Lib.total = page.total;
    libList.insertAdjacentHTML("beforeend", page.items.map(libRowHtml).join(""));
    $("#libCount").textContent = T.libCount(Lib.total);
  } catch (e) {
    toast(e.message);
  } finally {
    if (seq === Lib.seq) Lib.loading = false;
  }
}

// The list is not polled: the status is, and the list reloads when `rev` moves.
async function libStatus() {
  clearTimeout(Lib.statusTimer);
  if (Lib.view !== "library") return;
  let running = false;
  try {
    const s = await api("/api/library/status");
    const ix = s.indexing || {};
    running = !!ix.running;
    Lib.trashCount = (s.counts || {}).trashed || 0;
    $("#libUnavailable").classList.toggle("hidden", !s.unavailable);
    const progress = $("#libProgress");
    progress.classList.toggle("hidden", !(running && ix.total));
    if (running && ix.total) {
      $("#libProgressText").textContent = T.libIndexing(ix.done, ix.total);
      $("#libProgressFill").style.width = `${((ix.done / ix.total) * 100).toFixed(1)}%`;
    }
    if (Lib.rev !== null && s.rev !== Lib.rev && !Lib.loading) libLoad(true);
    else libTexts();
  } catch { /* the next tick tries again */ }
  Lib.statusTimer = setTimeout(libStatus, running ? 1500 : 5000);
}

function setView(view) {
  Lib.view = view === "library" ? "library" : "downloads";
  document.body.classList.toggle("view-library", Lib.view === "library");
  document.querySelectorAll("[data-view]").forEach((b) =>
    b.setAttribute("aria-pressed", String(b.dataset.view === Lib.view)));
  if (Lib.view === "library") {
    history.replaceState({}, "", "#library");
    // Opening the view is a reason to look at the disk now (design 4.1).
    api("/api/library/rescan", { method: "POST" }).catch(() => { /* status shows it */ });
    libLoad(Lib.rev !== null).then(libStatus);
  } else {
    if (location.hash) history.replaceState({}, "", location.pathname + location.search);
    clearTimeout(Lib.statusTimer);
  }
}

document.querySelectorAll("[data-view]").forEach((b) =>
  b.addEventListener("click", () => setView(b.dataset.view)));

// ------------------------------------------------------------- the trash
// The trash is the same list over the trashed tracks, with Restore on each
// row and Empty trash in the bar (design 4.4, 4.5).
function setTrash(on) {
  Lib.trash = !!on;
  document.body.classList.toggle("lib-in-trash", Lib.trash);
  $("#libBack").classList.toggle("hidden", !Lib.trash);
  $("#libTrashBtn").classList.toggle("hidden", Lib.trash);
  $("#libEmptyTrash").classList.toggle("hidden", !Lib.trash);
  Lib.items = [];
  Lib.next = null;
  libRender();
  libLoad();
  if (Lib.trash) {
    api("/api/settings").then((s) => { Lib.trashDays = s.trash_days; libTexts(); }).catch(() => { /* no note */ });
  }
  window.scrollTo(0, 0);
}

// A toast with one action button, for Undo; it stays a little longer than a plain one.
function toastAction(msg, label, fn) {
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

function libDrop(id) {
  Lib.items = Lib.items.filter((i) => i.id !== id);
  Lib.total = Math.max(0, Lib.total - 1);
  const row = libList.querySelector(`.lib-row[data-id="${id}"]`);
  if (row) row.remove();
  $("#libEmpty").classList.toggle("hidden", Lib.items.length > 0);
  $("#libHead").classList.toggle("hidden", !Lib.items.length);
}

async function libDelete(id) {
  const t = Lib.items.find((i) => i.id === id);
  try {
    const res = await api(`/api/library/${id}`, { method: "DELETE" });
    Lib.rev = res.rev; // our own change: no reload needed for it
  } catch (e) {
    toast(e.message);
    return;
  }
  libDrop(id);
  Lib.trashCount += 1;
  libTexts();
  toastAction(T.libDeleted(libLabel(t)), T.libUndo, () => libRestore(id, t));
}

async function libRestore(id, t = Lib.items.find((i) => i.id === id)) {
  try {
    await api(`/api/library/${id}/restore`, { method: "POST" });
  } catch (e) {
    toast(e.status === 409 ? T.libRestoreTaken : e.message);
    return;
  }
  Lib.trashCount = Math.max(0, Lib.trashCount - 1);
  if (Lib.trash) libDrop(id);
  else libLoad(true); // an Undo: the track goes back in its place
  libTexts();
  toast(T.libRestored(libLabel(t)));
}

libList.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-act]");
  const row = btn && btn.closest(".lib-row");
  if (!row) return;
  const id = Number(row.dataset.id);
  btn.disabled = true; // one tap, one request
  if (btn.dataset.act === "delete") libDelete(id).finally(() => { btn.disabled = false; });
  else if (btn.dataset.act === "restore") libRestore(id).finally(() => { btn.disabled = false; });
});

$("#libTrashBtn").addEventListener("click", () => setTrash(true));
$("#libBack").addEventListener("click", () => setTrash(false));
$("#libEmptyTrash").addEventListener("click", async () => {
  if (!Lib.trashCount || !confirm(T.libEmptyConfirm(Lib.trashCount))) return;
  try {
    const res = await api("/api/library/trash", { method: "DELETE" });
    toast(T.libEmptied(res.purged));
  } catch (e) {
    toast(e.message);
  }
  Lib.trashCount = 0;
  libLoad();
  libStatus();
});

$("#libSearch").addEventListener("input", (e) => {
  clearTimeout(Lib.searchTimer);
  Lib.searchTimer = setTimeout(() => {
    Lib.q = e.target.value.trim();
    libLoad();
  }, 250);
});
$("#libSearchForm").addEventListener("submit", (e) => {
  e.preventDefault();
  $("#libSearch").blur(); // closes the phone keyboard; the list is already filtered
});

new IntersectionObserver((entries) => {
  if (entries.some((e) => e.isIntersecting) && Lib.view === "library") libMore();
}, { rootMargin: "600px 0px" }).observe($("#libMore"));

// The toast and the footer keep clear of whichever deck is showing.
const libDock = $("#libDock");
new ResizeObserver(() => {
  if (libDock.offsetHeight) document.documentElement.style.setProperty("--dock-h", `${libDock.offsetHeight}px`);
}).observe(libDock);

if (location.hash === "#library" && location.pathname !== "/share") setView("library");
