// Ekran „Sprawdź dane”: pola wyodrębnione z dokumentu obok podglądu PDF z podświetleniem źródła.

import { backToResults, doctypeLabel, jsonUrl, pdfUrl, setReviewOpener } from "./app.js";
import { buildTree, displayValue, leaves, ocrPages, shortSnippet, sourceState, traceIndex } from "./fields.js";
import { locateInDocument } from "./match.js";
import { $, el, setStep, showScreen } from "./ui.js";
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
  const shown = displayValue(node.value);
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
  return el("li", { class: "field-item" }, [button, source]);
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
          onclick: () => setStep(4),
        },
        ["Pobierz JSON", el("span", { class: "muted-inline", text: " (plik .json)" })],
      ),
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
  current = { job, file, fields: new Map() };
  const docBox = buildScreen(job, file);
  setView("fields");
  showScreen("review", `Sprawdź dane: ${file.file}`);

  const status = $("#doc-status");
  viewer = new PdfViewer(docBox, { onSelect: (path) => select(path, { scroll: false }) });
  try {
    const pages = await viewer.open(pdfUrl(job.job_id, file.name));
    const texts = viewer.pageTexts();
    let found = 0;
    let missing = 0;
    for (const entry of current.fields.values()) {
      if (entry.state !== "source") continue;
      const hit = locateInDocument(texts, entry.trace.page, entry.trace.source_snippet, entry.node.value);
      if (hit) {
        viewer.addHighlight(entry.node.path, entry.node.label, hit);
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
  } catch {
    status.classList.remove("visually-hidden");
    status.className = "doc-status notice notice-error";
    status.replaceChildren(
      el("span", { class: "icon icon-error", "aria-hidden": "true", text: "!" }),
      el("span", { text: "Nie udało się wyświetlić podglądu dokumentu. Dane w polach są nadal dostępne." }),
    );
    for (const entry of current.fields.values()) if (entry.state === "source") renderSource(entry, false);
  }
}

NARROW.addEventListener("change", () => viewer?.redraw());
setReviewOpener(openReview);
