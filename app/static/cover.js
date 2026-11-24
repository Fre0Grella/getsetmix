/* The cover picker: an iTunes search and an upload, shared by a staged
   download (app.js) and the Library sheet (library.js). The caller says what
   a pick does; the picker only finds and hands over. */
import { $, api, esc } from "./core.js";

let sink = null; // { url(fullUrl), file(File) } of whoever opened the picker

// Open the picker searching `query`; a picked image goes to sink.url, an
// uploaded file to sink.file.
export function openCoverModal(query, pick) {
  sink = pick;
  $("#coverQuery").value = query;
  $("#coverResults").innerHTML = "";
  $("#coverModal").classList.remove("hidden");
  if (query) search();
}

async function search() {
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

$("#btnCoverSearch").addEventListener("click", search);
$("#coverQuery").addEventListener("keydown", (e) => { if (e.key === "Enter") search(); });

$("#coverResults").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-full]");
  if (btn && sink) sink.url(btn.dataset.full);
});

$("#coverFile").addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (file && sink) sink.file(file);
  e.target.value = "";
});
