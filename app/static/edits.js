/* GetSetMix: batch editing (docs/design/batch-editing.md 4.3, 4.4), the first
   slice: one field for the selected tracks. The bulk bar's *Edit tags* opens
   a panel; *Preview* asks the server for the changes, which it stores, and
   lists them; *Apply* writes exactly those, one file at a time, and the panel
   follows the progress. Files that failed can be tried again; a file changed
   meanwhile is left alone and said so. *Undo* writes the old values back,
   from the panel or from the History (slice 3). Loaded by app.js. */
import { $, api, errorOf, esc, libRules, request, toast } from "./core.js";
import { lang, num, plural, serverError, STR, T } from "./i18n.js";
import { cleanupOpen, cleanupSetId, cleanupSteps } from "./cleanup.js";
import { addSelAction, libChanged, libView, selectedIds } from "./library.js";

const SKIP_IT = {
  "read-only format": "formato in sola lettura", "damaged file": "file danneggiato",
  "in the trash": "nel cestino", "not on disk": "non sul disco",
  "not in the library": "non più nella libreria", "no such track": "brano non trovato",
};
Object.assign(STR.en, {
  edEditTags: "Edit tags",
  edTitle: (n) => plural(n, "Edit tags of 1 track", "Edit tags of {n} tracks"),
  edPreview: "Preview",
  edOps: { leave: "Leave as it is", set: "Set to", clear: "Clear", prepend: "Add before",
    append: "Add after", replace: "Replace" },
  edValuePh: "New value", edFind: "Find", edWith: "Replace with",
  edWord: "Whole words", edCase: "Match case",
  edScopeIds: (n) => plural(n, "The selected track", "The {n} selected tracks"),
  edScopeAll: (n) => plural(n, "The 1 track in this view", "All {n} tracks in this view"),
  edPickOne: "Choose a change for at least one field.",
  edCover: "Cover", edCoverOps: { leave: "Leave as it is", set_cover: "New image", clear_cover: "Remove" },
  edCoverPick: "Image for the cover", edCoverNeeded: "Choose an image for the cover.",
  edCoverNew: "new image", edCoverNone: "no cover", edCoverHad: "its cover",
  edAll: "All", edWarned: "With a warning", edKeepTrack: "Keep this track in the edit",
  edKeepChange: "Keep this change",
  edResend: (t, mb) => `${plural(t, "Each paired computer downloads 1 track again", "Each paired computer downloads {n} tracks again")} (${mb} MB).`,
  edCounts: (c, t) => `${plural(c, "1 change", "{n} changes")} on ${plural(t, "1 track", "{n} tracks")}`,
  edNothing: "Nothing to change: the selected tracks already hold this value.",
  edUnchanged: (n) => plural(n, "1 track already holds it.", "{n} tracks already hold it."),
  edSkipped: (list) => `Left out: ${list}.`,
  edWhy: (r) => r,
  edApply: (c, t) => `Change ${plural(c, "1 tag", "{n} tags")} on ${plural(t, "1 track", "{n} tracks")}`,
  edRetry: (n) => plural(n, "Try 1 file again", "Try {n} files again"),
  edWriting: (d, t) => `Writing: ${num(d)} of ${num(t)} files`,
  edDone: (n) => plural(n, "Written to 1 file.", "Written to {n} files."),
  edFailed: (n) => plural(n, "1 file could not be written.", "{n} files could not be written."),
  edConflict: (n) => plural(n, "1 file changed meanwhile and was left as it is.",
    "{n} files changed meanwhile and were left as they are."),
  edMore: (n) => plural(n, "and 1 more change", "and {n} more changes"),
  edWarn: { would_empty: "it would be empty: left out", too_long: "longer than 255 characters: left out",
    merges_values: "the file holds several values; they become this one" },
  edState: { pending: "", applied: "Written", failed: "Not written", conflict: "Changed meanwhile",
    blocked: "Left out", excluded: "Left out", undone: "Undone" },
  edUndo: "Undo", edHistory: "History", edHistoryEmpty: "No batch edits yet.",
  edUndoLabel: (what) => `Undo: ${what}`,
  edUndoing: "Undoing…",
  edLineUndone: { all: "Undone", some: "Partly undone" },
  edLineGone: "Can no longer be undone",
});
Object.assign(STR.it, {
  edEditTags: "Modifica tag",
  edTitle: (n) => plural(n, "Modifica i tag di 1 brano", "Modifica i tag di {n} brani"),
  edPreview: "Anteprima",
  edOps: { leave: "Lascia com'è", set: "Imposta a", clear: "Svuota", prepend: "Aggiungi prima",
    append: "Aggiungi dopo", replace: "Sostituisci" },
  edValuePh: "Nuovo valore", edFind: "Trova", edWith: "Sostituisci con",
  edWord: "Parole intere", edCase: "Maiuscole uguali",
  edScopeIds: (n) => plural(n, "Il brano selezionato", "I {n} brani selezionati"),
  edScopeAll: (n) => plural(n, "L'unico brano di questa vista", "Tutti i {n} brani di questa vista"),
  edPickOne: "Scegli una modifica per almeno un campo.",
  edCover: "Copertina", edCoverOps: { leave: "Lascia com'è", set_cover: "Nuova immagine", clear_cover: "Togli" },
  edCoverPick: "Immagine per la copertina", edCoverNeeded: "Scegli un'immagine per la copertina.",
  edCoverNew: "nuova immagine", edCoverNone: "nessuna copertina", edCoverHad: "la sua copertina",
  edAll: "Tutte", edWarned: "Con un avviso", edKeepTrack: "Tieni questo brano nella modifica",
  edKeepChange: "Tieni questa modifica",
  edResend: (t, mb) => `${plural(t, "Ogni computer abbinato riscarica 1 brano", "Ogni computer abbinato riscarica {n} brani")} (${mb} MB).`,
  edCounts: (c, t) => `${plural(c, "1 modifica", "{n} modifiche")} su ${plural(t, "1 brano", "{n} brani")}`,
  edNothing: "Niente da cambiare: i brani selezionati hanno già questo valore.",
  edUnchanged: (n) => plural(n, "1 brano lo ha già.", "{n} brani lo hanno già."),
  edSkipped: (list) => `Esclusi: ${list}.`,
  edWhy: (r) => SKIP_IT[r] || r,
  edApply: (c, t) => `Cambia ${plural(c, "1 tag", "{n} tag")} su ${plural(t, "1 brano", "{n} brani")}`,
  edRetry: (n) => plural(n, "Riprova 1 file", "Riprova {n} file"),
  edWriting: (d, t) => `Scrittura: ${num(d)} file su ${num(t)}`,
  edDone: (n) => plural(n, "Scritto in 1 file.", "Scritto in {n} file."),
  edFailed: (n) => plural(n, "1 file non è stato scritto.", "{n} file non sono stati scritti."),
  edConflict: (n) => plural(n, "1 file è cambiato nel frattempo ed è rimasto com'era.",
    "{n} file sono cambiati nel frattempo e sono rimasti com'erano."),
  edMore: (n) => plural(n, "e un'altra modifica", "e altre {n} modifiche"),
  edWarn: { would_empty: "resterebbe vuoto: escluso", too_long: "più lungo di 255 caratteri: escluso",
    merges_values: "il file ha più valori; diventano questo" },
  edState: { pending: "", applied: "Scritto", failed: "Non scritto", conflict: "Cambiato nel frattempo",
    blocked: "Escluso", excluded: "Escluso", undone: "Annullato" },
  edUndo: "Annulla", edHistory: "Cronologia", edHistoryEmpty: "Ancora nessuna modifica in blocco.",
  edUndoLabel: (what) => `Annulla: ${what}`,
  edUndoing: "Annullamento…",
  edLineUndone: { all: "Annullata", some: "Annullata in parte" },
  edLineGone: "Non si può più annullare",
});

const SHOWN = 500;        // changes listed in the panel; the rest are counted
const POLL_MS = 600;      // how often the progress of an apply is read
const FIELD_LABEL = { title: "libTitle", artist: "libArtist", album: "album", genre: "genre",
  year: "libYear", comment: "libComment", cover: "edCover" };

const modal = $("#edModal");
const FIELDS = ["title", "artist", "album", "genre", "year", "comment"];
// Which operations each field takes, as the server's rules allow them.
const FIELD_OPS = { title: ["set", "prepend", "append", "replace"], artist: ["set", "prepend", "append", "replace"],
  album: ["set", "clear", "prepend", "append", "replace"], genre: ["set", "clear", "prepend", "append", "replace"],
  year: ["set", "clear"], comment: ["set", "clear", "prepend", "append", "replace"] };
const Ed = { ids: [], view: null, edit: null, timer: null, busy: false, tab: "fields",
  items: [], filter: "all" };

function edReset() {
  clearTimeout(Ed.timer);
  Ed.edit = null;
  $("#edPreview").classList.add("hidden");
  $("#edApply").classList.add("hidden");
  $("#edUndo").classList.add("hidden");
  $("#edResult").classList.add("hidden");
  $("#edProgress").classList.add("hidden");
  $("#edList").innerHTML = "";
  $("#edFilter").innerHTML = "";
  Ed.items = [];
  Ed.filter = "all";
}

// Fields or Cleanup: the preview is made from the tab that shows.
function edTab(tab) {
  Ed.tab = tab;
  document.querySelectorAll(".ed-tab").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === tab)));
  $("#edFields").classList.toggle("hidden", tab !== "fields");
  $("#edCleanup").classList.toggle("hidden", tab !== "cleanup");
  if (tab === "cleanup") cleanupOpen();
  if (Ed.edit && Ed.edit.state === "preview") edReset();
}
document.querySelectorAll(".ed-tab").forEach((b) => b.addEventListener("click", () => edTab(b.dataset.tab)));
$("#edCleanup").addEventListener("cleanup-change", () => { if (Ed.edit && Ed.edit.state === "preview") edReset(); });

// One row per field (design 4.3, the Fields tab): what to do, and its inputs.
function edRows() {
  $("#edFields").innerHTML = FIELDS.map((f) => {
    const name = T[FIELD_LABEL[f]];
    const ops = ["leave", ...FIELD_OPS[f]].map((op) => `<option value="${op}">${esc(T.edOps[op])}</option>`).join("");
    const extra = f === "genre" ? ' list="genres"' : f === "year" ? ' inputmode="numeric" maxlength="4"' : "";
    return `<div class="ed-frow" data-field="${f}" data-op="leave">
      <span class="ed-fname">${esc(name)}</span>
      <select class="ed-select ed-op" aria-label="${esc(name)}">${ops}</select>
      <div class="ed-args">
        <input class="ed-v" type="text" spellcheck="false" placeholder="${esc(T.edValuePh)}" aria-label="${esc(`${name}: ${T.edValuePh}`)}"${extra} />
        <input class="ed-find" type="text" spellcheck="false" placeholder="${esc(T.edFind)}" aria-label="${esc(`${name}: ${T.edFind}`)}" />
        <input class="ed-with" type="text" spellcheck="false" placeholder="${esc(T.edWith)}" aria-label="${esc(`${name}: ${T.edWith}`)}" />
        <label class="ed-check"><input class="ed-word" type="checkbox" /> ${esc(T.edWord)}</label>
        <label class="ed-check"><input class="ed-case" type="checkbox" /> ${esc(T.edCase)}</label>
      </div>
    </div>`;
  }).join("") + `<div class="ed-frow" data-field="cover" data-op="leave">
      <span class="ed-fname">${esc(T.edCover)}</span>
      <select class="ed-select ed-op" aria-label="${esc(T.edCover)}">${["leave", "set_cover", "clear_cover"]
    .map((op) => `<option value="${op}">${esc(T.edCoverOps[op])}</option>`).join("")}</select>
      <div class="ed-args"><input class="ed-file-in" type="file" accept="image/jpeg,image/png,image/webp" aria-label="${esc(T.edCoverPick)}" /></div>
    </div>`;
}

function edOpen() {
  Ed.ids = selectedIds();
  if (!Ed.ids.length) return;
  Ed.view = libView();
  edReset();
  $("#edTitle").textContent = T.edTitle(Ed.ids.length);
  // The whole view is offered when it holds more than the selection: one
  // request, resolved by the server, however long the list.
  const more = Ed.view.total > Ed.ids.length;
  $("#edScope").classList.toggle("hidden", !more);
  $('#edScope input[value="ids"]').checked = true;
  edScopeTexts();
  edRows();
  edTab("fields");
  modal.classList.remove("hidden");
  $("#edFields .ed-op").focus();
}
function edScopeTexts() {
  $("#edScopeIds").textContent = T.edScopeIds(Ed.ids.length);
  $("#edScopeAll").textContent = T.edScopeAll(Ed.view ? Ed.view.total : 0);
}

$("#edFields").addEventListener("change", (e) => {
  const sel = e.target.closest(".ed-op");
  if (sel) {
    const row = sel.closest(".ed-frow");
    row.dataset.op = sel.value;
    const first = row.querySelector(sel.value === "replace" ? ".ed-find" : ".ed-v, .ed-file-in");
    if (first && !["leave", "clear", "clear_cover"].includes(sel.value)) first.focus();
  }
  if (Ed.edit && Ed.edit.state === "preview") edReset();
});
$("#edFields").addEventListener("input", () => { if (Ed.edit && Ed.edit.state === "preview") edReset(); });
$("#edScope").addEventListener("change", () => { if (Ed.edit && Ed.edit.state === "preview") edReset(); });

// The steps the rows ask for, in field order; NaN marks a year that is not one.
function edSteps() {
  const steps = [];
  for (const row of $("#edFields").querySelectorAll(".ed-frow")) {
    const op = row.dataset.op;
    const f = row.dataset.field;
    if (op === "leave") continue;
    if (f === "cover") {   // the image is uploaded when the preview is made
      steps.push(op === "set_cover" ? { op, file: row.querySelector(".ed-file-in").files[0] || null } : { op });
      continue;
    }
    const v = row.querySelector(".ed-v").value;
    if (op === "clear") steps.push({ op, field: f });
    else if (op === "replace") {
      steps.push({ op, field: f, find: row.querySelector(".ed-find").value, with: row.querySelector(".ed-with").value,
        match: row.querySelector(".ed-word").checked ? "word" : "text", ignore_case: !row.querySelector(".ed-case").checked });
    } else if (f === "year") {
      const s = v.trim();
      steps.push({ op, field: f, value: !s ? null : /^\d{4}$/.test(s) ? Number(s) : NaN });
    } else steps.push({ op, field: f, value: v });
  }
  return steps;
}

$("#edForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (Ed.busy) return;
  const cleanup = Ed.tab === "cleanup";
  const steps = cleanup ? cleanupSteps() : edSteps();
  if (!steps.length) { toast(cleanup ? T.edNoRules : T.edPickOne); return; }
  if (steps.some((s) => Number.isNaN(s.value))) { toast(T.libBadYear(...(libRules.year || [1000, 9999]))); return; }
  const all = $('#edScope input[value="filter"]').checked && !$("#edScope").classList.contains("hidden");
  const pic = steps.find((s) => s.op === "set_cover");
  if (pic && !pic.file) { toast(T.edCoverNeeded); return; }
  Ed.busy = true;
  edReset();
  try {
    if (pic) {
      const form = new FormData();
      form.append("file", pic.file);
      const res = await request("/api/library/edits/covers", { method: "POST", body: form });
      if (!res.ok) throw await errorOf(res);
      pic.source = (await res.json()).source;
      delete pic.file;
    }
    const edit = await api("/api/library/edits", {
      method: "POST",
      body: JSON.stringify({ selection: all ? { filter: Ed.view.filter } : { ids: Ed.ids }, steps,
        ...(cleanup && cleanupSetId() ? { ruleset_id: cleanupSetId() } : {}) }),
    });
    Ed.edit = edit;
    await edShow(edit);
  } catch (err) {
    toast(err.message);
  } finally {
    Ed.busy = false;
  }
});

function edSummary(edit) {
  const c = edit.counts;
  $("#edCounts").textContent = c.changes ? T.edCounts(c.changes, c.changed) : T.edNothing;
  const notes = [];
  if (c.unchanged && c.changes) notes.push(T.edUnchanged(c.unchanged));
  const skipped = Object.entries(c.skipped_by_reason || {});
  if (skipped.length) notes.push(T.edSkipped(skipped.map(([r, n]) => `${T.edWhy(r)} (${num(n)})`).join(", ")));
  if (edit.state === "preview" && edit.resend && edit.resend.tracks) {
    notes.push(T.edResend(edit.resend.tracks, (edit.resend.bytes / 1048576).toLocaleString(lang, { maximumFractionDigits: 1 })));
  }
  $("#edNotes").textContent = notes.join(" ");
}

// The part of a value that changed, marked: what goes in <del>, what comes in <mark>.
function edDiff(before, after) {
  const a = String(before ?? ""), b = String(after ?? "");
  let p = 0;
  while (p < a.length && p < b.length && a[p] === b[p]) p += 1;
  let s = 0;
  while (s < a.length - p && s < b.length - p && a[a.length - 1 - s] === b[b.length - 1 - s]) s += 1;
  const part = (t, tag) => esc(t.slice(0, p)) + (t.length - p - s > 0 ? `<${tag}>${esc(t.slice(p, t.length - s))}</${tag}>` : "") + esc(t.slice(t.length - s));
  return [part(a, "del"), part(b, "mark")];
}

// The changes, grouped by track (they come adjacent): a checkbox per track
// and per change while it is a preview, then what happened once written.
async function edList(edit) {
  const page = await api(`/api/library/edits/${edit.id}/changes?limit=${SHOWN}`);
  Ed.items = page.items;
  edFilters(edit);
  edRender();
}

function edFilters(edit) {
  const fields = Object.keys(edit.counts.by_field || {});
  const chips = [["all", T.edAll]];
  if (Ed.items.some((c) => c.warnings.length)) chips.push(["warn", T.edWarned]);
  if (fields.length > 1) fields.forEach((f) => chips.push([`field:${f}`, T[FIELD_LABEL[f]] || f]));
  if (!chips.some(([k]) => k === Ed.filter)) Ed.filter = "all";
  $("#edFilter").innerHTML = chips.length > 1 ? chips.map(([k, label]) =>
    `<button type="button" class="chip" data-filter="${esc(k)}" aria-pressed="${k === Ed.filter}">${esc(label)}</button>`).join("") : "";
}

function edRender() {
  const open = Ed.edit && Ed.edit.state === "preview";
  const shown = Ed.items.filter((c) => Ed.filter === "all" || (Ed.filter === "warn" ? c.warnings.length
    : c.field === Ed.filter.slice(6)));
  const groups = [];
  for (const c of shown) {
    if (!groups.length || groups[groups.length - 1].id !== c.file_id) groups.push({ id: c.file_id, path: c.path, items: [] });
    groups[groups.length - 1].items.push(c);
  }
  const html = groups.map((g) => {
    const name = g.path.slice(g.path.lastIndexOf("/") + 1);
    const kept = g.items.some((c) => c.state === "pending");
    const can = g.items.some((c) => c.state === "pending" || c.state === "excluded");
    const box = open && can ? `<input type="checkbox" data-file="${g.id}" aria-label="${esc(T.edKeepTrack)}"${kept ? " checked" : ""} />` : "";
    return `<div class="ed-track">
      <label class="ed-file" title="${esc(g.path)}">${box}<span>${esc(name)}</span></label>
      ${g.items.map((c) => {
    const label = T[FIELD_LABEL[c.field]] || c.field;
    const warn = c.warnings.filter((w) => T.edWarn[w]).map((w) => T.edWarn[w]);
    const why = c.error ? serverError(c.error) : warn.join(" · ");
    const [was, now] = c.field === "cover"
      ? [esc(c.old ? T.edCoverHad : T.edCoverNone), esc(c.new ? T.edCoverNew : T.edCoverNone)]
      : edDiff(c.old, c.new);
    const cbox = open && c.state !== "blocked"
      ? `<input type="checkbox" data-change="${c.change_id}" aria-label="${esc(T.edKeepChange)}"${c.state === "pending" ? " checked" : ""} />` : "<span></span>";
    return `<div class="ed-row" data-state="${esc(c.state)}">${cbox}<span class="ed-change">${esc(label)}: <span class="ed-old">${was}</span> → <span class="ed-new">${now}</span></span><span class="ed-state">${esc(T.edState[c.state] || "")}</span>${why ? `<span class="ed-why">${esc(why)}</span>` : ""}</div>`;
  }).join("")}
    </div>`;
  });
  const more = Ed.edit ? Ed.edit.counts.changes - Ed.items.length : 0;
  $("#edList").innerHTML = html.join("") + (more > 0 ? `<p class="ed-more">${esc(T.edMore(more))}</p>` : "");
}

$("#edFilter").addEventListener("click", (e) => {
  const chip = e.target.closest("[data-filter]");
  if (!chip) return;
  Ed.filter = chip.dataset.filter;
  $("#edFilter").querySelectorAll("[data-filter]").forEach((b) => b.setAttribute("aria-pressed", String(b === chip)));
  edRender();
});

// Leaving out a track or a change, or putting it back, before Apply.
$("#edList").addEventListener("change", async (e) => {
  const box = e.target;
  const edit = Ed.edit;
  if (!edit || edit.state !== "preview" || !(box.dataset.file || box.dataset.change)) return;
  const what = box.dataset.file ? { files: [Number(box.dataset.file)] } : { changes: [Number(box.dataset.change)] };
  try {
    Ed.edit = await api(`/api/library/edits/${edit.id}`, {
      method: "PATCH", body: JSON.stringify({ [box.checked ? "include" : "exclude"]: what }),
    });
    edSummary(Ed.edit);
    edButton(Ed.edit);
    await edList(Ed.edit);
  } catch (err) {
    toast(err.message);
    box.checked = !box.checked;
  }
});

// The Apply button names the numbers; after an apply it offers to retry failures.
function edButton(edit) {
  const btn = $("#edApply");
  const s = edit.counts.by_state || {};
  const p = edit.progress;
  let text = "";
  if (edit.state === "preview" && s.pending) text = T.edApply(s.pending, p.files_total);
  else if (edit.state !== "applying" && edit.state !== "preview" && s.failed) text = T.edRetry(p.files_failed);
  btn.textContent = text;
  btn.classList.toggle("hidden", !text);
  btn.disabled = false;
  const undo = $("#edUndo");
  undo.classList.toggle("hidden", !edit.undoable || edit.state === "applying");
  undo.disabled = false;
}

async function edShow(edit) {
  edSummary(edit);
  $("#edPreview").classList.remove("hidden");
  await edList(edit);
  edButton(edit);
}

function edProgress(edit) {
  const p = edit.progress;
  const done = p.files_done + p.files_failed + p.files_conflict;
  const box = $("#edProgress");
  box.classList.toggle("hidden", edit.state !== "applying");
  $("#edProgressText").textContent = T.edWriting(done, p.files_total);
  $("#edProgressFill").style.width = `${p.files_total ? ((done / p.files_total) * 100).toFixed(1) : 0}%`;
}

function edResult(edit) {
  const p = edit.progress;
  const lines = [];
  if (p.files_done) lines.push(T.edDone(p.files_done));
  if (p.files_failed) lines.push(T.edFailed(p.files_failed));
  if (p.files_conflict) lines.push(T.edConflict(p.files_conflict));
  const el = $("#edResult");
  el.textContent = lines.join(" ");
  el.classList.toggle("hidden", !lines.length);
}

// Follow an apply until it ends; the panel may be closed meanwhile, the write goes on.
async function edFollow(id) {
  let edit;
  try {
    edit = await api(`/api/library/edits/${id}`);
  } catch {
    Ed.timer = setTimeout(() => edFollow(id), POLL_MS * 3);
    return;
  }
  if (!Ed.edit || Ed.edit.id !== id) return;
  Ed.edit = edit;
  edProgress(edit);
  if (edit.state === "applying") {
    Ed.timer = setTimeout(() => edFollow(id), POLL_MS);
    return;
  }
  edResult(edit);
  await edList(edit);
  edButton(edit);
  libChanged();
}

$("#edApply").addEventListener("click", async () => {
  const edit = Ed.edit;
  if (!edit || Ed.busy) return;
  const btn = $("#edApply");
  btn.disabled = true;
  Ed.busy = true;
  try {
    Ed.edit = await api(`/api/library/edits/${edit.id}/apply`, { method: "POST" });
    btn.classList.add("hidden");
    $("#edResult").classList.add("hidden");
    edProgress(Ed.edit);
    edFollow(edit.id);
  } catch (err) {
    toast(err.message);
    btn.disabled = false;
  } finally {
    Ed.busy = false;
  }
});

// Undo: a new edit that writes the old values back, followed like an apply.
async function edUndoStart(id) {
  const edit = await api(`/api/library/edits/${id}/undo`, { method: "POST" });
  toast(T.edUndoing);
  return edit;
}
$("#edUndo").addEventListener("click", async () => {
  const edit = Ed.edit;
  if (!edit || Ed.busy) return;
  Ed.busy = true;
  $("#edUndo").disabled = true;
  try {
    Ed.edit = await edUndoStart(edit.id);
    $("#edUndo").classList.add("hidden");
    $("#edResult").classList.add("hidden");
    edProgress(Ed.edit);
    edFollow(Ed.edit.id);
  } catch (err) {
    toast(err.message);
    $("#edUndo").disabled = false;
  } finally {
    Ed.busy = false;
  }
});

// A language change keeps what was chosen in the rows; only their words follow.
function edRowTexts() {
  for (const row of $("#edFields").querySelectorAll(".ed-frow")) {
    const name = T[FIELD_LABEL[row.dataset.field]];
    row.querySelector(".ed-fname").textContent = name;
    row.querySelectorAll(".ed-op option").forEach((o) => { o.textContent = (T.edOps[o.value] || T.edCoverOps[o.value]); });
    if (row.dataset.field === "cover") continue;
    row.querySelector(".ed-v").placeholder = T.edValuePh;
    row.querySelector(".ed-find").placeholder = T.edFind;
    row.querySelector(".ed-with").placeholder = T.edWith;
    const [word, kase] = row.querySelectorAll(".ed-check");
    word.lastChild.textContent = ` ${T.edWord}`;
    kase.lastChild.textContent = ` ${T.edCase}`;
  }
}

// ------------------------------------------------------------ history
const histModal = $("#edHistoryModal");
const edLabel = (label) => (label.startsWith("undo: ") ? T.edUndoLabel(edLabel(label.slice(6))) : label);

function edLineHtml(e) {
  const when = new Date(e.applied_at || e.created_at).toLocaleString(lang, { dateStyle: "medium", timeStyle: "short" });
  const bits = [when];
  if (e.counts.changes) bits.push(T.edCounts(e.counts.changes, e.counts.changed));
  if (e.undone) bits.push(T.edLineUndone[e.undone]);
  else if (e.purged) bits.push(T.edLineGone);
  if (e.progress.files_failed) bits.push(T.edFailed(e.progress.files_failed));
  const undo = e.undoable ? `<button type="button" class="btn btn-quiet" data-undo="${e.id}">${esc(T.edUndo)}</button>` : "";
  return `<div class="ed-row ed-line" data-id="${e.id}">
    <span class="ed-line-what">${esc(edLabel(e.label))}</span>${undo}
    <span class="ed-line-meta">${esc(bits.join(" · "))}</span>
  </div>`;
}

async function edHistory() {
  try {
    const page = await api("/api/library/edits?limit=50");
    $("#edHistoryList").innerHTML = page.items.map(edLineHtml).join("");
    $("#edHistoryEmpty").classList.toggle("hidden", page.items.length > 0);
  } catch (err) { toast(err.message); }
}

// Wait for an undo started from the history, then show where things are.
async function edHistoryFollow(id) {
  try {
    const e = await api(`/api/library/edits/${id}`);
    if (e.state === "applying") { setTimeout(() => edHistoryFollow(id), POLL_MS); return; }
    const p = e.progress;
    toast([p.files_done && T.edDone(p.files_done), p.files_failed && T.edFailed(p.files_failed),
      p.files_conflict && T.edConflict(p.files_conflict)].filter(Boolean).join(" ") || T.edNothing);
  } catch (err) { toast(err.message); }
  libChanged();
  if (!histModal.classList.contains("hidden")) edHistory();
}

$("#libHistoryBtn").addEventListener("click", () => {
  histModal.classList.remove("hidden");
  edHistory();
});
$("#edHistoryList").addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-undo]");
  if (!btn) return;
  btn.disabled = true;
  try {
    const started = await edUndoStart(Number(btn.dataset.undo));
    edHistoryFollow(started.id);
  } catch (err) {
    toast(err.message);
    btn.disabled = false;
  }
});

// Closed: stop following; a running apply carries on and the list reloads by itself.
new MutationObserver(() => {
  if (modal.classList.contains("hidden")) clearTimeout(Ed.timer);
}).observe(modal, { attributes: true, attributeFilter: ["class"] });

// A language change: the texts set from code follow.
new MutationObserver(() => {
  if (!histModal.classList.contains("hidden")) edHistory();
  if (modal.classList.contains("hidden")) return;
  $("#edTitle").textContent = T.edTitle(Ed.ids.length);
  edScopeTexts();
  edRowTexts();
  if (Ed.edit) { edSummary(Ed.edit); edButton(Ed.edit); edList(Ed.edit).catch(() => {}); }
}).observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });

addSelAction("edit", edOpen);
