/* GetSetMix: the Cleanup tab of the edit panel (docs/design/batch-editing.md
   4.2, 4.3): pick a rule set, switch its rules on and off, give them
   parameters, reorder them, and save the result as a set of your own. The
   built-in set is never changed: Save as new copies it. The rules and their
   names come from the server's catalogue (/api/library/rules); the panel in
   edits.js reads the steps from here when it makes a preview. */
import { $, api, askConfirm, esc, toast } from "./core.js";
import { lang, STR, T } from "./i18n.js";

Object.assign(STR.en, {
  edTabFields: "Fields", edTabCleanup: "Cleanup", edRuleSet: "Rule set",
  edSetSave: "Save", edSetCopy: "Save as new", edSetDelete: "Delete",
  edSetName: "Name of the new set", edSetSaved: "Rule set saved", edSetDeleted: "Rule set removed",
  edSetDeleteAsk: (n) => `Remove the rule set “${n}”?`, edSetBuiltin: "Built in: save a copy to change it.",
  edUp: "Move up", edDown: "Move down", edSettings: "Settings", edNoRules: "Switch on at least one rule.",
  edBuiltinName: { "Standard cleanup": "Standard cleanup" },
  edParam: { underscores: "Underscores are spaces", phrases: "Phrases to remove", when: "When",
    spelling: "Spelling", to: "Into", labels: "Mix names to remove", mix_words: "Mix words",
    from: "Separators to replace", keep: "Keep as they are", scope: "Which values",
    small_words: "Small words", aliases: "Spellings (from = to)", remove: "Remove it from where it was" },
});
Object.assign(STR.it, {
  edTabFields: "Campi", edTabCleanup: "Pulizia", edRuleSet: "Insieme di regole",
  edSetSave: "Salva", edSetCopy: "Salva come nuovo", edSetDelete: "Elimina",
  edSetName: "Nome del nuovo insieme", edSetSaved: "Insieme di regole salvato", edSetDeleted: "Insieme di regole eliminato",
  edSetDeleteAsk: (n) => `Eliminare l'insieme di regole “${n}”?`, edSetBuiltin: "Predefinito: salvane una copia per cambiarlo.",
  edUp: "Sposta su", edDown: "Sposta giù", edSettings: "Impostazioni", edNoRules: "Attiva almeno una regola.",
  edBuiltinName: { "Standard cleanup": "Pulizia standard" },
  edParam: { underscores: "I trattini bassi sono spazi", phrases: "Frasi da togliere", when: "Quando",
    spelling: "Grafia", to: "In", labels: "Nomi di mix da togliere", mix_words: "Parole dei mix",
    from: "Separatori da sostituire", keep: "Lascia come sono", scope: "Quali valori",
    small_words: "Parole brevi", aliases: "Grafie (da = a)", remove: "Toglilo da dove era" },
});

const C = { catalogue: null, byId: {}, sets: [], set: null, rules: [] };
const list = $("#edRules");

// Each rule as a step, with only the parameters that differ from its defaults.
export function cleanupSteps() {
  return C.rules.filter((r) => r.on).map((r) => ({
    rule: r.rule, ...(r.fields ? { fields: r.fields } : {}),
    ...(Object.keys(r.params).length ? { params: r.params } : {}),
  }));
}
export const cleanupSetId = () => (C.set ? C.set.id : null);

async function loadCatalogue() {
  if (C.catalogue) return;
  C.catalogue = await api("/api/library/rules");
  C.byId = Object.fromEntries(C.catalogue.rules.map((r) => [r.id, r]));
}

export async function cleanupOpen() {
  try {
    await loadCatalogue();
    await loadSets(C.set ? C.set.id : null);
  } catch (err) { toast(err.message); }
}

// A set's name as shown: a built-in set speaks the UI's language.
export const setName = (s) => (s.builtin && T.edBuiltinName[s.name]) || s.name;

// The rule sets for one tap (the phone's first step): each with its rules'
// names, in the UI's language, from the catalogue.
export async function quickSets() {
  await loadCatalogue();
  const sets = await api("/api/library/rulesets");
  return sets.map((s) => ({ id: s.id, name: setName(s),
    rules: s.steps.filter((x) => x.rule && C.byId[x.rule]).map((x) => say(C.byId[x.rule].name)) }));
}

async function loadSets(id) {
  C.sets = await api("/api/library/rulesets");
  choose(id);
}

function choose(id) {
  C.set = C.sets.find((s) => s.id === id) || C.sets[0] || null;
  C.rules = (C.set ? C.set.steps : []).filter((s) => s.rule && C.byId[s.rule])
    .map((s) => ({ rule: s.rule, on: true, params: { ...(s.params || {}) }, fields: s.fields }));
  render();
}

const say = (pair) => (pair ? pair[lang] || pair.en : "");
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

function paramInput(r, p) {
  const v = r.params[p.name] ?? p.default;
  const attrs = `data-param="${esc(p.name)}" aria-label="${esc(T.edParam[p.name] || p.name)}"`;
  if (p.type === "bool") return `<input type="checkbox" ${attrs}${v ? " checked" : ""} />`;
  if (p.type === "choice") {
    return `<select class="ed-select" ${attrs}>${p.choices.map((c) =>
      `<option value="${esc(c)}"${c === v ? " selected" : ""}>${esc(c)}</option>`).join("")}</select>`;
  }
  if (p.type === "string_list") return `<textarea rows="3" ${attrs}>${esc(v.join("\n"))}</textarea>`;
  if (p.type === "string_map") {
    return `<textarea rows="3" ${attrs}>${esc(Object.entries(v).map(([k, x]) => `${k} = ${x}`).join("\n"))}</textarea>`;
  }
  return `<input type="text" ${attrs} value="${esc(v)}" />`;
}

function ruleHtml(r, i) {
  const c = C.byId[r.rule];
  const params = c.params.length ? `<details class="ed-rule-params"><summary>${esc(T.edSettings)}</summary>
    ${c.params.map((p) => `<label class="ed-param"><span>${esc(T.edParam[p.name] || p.name)}</span>${paramInput(r, p)}</label>`).join("")}
    </details>` : "";
  return `<li class="ed-rule${r.on ? "" : " is-off"}" data-i="${i}">
    <label class="ed-rule-on"><input type="checkbox" data-on${r.on ? " checked" : ""} /> <span>${esc(say(c.name))}</span></label>
    <span class="ed-rule-move">
      <button type="button" class="icon-btn" data-move="-1" aria-label="${esc(T.edUp)}" title="${esc(T.edUp)}"${i ? "" : " disabled"}>↑</button>
      <button type="button" class="icon-btn" data-move="1" aria-label="${esc(T.edDown)}" title="${esc(T.edDown)}"${i < C.rules.length - 1 ? "" : " disabled"}>↓</button>
    </span>
    <small class="ed-rule-desc">${esc(say(c.description))}</small>
    ${params}
  </li>`;
}

function render() {
  $("#edSet").innerHTML = C.sets.map((s) =>
    `<option value="${s.id}"${C.set && s.id === C.set.id ? " selected" : ""}>${esc(setName(s))}</option>`).join("");
  const builtin = !C.set || C.set.builtin;
  $("#edSetSave").classList.toggle("hidden", builtin);
  $("#edSetDelete").classList.toggle("hidden", builtin);
  $("#edSetNote").classList.toggle("hidden", !builtin);
  $("#edSetNote").textContent = T.edSetBuiltin;
  $("#edSetNew").classList.add("hidden");
  // the open settings stay open across a redraw
  const open = new Set([...list.querySelectorAll(".ed-rule-params[open]")].map((d) => d.closest(".ed-rule").dataset.i));
  list.innerHTML = C.rules.map(ruleHtml).join("");
  open.forEach((i) => { const d = list.querySelector(`.ed-rule[data-i="${i}"] .ed-rule-params`); if (d) d.open = true; });
}

function readParam(el, p) {
  if (p.type === "bool") return el.checked;
  if (p.type === "string_list") return el.value.split("\n").map((s) => s.trim()).filter(Boolean);
  if (p.type === "string_map") {
    return Object.fromEntries(el.value.split("\n").map((l) => l.split("=").map((s) => s.trim()))
      .filter((kv) => kv.length === 2 && kv[0]));
  }
  return el.value;
}

list.addEventListener("change", (e) => {
  const li = e.target.closest(".ed-rule");
  if (!li) return;
  const r = C.rules[Number(li.dataset.i)];
  if (e.target.matches("[data-on]")) {
    r.on = e.target.checked;
    li.classList.toggle("is-off", !r.on);
  } else if (e.target.dataset.param) {
    const p = C.byId[r.rule].params.find((x) => x.name === e.target.dataset.param);
    const v = readParam(e.target, p);
    if (same(v, p.default)) delete r.params[p.name]; else r.params[p.name] = v;
  }
  list.dispatchEvent(new CustomEvent("cleanup-change", { bubbles: true }));
});
list.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-move]");
  if (!btn) return;
  const i = Number(btn.closest(".ed-rule").dataset.i);
  const j = i + Number(btn.dataset.move);
  if (j < 0 || j >= C.rules.length) return;
  [C.rules[i], C.rules[j]] = [C.rules[j], C.rules[i]];
  render();
  list.querySelector(`.ed-rule[data-i="${j}"] [data-move="${btn.dataset.move}"]`)?.focus();
  list.dispatchEvent(new CustomEvent("cleanup-change", { bubbles: true }));
});

$("#edSet").addEventListener("change", (e) => {
  choose(Number(e.target.value));
  list.dispatchEvent(new CustomEvent("cleanup-change", { bubbles: true }));
});
$("#edSetSave").addEventListener("click", async () => {
  if (!C.set || C.set.builtin) return;
  if (!cleanupSteps().length) { toast(T.edNoRules); return; }
  try {
    await api(`/api/library/rulesets/${C.set.id}`, { method: "PUT", body: JSON.stringify({ steps: cleanupSteps() }) });
    toast(T.edSetSaved);
    await loadSets(C.set.id);
  } catch (err) { toast(err.message); }
});
$("#edSetCopy").addEventListener("click", () => {
  $("#edSetNew").classList.remove("hidden");
  const name = $("#edSetName");
  name.value = "";
  name.focus();
});
$("#edSetNewSave").addEventListener("click", async () => {
  const name = $("#edSetName").value.trim();
  if (!name) { $("#edSetName").focus(); return; }
  if (!cleanupSteps().length) { toast(T.edNoRules); return; }
  try {
    const made = await api("/api/library/rulesets", { method: "POST", body: JSON.stringify({ name, steps: cleanupSteps() }) });
    toast(T.edSetSaved);
    await loadSets(made.id);
  } catch (err) { toast(err.message); }
});
$("#edSetDelete").addEventListener("click", async () => {
  if (!C.set || C.set.builtin) return;
  if (!(await askConfirm(T.edSetDeleteAsk(setName(C.set)), T.edSetDelete, T.cancel, { danger: true }))) return;
  try {
    await api(`/api/library/rulesets/${C.set.id}`, { method: "DELETE" });
    toast(T.edSetDeleted);
    await loadSets(null);
  } catch (err) { toast(err.message); }
});

// A language change: rule names and descriptions follow, what was set stays.
new MutationObserver(() => { if (C.catalogue) render(); })
  .observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });
