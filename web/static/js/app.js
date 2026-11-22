// jsonix — GUI: wgrywanie plików, analiza w tle (joby API), wyniki klasyfikacji.

import {
  $,
  announce,
  clearErrors,
  el,
  formatSize,
  initA11yBar,
  plural,
  showErrors,
  showScreen,
  setTitle,
} from "./ui.js";
import { explainEvidence } from "./evidence.js";

const MAX_FILE_BYTES = 25 * 1024 * 1024;
const MAX_FILE_LABEL = "25 MB";
const MAX_FILES = 50; // jak limit API (ODW2JSON_MAX_FILES)
const POLL_MS = 400;
const LOW_CONFIDENCE = 0.7;
const POLL_RETRIES = 5;
const UPLOAD_TIMEOUT_MS = 5 * 60 * 1000;

class FatalError extends Error {}

/** Komunikat z odpowiedzi API (FastAPI: detail bywa tekstem albo listą błędów walidacji). */
function apiMessage(body) {
  return typeof body?.detail === "string" ? body.detail : null;
}

const MSG = {
  noFiles: "Wybierz co najmniej jeden plik PDF.",
  notPdf: "Wybrany plik musi być w formacie PDF.",
  empty: "Wybrany plik jest pusty.",
  tooLarge: `Wybrany plik musi być mniejszy niż ${MAX_FILE_LABEL}.`,
  sendFailed: "Nie udało się wysłać plików. Sprawdź połączenie i spróbuj ponownie.",
  jobFailed: "Nie udało się przeanalizować plików. Spróbuj ponownie.",
  tooMany: `Możesz przeanalizować najwyżej ${MAX_FILES} ${plural(MAX_FILES, "plik", "pliki", "plików")} naraz. Usuń część plików z listy.`,
};

const state = {
  files: [], // {id, file, error}
  nextId: 1,
  job: null, // ostatni snapshot z API
  doctypes: {}, // id -> nazwa
  busy: false,
};

// --- typy dokumentów ---
async function loadDoctypes() {
  try {
    const resp = await fetch("/api/doctypes");
    if (!resp.ok) return;
    for (const d of await resp.json()) state.doctypes[d.id] = d.title;
  } catch {
    /* nazwy techniczne zostaną użyte zamiast czytelnych */
  }
}

export function doctypeLabel(docType) {
  if (!docType) return "Nieznany dokument";
  return state.doctypes[docType] || docType;
}

// --- ekran 1: wybór plików ---
function validateFile(file) {
  if (!file.name.toLowerCase().endsWith(".pdf")) return MSG.notPdf;
  if (file.size === 0) return MSG.empty;
  if (file.size > MAX_FILE_BYTES) return MSG.tooLarge;
  return null;
}

function addFiles(fileList) {
  const added = [];
  for (const file of fileList) {
    const entry = { id: `plik-${state.nextId++}`, file, error: validateFile(file) };
    state.files.push(entry);
    added.push(entry);
  }
  renderFileList();
  if (added.length) hideUploadError();
  if (added.length) {
    const names = added.map((e) => e.file.name).join(", ");
    const bad = added.filter((e) => e.error).length;
    announce(
      `Dodano plików: ${added.length} (${names}).` +
        (bad ? ` Pliki z błędem: ${bad}.` : "") +
        ` Razem na liście: ${state.files.length}.`,
    );
    if (state.files.some((e) => e.error)) showFileErrors();
    else clearErrors();
  }
}

function removeFile(id) {
  const index = state.files.findIndex((e) => e.id === id);
  if (index < 0) return;
  const [removed] = state.files.splice(index, 1);
  renderFileList();
  announce(`Usunięto plik ${removed.file.name}. Na liście: ${state.files.length}.`);
  const next = state.files[index] || state.files[index - 1];
  const focusTarget = next ? document.querySelector(`#${next.id} .remove-btn`) : $("#file-input");
  focusTarget?.focus();
  if (state.files.some((e) => e.error)) showFileErrors({ focus: false });
  else clearErrors();
}

function renderFileList() {
  const list = $("#file-list");
  list.replaceChildren();
  for (const entry of state.files) {
    const errorId = `${entry.id}-blad`;
    const item = el("li", { class: `file-item${entry.error ? " has-error" : ""}`, id: entry.id }, [
      el("span", { class: "file-icon", "aria-hidden": "true", text: "PDF" }),
      el("span", {}, [
        el("span", { class: "file-name", text: entry.file.name }),
        " ",
        el("span", { class: "file-meta", text: `(${formatSize(entry.file.size)})` }),
      ]),
      el(
        "button",
        {
          type: "button",
          class: "remove-btn",
          "aria-describedby": entry.error ? errorId : null,
          onclick: () => removeFile(entry.id),
          disabled: state.busy,
        },
        ["Usuń", el("span", { class: "visually-hidden", text: ` plik ${entry.file.name}` })],
      ),
      entry.error
        ? el("p", { class: "file-error", id: errorId }, [
            el("span", { class: "visually-hidden", text: "Błąd: " }),
            entry.error,
          ])
        : null,
    ]);
    list.append(item);
  }
  const hasError = state.files.some((e) => e.error);
  $("#uploader").classList.toggle("has-error", hasError);
}

function hideUploadError() {
  const msg = $("#upload-error");
  msg.hidden = true;
  msg.textContent = "";
}

function showFileErrors({ focus = true } = {}) {
  const errors = state.files
    .filter((e) => e.error)
    .map((e) => ({ target: e.id, message: `${e.file.name}: ${e.error}` }));
  if (!errors.length) return false;
  showErrors(errors, { focus });
  return true;
}

function setBusy(busy) {
  state.busy = busy;
  const btn = $("#analyse-btn");
  // aria-disabled zamiast disabled: fokus zostaje na przycisku
  if (busy) btn.setAttribute("aria-disabled", "true");
  else btn.removeAttribute("aria-disabled");
  btn.textContent = busy ? "Trwa analiza…" : "Analizuj";
  $("#upload-form").setAttribute("aria-busy", String(busy));
  $("#file-input").disabled = busy;
  for (const b of document.querySelectorAll(".remove-btn")) b.disabled = busy;
}

function setProgress(label, value, max, text) {
  const box = $("#progress-box");
  box.hidden = false;
  $("#progress-label").textContent = label;
  const bar = $("#progress");
  bar.max = max;
  bar.value = value;
  $("#progress-text").textContent = text;
}

// --- wysyłka i odpytywanie joba ---
function uploadFiles(files) {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    for (const entry of files) form.append("files", entry.file, entry.file.name);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/jobs");
    xhr.responseType = "json";
    xhr.upload.addEventListener("progress", (ev) => {
      if (!ev.lengthComputable) return;
      const pct = Math.round((ev.loaded / ev.total) * 100);
      setProgress("Wysyłanie plików", pct, 100, `${pct}%`);
    });
    xhr.timeout = UPLOAD_TIMEOUT_MS;
    xhr.addEventListener("load", () => {
      if (xhr.status === 202 && xhr.response?.job_id) resolve(xhr.response.job_id);
      else reject(new Error(apiMessage(xhr.response) || MSG.sendFailed));
    });
    for (const type of ["error", "abort", "timeout"]) {
      xhr.addEventListener(type, () => reject(new Error(MSG.sendFailed)));
    }
    xhr.send(form);
  });
}

async function pollJob(jobId) {
  let lastProcessed = -1;
  let failures = 0;
  for (;;) {
    let job;
    try {
      const resp = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`);
      const body = await resp.json().catch(() => null);
      if (resp.status === 404) throw new FatalError(apiMessage(body) || MSG.jobFailed);
      if (!resp.ok || !body) throw new Error(MSG.jobFailed);
      job = body;
      failures = 0;
    } catch (err) {
      if (err instanceof FatalError || ++failures > POLL_RETRIES) {
        throw new Error(err instanceof FatalError ? err.message : MSG.jobFailed);
      }
      await new Promise((r) => window.setTimeout(r, POLL_MS * failures));
      continue;
    }
    if (job.processed !== lastProcessed) {
      lastProcessed = job.processed;
      const text = `Przeanalizowano ${job.processed} z ${job.total} ${plural(job.total, "pliku", "plików", "plików")}`;
      setProgress("Analiza dokumentów", job.processed, job.total, text);
      announce(text);
    }
    if (job.status === "done") return job;
    if (job.status === "error") throw new Error(job.error || MSG.jobFailed);
    await new Promise((r) => window.setTimeout(r, POLL_MS));
  }
}

async function onAnalyse(ev) {
  ev.preventDefault();
  if (state.busy) return;
  if (!state.files.length) {
    $("#upload-error").hidden = false;
    $("#upload-error").textContent = MSG.noFiles;
    $("#uploader").classList.add("has-error");
    showErrors([{ target: "file-input", message: MSG.noFiles }]);
    return;
  }
  if (state.files.length > MAX_FILES) {
    $("#upload-error").hidden = false;
    $("#upload-error").textContent = MSG.tooMany;
    $("#uploader").classList.add("has-error");
    showErrors([{ target: "file-input", message: MSG.tooMany }]);
    return;
  }
  hideUploadError();
  if (showFileErrors()) return;
  clearErrors();
  setBusy(true);
  announce("Wysyłanie plików. Poczekaj na wyniki analizy.");
  try {
    const jobId = await uploadFiles(state.files);
    setProgress("Analiza dokumentów", 0, state.files.length, `Przeanalizowano 0 z ${state.files.length}`);
    state.job = await pollJob(jobId);
    const fileErrors = renderResults(state.job);
    showScreen("results", "Wyniki klasyfikacji");
    if (fileErrors.length) showErrors(fileErrors);
  } catch (err) {
    showErrors([{ target: "file-input", message: err.message || MSG.jobFailed }]);
  } finally {
    setBusy(false);
    $("#progress-box").hidden = true;
  }
}

// --- ekran 2: wyniki klasyfikacji ---
export function jsonUrl(jobId, name) {
  return `/api/jobs/${encodeURIComponent(jobId)}/files/${encodeURIComponent(name)}/json`;
}

export function pdfUrl(jobId, name) {
  return `/api/jobs/${encodeURIComponent(jobId)}/files/${encodeURIComponent(name)}/pdf`;
}

function confidenceCell(cls) {
  const pct = `${Math.round(cls.confidence * 100)}%`;
  if (cls.doc_type && cls.confidence < LOW_CONFIDENCE) {
    return el("td", {}, [
      el("span", { class: "confidence-low" }, [
        el("span", { class: "icon icon-warning", "aria-hidden": "true", text: "!" }),
        ` ${pct} (niska)`,
      ]),
    ]);
  }
  return el("td", { text: pct });
}

const WHY_ICON = { plus: "+", minus: "−", info: "•" };

/**
 * Rozwijane uzasadnienie klasyfikacji: zdania po polsku (evidence.js) i surowe cechy klasyfikatora
 * w „Szczegółach technicznych” (transparentność). Brak uzasadnienia dla rozpoznanego typu → nic.
 */
function whyDetails(cls, title) {
  const raw = Array.isArray(cls.evidence) ? cls.evidence.filter((e) => typeof e === "string" && e) : [];
  const reasons = explainEvidence(raw, { known: Boolean(cls.doc_type), label: doctypeLabel });
  if (!reasons.length) return null;
  return el("details", { class: "why" }, [
    el("summary", { text: title }),
    el(
      "ul",
      { class: "why-list" },
      reasons.map((r) =>
        el("li", { class: `why-${r.tone}` }, [
          el("span", { class: "why-icon", "aria-hidden": "true", text: WHY_ICON[r.tone] || "•" }),
          el("span", { text: r.text }),
        ]),
      ),
    ),
    raw.length
      ? el("details", { class: "why-raw" }, [
          el("summary", { text: "Szczegóły techniczne" }),
          el("ul", {}, raw.map((e) => el("li", {}, [el("code", { text: e })]))),
        ])
      : null,
  ]);
}

function typeCell(file) {
  if (file.status === "error") {
    return el("td", {}, [
      el("span", { class: "tag tag-error" }, [el("span", { "aria-hidden": "true", text: "✕" }), " Błąd"]),
    ]);
  }
  const t = file.classification.doc_type;
  if (!t) {
    return el("td", {}, [
      el("span", { class: "tag tag-unknown" }, [el("span", { "aria-hidden": "true", text: "?" }), " Nieznany dokument"]),
      el("p", { class: "muted", text: "Zapiszemy pusty plik JSON: {}" }),
      whyDetails(file.classification, "Dlaczego nie rozpoznano?"),
    ]);
  }
  return el("td", {}, [
    el("span", { class: "tag tag-ok" }, [el("span", { "aria-hidden": "true", text: "✓" }), ` ${doctypeLabel(t)}`]),
    whyDetails(file.classification, "Dlaczego ten typ?"),
  ]);
}

function notesCell(file) {
  if (file.status === "error") {
    return el("td", {}, [el("p", { class: "file-error", text: file.error })]);
  }
  if (!file.warnings.length) return el("td", { class: "muted", text: "Brak" });
  return el("td", {}, [el("ul", {}, file.warnings.map((w) => el("li", { text: w })))]);
}

let reviewOpener = null;

/** Rejestruje otwieranie ekranu „Sprawdź dane” (moduł review.js). */
export function setReviewOpener(fn) {
  reviewOpener = fn;
}

function actionsCell(job, file) {
  if (file.status !== "done") return el("td", { class: "muted", text: "—" });
  const items = [];
  if (reviewOpener) {
    items.push(
      el(
        "button",
        {
          type: "button",
          class: "btn btn-secondary btn-small",
          onclick: () => reviewOpener(job, file),
        },
        ["Sprawdź dane", el("span", { class: "visually-hidden", text: ` z pliku ${file.file}` })],
      ),
    );
  }
  items.push(
    el("a", { href: jsonUrl(job.job_id, file.name), download: "" }, [
      "Pobierz JSON",
      el("span", { class: "visually-hidden", text: ` dla pliku ${file.file}` }),
    ]),
  );
  return el("td", {}, [el("div", { class: "actions", style: "margin-top:0" }, items)]);
}

export function renderResults(job) {
  const body = $("#results-body");
  body.replaceChildren();
  job.files.forEach((file, index) => {
    file.rowId = `wynik-${index + 1}`;
    const rowId = file.rowId;
    body.append(
      el("tr", { id: rowId }, [
        el("th", { scope: "row", class: "file-name", text: file.file }),
        typeCell(file),
        file.status === "done" && file.classification.doc_type
          ? confidenceCell(file.classification)
          : el("td", { class: "muted", text: "—" }),
        notesCell(file),
        actionsCell(job, file),
      ]),
    );
  });
  $("#results-caption").textContent = `Rozpoznane dokumenty (${job.files.length})`;

  const ok = job.files.filter((f) => f.status === "done");
  const unknown = ok.filter((f) => !f.classification.doc_type).length;
  const failed = job.files.filter((f) => f.status !== "done");
  const notice = $("#results-notice");
  notice.hidden = !ok.length;
  const allGood = !failed.length && !unknown;
  notice.className = `notice ${allGood ? "notice-success" : "notice-warning"}`;
  const icon = notice.querySelector(".icon");
  icon.className = `icon ${allGood ? "icon-success" : "icon-warning"}`;
  icon.textContent = allGood ? "✓" : "!";
  $("#results-notice-text").textContent =
    `Przeanalizowano ${ok.length} z ${job.files.length} ${plural(job.files.length, "pliku", "plików", "plików")}.` +
    (unknown ? ` Nierozpoznane dokumenty: ${unknown}.` : "");

  const zip = $("#zip-btn");
  if (ok.length) {
    zip.href = `/api/jobs/${encodeURIComponent(job.job_id)}/zip`;
    zip.removeAttribute("aria-disabled");
    zip.hidden = false;
  } else {
    zip.hidden = true;
  }

  return failed.map((f) => ({
    target: f.rowId,
    message: `${f.file}: ${f.error}`,
  }));
}

function restart() {
  state.files = [];
  state.job = null;
  renderFileList();
  $("#upload-error").hidden = true;
  $("#uploader").classList.remove("has-error");
  showScreen("upload", "Dodaj pliki");
}

export function backToResults() {
  document.dispatchEvent(new CustomEvent("o2j:leave-review"));
  showScreen("results", "Wyniki klasyfikacji");
}

export function getState() {
  return state;
}

// --- inicjalizacja ---
function initUploader() {
  const input = $("#file-input");
  input.addEventListener("change", () => {
    addFiles(input.files);
    input.value = "";
  });
  const zone = $("#dropzone");
  const stop = (ev) => {
    ev.preventDefault();
    ev.stopPropagation();
  };
  let depth = 0;
  zone.addEventListener("dragenter", (ev) => {
    stop(ev);
    depth += 1;
    if (!state.busy) zone.classList.add("is-dragover");
  });
  zone.addEventListener("dragover", stop);
  zone.addEventListener("dragleave", (ev) => {
    stop(ev);
    depth = Math.max(0, depth - 1);
    if (!depth) zone.classList.remove("is-dragover");
  });
  zone.addEventListener("drop", (ev) => {
    stop(ev);
    depth = 0;
    zone.classList.remove("is-dragover");
    if (!state.busy && ev.dataTransfer?.files?.length) addFiles(ev.dataTransfer.files);
  });
  // upuszczenie pliku poza polem nie otwiera go w przeglądarce
  window.addEventListener("dragover", (ev) => ev.preventDefault());
  window.addEventListener("drop", (ev) => ev.preventDefault());
  $("#upload-form").addEventListener("submit", onAnalyse);
}

function init() {
  initA11yBar();
  initUploader();
  $("#restart-btn").addEventListener("click", restart);
  setTitle("Dodaj pliki");
  loadDoctypes();
  import("./review.js").catch(() => {
    /* ekran „Sprawdź dane” niedostępny */
  });
}

init();
