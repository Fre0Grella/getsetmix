/* GetSetMix: the Library view (docs/design/library.md 4.5): a virtualised
   list with covers, genre and folder filters and sorts, the detail sheet that
   edits one track (tags, cover, a preview player), and the trash (delete with
   an Undo toast, Restore, Empty trash), and the selection with its bulk bar
   (Delete, Restore, Set genre). Loaded by app.js, which opens a
   track's sheet from the Downloads screen through openSheet(). */
import {
  $, api, askConfirm, esc, fmtDur, libRules, narrow, request, shared, toast,
  toastAction,
} from "./core.js";
import { openCoverModal } from "./cover.js";
import { lang, num, plural, serverError, STR, T } from "./i18n.js";

Object.assign(STR.en, {
  viewSwitch: "View", viewDownloads: "Downloads", viewLibrary: "Library",
  libSearchPh: "Search title, artist, album, genre or file",
  libCount: (n) => plural(n, "1 track", "{n} tracks"),
  libIndexing: (d, t) => `Indexing the library: ${num(d)} of ${num(t)} files`,
  libUnavailable: "The library folder can't be read right now: a drive may be unplugged or a network share may have dropped. Nothing is marked as removed until it is back.",
  libEmptyTitle: "No tracks in the library yet",
  libEmptyHint: "Audio files in the library folder show up here, and so does every download.",
  libNoMatch: "No track matches",
  libNoMatchHint: "Try fewer words, or another spelling.",
  libDamaged: "Read-only: this file could not be read as audio",
  libDamagedShort: "Damaged", libRo: "Read-only",
  libDup: "Same audio",
  libDupTitle: (n) => plural(n, "Same audio as 1 other file in the library", "Same audio as {n} other files in the library"),
  libSameAs: "Same audio as",
  libSort: "Sort", libSortAdded: "Added", libSortArtist: "Artist", libSortTitle: "Title", libSortGenre: "Genre",
  libReverse: "Reverse the order",
  libGenres: "Genres", libFolderLabel: "Folder", libAllFolders: "All folders",
  libCoverAlt: "Cover", libNoCover: "No cover",
  libAddCover: "Add a cover",
  libCoverSaved: "Cover saved to the file",
  libNoPlay: "This browser can't play this file. The track itself is fine.",
  libTrash: "Trash", libTrashN: (n) => (n ? `Trash · ${num(n)}` : "Trash"),
  libEmptyTrash: "Empty trash",
  libTrashNote: (d) => (d > 0
    ? `Deleted tracks stay here for ${plural(d, "1 day", "{n} days")}, then they are removed for good.`
    : "Deleted tracks stay here until you empty the trash."),
  libTrashEmptyTitle: "The trash is empty",
  libTrashEmptyHint: "Tracks you delete wait here, so a wrong tap can always be undone.",
  libDelete: "Delete", libRestore: "Restore", libUndo: "Undo", cancel: "Cancel",
  libDeleteAsk: (t) => `Move “${t}” to the trash?`,
  libRestoreAsk: (t) => `Put “${t}” back in the library?`,
  libEmptyYes: "Remove for good",
  libDeleted: (t) => `Deleted “${t}”`,
  libRestored: (t) => `Restored “${t}”`,
  libRestoreTaken: "Another file now has this track's name: move or rename it first.",
  libEmptyConfirm: (n) => plural(n, "Remove 1 track for good? This can't be undone.",
    "Remove {n} tracks for good? This can't be undone."),
  libEmptied: (n) => plural(n, "1 track removed for good", "{n} tracks removed for good"),
  libTitle: "Title", libArtist: "Artist", 
  libYear: "Year", libComment: "Comment",
  libReadOnlyFormat: (f) => `Read-only: GetSetMix can't write ${f.toUpperCase()} tags yet. MP3 and FLAC files can be edited.`,
  libMulti: "Holds several values in the file. Saving writes the one value shown here.",
  libSource: "Source",
  libAsk: "This comment holds the link the track was downloaded from, the only record of its source inside the file. Replace it?",
  libAskKeep: "Keep the link", libAskReplace: "Replace it",
  libSaved: "Saved to the file",
  libNoChange: "Nothing changed",
  libBadYear: (lo, hi) => `The year needs four digits, from ${lo} to ${hi}`,
  libChanged: "The file changed meanwhile. The sheet now shows what it holds; check and save again.",
  libInUse: "Another program has this file open, maybe a deck in Rekordbox. Unload it and try again.",
  libSelBar: "Selected tracks", libSelClear: "Clear the selection",
  libSelWord: (n) => plural(n, "selected", "selected"),
  libSelect: "Select", libSelPick: "Pick tracks", libSelectAll: "Select all",
  libSelectAllN: (n) => `Select all ${num(n)}`, libAllSelected: (n) => plural(n, "1 selected", `All ${num(n)} selected`),
  libFilters: "Filters", libArtistPh: "Artist", libProblems: "Problems: any",
  libProblem: { no_genre: "No genre", no_year: "No year", no_cover: "No cover",
    lowercase: "All lowercase", feat: "“feat.” in the artist", promo: "Promo text in the title",
    same_audio: "Same audio" },
  libBulkDeleteAsk: (n) => plural(n, "Move 1 track to the trash?", "Move {n} tracks to the trash?"),
  libBulkDeleted: (n) => plural(n, "Deleted 1 track", "Deleted {n} tracks"),
  libBulkRestored: (n) => plural(n, "Restored 1 track", "Restored {n} tracks"),
  libBulkFailed: (n, why) => plural(n, "1 track was not changed: ", "{n} tracks were not changed: ") + why,
});
Object.assign(STR.it, {
  viewSwitch: "Vista", viewDownloads: "Download", viewLibrary: "Libreria",
  libSearchPh: "Cerca titolo, artista, album, genere o file",
  libCount: (n) => plural(n, "1 brano", "{n} brani"),
  libIndexing: (d, t) => `Indicizzazione della libreria: ${num(d)} file su ${num(t)}`,
  libUnavailable: "La cartella della libreria ora non è leggibile: forse un disco è scollegato o una condivisione di rete è caduta. Nulla viene segnato come rimosso finché non torna.",
  libEmptyTitle: "Ancora nessun brano nella libreria",
  libEmptyHint: "Qui compaiono i file audio della cartella della libreria, e ogni download.",
  libNoMatch: "Nessun brano corrisponde",
  libNoMatchHint: "Prova con meno parole, o un'altra grafia.",
  libDamaged: "Sola lettura: questo file non si legge come audio",
  libDamagedShort: "Danneggiato", libRo: "Sola lettura",
  libDup: "Stesso audio",
  libDupTitle: (n) => plural(n, "Stesso audio di un altro file della libreria", "Stesso audio di altri {n} file della libreria"),
  libSameAs: "Stesso audio di",
  libSort: "Ordina", libSortAdded: "Aggiunti", libSortArtist: "Artista", libSortTitle: "Titolo", libSortGenre: "Genere",
  libReverse: "Inverti l'ordine",
  libGenres: "Generi", libFolderLabel: "Cartella", libAllFolders: "Tutte le cartelle",
  libCoverAlt: "Copertina", libNoCover: "Nessuna copertina",
  libAddCover: "Aggiungi una copertina",
  libCoverSaved: "Copertina salvata nel file",
  libNoPlay: "Questo browser non riesce a riprodurre il file. Il brano in sé è a posto.",
  libTrash: "Cestino", libTrashN: (n) => (n ? `Cestino · ${num(n)}` : "Cestino"),
  libEmptyTrash: "Svuota il cestino",
  libTrashNote: (d) => (d > 0
    ? `I brani eliminati restano qui ${plural(d, "1 giorno", "{n} giorni")}, poi vengono cancellati per sempre.`
    : "I brani eliminati restano qui finché non svuoti il cestino."),
  libTrashEmptyTitle: "Il cestino è vuoto",
  libTrashEmptyHint: "I brani che elimini aspettano qui, così un tocco sbagliato si può sempre annullare.",
  libDelete: "Elimina", libRestore: "Ripristina", libUndo: "Annulla", cancel: "Annulla",
  libDeleteAsk: (t) => `Spostare “${t}” nel cestino?`,
  libRestoreAsk: (t) => `Rimettere “${t}” nella libreria?`,
  libEmptyYes: "Cancella per sempre",
  libDeleted: (t) => `Eliminato “${t}”`,
  libRestored: (t) => `Ripristinato “${t}”`,
  libRestoreTaken: "Un altro file ora ha il nome di questo brano: spostalo o rinominalo prima.",
  libEmptyConfirm: (n) => plural(n, "Cancellare per sempre 1 brano? Non si può annullare.",
    "Cancellare per sempre {n} brani? Non si può annullare."),
  libEmptied: (n) => plural(n, "1 brano cancellato per sempre", "{n} brani cancellati per sempre"),
  libTitle: "Titolo", libArtist: "Artista", 
  libYear: "Anno", libComment: "Commento",
  libReadOnlyFormat: (f) => `Sola lettura: GetSetMix non sa ancora scrivere i tag ${f.toUpperCase()}. I file MP3 e FLAC si possono modificare.`,
  libMulti: "Nel file ha più valori. Salvando si scrive solo il valore mostrato qui.",
  libSource: "Fonte",
  libAsk: "Questo commento contiene il link da cui il brano è stato scaricato, l'unica traccia della sua fonte dentro il file. Sostituirlo?",
  libAskKeep: "Tieni il link", libAskReplace: "Sostituisci",
  libSaved: "Salvato nel file",
  libNoChange: "Nessuna modifica",
  libBadYear: (lo, hi) => `L'anno deve avere quattro cifre, da ${lo} a ${hi}`,
  libChanged: "Nel frattempo il file è cambiato. Ora la scheda mostra cosa contiene: controlla e salva di nuovo.",
  libInUse: "Un altro programma ha aperto questo file, forse un deck di Rekordbox. Scaricalo dal deck e riprova.",
  libSelBar: "Brani selezionati", libSelClear: "Annulla la selezione",
  libSelWord: (n) => plural(n, "selezionato", "selezionati"),
  libSelect: "Seleziona", libSelPick: "Scegli i brani", libSelectAll: "Seleziona tutti",
  libSelectAllN: (n) => `Seleziona tutti (${num(n)})`, libAllSelected: (n) => plural(n, "1 selezionato", `Tutti i ${num(n)} selezionati`),
  libFilters: "Filtri", libArtistPh: "Artista", libProblems: "Problemi: tutti",
  libProblem: { no_genre: "Senza genere", no_year: "Senza anno", no_cover: "Senza copertina",
    lowercase: "Tutto minuscolo", feat: "“feat.” nell'artista", promo: "Testo promozionale nel titolo",
    same_audio: "Stesso audio" },
  libBulkDeleteAsk: (n) => plural(n, "Spostare 1 brano nel cestino?", "Spostare {n} brani nel cestino?"),
  libBulkDeleted: (n) => plural(n, "Eliminato 1 brano", "Eliminati {n} brani"),
  libBulkRestored: (n) => plural(n, "Ripristinato 1 brano", "Ripristinati {n} brani"),
  libBulkFailed: (n, why) => plural(n, "1 brano non è stato modificato: ", "{n} brani non sono stati modificati: ") + why,
});

const PAGE = 200;          // rows per request (design 4.5)
const LONG_PRESS = 500;    // ms a finger rests on a row to start a selection
const MARGIN = 8;          // rows kept in the page above and below what is visible
const COVER_PX = 96;       // the size a row's cover is kept at (2x the largest row cover)

const Lib = {
  view: "downloads",
  q: "", genre: "", folder: "", artist: "", problem: "", sort: "added", order: null,
  rows: [],          // the list by position; rows past `rows.length` are not loaded yet
  next: null,        // the cursor of the next page
  started: false,    // the first page of this query has arrived
  total: 0,
  rev: null,
  seq: 0,            // the newest query or reload; older answers are dropped
  filling: 0,        // the seq of the loop that is fetching pages
  fillTo: 0,
  failed: false,
  reloading: false,
  win: [0, -1],      // first and last position in the page
  facets: null,
  statusTimer: null,
  searchTimer: null,
  trash: false,      // showing the trash instead of the library
  trashCount: 0,
  trashDays: null,   // the setting, for the note above the trash
  lang: null,
};

// The tracks picked for the bulk bar, by id; `anchor` is the position a
// Shift-click extends from.
const Sel = { mode: false, all: false, ids: new Set(), anchor: null, press: null, pressTimer: null,
  longPressed: false };

const libList = $("#libList");
const shown = new Map();   // position -> the row element in the page
const NS = 'viewBox="0 0 24 24" aria-hidden="true"';
const TRASH = `<svg ${NS}><use href="#i-trash"/></svg>`; // the sprite in index.html
const NOTE = `<svg ${NS}><path d="M9 17.5V6l10-2v11.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><circle cx="6.5" cy="17.5" r="2.5" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="16.5" cy="15.5" r="2.5" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>`;
const LOCK = `<svg ${NS}><rect x="5" y="11" width="14" height="9" rx="2" fill="none" stroke="currentColor" stroke-width="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3" fill="none" stroke="currentColor" stroke-width="2"/></svg>`;
const DUP = `<svg ${NS}><rect x="8" y="8" width="11" height="11" rx="2" fill="none" stroke="currentColor" stroke-width="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" fill="none" stroke="currentColor" stroke-width="2"/></svg>`;

const rowH = () => (narrow.matches ? 64 : 52);   // fixed, in step with library.css

function libName(path) {
  const base = path.slice(path.lastIndexOf("/") + 1);
  const dot = base.lastIndexOf(".");
  return dot > 0 ? base.slice(0, dot) : base;
}

// What a toast calls a track: its title, or its file name.
function libLabel(t) {
  return t && t.title.trim() ? t.title.trim() : libName(t ? t.path : "");
}


// A small marker for a row that shares its audio with another file, and one
// that says why a row is read-only (design 4.5).
function libFlags(t) {
  let html = "";
  if (t.same_audio.length) {
    const why = T.libDupTitle(t.same_audio.length);
    html += `<span class="lib-flag lib-flag--dup" role="img" title="${esc(why)}" aria-label="${esc(why)}">${DUP}<span class="lib-flag-text">${esc(T.libDup)}</span></span>`;
  }
  if (!t.editable) {
    const why = t.damaged ? T.libDamaged : T.libReadOnlyFormat(t.format);
    const what = t.damaged ? T.libDamagedShort : t.format.toUpperCase();
    html += `<span class="lib-flag lib-flag--ro" role="img" title="${esc(why)}" aria-label="${esc(why)}">${LOCK}<span class="lib-flag-text"><span class="lib-flag-long">${esc(T.libRo)} · </span>${esc(what)}</span></span>`;
  }
  return html;
}

const coverKey = (t) => (t.has_cover ? `${t.id}:${t.content_rev}` : "");

function libRowHtml(t, i) {
  const title = t.title.trim() ? esc(t.title) : `<span class="lib-file">${esc(libName(t.path))}</span>`;
  const act = Lib.trash
    ? `<button type="button" class="btn btn-quiet lib-act lib-restore" data-act="restore">${esc(T.libRestore)}</button>`
    : `<button type="button" class="icon-btn lib-act lib-del" data-act="delete" title="${esc(T.libDelete)}" aria-label="${esc(T.libDelete)}">${TRASH}</button>`;
  const key = coverKey(t);
  return `<article class="lib-row${Sel.all || Sel.ids.has(t.id) ? " is-selected" : ""}" role="listitem" aria-setsize="${Lib.total}" aria-posinset="${i + 1}" data-i="${i}" data-id="${t.id}" tabindex="0">
    <div class="lib-art${key ? " has-cover" : ""}"${key ? ` data-cover="${key}"` : ""}>${NOTE}<span class="lib-check" aria-hidden="true"></span></div>
    <div class="lib-who">
      <span class="lib-title">${title}</span>
      <span class="lib-sub"><span class="lib-artist">${esc(t.artist)}</span>${libFlags(t)}</span>
    </div>
    <span class="lib-genre">${t.genre ? `<span class="lib-chip badge">${esc(t.genre)}</span>` : ""}</span>
    <span class="lib-dur">${fmtDur(t.duration)}</span>
    ${act}
  </article>`;
}

// A row whose page has not arrived yet.
const SKELETON = (i) => `<article class="lib-row lib-skel" role="listitem" aria-hidden="true" data-i="${i}"><div class="lib-art"></div><div class="lib-who"><span class="lib-bar-a"></span><span class="lib-bar-b"></span></div></article>`;

// ------------------------------------------------- the virtualised list
// The list is as tall as all its rows, so the scroll bar is true, but only the
// rows in or near the screen exist in the page: each is placed by its position
// (rows have one fixed height). Pages of 200 come from the API as the list is
// scrolled; the cursor only goes forward, so a jump far down fetches the pages
// in between, in a row.
const listRows = () => (Lib.started ? Lib.total : 12);

function libSize() {
  const h = rowH();
  libList.style.setProperty("--row-h", `${h}px`);
  libList.style.height = `${listRows() * h}px`;
}

function libMake(i) {
  const t = Lib.rows[i];
  const tpl = document.createElement("template");
  tpl.innerHTML = t ? libRowHtml(t, i) : SKELETON(i);
  const el = tpl.content.firstElementChild;
  el.style.transform = `translateY(${i * rowH()}px)`;
  return el;
}

function libPaint() {
  if (Lib.view !== "library") return;
  const h = rowH();
  libSize();
  const n = listRows();
  const into = -libList.getBoundingClientRect().top;      // px of the list above the screen
  const first = Math.max(0, Math.floor(into / h) - MARGIN);
  const last = Math.min(n - 1, Math.ceil((into + innerHeight) / h) + MARGIN);
  Lib.win = [first, last];
  for (const [i, el] of shown) {
    const stale = el.classList.contains("lib-skel") && Lib.rows[i];
    if (((i < first || i > last) && el !== document.activeElement) || stale) {
      el.remove();
      shown.delete(i);
    }
  }
  const fresh = [];
  for (let i = first; i <= last; i += 1) {
    if (shown.has(i)) continue;
    const el = libMake(i);
    shown.set(i, el);
    fresh.push(el);
  }
  if (fresh.length) {
    libList.append(...fresh);
    fresh.forEach((el) => {
      const art = el.querySelector(".lib-art[data-cover]");
      if (art) coverPaint(art);
    });
  }
  if (Lib.started && last >= Lib.rows.length - 1 && Lib.next) libFill(last + 1 + PAGE / 2);
}

let paintQueued = false;
function libSchedule() {
  if (paintQueued) return;
  paintQueued = true;
  requestAnimationFrame(() => { paintQueued = false; libPaint(); });
}
function libClear() {
  shown.forEach((el) => el.remove());
  shown.clear();
}
function libRepaint() { libClear(); libPaint(); libTexts(); }

addEventListener("scroll", () => { if (Lib.view === "library") libSchedule(); }, { passive: true });
addEventListener("resize", () => {
  if (Lib.view !== "library") return;
  libClear();        // the row height may have changed with the width
  libSchedule();
});

function libQuery(extra = {}) {
  const p = new URLSearchParams({ sort: Lib.sort, ...extra });
  if (Lib.order) p.set("order", Lib.order);
  if (Lib.q) p.set("q", Lib.q);
  if (Lib.genre) p.set("genre", Lib.genre);
  if (Lib.folder) p.set("folder", Lib.folder);
  if (Lib.artist) p.set("artist", Lib.artist);
  if (Lib.problem) p.set("problem", Lib.problem);
  if (Lib.trash) p.set("state", "trashed");
  return p;
}

// Fetch pages until `upto` rows are loaded (or the list ends). One loop at a
// time; a new query or reload bumps `seq` and the old loop stops at its next answer.
async function libFill(upto) {
  if (Lib.failed || Lib.reloading) return;
  Lib.fillTo = Math.max(Lib.fillTo, upto);
  const seq = Lib.seq;
  if (Lib.filling === seq) return;
  Lib.filling = seq;
  try {
    while (seq === Lib.seq && (!Lib.started || (Lib.next && Lib.rows.length < Lib.fillTo))) {
      const page = await api(`/api/library?${libQuery({ limit: PAGE, ...(Lib.started ? { cursor: Lib.next } : {}) })}`);
      if (seq !== Lib.seq) return;
      Lib.rows.push(...page.items);
      Object.assign(Lib, { next: page.next, total: page.total, rev: page.rev, shownOrder: page.order, started: true });
      libSize();
      libPaint();
      libTexts();
    }
  } catch (e) {
    if (seq === Lib.seq) { Lib.failed = true; toast(e.message); libTexts(); }
  } finally {
    if (Lib.filling === seq) Lib.filling = 0;
  }
}

// A new query: the list starts over from its top.
function libLoad() {
  selClear();       // what was picked may not be in the new list
  Lib.seq += 1;
  Object.assign(Lib, { rows: [], next: null, started: false, total: 0, failed: false,
    fillTo: PAGE, filling: 0, reloading: false });
  libClear();
  window.scrollTo(0, 0);
  libSize();
  libPaint();
  libTexts();
  return libFill(PAGE);
}

// Something changed (`rev` moved): fetch again what is on screen, and swap it in
// once it is all there, so the rows do not flicker.
async function libReload() {
  if (Lib.reloading || !Lib.started) return;
  Lib.reloading = true;
  const seq = ++Lib.seq;
  const need = Math.max(PAGE, Lib.win[1] + 1 + MARGIN);
  try {
    const rows = [];
    let next = null, total = 0, rev = 0, started = false;
    while (!started || (next && rows.length < need)) {
      const page = await api(`/api/library?${libQuery({ limit: PAGE, ...(started ? { cursor: next } : {}) })}`);
      if (seq !== Lib.seq) return;
      rows.push(...page.items);
      ({ next, total, rev } = page);
      started = true;
    }
    Object.assign(Lib, { rows, next, total, rev, failed: false, filling: 0, fillTo: need,
      reloading: false });
    libClear();
    libPaint();
    libTexts();
    libFacets();
  } catch { /* the next status tick tries again */ } finally {
    if (seq === Lib.seq) Lib.reloading = false;
  }
}

// Texts set from code, so they follow a language change.
function libTexts() {
  $(".view-switch").setAttribute("aria-label", T.viewSwitch);
  const empty = Lib.started && !Lib.total;
  $("#libEmpty").classList.toggle("hidden", !empty);
  $("#libHead").classList.toggle("hidden", !Lib.total);
  const filtered = Lib.q || Lib.genre || Lib.folder || Lib.artist || Lib.problem;
  // Select all sits beside the count whenever the list is narrowed (design 4.5.2)
  const countAll = $("#libCountAll");
  countAll.dataset.can = filtered && Lib.total ? "1" : "";
  countAll.classList.toggle("hidden", !countAll.dataset.can || Sel.mode);
  const on = [Lib.genre, Lib.folder, Lib.artist, Lib.problem].filter(Boolean).length;
  const badge2 = $("#libFiltersBadge");
  badge2.textContent = String(on);
  badge2.classList.toggle("hidden", !on);
  $("#libSelectBtn").setAttribute("aria-pressed", String(Sel.mode));
  $("#libEmptyTitle").textContent = filtered ? T.libNoMatch : Lib.trash ? T.libTrashEmptyTitle : T.libEmptyTitle;
  $("#libEmptyHint").textContent = filtered ? T.libNoMatchHint : Lib.trash ? T.libTrashEmptyHint : T.libEmptyHint;
  $("#libCount").textContent = Lib.started ? T.libCount(Lib.total) : "";
  $("#libTrashLabel").textContent = T.libTrashN(Lib.trashCount);
  const badge = $("#libTrashBadge");   // a phone shows the trash as an icon and this count
  badge.textContent = Lib.trashCount > 99 ? "99+" : String(Lib.trashCount);
  badge.classList.toggle("hidden", !Lib.trashCount);
  const note = $("#libTrashNote");
  note.classList.toggle("hidden", !Lib.trash || Lib.trashDays === null);
  if (Lib.trashDays !== null) note.textContent = T.libTrashNote(Lib.trashDays);
  $("#libEmptyTrash").disabled = !Lib.trashCount;
  $("#libSort").setAttribute("aria-label", T.libSort);
  $("#libSort").value = Lib.sort;
  const reverse = $("#libOrder");
  reverse.setAttribute("aria-label", T.libReverse);
  reverse.title = T.libReverse;
  reverse.dataset.dir = Lib.order || Lib.shownOrder || ""; // the server says its default
  $("#libGenres").setAttribute("aria-label", T.libGenres);
  $("#libFolder").setAttribute("aria-label", T.libFolderLabel);
}

// ------------------------------------------------- facets: chips, folders
async function libFacets() {
  try {
    Lib.facets = await api(`/api/library/facets${Lib.trash ? "?state=trashed" : ""}`);
    libFacetsRender();
  } catch { /* no filters this time */ }
}

function libFacetsRender() {
  const f = Lib.facets;
  if (!f) return;
  const genres = f.genres.slice(0, 16);
  if (Lib.genre && !genres.some((g) => g.name === Lib.genre)) {
    genres.unshift({ name: Lib.genre, count: (f.genres.find((g) => g.name === Lib.genre) || {}).count || 0 });
  }
  $("#libGenres").innerHTML = genres.map((g) =>
    `<button type="button" class="chip lib-gchip" data-genre="${esc(g.name)}" aria-pressed="${g.name === Lib.genre}">${esc(g.name)}<small>${num(g.count)}</small></button>`).join("");
  const folders = f.folders.slice();
  if (Lib.folder && !folders.some((x) => x.path === Lib.folder)) folders.push({ path: Lib.folder, count: 0 });
  $("#libFolder").innerHTML = `<option value="">${esc(T.libAllFolders)}</option>` + folders.map((x) =>
    `<option value="${esc(x.path)}">${esc(x.path)} (${num(x.count)})</option>`).join("");
  $("#libFolder").value = Lib.folder;
  $("#libFolder").parentElement.classList.toggle("hidden", !folders.length);
  $("#libArtistList").innerHTML = (f.artists || []).slice(0, 500).map((a) =>
    `<option value="${esc(a.name)}">${esc(a.name)} (${num(a.count)})</option>`).join("");
  $("#libArtist").value = Lib.artist;
  $("#libProblem").innerHTML = `<option value="">${esc(T.libProblems)}</option>` + (f.problems || [])
    .filter((p) => p.count || p.id === Lib.problem)
    .map((p) => `<option value="${p.id}">${esc(T.libProblem[p.id] || p.id)} (${num(p.count)})</option>`).join("");
  $("#libProblem").value = Lib.problem;
}

$("#libGenres").addEventListener("click", (e) => {
  const chip = e.target.closest("[data-genre]");
  if (!chip) return;
  Lib.genre = Lib.genre === chip.dataset.genre ? "" : chip.dataset.genre; // tap again to clear
  libFacetsRender();
  libLoad();
});
$("#libFolder").addEventListener("change", (e) => { Lib.folder = e.target.value; libLoad(); });
// The artist filter takes a name as it is chosen or typed in full (or cleared).
$("#libArtist").addEventListener("change", (e) => {
  const name = e.target.value.trim();
  if (name === Lib.artist) return;
  Lib.artist = name;
  libLoad();
});
$("#libArtist").addEventListener("search", (e) => { if (!e.target.value && Lib.artist) { Lib.artist = ""; libLoad(); } });
$("#libProblem").addEventListener("change", (e) => { Lib.problem = e.target.value; libLoad(); });
// On a phone the filters (and the sort) are a sheet opened from one button.
function filtersSheet(open) { document.body.classList.toggle("lib-filters-open", open); }
$("#libFiltersBtn").addEventListener("click", () => filtersSheet(true));
$("#libFiltersClose").addEventListener("click", () => filtersSheet(false));
$("#libFiltersShade").addEventListener("click", () => filtersSheet(false));
$("#libSort").addEventListener("change", (e) => { Lib.sort = e.target.value; Lib.order = null; libLoad(); });
$("#libOrder").addEventListener("click", () => {
  const now = Lib.order || Lib.shownOrder;
  Lib.order = now === "asc" ? "desc" : "asc";
  libLoad();
});

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
    if (Lib.rev !== null && s.rev !== Lib.rev) libReload();
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
    libFacets();
    if (Lib.started) { libPaint(); libReload(); } else libLoad();
    libStatus();
  } else {
    selClear();
    if (location.hash) history.replaceState({}, "", location.pathname + location.search);
    clearTimeout(Lib.statusTimer);
  }
}

// ---------------------------------------------------------- row covers
// A row's cover is loaded only when the row is on screen and has one, a moment
// after it appears (a fast fling loads nothing), a few at a time, and kept as a
// 96 px copy. The server sends a small thumbnail (`?size=thumb`, a few KB; the
// full picture only if it cannot make one) once per revision (`?v=`, cached for
// good); an edited cover has a new revision.
const Cover = { cache: new Map(), queue: [], active: 0, limit: 4, delay: 120, keep: 600, none: new Set() };

function coverDraw(art, bitmap) {
  let cv = art.querySelector("canvas");
  if (!cv) {
    cv = document.createElement("canvas");
    cv.width = cv.height = COVER_PX;
    art.append(cv);
  }
  const ctx = cv.getContext("2d");
  const scale = Math.max(COVER_PX / bitmap.width, COVER_PX / bitmap.height);
  const w = bitmap.width * scale, h = bitmap.height * scale;
  ctx.clearRect(0, 0, COVER_PX, COVER_PX);
  ctx.drawImage(bitmap, (COVER_PX - w) / 2, (COVER_PX - h) / 2, w, h);
  art.classList.add("has-image");
}

function coverPaint(art) {
  const key = art.dataset.cover;
  const hit = Cover.cache.get(key);
  if (hit) {
    Cover.cache.delete(key);
    Cover.cache.set(key, hit);          // most recently used last
    coverDraw(art, hit);
  } else if (!Cover.none.has(key)) {
    setTimeout(() => {
      if (art.isConnected && !Cover.cache.has(key)) { Cover.queue.push(key); coverPump(); }
    }, Cover.delay);
  }
}

// The newest request first: that is the row the DJ is looking at now.
function coverPump() {
  while (Cover.active < Cover.limit && Cover.queue.length) {
    const key = Cover.queue.pop();
    if (Cover.cache.has(key) || !document.querySelector(`.lib-art[data-cover="${key}"]`)) continue;
    Cover.active += 1;
    coverLoad(key).finally(() => { Cover.active -= 1; coverPump(); });
  }
}

async function coverThumb(blob) {
  let bitmap;
  try {
    bitmap = await createImageBitmap(blob, { resizeWidth: COVER_PX, resizeQuality: "medium" });
  } catch {
    bitmap = await createImageBitmap(blob);
  }
  if (bitmap.width <= COVER_PX * 1.5) return bitmap;
  // the full image came back (no thumbnail, or no resize options here): keep a small copy, not that
  const small = document.createElement("canvas");
  small.width = COVER_PX;
  small.height = Math.max(1, Math.round((COVER_PX * bitmap.height) / bitmap.width));
  small.getContext("2d").drawImage(bitmap, 0, 0, small.width, small.height);
  bitmap.close();
  return small;
}

async function coverLoad(key) {
  const [id, rev] = key.split(":");
  let res;
  try {
    res = await request(`/api/library/${id}/cover?size=thumb&v=${rev}`);
  } catch {
    return;                         // a dropped connection: asked again when the row next appears
  }
  if (!res.ok) {
    if (res.status === 404 || res.status === 410) Cover.none.add(key);  // no image there: do not ask again
    return;
  }
  try {
    const bitmap = await coverThumb(await res.blob());
    Cover.cache.set(key, bitmap);
    while (Cover.cache.size > Cover.keep) {
      const oldest = Cover.cache.keys().next().value;
      const old = Cover.cache.get(oldest);
      Cover.cache.delete(oldest);
      if (old.close) old.close();
    }
    document.querySelectorAll(`.lib-art[data-cover="${key}"]`).forEach((art) => coverDraw(art, bitmap));
  } catch {
    Cover.none.add(key);               // the picture cannot be decoded: the placeholder stays
  }
}

// ------------------------------------------------------ the detail sheet
// Six fields, the download view's one-tap genre picks, the cover, a preview
// player, and a question before a comment that holds the source link is
// replaced (design 4.5). Only the fields that changed are sent, each with the
// value the sheet showed as `expect`, so an edit made meanwhile elsewhere is
// never overwritten.
const TAGS = ["title", "artist", "album", "genre", "year", "comment"];
const sheet = $("#libSheet");
const tagInput = (f) => sheet.querySelector(`[data-tag="${f}"]`);
const Sheet = { item: null, shown: {}, saving: false, askDone: false, coverUrl: null, coverSeq: 0 };
const audio = $("#libAudio");

function sheetValue(f) {
  const v = tagInput(f).value;
  if (f !== "year") return v;
  const s = v.trim();
  if (s === "") return null;
  const n = /^\d+$/.test(s) ? Number(s) : NaN;
  const [lo, hi] = libRules.year || [-Infinity, Infinity]; // the server's range; it checks again
  return n >= lo && n <= hi ? n : NaN;
}

function sheetChanges() {
  const changes = {}, expect = {};
  for (const f of TAGS) {
    // Against what the field showed: a browser folds line breaks in a value,
    // and that alone must not count as an edit of the file.
    if (tagInput(f).value === Sheet.shown[f]) continue;
    changes[f] = sheetValue(f);
    expect[f] = Sheet.item[f] ?? (f === "year" ? null : "");
  }
  return { changes, expect };
}

// The one-tap genre picks under a genre field, `current` pressed.
function genreChips(picks, current) {
  return picks.slice(0, 9).map((g) =>
    `<button type="button" class="chip" data-genre="${esc(g)}" aria-pressed="${g === current}">${esc(g)}</button>`).join("");
}

function sheetChips() {
  const picks = [...new Set([...(Sheet.item?.genre ? [Sheet.item.genre] : []), ...shared.genrePicks])];
  $("#libSheetChips").innerHTML = genreChips(picks, tagInput("genre").value);
}

function sheetSource() {
  // the server's rule (libRules.source): "Source: <url>", as the tagger writes it
  const found = libRules.source && tagInput("comment").value.match(libRules.source);
  const m = found ? found[1].replace(/;$/, "") : "";
  const el = $("#libSheetSource");
  el.classList.toggle("hidden", !m);
  el.innerHTML = m ? `${esc(T.libSource)}: <a href="${esc(m)}" target="_blank" rel="noreferrer">${esc(m)}</a>` : "";
}

// The preview: the browser asks the server for ranges, and nothing is fetched
// until Play. The address carries the access token when there is one, because
// an audio element cannot send a header.
function audioUrl(id) {
  const tok = localStorage.getItem("gsm_token");
  return `/api/library/${id}/audio${tok ? `?token=${encodeURIComponent(tok)}` : ""}`;
}
function audioStop() {
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
  $("#libAudioNote").classList.add("hidden");
}
function audioArm(item) {
  audioStop();
  audio.src = audioUrl(item.id);
}
audio.addEventListener("error", () => {
  if (!audio.getAttribute("src")) return;
  const note = $("#libAudioNote");
  note.textContent = T.libNoPlay;
  note.classList.remove("hidden");
});

// The sheet's cover: the whole image, once, as a blob (a header carries the token).
async function sheetCover(item) {
  const box = $("#libSheetCover");
  const seq = ++Sheet.coverSeq;
  if (Sheet.coverUrl) { URL.revokeObjectURL(Sheet.coverUrl); Sheet.coverUrl = null; }
  box.innerHTML = NOTE;
  box.classList.toggle("has-image", false);
  box.setAttribute("aria-label", T.libNoCover);
  $("#libCoverBtn").textContent = item.has_cover ? T.changeCover : T.libAddCover;
  if (!item.has_cover) return;
  try {
    const res = await request(`/api/library/${item.id}/cover?v=${item.content_rev}`);
    if (!res.ok) throw new Error(String(res.status));
    const url = URL.createObjectURL(await res.blob());
    if (seq !== Sheet.coverSeq) { URL.revokeObjectURL(url); return; }
    Sheet.coverUrl = url;
    box.innerHTML = `<img alt="" src="${url}" decoding="async">`;
    box.classList.add("has-image");
    box.setAttribute("aria-label", T.libCoverAlt);
  } catch { /* the placeholder stays */ }
}

async function sheetSame(item) {
  const el = $("#libSheetSame");
  el.classList.add("hidden");
  if (!item.same_audio.length) return;
  const found = await Promise.all(item.same_audio.slice(0, 4).map((id) => api(`/api/library/${id}`).catch(() => null)));
  if (Sheet.item?.id !== item.id) return;
  const more = item.same_audio.length - found.length;
  el.innerHTML = `${esc(T.libSameAs)}: ${found.filter(Boolean).map((o) => `<code>${esc(o.path)}</code>`).join(", ")}${more > 0 ? ` +${more}` : ""}`;
  el.classList.remove("hidden");
}

function sheetMeta(item) {
  const bits = [item.format.toUpperCase()];
  if (item.bitrate) bits.push(`${item.bitrate} kbps`);
  if (fmtDur(item.duration)) bits.push(fmtDur(item.duration));
  if (item.size) bits.push(`${(item.size / 1048576).toFixed(1)} MB`);
  $("#libSheetMeta").textContent = bits.join(" · ");
}

function sheetFill(item) {
  Sheet.item = item;
  Sheet.askDone = false;
  $("#libSheetAsk").classList.add("hidden");
  $("#libSheetTitle").textContent = item.title.trim() || libName(item.path);
  $("#libSheetFile").textContent = item.path;
  for (const f of TAGS) {
    const input = tagInput(f);
    input.value = item[f] ?? "";
    Sheet.shown[f] = input.value;
    input.disabled = !item.editable;
    const label = input.closest(".lib-field");
    let note = label.querySelector(".lib-multi");
    if (item.multi.includes(f) && !note) {
      note = document.createElement("small");
      note.className = "lib-multi";
      label.append(note);
    }
    if (note) {
      note.textContent = T.libMulti;
      note.hidden = !item.multi.includes(f);
    }
  }
  const ro = $("#libSheetReadOnly");
  ro.classList.toggle("hidden", item.editable);
  ro.textContent = item.editable ? "" : (item.damaged ? T.libDamaged : T.libReadOnlyFormat(item.format));
  $("#libSheetSave").classList.toggle("hidden", !item.editable);
  $("#libSheetChips").classList.toggle("hidden", !item.editable);
  $("#libCoverBtn").disabled = !item.editable;
  sheetChips();
  sheetSource();
  sheetMeta(item);
  sheetCover(item);
  sheetSame(item);
  audioArm(item);
}

export async function openSheet(id) {
  try {
    const item = await api(`/api/library/${id}`);
    sheetFill(item);
    sheet.classList.remove("hidden");
    if (item.editable && !narrow.matches) tagInput("title").focus();
  } catch (e) { toast(e.message); }
}

// The sheet closes by its own buttons, the backdrop and Escape (app.js): stop
// the preview and let go of the picture whenever it is hidden.
new MutationObserver(() => {
  if (!sheet.classList.contains("hidden")) return;
  audioStop();
  Sheet.coverSeq += 1;
  if (Sheet.coverUrl) { URL.revokeObjectURL(Sheet.coverUrl); Sheet.coverUrl = null; }
  Sheet.item = null;
}).observe(sheet, { attributes: true, attributeFilter: ["class"] });

// A saved item goes into the list (and its row). When only its tags changed
// the picture is the same, so its thumbnail moves to the new revision's key
// instead of being fetched again.
function libSaved(item, coverEdited = false) {
  const i = Lib.rows.findIndex((t) => t.id === item.id);
  if (i >= 0) {
    const from = coverKey(Lib.rows[i]);
    Lib.rows[i] = { ...Lib.rows[i], ...item };
    const to = coverKey(Lib.rows[i]);
    if (!coverEdited && from && to && from !== to && Cover.cache.has(from)) {
      Cover.cache.set(to, Cover.cache.get(from));
      Cover.cache.delete(from);
    }
    libRefreshRow(i);
  }
  // Our own write took the next `rev` (and `content_rev` is that rev): no reload for it.
  if (Lib.rev !== null && item.content_rev === Lib.rev + 1) Lib.rev = item.content_rev;
  libFacets();
}
function libRefreshRow(i) {
  const el = shown.get(i);
  if (!el) return;
  const fresh = libMake(i);
  el.replaceWith(fresh);
  shown.set(i, fresh);
  const art = fresh.querySelector(".lib-art[data-cover]");
  if (art) coverPaint(art);
}

async function saveSheet() {
  if (!Sheet.item || Sheet.saving) return;
  const { changes, expect } = sheetChanges();
  if (Number.isNaN(changes.year)) { toast(T.libBadYear(...libRules.year)); tagInput("year").focus(); return; }
  if (!Object.keys(changes).length) { sheet.classList.add("hidden"); toast(T.libNoChange); return; }
  // The source link is the only record of a download's origin in the file: ask once.
  if ("comment" in changes && Sheet.item.source && !Sheet.askDone) {
    $("#libSheetAskText").textContent = T.libAsk;
    $("#libSheetAsk").classList.remove("hidden");
    $("#libAskReplace").focus();
    $("#libSheetAsk").scrollIntoView({ block: "nearest", behavior: "smooth" });
    return;
  }
  Sheet.saving = true;
  $("#libSheetSave").disabled = true;
  audioStop(); // the write moves the audio inside the file: a playing preview would go wrong
  const item = Sheet.item;
  try {
    const res = await request(`/api/library/${item.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...changes, expect }),
    });
    const body = await res.json().catch(() => ({}));
    if (res.status === 412) {
      toast(T.libChanged);
      sheetFill(await api(`/api/library/${item.id}`));
      return;
    }
    if (res.status === 423) { toast(T.libInUse); audioArm(item); return; }
    if (!res.ok) { toast(serverError(body.detail) || res.statusText); audioArm(item); return; }
    libSaved(body);
    sheet.classList.add("hidden");
    toast(T.libSaved);
  } catch (e) {
    toast(e.message);
  } finally {
    Sheet.saving = false;
    $("#libSheetSave").disabled = false;
  }
}

$("#libSheetForm").addEventListener("submit", (e) => { e.preventDefault(); saveSheet(); });
$("#libAskReplace").addEventListener("click", () => {
  Sheet.askDone = true;
  $("#libSheetAsk").classList.add("hidden");
  saveSheet();
});
$("#libAskKeep").addEventListener("click", () => {
  tagInput("comment").value = Sheet.shown.comment;
  $("#libSheetAsk").classList.add("hidden");
  sheetSource();
  saveSheet();
});
$("#libSheetChips").addEventListener("click", (e) => {
  const chip = e.target.closest("[data-genre]");
  if (!chip) return;
  const input = tagInput("genre");
  input.value = input.value === chip.dataset.genre ? "" : chip.dataset.genre; // tap again to clear
  sheetChips();
});
tagInput("genre").addEventListener("input", sheetChips);
tagInput("comment").addEventListener("input", () => {
  sheetSource();
  $("#libSheetAsk").classList.add("hidden");
});

// ------------------------------------------------------ cover edit
// The download view's cover search and upload, in front of the library's own
// write: a pick is sent to POST /api/library/{id}/cover (design 4.3).
async function saveCover(body, isUpload) {
  const item = Sheet.item;
  if (!item || Sheet.saving) return;
  Sheet.saving = true;
  audioStop(); // the write moves the audio inside the file
  try {
    const res = await request(`/api/library/${item.id}/cover`, {
      method: "POST",
      headers: isUpload ? {} : { "Content-Type": "application/json" },
      body: isUpload ? body : JSON.stringify(body),
    });
    const out = await res.json().catch(() => ({}));
    if (res.status === 423) { toast(T.libInUse); return; }
    if (!res.ok) { toast(serverError(out.detail) || res.statusText); return; }
    $("#coverModal").classList.add("hidden");
    libSaved(out, true);
    if (Sheet.item && Sheet.item.id === out.id) {
      Sheet.item = out;   // the file's tags are as they were: what is typed in the fields stays
      sheetCover(out);
      sheetMeta(out);
    }
    toast(T.libCoverSaved);
  } catch (e) {
    toast(e.message);
  } finally {
    Sheet.saving = false;
    if (Sheet.item) audioArm(Sheet.item);
  }
}

$("#libCoverBtn").addEventListener("click", () => {
  const item = Sheet.item;
  if (!item || !item.editable) return;
  openCoverModal([item.artist, item.title].filter(Boolean).join(" "), {
    url: (full) => saveCover({ url: full }, false),
    file: (f) => { const fd = new FormData(); fd.append("file", f); return saveCover(fd, true); },
  });
});

// --------------------------------------------------------- selection
// Several tracks are picked for the bulk bar (design 4.5.1). The Select
// button starts selection mode: every row shows a checkbox and a tap or
// click picks it. A long press on a phone, Ctrl- or Cmd-click, Shift-click
// and the checkbox a computer shows over a hovered cover start it too, with
// that row picked. Select all takes the whole view, however long, as its
// filter. Escape, ✕ and a new search, filter or sort end it. The bar's
// actions read selection(); each button in #libSelActions names its action
// in `data-bulk`, and SEL_ACTIONS below runs it.
export function selection() {
  return { all: Sel.all, ids: [...Sel.ids], count: Sel.all ? Lib.total : Sel.ids.size,
    filter: libFilter() };
}
export const selectedIds = () => [...Sel.ids];

// The filter of the list as GET /api/library takes it.
function libFilter() {
  return { q: Lib.q, genre: Lib.genre, folder: Lib.folder, artist: Lib.artist, problem: Lib.problem };
}

function selPaint() {
  const n = Sel.all ? Lib.total : Sel.ids.size;
  document.body.classList.toggle("lib-selecting", Sel.mode);
  $("#libSelBar").classList.toggle("hidden", !Sel.mode);
  $("#libSelectBtn").setAttribute("aria-pressed", String(Sel.mode));
  $("#libCountAll").classList.toggle("hidden", Sel.mode || !$("#libCountAll").dataset.can);
  // the number always; the word only where there is room for it (library.css)
  $("#libSelCount").innerHTML = !n ? esc(T.libSelPick) : Sel.all ? esc(T.libAllSelected(n))
    : `${num(n)}<span class="lib-sel-word"> ${esc(T.libSelWord(n))}</span>`;
  const all = $("#libSelAll");
  all.textContent = T.libSelectAllN(Lib.total);
  all.classList.toggle("hidden", Sel.all || Lib.total <= Sel.ids.size);
  document.querySelectorAll("#libSelActions [data-bulk]").forEach((b) => {
    b.classList.toggle("hidden", (b.dataset.bulk === "restore") !== Lib.trash);
    b.disabled = !n;
  });
  shown.forEach((el) => {
    if (el.dataset.id) el.classList.toggle("is-selected", Sel.all || Sel.ids.has(Number(el.dataset.id)));
  });
}
function selStart() {
  Sel.mode = true;
  selPaint();
}
function selClear() {
  if (!Sel.mode && !Sel.ids.size) return;
  Object.assign(Sel, { mode: false, all: false, anchor: null });
  Sel.ids.clear();
  selPaint();
}
function selAll() {
  Object.assign(Sel, { mode: true, all: true, anchor: null });
  Sel.ids.clear();
  selPaint();
}
// Every id of the view, for an action that needs them (Delete) or when one
// track is taken out of "all".
async function viewIds() {
  const p = new URLSearchParams(Object.entries(libFilter()).filter(([, v]) => v));
  if (Lib.trash) p.set("state", "trashed");
  return (await api(`/api/library/ids?${p}`)).ids;
}
async function selToggle(i, on) {
  const t = Lib.rows[i];
  if (!t) return;
  if (Sel.all) {   // out of "all": every track of the view, then this one changes
    try { Sel.ids = new Set(await viewIds()); } catch (e) { toast(e.message); return; }
    Sel.all = false;
  }
  if (on ?? !Sel.ids.has(t.id)) Sel.ids.add(t.id); else Sel.ids.delete(t.id);
  Object.assign(Sel, { mode: true, anchor: i });
  selPaint();
}
// Shift: every loaded row from the anchor to this one joins.
function selRange(i) {
  if (Sel.anchor === null || Sel.all) { selToggle(i); return; }
  const [a, b] = Sel.anchor < i ? [Sel.anchor, i] : [i, Sel.anchor];
  for (let k = a; k <= b; k += 1) if (Lib.rows[k]) Sel.ids.add(Lib.rows[k].id);
  Sel.mode = true;
  selPaint();
}

function rowOf(e) {
  if (e.target.closest("[data-act]")) return null;     // its own delete or restore button
  const row = e.target.closest(".lib-row");
  return row && row.dataset.id ? row : null;
}
function rowPick(e, row, viaCheck) {
  const i = Number(row.dataset.i);
  if (e.shiftKey) selRange(i);
  else if (Sel.mode || e.ctrlKey || e.metaKey || viaCheck) selToggle(i);
  else if (!Lib.trash) openSheet(Number(row.dataset.id));
}
libList.addEventListener("click", (e) => {
  if (Sel.longPressed) { Sel.longPressed = false; return; }  // the press has already picked it
  const row = rowOf(e);
  if (row) rowPick(e, row, !!e.target.closest(".lib-check"));
});
libList.addEventListener("keydown", (e) => {
  const row = rowOf(e);
  if (row && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); rowPick(e, row, false); }
});
// Shift-click picks rows, not the text between them.
libList.addEventListener("mousedown", (e) => { if (e.shiftKey && rowOf(e)) e.preventDefault(); });

// A long press: a finger that rests on a row without moving picks it.
function pressEnd() { clearTimeout(Sel.pressTimer); Sel.pressTimer = null; }
libList.addEventListener("pointerdown", (e) => {
  Sel.longPressed = false;
  const row = e.pointerType !== "mouse" && rowOf(e);
  if (!row) return;
  pressEnd();
  Sel.press = { x: e.clientX, y: e.clientY };
  Sel.pressTimer = setTimeout(() => {
    Sel.pressTimer = null;
    Sel.longPressed = true;
    selToggle(Number(row.dataset.i), true);
    if (navigator.vibrate) navigator.vibrate(10);
  }, LONG_PRESS);
});
libList.addEventListener("pointermove", (e) => {
  if (Sel.pressTimer && Math.hypot(e.clientX - Sel.press.x, e.clientY - Sel.press.y) > 10) pressEnd();
});
["pointerup", "pointercancel", "pointerleave"].forEach((t) => libList.addEventListener(t, pressEnd));
libList.addEventListener("contextmenu", (e) => { if (Sel.longPressed || Sel.mode) e.preventDefault(); });
// Escape lets go of the selection, unless it is closing a dialog (app.js does that).
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && Sel.mode && !document.querySelector(".modal:not(.hidden)")) selClear();
});
$("#libSelClear").addEventListener("click", selClear);
$("#libSelectBtn").addEventListener("click", () => (Sel.mode ? selClear() : selStart()));
$("#libSelAll").addEventListener("click", selAll);
$("#libCountAll").addEventListener("click", selAll);

// ------------------------------------------------------- bulk actions
// One request for all of them (POST /api/library/bulk); the answer says per
// track what was done, so a failure is named and the rest still happens.
async function libBulk(action, ids, extra = {}) {
  let res;
  try {
    res = await api("/api/library/bulk", { method: "POST", body: JSON.stringify({ ids, action, ...extra }) });
  } catch (e) {
    toast(e.message);
    return null;
  }
  selClear();
  libReload();
  libFacets();
  libStatus();      // the trash count
  return res;
}
// The toast after a bulk action: what was done, then what was not and why.
function bulkToast(res, done) {
  if (!res.failed.length) { toast(done); return; }
  const failed = T.libBulkFailed(res.failed.length, serverError(res.failed[0].detail));
  toast(res.done.length ? `${done} · ${failed}` : failed);
}
// The ids an action works on: the picked ones, or the whole view.
async function pickedIds() {
  return Sel.all ? viewIds() : [...Sel.ids];
}

async function bulkDelete() {
  let ids;
  try { ids = await pickedIds(); } catch (e) { toast(e.message); return; }
  if (!ids.length) return;
  if (!(await askConfirm(T.libBulkDeleteAsk(ids.length), T.libDelete, T.cancel, { danger: true }))) return;
  const res = await libBulk("delete", ids);
  if (!res) return;
  if (res.failed.length) { bulkToast(res, T.libBulkDeleted(res.done.length)); return; }
  const done = res.done;
  toastAction(T.libBulkDeleted(done.length), T.libUndo, () => bulkRestore(done));
}
async function bulkRestore(ids) {
  let which = ids;
  if (!which) { try { which = await pickedIds(); } catch (e) { toast(e.message); return; } }
  const res = await libBulk("restore", which);
  if (res) bulkToast(res, T.libBulkRestored(res.done.length));
}

const SEL_ACTIONS = { delete: bulkDelete, restore: () => bulkRestore() };
// What the list shows now, for an action on the whole view: its filter, as
// GET /api/library takes it, and how many tracks it holds.
export function libView() {
  return { filter: libFilter(), total: Lib.total };
}
// Another screen adds its action to the bar (a button with that `data-bulk`).
export function addSelAction(name, fn) { SEL_ACTIONS[name] = fn; }
// Another screen wrote to files: the selection goes and the list reloads.
export function libChanged() {
  selClear();
  libReload();
  libFacets();
}
$("#libSelActions").addEventListener("click", (e) => {
  const btn = e.target.closest("[data-bulk]");
  if (btn && (Sel.all || Sel.ids.size)) SEL_ACTIONS[btn.dataset.bulk]();
});

document.querySelectorAll("[data-view]").forEach((b) =>
  b.addEventListener("click", () => setView(b.dataset.view)));

// ------------------------------------------------------------- the trash
// The trash is the same list over the trashed tracks, with Restore on each
// row and Empty trash in the bar (design 4.4, 4.5).
function setTrash(on) {
  Lib.trash = !!on;
  Lib.genre = "";
  Lib.folder = "";
  Lib.artist = "";
  Lib.problem = "";
  Lib.sort = "added";   // the trash has no sort menu
  Lib.order = null;
  document.body.classList.toggle("lib-in-trash", Lib.trash);
  $("#libBack").classList.toggle("hidden", !Lib.trash);
  $("#libTrashBtn").classList.toggle("hidden", Lib.trash);
  $("#libEmptyTrash").classList.toggle("hidden", !Lib.trash);
  libLoad();
  libFacets();
  if (Lib.trash) {
    api("/api/settings").then((s) => { Lib.trashDays = s.trash_days; libTexts(); }).catch(() => { /* no note */ });
  }
}

// A toast with one action button, for Undo; it stays a little longer than a plain one.

function libDrop(id) {
  const i = Lib.rows.findIndex((t) => t.id === id);
  if (i < 0) return;
  Lib.rows.splice(i, 1);
  Lib.total = Math.max(0, Lib.total - 1);
  libRepaint();
}

async function libDelete(id) {
  const t = Lib.rows.find((i) => i.id === id);
  try {
    const res = await api(`/api/library/${id}`, { method: "DELETE" });
    Lib.rev = res.rev; // our own change: no reload needed for it
  } catch (e) {
    toast(e.message);
    return;
  }
  libDrop(id);
  libFacets();
  Lib.trashCount += 1;
  libTexts();
  toastAction(T.libDeleted(libLabel(t)), T.libUndo, () => libRestore(id, t));
}

async function libRestore(id, t = Lib.rows.find((i) => i.id === id)) {
  try {
    await api(`/api/library/${id}/restore`, { method: "POST" });
  } catch (e) {
    toast(e.status === 409 ? T.libRestoreTaken : e.message);
    return;
  }
  Lib.trashCount = Math.max(0, Lib.trashCount - 1);
  if (Lib.trash) libDrop(id);
  else libReload(); // an Undo: the track goes back in its place
  libFacets();
  libTexts();
  toast(T.libRestored(libLabel(t)));
}

libList.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-act]");
  const row = btn && btn.closest(".lib-row");
  if (!row || !row.dataset.id) return;
  const id = Number(row.dataset.id);
  const del = btn.dataset.act === "delete";
  const label = libLabel(Lib.rows.find((t) => t.id === id));
  btn.disabled = true; // one tap, one request
  // asked first: both buttons sit on the row, where a scroll can become a tap
  askConfirm(del ? T.libDeleteAsk(label) : T.libRestoreAsk(label),
    del ? T.libDelete : T.libRestore, T.cancel, { danger: del })
    .then((yes) => (yes ? (del ? libDelete(id) : libRestore(id)) : null))
    .finally(() => { btn.disabled = false; });
});

$("#libTrashBtn").addEventListener("click", () => setTrash(true));
$("#libBack").addEventListener("click", () => setTrash(false));
$("#libEmptyTrash").addEventListener("click", async () => {
  if (!Lib.trashCount) return;
  if (!(await askConfirm(T.libEmptyConfirm(Lib.trashCount), T.libEmptyYes, T.cancel, { danger: true }))) return;
  try {
    const res = await api("/api/library/trash", { method: "DELETE" });
    toast(T.libEmptied(res.purged));
  } catch (e) {
    toast(e.message);
  }
  Lib.trashCount = 0;
  libLoad();
  libFacets();
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

// A language change (app.js sets <html lang>): rows and filters hold translated text.
new MutationObserver(() => {
  if (Lib.lang === lang) return;
  Lib.lang = lang;
  libFacetsRender();
  libRepaint();
  selPaint();
}).observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });
Lib.lang = lang;

// The toast and the footer keep clear of whichever deck is showing.
const libDock = $("#libDock");
new ResizeObserver(() => {
  if (libDock.offsetHeight) document.documentElement.style.setProperty("--dock-h", `${libDock.offsetHeight}px`);
}).observe(libDock);

if (location.hash === "#library" && location.pathname !== "/share") setView("library");
