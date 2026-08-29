/* GetSetMix setup wizard.
   Served by the server, opened from the DJ machine's browser. The companion
   has no UI of its own — what it finds shows up here. */
"use strict";

const STR = {
  en: {
    tokenPrompt: "Access token:",
    next: "Next", back: "Back", finish: "Finish", saving: "Saving…",
    pickLibrary: "Choose the library folder first",
    pickDelivery: "Pick how the files get across",
    needMachine: "Add a machine, or pair the companion",
    needRoot: "Enter the folder as that machine sees it",
    added: "Machine added", removed: "Machine removed",
    remove: "Remove", rechecking: "Re-checking…", allGood: "Everything checks out",
    davIncomplete: "Fill in the WebDAV URL, user and app password",
    paired: n => `${n} machine(s) paired`,
    manualXml: "In Rekordbox: Preferences ▸ Advanced ▸ Database ▸ rekordbox xml → ",
  },
  it: {
    tokenPrompt: "Token di accesso:",
    next: "Avanti", back: "Indietro", finish: "Fine", saving: "Salvataggio…",
    pickLibrary: "Scegli prima la cartella della libreria",
    pickDelivery: "Scegli come arrivano i file",
    needMachine: "Aggiungi una macchina o accoppia il companion",
    needRoot: "Inserisci la cartella come la vede quella macchina",
    added: "Macchina aggiunta", removed: "Macchina rimossa",
    remove: "Rimuovi", rechecking: "Ricontrollo…", allGood: "Va tutto bene",
    davIncomplete: "Inserisci URL, utente e password app di WebDAV",
    paired: n => `${n} macchina/e accoppiate`,
    manualXml: "In Rekordbox: Preferenze ▸ Avanzate ▸ Database ▸ rekordbox xml → ",
  },
};
let T = STR.en;

let step = 0;
let settings = {};
let profiles = [];
let pairPoll = null;
let pairedBefore = 0;
const LAST = 3;

// -------------------------------------------------------------- navigation
function showStep(n) {
  step = Math.max(0, Math.min(LAST, n));
  document.querySelectorAll(".step").forEach((el) =>
    el.classList.toggle("active", Number(el.dataset.step) === step));
  document.querySelectorAll("#steps li").forEach((el) => {
    const i = Number(el.dataset.step);
    el.classList.toggle("current", i === step);
    el.classList.toggle("done", i < step);
  });
  $("#btnBack").classList.toggle("hidden", step === 0);
  $("#btnNext").textContent = step === LAST ? T.finish : T.next;
  stopPairPolling();
  if (step === 2 && currentMachineMode() === "pair") startPairing();
  if (step === 3) runVerify();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function currentDelivery() {
  const el = document.querySelector('input[name="delivery"]:checked');
  return el ? el.value : "";
}
function currentMachineMode() {
  const el = document.querySelector('input[name="machmode"]:checked');
  return el ? el.value : "";
}

// ------------------------------------------------------------------ step 1
async function saveLibrary() {
  const root = $("#setLibrary").value.trim();
  if (!root) { toast(T.pickLibrary); return false; }
  await api("/api/settings", { method: "PUT", body: JSON.stringify({ library_root: root }) });
  return true;
}

async function refreshLibraryCheck() {
  try {
    const health = await api("/api/health/link");
    const relevant = health.checks.filter((c) => c.id === "library");
    $("#libCheck").innerHTML = checksHtml(relevant);
  } catch { /* the verify step will say so */ }
}

// ------------------------------------------------------------------ step 2
function syncDeliveryUi() {
  const mode = currentDelivery();
  document.querySelectorAll("#deliveryChoices .choice").forEach((el) =>
    el.classList.toggle("selected", el.querySelector("input").checked));
  $("#webdavFields").classList.toggle("hidden", mode !== "webdav");
}

async function saveDelivery() {
  const mode = currentDelivery();
  if (!mode) { toast(T.pickDelivery); return false; }
  const patch = { delivery_mode: mode === "webdav" ? "webdav" : "filesystem" };
  if (mode === "webdav") {
    patch.webdav_url = $("#setDavUrl").value.trim();
    patch.webdav_user = $("#setDavUser").value.trim();
    patch.webdav_pass = $("#setDavPass").value;
    patch.webdav_root = $("#setDavRoot").value.trim();
    const havePass = patch.webdav_pass || settings.webdav_pass_set;
    if (!patch.webdav_url || !patch.webdav_user || !havePass) {
      toast(T.davIncomplete); return false;
    }
  }
  settings = await api("/api/settings", { method: "PUT", body: JSON.stringify(patch) });
  return true;
}

// ------------------------------------------------------------------ step 3
function syncMachineUi() {
  const mode = currentMachineMode();
  document.querySelectorAll("#machineChoices .choice").forEach((el) =>
    el.classList.toggle("selected", el.querySelector("input").checked));
  $("#pairPane").classList.toggle("hidden", mode !== "pair");
  $("#manualPane").classList.toggle("hidden", mode !== "manual");
  if (mode === "pair") startPairing(); else stopPairPolling();
  if (mode === "manual") { renderMachines(); refreshPreview(); }
}

async function startPairing() {
  stopPairPolling();
  await loadProfiles();
  pairedBefore = profiles.filter((p) => p.paired).length;
  const origin = location.origin;
  $("#pairSnippet").textContent =
    `curl -fsSLO ${origin}/link/gsm_link.py\n` +
    `python3 gsm_link.py pair --server ${origin} --code `;
  try {
    const res = await api("/api/link/code", { method: "POST", body: JSON.stringify({}) });
    $("#pairCode").textContent = res.code;
    $("#pairSnippet").textContent =
      `curl -fsSLO ${origin}/link/gsm_link.py\n` +
      `python3 gsm_link.py pair --server ${origin} --code ${res.code}`;
  } catch (e) { toast(e.message); return; }
  // The agent claims the code out of band, so poll for the new profile.
  pairPoll = setInterval(checkPaired, 3000);
}

function stopPairPolling() {
  clearInterval(pairPoll);
  pairPoll = null;
}

async function checkPaired() {
  await loadProfiles();
  const paired = profiles.filter((p) => p.paired);
  if (paired.length > pairedBefore) {
    stopPairPolling();
    $("#pairWaiting").classList.add("hidden");
    toast(T.paired(paired.length));
  }
  renderMachines("#pairedList");
}

async function loadProfiles() {
  try { profiles = (await api("/api/profiles")).profiles || []; } catch { /* noop */ }
}

function machineHtml(p) {
  const root = p.library_root || "—";
  return `<div class="machine" data-id="${esc(p.id)}">
    <div class="machine-head">
      <strong>${esc(p.name || p.id)}</strong>
      <span class="machine-os">${esc(p.os)}</span>
      ${p.paired ? '<span class="machine-os">paired</span>' : ""}
      <span class="spacer"></span>
      <button class="btn btn-ghost" data-remove="${esc(p.id)}">${esc(T.remove)}</button>
    </div>
    <div class="machine-path">${esc(root)}</div>
    <div class="machine-path">${esc(p.dj_xml_path || "")}</div>
  </div>`;
}

function renderMachines(target) {
  const html = profiles.map(machineHtml).join("");
  for (const sel of target ? [target] : ["#machineList", "#pairedList"]) {
    const el = $(sel);
    if (el) el.innerHTML = html;
  }
}

async function addMachine() {
  const root = $("#setMachRoot").value.trim();
  if (!root) { toast(T.needRoot); return; }
  try {
    await api("/api/profiles", {
      method: "POST",
      body: JSON.stringify({
        name: $("#setMachName").value.trim() || "DJ machine",
        os: $("#setMachOs").value,
        library_root: root,
      }),
    });
    $("#setMachName").value = "";
    $("#setMachRoot").value = "";
    toast(T.added);
    await loadProfiles();
    renderMachines();
    refreshPreview();
  } catch (e) { toast(e.message); }
}

// The live preview is what turns the path mapping from a guess into something
// you can eyeball before committing to it.
let previewTimer = null;
function refreshPreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(async () => {
    const box = $("#pathPreview");
    const root = $("#setMachRoot").value.trim();
    if (!root) { box.innerHTML = ""; box.classList.remove("bad"); return; }
    try {
      const r = await api("/api/profiles/preview", {
        method: "POST",
        body: JSON.stringify({
          os: $("#setMachOs").value, library_root: root,
          name: $("#setMachName").value.trim(),
        }),
      });
      box.classList.toggle("bad", !r.mapped);
      box.innerHTML = `
        <div class="row"><span class="k">server</span><span>${esc(r.server_path)}</span></div>
        <div class="row"><span class="k">that machine</span><span>${esc(r.dj_path)}</span></div>
        <div class="row"><span class="k">in the xml</span><span>${esc(r.location)}</span></div>
        <div class="row"><span class="k">xml file</span><span>${esc(r.dj_xml_path)}</span></div>`;
    } catch (e) { box.textContent = e.message; }
  }, 250);
}

// ------------------------------------------------------------------ step 4
async function runVerify() {
  $("#verifyChecks").innerHTML = `<div class="waiting"><span class="dashes"><i></i><i></i><i></i></span><span>${esc(T.rechecking)}</span></div>`;
  try {
    const health = await api("/api/health/link");
    // The "you haven't run setup" nag is noise inside setup itself.
    const checks = health.checks.filter((c) => c.id !== "setup");
    $("#verifyChecks").innerHTML = checksHtml(checks) ||
      `<div class="check is-ok"><span class="mark">✓</span><div class="title">${esc(T.allGood)}</div></div>`;
  } catch (e) { toast(e.message); }
  await loadProfiles();
  const paths = profiles.map((p) => p.dj_xml_path).filter(Boolean);
  $("#rekordboxTodo").textContent = paths.length ? T.manualXml + paths.join("  ·  ") : "";
}

// -------------------------------------------------------------------- wire
$("#btnNext").addEventListener("click", async () => {
  try {
    if (step === 0 && !(await saveLibrary())) return;
    if (step === 1 && !(await saveDelivery())) return;
    if (step === 2) {
      await loadProfiles();
      if (!profiles.length && currentDelivery() !== "same") { toast(T.needMachine); return; }
    }
    if (step === LAST) {
      await api("/api/settings", { method: "PUT", body: JSON.stringify({ setup_complete: true }) });
      location.href = "/";
      return;
    }
    showStep(step + 1);
    if (step === 0) refreshLibraryCheck();
  } catch (e) { toast(e.message); }
});

$("#btnBack").addEventListener("click", () => showStep(step - 1));
$("#btnSkip").addEventListener("click", async () => {
  try { await api("/api/settings", { method: "PUT", body: JSON.stringify({ setup_complete: true }) }); }
  catch { /* leaving anyway */ }
  location.href = "/";
});

$("#deliveryChoices").addEventListener("change", syncDeliveryUi);
$("#machineChoices").addEventListener("change", syncMachineUi);
$("#btnAddMachine").addEventListener("click", addMachine);
$("#setMachRoot").addEventListener("input", refreshPreview);
$("#setMachName").addEventListener("input", refreshPreview);
$("#setMachOs").addEventListener("change", refreshPreview);
$("#setLibrary").addEventListener("input", () => {
  clearTimeout(refreshLibraryCheck._t);
  refreshLibraryCheck._t = setTimeout(refreshLibraryCheck, 400);
});

document.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-remove]");
  if (!btn) return;
  try {
    await api(`/api/profiles/${encodeURIComponent(btn.dataset.remove)}`, { method: "DELETE" });
    toast(T.removed);
    await loadProfiles();
    renderMachines();
  } catch (err) { toast(err.message); }
});

wireModals();
wirePicker({ library: { input: "#setLibrary", mode: "dir", ext: "" } });

(async function init() {
  try {
    settings = await api("/api/settings");
  } catch { settings = {}; }
  T = STR[settings.language] || STR.en;
  document.documentElement.lang = settings.language || "en";
  applyTheme(settings.theme || "dark");
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const v = T[el.dataset.i18n];
    if (typeof v === "string") el.textContent = v;
  });

  $("#setLibrary").value = settings.library_root || "";
  $("#setDavUrl").value = settings.webdav_url || "";
  $("#setDavUser").value = settings.webdav_user || "";
  $("#setDavRoot").value = settings.webdav_root || "";
  if (settings.webdav_pass_set) $("#setDavPass").placeholder = "••••••••  (unchanged)";

  const delivery = settings.delivery_mode === "webdav" ? "webdav" : "";
  if (delivery) {
    const el = document.querySelector(`input[name="delivery"][value="${delivery}"]`);
    if (el) el.checked = true;
  }
  syncDeliveryUi();

  await loadProfiles();
  const mode = profiles.some((p) => p.paired) ? "pair" : "manual";
  const el = document.querySelector(`input[name="machmode"][value="${mode}"]`);
  if (el) el.checked = true;
  document.querySelectorAll("#machineChoices .choice").forEach((c) =>
    c.classList.toggle("selected", c.querySelector("input").checked));
  $("#pairPane").classList.toggle("hidden", mode !== "pair");
  $("#manualPane").classList.toggle("hidden", mode !== "manual");
  renderMachines();

  showStep(0);
  refreshLibraryCheck();
})();
