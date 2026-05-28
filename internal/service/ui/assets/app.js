const batchIdEl = document.getElementById("batch-id");
const runningEl = document.getElementById("batch-running");
const statusMessageEl = document.getElementById("status-message");
const tokenInput = document.getElementById("token");
const sourceInput = document.getElementById("source-url");
const previewTitleEl = document.getElementById("preview-title");
const previewMetaEl = document.getElementById("preview-meta");
const tracksEl = document.getElementById("tracks");

let batchId = null;
let pollTimer = null;

function loadToken() {
  return localStorage.getItem("gsm-token") || "";
}

function saveToken(token) {
  localStorage.setItem("gsm-token", token);
}

function authHeaders() {
  const token = loadToken().trim();
  if (!token) {
    return {};
  }
  return { Authorization: `Bearer ${token}` };
}

function setStatus(message) {
  statusMessageEl.textContent = message;
}

async function apiRequest(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...authHeaders(),
    ...options.headers,
  };
  const resp = await fetch(path, { ...options, headers });
  if (resp.status === 401) {
    setStatus("Unauthorized. Add a token.");
  }
  return resp;
}

async function createBatch() {
  const resp = await apiRequest("/batches", { method: "POST", body: "{}" });
  if (!resp.ok) {
    setStatus("Failed to create batch.");
    return;
  }
  const body = await resp.json();
  batchId = body.batch_id;
  batchIdEl.textContent = batchId;
  setStatus("Batch created.");
  startPolling();
}

async function stageTrack() {
  if (!batchId) {
    setStatus("Create a batch first.");
    return;
  }
  const sourceURL = sourceInput.value.trim();
  if (!sourceURL) {
    setStatus("Enter a Source URL.");
    return;
  }
  const resp = await apiRequest(`/batches/${batchId}/items`, {
    method: "POST",
    body: JSON.stringify({ source_url: sourceURL }),
  });
  if (!resp.ok) {
    const errBody = await resp.json().catch(() => ({}));
    setStatus(errBody.error || "Failed to stage track.");
    return;
  }
  const body = await resp.json();
  previewTitleEl.textContent = `${body.metadata.title} — ${body.metadata.artist}`;
  previewMetaEl.textContent = body.metadata.album || body.metadata.genre || "Metadata previewed.";
  sourceInput.value = "";
  setStatus("Track staged.");
  await refreshBatch();
}

async function startBatch() {
  if (!batchId) {
    setStatus("Create a batch first.");
    return;
  }
  const resp = await apiRequest(`/batches/${batchId}/start`, { method: "POST", body: "{}" });
  if (!resp.ok) {
    const errBody = await resp.json().catch(() => ({}));
    setStatus(errBody.error || "Failed to start batch.");
    return;
  }
  setStatus("Batch started.");
  await refreshBatch();
}

function renderTracks(tracks) {
  tracksEl.innerHTML = "";
  if (!tracks.length) {
    tracksEl.innerHTML = '<div class="muted">No staged tracks yet.</div>';
    return;
  }
  tracks.forEach((track) => {
    const row = document.createElement("div");
    row.className = "table-row";
    const title = `${track.metadata.title} — ${track.metadata.artist}`;
    row.innerHTML = `
      <div>${title}</div>
      <div>${track.source_url}</div>
      <div><span class="status-pill">${track.status}</span></div>
      <div class="${track.status === "error" ? "status-error" : ""}">${track.error || ""}</div>
    `;
    tracksEl.appendChild(row);
  });
}

async function refreshBatch() {
  if (!batchId) {
    return;
  }
  const resp = await apiRequest(`/batches/${batchId}`);
  if (!resp.ok) {
    return;
  }
  const body = await resp.json();
  runningEl.textContent = body.running ? "Running" : "Idle";
  renderTracks(body.tracks || []);
}

function startPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
  }
  refreshBatch();
  pollTimer = setInterval(refreshBatch, 2000);
}

document.getElementById("create-batch").addEventListener("click", createBatch);
document.getElementById("stage-track").addEventListener("click", stageTrack);
document.getElementById("start-batch").addEventListener("click", startBatch);
document.getElementById("save-token").addEventListener("click", () => {
  saveToken(tokenInput.value);
  setStatus("Token saved.");
});

tokenInput.value = loadToken();
