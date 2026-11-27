/* GetSetMix: batch editing (docs/design/batch-editing.md 4.3, 4.4), the first
   slice: one field for the selected tracks. The bulk bar's *Edit tags* opens
   a panel; *Preview* asks the server for the changes, which it stores, and
   lists them; *Apply* writes exactly those, one file at a time, and the panel
   follows the progress. Files that failed can be tried again; a file changed
   meanwhile is left alone and said so. *Undo* writes the old values back,
   from the panel or from the History (slice 3). Loaded by app.js. */
import { $, api, esc, libRules, toast } from "./core.js";
import { lang, num, plural, serverError, STR, T } from "./i18n.js";
import { addSelAction, libChanged, selectedIds } from "./library.js";

const SKIP_IT = {
  "read-only format": "formato in sola lettura", "damaged file": "file danneggiato",
  "in the trash": "nel cestino", "not on disk": "non sul disco",
  "not in the library": "non più nella libreria", "no such track": "brano non trovato",
};
Object.assign(STR.en, {
  edEditTags: "Edit tags",
  edTitle: (n) => plural(n, "Edit tags of 1 track", "Edit tags of {n} tracks"),
  edField: "Field", edValue: "New value", edPreview: "Preview",
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
  edField: "Campo", edValue: "Nuovo valore", edPreview: "Anteprima",
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
  year: "libYear", comment: "libComment" };

const modal = $("#edModal");
const field = $("#edField");
const value = $("#edValue");
const Ed = { ids: [], edit: null, timer: null, busy: false };

function edReset() {
  clearTimeout(Ed.timer);
  Ed.edit = null;
  $("#edPreview").classList.add("hidden");
  $("#edApply").classList.add("hidden");
  $("#edUndo").classList.add("hidden");
  $("#edResult").classList.add("hidden");
  $("#edProgress").classList.add("hidden");
  $("#edList").innerHTML = "";
}

function edOpen() {
  Ed.ids = selectedIds();
  if (!Ed.ids.length) return;
  edReset();
  $("#edTitle").textContent = T.edTitle(Ed.ids.length);
  value.value = "";
  edField();
  modal.classList.remove("hidden");
  value.focus();
}

// The value box follows the field: the genre list for a genre, digits for a year.
function edField() {
  const f = field.value;
  if (f === "genre") value.setAttribute("list", "genres"); else value.removeAttribute("list");
  value.inputMode = f === "year" ? "numeric" : "text";
  value.maxLength = f === "year" ? 4 : 524288;
}
field.addEventListener("change", () => { edField(); edReset(); value.focus(); });
value.addEventListener("input", () => { if (Ed.edit && Ed.edit.state === "preview") edReset(); });

// What the step sets: the year as a number (empty clears it), text as typed.
function edValue() {
  if (field.value !== "year") return value.value;
  const s = value.value.trim();
  if (!s) return null;
  return /^\d{4}$/.test(s) ? Number(s) : NaN;
}

$("#edForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (Ed.busy) return;
  const v = edValue();
  if (Number.isNaN(v)) { toast(T.libBadYear(...(libRules.year || [1000, 9999]))); value.focus(); return; }
  Ed.busy = true;
  edReset();
  try {
    const edit = await api("/api/library/edits", {
      method: "POST",
      body: JSON.stringify({ selection: { ids: Ed.ids }, steps: [{ op: "set", field: field.value, value: v }] }),
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
  $("#edNotes").textContent = notes.join(" ");
}

// The changes as rows: the track, then before -> after, and once written, what happened.
async function edList(edit) {
  const page = await api(`/api/library/edits/${edit.id}/changes?limit=${SHOWN}`);
  const rows = page.items.map((c) => {
    const name = c.path.slice(c.path.lastIndexOf("/") + 1);
    const label = T[FIELD_LABEL[c.field]] || c.field;
    const warn = c.warnings.filter((w) => T.edWarn[w]).map((w) => T.edWarn[w]);
    const why = c.error ? serverError(c.error) : warn.join(" · ");
    return `<div class="ed-row" data-state="${esc(c.state)}">
      <span class="ed-file" title="${esc(c.path)}">${esc(name)}</span>
      <span class="ed-state">${esc(T.edState[c.state] || "")}</span>
      <span class="ed-change">${esc(label)}: <span class="ed-old">${esc(c.old ?? "")}</span> → <span class="ed-new">${esc(c.new ?? "")}</span></span>
      ${why ? `<span class="ed-why">${esc(why)}</span>` : ""}
    </div>`;
  });
  const more = edit.counts.changes - page.items.length;
  $("#edList").innerHTML = rows.join("") + (more > 0 ? `<p class="ed-more">${esc(T.edMore(more))}</p>` : "");
}

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
  if (Ed.edit) { edSummary(Ed.edit); edButton(Ed.edit); edList(Ed.edit).catch(() => {}); }
}).observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });

addSelAction("edit", edOpen);
