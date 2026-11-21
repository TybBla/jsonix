// Ekran „Sprawdź dane”: pola wyodrębnione z dokumentu obok podglądu PDF z podświetleniem źródła.

import { backToResults, doctypeLabel, jsonUrl, pdfUrl, setReviewOpener } from "./app.js";
import {
  applyEdits,
  buildTree,
  displayValue,
  ocrPages,
  parseEditedValue,
  shortSnippet,
  sourceState,
  traceIndex,
} from "./fields.js";
import { locateInDocument } from "./match.js";
import { $, announce, el, setStep, showScreen } from "./ui.js";
import { PdfViewer } from "./viewer.js";

const NARROW = window.matchMedia("(max-width: 63.99rem)");
const NOT_FOUND = "Nie znaleziono tego fragmentu w dokumencie.";

function plural(n, one, few, many) {
  if (n === 1) return one;
  const d = n % 10;
  const t = n % 100;
  return d >= 2 && d <= 4 && (t < 12 || t > 14) ? few : many;
}

let viewer = null;
const EDITS = new Map(); // `${job_id}/${name}` → Map(path → wartość po edycji)
let current = null; // {job, file, fields: Map(path -> {node, trace, state, button, source})}

function fieldId(path) {
  return `pole-${path.replace(/[^\w]+/g, "-")}`;
}

function setView(view, { focus = false } = {}) {
  const screen = $("#screen-review");
  screen.dataset.view = view;
  for (const b of screen.querySelectorAll(".view-switch button")) {
    b.setAttribute("aria-pressed", String(b.dataset.view === view));
  }
  if (focus) {
    const target = view === "doc" ? $("#doc-heading") : $("#fields-heading");
    target?.focus();
  }
}

function sourceText(entry) {
  const { trace } = entry;
  return `Źródło: strona ${trace.page + 1}, „${shortSnippet(trace.source_snippet)}”`;
}

function renderSource(entry, located) {
  const p = entry.source;
  p.replaceChildren();
  p.className = "field-source";
  if (entry.state === "empty") {
    p.hidden = true;
    return;
  }
  p.hidden = false;
  if (entry.state === "source" && located !== false) {
    p.append(sourceText(entry));
    return;
  }
  p.classList.add("is-warning");
  const reason =
    entry.trace?.method === "derived"
      ? " Wartość wyliczono z innych danych dokumentu."
      : entry.ocr
        ? " Ta strona jest skanem bez warstwy tekstowej."
        : "";
  p.append(el("span", { class: "icon icon-warning", "aria-hidden": "true", text: "!" }), ` ${NOT_FOUND}${reason}`);
}

function renderField(node, index, ocr) {
  const trace = index.get(node.path) || null;
  const state = sourceState(node, trace);
  const edited = current.edits.has(node.path);
  const shown = displayValue(edited ? current.edits.get(node.path) : node.value);
  const id = fieldId(node.path);
  const source = el("p", { class: "field-source", id: `${id}-zrodlo` });
  const button = el(
    "button",
    {
      type: "button",
      class: `field${shown === null ? " is-empty" : ""}`,
      id,
      dataset: { path: node.path },
      "aria-describedby": source.id,
    },
    [
      el("span", { class: "field-label", text: node.label }),
      el("span", { class: "field-value", text: shown ?? "Nie podano" }),
    ],
  );
  const entry = { node, trace, state, button, source, ocr: trace && ocr.has(trace.page) };
  entry.controls = el("div", { class: "field-controls" });
  renderSource(entry);
  button.addEventListener("focus", () => select(node.path, { scroll: true, fromField: true }));
  button.addEventListener("click", () => {
    select(node.path, { scroll: true, fromField: true });
    if (NARROW.matches && viewer?.highlights.has(node.path)) {
      setView("doc");
      viewer.activate(node.path);
      viewer.focusHighlight(node.path);
    }
  });
  current.fields.set(node.path, entry);
  renderControls(entry);
  return el("li", { class: "field-item" }, [button, source, entry.controls]);
}

// --- edycja wartości ---

function editKey(job, file) {
  return `${job.job_id}/${file.name}`;
}

function rawText(value) {
  if (value === null || value === undefined) return "";
  return typeof value === "number" ? String(value).replace(".", ",") : String(value);
}

function currentValue(entry) {
  return current.edits.has(entry.node.path) ? current.edits.get(entry.node.path) : entry.node.value;
}

function refreshField(entry) {
  const shown = displayValue(currentValue(entry));
  entry.button.classList.toggle("is-empty", shown === null);
  entry.button.classList.toggle("is-edited", current.edits.has(entry.node.path));
  entry.button.querySelector(".field-value").textContent = shown ?? "Nie podano";
  renderControls(entry);
  updateDownloadInfo();
}

function renderControls(entry) {
  const label = entry.node.label;
  const edited = current.edits.has(entry.node.path);
  const change = el(
    "button",
    { type: "button", class: "btn btn-tertiary btn-small edit-btn", onclick: () => openEditor(entry) },
    ["Zmień", el("span", { class: "visually-hidden", text: ` pole ${label}` })],
  );
  const items = [change];
  if (edited) {
    items.unshift(
      el("span", { class: "tag tag-edited" }, [el("span", { "aria-hidden": "true", text: "✎" }), " Zmieniono ręcznie"]),
    );
    items.push(
      el(
        "button",
        {
          type: "button",
          class: "btn btn-tertiary btn-small",
          onclick: () => {
            current.edits.delete(entry.node.path);
            refreshField(entry);
            announce(`Przywrócono wartość z dokumentu w polu ${label}.`);
            entry.controls.querySelector(".edit-btn")?.focus();
          },
        },
        ["Przywróć wartość z dokumentu", el("span", { class: "visually-hidden", text: ` w polu ${label}` })],
      ),
    );
  }
  entry.controls.replaceChildren(...items);
}

function openEditor(entry) {
  const id = `${fieldId(entry.node.path)}-edycja`;
  const input = el("input", { class: "edit-input", type: "text", id, value: rawText(currentValue(entry)) });
  const close = () => {
    renderControls(entry);
    entry.controls.querySelector(".edit-btn")?.focus();
  };
  const form = el("form", { class: "edit-form", novalidate: true }, [
    el("label", { for: id, text: `Nowa wartość: ${entry.node.label}` }),
    el("p", { class: "hint", id: `${id}-pomoc`, text: "Zostaw puste, jeśli w dokumencie nie ma tej informacji." }),
    input,
    el("div", { class: "actions" }, [
      el("button", { type: "submit", class: "btn btn-secondary btn-small" }, "Zapisz"),
      el("button", { type: "button", class: "btn btn-tertiary btn-small", onclick: close }, "Anuluj"),
    ]),
  ]);
  input.setAttribute("aria-describedby", `${id}-pomoc`);
  input.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") {
      ev.preventDefault();
      close();
    }
  });
  form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const value = parseEditedValue(input.value, entry.node.value);
    const same = JSON.stringify(value) === JSON.stringify(entry.node.value ?? null);
    if (same) current.edits.delete(entry.node.path);
    else current.edits.set(entry.node.path, value);
    refreshField(entry);
    announce(
      same
        ? `Pole ${entry.node.label} ma wartość z dokumentu.`
        : `Zapisano zmianę w polu ${entry.node.label}. Pobrany JSON będzie ją zawierał.`,
    );
    entry.controls.querySelector(".edit-btn")?.focus();
  });
  entry.controls.replaceChildren(form);
  input.focus();
  input.select();
}

function updateDownloadInfo() {
  const info = $("#edits-info");
  if (!info) return;
  const n = current.edits.size;
  info.hidden = n === 0;
  info.textContent = n ? `Pobrany JSON będzie zawierał Twoje zmiany (${n}).` : "";
}

function downloadEdited(ev) {
  setStep(4);
  if (!current.edits.size) return; // bez zmian: plik prosto z serwera
  ev.preventDefault();
  const data = applyEdits(current.file.data, current.edits);
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const name = current.file.file.replace(/\.pdf$/i, "") + ".json";
  const a = el("a", { href: url, download: name });
  document.body.append(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function renderNode(node, depth, index, ocr) {
  if (node.kind === "field") return el("ul", { class: "field-list" }, [renderField(node, index, ocr)]);
  const heading = el(depth === 0 ? "h3" : "h4", { class: "group-title", text: node.label });
  if (node.kind === "list") {
    if (!node.children.length) {
      return el("section", { class: "group" }, [heading, el("p", { class: "muted", text: "Nie podano" })]);
    }
    return el(
      "section",
      { class: "group" },
      node.children.map((child) => renderNode(child, depth, index, ocr)),
    );
  }
  const simple = node.children.filter((c) => c.kind === "field");
  const nested = node.children.filter((c) => c.kind !== "field");
  return el("section", { class: `group depth-${depth}` }, [
    heading,
    simple.length ? el("ul", { class: "field-list" }, simple.map((c) => renderField(c, index, ocr))) : null,
    ...nested.map((c) => renderNode(c, depth + 1, index, ocr)),
  ]);
}

function select(path, { scroll = true, fromField = false } = {}) {
  for (const entry of current.fields.values()) entry.button.classList.toggle("is-selected", entry.node.path === path);
  const entry = current.fields.get(path);
  if (!entry) return;
  const found = viewer?.activate(path, { scroll }) ?? false;
  if (!fromField) {
    if (NARROW.matches) setView("fields");
    entry.button.focus({ preventScroll: true });
    entry.button.scrollIntoView({ block: "center", behavior: "smooth" });
  }
  return found;
}

function buildScreen(job, file) {
  const screen = $("#screen-review");
  const cls = file.classification;
  const known = Boolean(cls.doc_type);
  const tree = buildTree(file.data);

  const fieldsBox = el("div", { class: "fields-scroll" });
  const docBox = el("div", {
    class: "pdf-scroll",
    id: "pdf-view",
    tabindex: "0",
    role: "region",
    "aria-label": `Podgląd dokumentu ${file.file}`,
  });

  screen.replaceChildren(
    el("h1", { id: "h-review", tabindex: "-1", text: "Sprawdź dane" }),
    el("p", { class: "lead" }, [
      el("strong", { text: file.file }),
      ` — ${doctypeLabel(cls.doc_type)}`,
      known ? `, pewność ${Math.round(cls.confidence * 100)}%` : "",
    ]),
    known
      ? el("p", {
          class: "hint",
          text: "Wybierz pole, aby zobaczyć w dokumencie fragment, z którego pochodzi wartość. Możesz też kliknąć podświetlenie w dokumencie.",
        })
      : el("div", { class: "notice notice-warning" }, [
          el("span", { class: "icon icon-warning", "aria-hidden": "true", text: "!" }),
          el("p", { text: "Nie rozpoznaliśmy typu tego dokumentu. Plik JSON będzie pusty: {}" }),
        ]),
    el("div", { class: "view-switch", role: "group", "aria-label": "Widok" }, [
      el("button", { type: "button", class: "btn btn-secondary btn-small", dataset: { view: "fields" } }, "Pola"),
      el("button", { type: "button", class: "btn btn-secondary btn-small", dataset: { view: "doc" } }, "Dokument"),
    ]),
    el("div", { class: "review-grid" }, [
      el("section", { class: "fields-panel", "aria-labelledby": "fields-heading" }, [
        el("h2", { id: "fields-heading", tabindex: "-1", text: "Wyodrębnione dane" }),
        fieldsBox,
      ]),
      el("section", { class: "doc-panel", "aria-labelledby": "doc-heading" }, [
        el("h2", { id: "doc-heading", tabindex: "-1", text: "Dokument źródłowy" }),
        el("p", { class: "doc-status", id: "doc-status", role: "status", text: "Wczytywanie dokumentu…" }),
        docBox,
      ]),
    ]),
    el("div", { class: "actions" }, [
      el(
        "a",
        {
          class: "btn btn-primary",
          id: "json-btn",
          "data-screen": "review",
          href: jsonUrl(job.job_id, file.name),
          download: "",
          onclick: downloadEdited,
        },
        ["Pobierz JSON", el("span", { class: "muted-inline", text: " (plik .json)" })],
      ),
      el("p", { class: "edits-info", id: "edits-info", role: "status", hidden: true }),
      el("button", { type: "button", class: "btn btn-tertiary", onclick: backToResults }, "Wróć do wyników"),
    ]),
  );
  for (const b of screen.querySelectorAll(".view-switch button")) {
    b.addEventListener("click", () => {
      setView(b.dataset.view, { focus: true });
      viewer?.redraw();
    });
  }

  const index = traceIndex(file.trace);
  const ocr = ocrPages(file.warnings);
  if (tree.length) {
    fieldsBox.append(...tree.map((n) => renderNode(n, 0, index, ocr)));
  } else {
    fieldsBox.append(el("p", { class: "muted", text: "Brak danych do wyświetlenia." }));
  }
  return docBox;
}

async function openReview(job, file) {
  viewer?.destroy();
  viewer = null;
  const key = editKey(job, file);
  if (!EDITS.has(key)) EDITS.set(key, new Map());
  current = { job, file, fields: new Map(), edits: EDITS.get(key) };
  const docBox = buildScreen(job, file);
  setView("fields");
  updateDownloadInfo();
  showScreen("review", `Sprawdź dane: ${file.file}`);

  const status = $("#doc-status");
  const mine = new PdfViewer(docBox, { onSelect: (path) => select(path, { scroll: false }) });
  const cur = current;
  viewer = mine;
  let pages;
  try {
    pages = await mine.open(pdfUrl(job.job_id, file.name));
  } catch {
    if (viewer !== mine) return; // otwarto inny dokument w międzyczasie
    status.classList.remove("visually-hidden");
    status.className = "doc-status notice notice-error";
    status.replaceChildren(
      el("span", { class: "icon icon-error", "aria-hidden": "true", text: "!" }),
      el("span", { text: "Nie udało się wyświetlić podglądu dokumentu. Dane w polach są nadal dostępne." }),
    );
    for (const entry of cur.fields.values()) if (entry.state === "source") renderSource(entry, false);
    return;
  }
  if (viewer !== mine) return;
  {
    const texts = mine.pageTexts();
    let found = 0;
    let missing = 0;
    for (const entry of cur.fields.values()) {
      if (entry.state !== "source") continue;
      // skan bez warstwy tekstowej: komunikat zamiast zgadywania miejsca na innej stronie
      const hit = entry.ocr
        ? null
        : locateInDocument(texts, entry.trace.page, entry.trace.source_snippet, entry.node.value);
      if (hit) {
        mine.addHighlight(entry.node.path, entry.node.label, hit);
        found += 1;
      } else {
        missing += 1;
        renderSource(entry, false);
      }
    }
    status.textContent =
      `Dokument ma ${pages} ${plural(pages, "stronę", "strony", "stron")}. ` +
      `Podświetlono źródło dla ${found} ${plural(found, "pola", "pól", "pól")}.` +
      (missing ? ` Nie znaleziono fragmentu dla ${missing} pól.` : "");
    status.classList.add("visually-hidden");
  }
}

NARROW.addEventListener("change", () => viewer?.redraw());
document.addEventListener("o2j:leave-review", () => {
  viewer?.destroy();
  viewer = null;
});
setReviewOpener(openReview);
