/* GetSetMix: the Library view (read-only list, docs/design/library.md 4.5).
   Loaded after app.js and uses its helpers: api(), esc(), fmtDur(), T, STR. */
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
};

const libList = $("#libList");
const NOTE = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 17.5V6l10-2v11.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><circle cx="6.5" cy="17.5" r="2.5" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="16.5" cy="15.5" r="2.5" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>';

function libName(path) {
  const base = path.slice(path.lastIndexOf("/") + 1);
  const dot = base.lastIndexOf(".");
  return dot > 0 ? base.slice(0, dot) : base;
}

function libRowHtml(t) {
  const title = t.title.trim() ? esc(t.title) : `<span class="lib-file">${esc(libName(t.path))}</span>`;
  const damaged = t.audio_id.startsWith("f1_");
  return `<article class="lib-row" data-id="${t.id}"${damaged ? ` title="${esc(T.libDamaged)}"` : ""}>
    <div class="lib-art${t.has_cover ? " has-cover" : ""}">${NOTE}</div>
    <div class="lib-who">
      <span class="lib-title">${title}</span>
      <span class="lib-artist">${esc(t.artist)}</span>
    </div>
    <span class="lib-genre">${t.genre ? `<span class="lib-chip">${esc(t.genre)}</span>` : ""}</span>
    <span class="lib-dur">${fmtDur(t.duration)}</span>
  </article>`;
}

// Texts set from code, so they follow a language change on the next status tick.
function libTexts() {
  $(".view-switch").setAttribute("aria-label", T.viewSwitch);
  $("#libEmptyTitle").textContent = Lib.q ? T.libNoMatch : T.libEmptyTitle;
  $("#libEmptyHint").textContent = Lib.q ? T.libNoMatchHint : T.libEmptyHint;
  $("#libCount").textContent = Lib.rev === null ? "" : T.libCount(Lib.total);
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
