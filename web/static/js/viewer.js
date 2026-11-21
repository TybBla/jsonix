// Podgląd PDF (PDF.js dołączony lokalnie w /static/vendor/pdfjs) z warstwą tekstową
// i podświetleniami fragmentów źródłowych.

import { visibleRange } from "./hover.js";
import { el } from "./ui.js";

const PDFJS_URL = "/static/vendor/pdfjs/pdf.min.mjs";
const WORKER_URL = "/static/vendor/pdfjs/pdf.worker.min.mjs";

let pdfjsPromise = null;

function loadPdfjs() {
  if (!pdfjsPromise) {
    pdfjsPromise = import(PDFJS_URL)
      .then((lib) => {
        lib.GlobalWorkerOptions.workerSrc = WORKER_URL;
        return lib;
      })
      .catch((err) => {
        pdfjsPromise = null; // pozwól ponowić po błędzie sieci
        throw err;
      });
  }
  return pdfjsPromise;
}

/** Tekst warstwy tekstowej strony z mapą: znak → (węzeł tekstowy, przesunięcie). */
function collectText(layer) {
  let text = "";
  const nodes = [];
  const walker = document.createTreeWalker(layer, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    if (n.nodeType === Node.TEXT_NODE) {
      nodes.push({ node: n, start: text.length });
      text += n.data;
    } else if (n.tagName === "BR") {
      text += "\n";
    }
  }
  return { text, nodes };
}

function domPoint(index, nodes, isEnd) {
  for (let i = nodes.length - 1; i >= 0; i -= 1) {
    const { node, start } = nodes[i];
    if (index > start || (index === start && !isEnd)) {
      return { node, offset: Math.min(index - start, node.data.length) };
    }
  }
  return nodes.length ? { node: nodes[0].node, offset: 0 } : null;
}

export class PdfViewer {
  /**
   * @param {HTMLElement} container przewijany kontener podglądu
   * @param {{onSelect: (path: string) => void,
   *          onPreview?: (path: string, source: string) => void,
   *          onLeave?: (path: string, source: string) => void}} options
   *   onPreview/onLeave: najechanie kursorem lub fokus na podświetlonym fragmencie i zejście z niego.
   */
  constructor(container, { onSelect, onPreview = () => {}, onLeave = () => {} }) {
    this.container = container;
    this.onSelect = onSelect;
    this.onPreview = onPreview;
    this.onLeave = onLeave;
    this.previewed = null; // pole z lekkim podświetleniem (podgląd przy najechaniu)
    this.pages = []; // {div, layer, hlLayer, text, nodes, viewportWidth}
    this.highlights = new Map(); // path -> {page, start, end, label, boxes: []}
    this.active = null;
    this.doc = null;
    this.width = 0;
    this._resizeTimer = null;
    this.destroyed = false;
    this._generation = 0;
    this._observer = new ResizeObserver(() => this._onResize());
  }

  async open(url) {
    const pdfjs = await loadPdfjs();
    const doc = await pdfjs.getDocument({ url, isEvalSupported: false }).promise;
    if (this.destroyed) {
      doc.destroy();
      throw new Error("viewer destroyed");
    }
    this.doc = doc;
    await this._renderAll();
    if (this.destroyed) throw new Error("viewer destroyed");
    this._observer.observe(this.container);
    return this.doc.numPages;
  }

  pageTexts() {
    return this.pages.map((p) => p.text);
  }

  async _renderAll() {
    const pdfjs = await loadPdfjs();
    const generation = ++this._generation;
    const stale = () => this.destroyed || generation !== this._generation;
    this.container.replaceChildren();
    this.pages = [];
    this.width = this.container.clientWidth;
    const available = Math.max(200, this.width - 24);
    for (let i = 1; i <= this.doc.numPages; i += 1) {
      const page = await this.doc.getPage(i);
      if (stale()) return;
      const base = page.getViewport({ scale: 1 });
      const viewport = page.getViewport({ scale: available / base.width });
      const ratio = window.devicePixelRatio || 1;

      const canvas = el("canvas", { "aria-hidden": "true" });
      canvas.width = Math.floor(viewport.width * ratio);
      canvas.height = Math.floor(viewport.height * ratio);
      canvas.style.width = `${Math.floor(viewport.width)}px`;
      canvas.style.height = `${Math.floor(viewport.height)}px`;

      const layer = el("div", { class: "textLayer" });
      const hlLayer = el("div", { class: "hl-layer" });
      const div = el(
        "div",
        {
          class: "pdf-page",
          role: "region",
          "aria-label": `Strona ${i} z ${this.doc.numPages}`,
          dataset: { page: String(i - 1) },
        },
        [canvas, layer, hlLayer],
      );
      div.style.width = `${Math.floor(viewport.width)}px`;
      div.style.height = `${Math.floor(viewport.height)}px`;
      div.style.setProperty("--scale-factor", String(viewport.scale));
      this.container.append(div);

      await page.render({
        canvasContext: canvas.getContext("2d"),
        viewport,
        transform: ratio !== 1 ? [ratio, 0, 0, ratio, 0, 0] : null,
      }).promise;
      const textLayer = new pdfjs.TextLayer({
        textContentSource: page.streamTextContent(),
        container: layer,
        viewport,
      });
      await textLayer.render();
      if (stale()) return;
      const { text, nodes } = collectText(layer);
      this.pages.push({ div, layer, hlLayer, text, nodes });
    }
  }

  /** Dodaje podświetlenie pola (hit = wynik locateInDocument / wpis mapy buildSourceMap). */
  addHighlight(path, label, hit) {
    this.highlights.set(path, { ...hit, label, boxes: [] });
    this._draw(path);
  }

  _draw(path) {
    const h = this.highlights.get(path);
    const page = this.pages[h.page];
    if (!page) return;
    if (h.boxes.length) {
      // usunięte węzły nie dostaną pewnego mouseleave/blur: zamknij podgląd z dokumentu jawnie
      this.onLeave(path, "doc-pointer");
      this.onLeave(path, "doc-focus");
    }
    for (const b of h.boxes) b.remove();
    h.boxes = [];
    const a = domPoint(h.start, page.nodes, false);
    const b = domPoint(h.end, page.nodes, true);
    if (!a || !b) return;
    const range = document.createRange();
    range.setStart(a.node, a.offset);
    range.setEnd(b.node, b.offset);
    const origin = page.div.getBoundingClientRect();
    const rects = [...range.getClientRects()].filter((r) => r.width > 0.5 && r.height > 0.5);
    rects.forEach((r, i) => {
      const box = el("div", { class: "hl-box", dataset: { path } });
      if (path === this.active) box.classList.add("is-active");
      if (path === this.previewed) box.classList.add("is-preview");
      box.addEventListener("mouseenter", () => this.onPreview(path, "doc-pointer"));
      box.addEventListener("mouseleave", () => this.onLeave(path, "doc-pointer"));
      box.style.left = `${r.left - origin.left - 2}px`;
      box.style.top = `${r.top - origin.top - 2}px`;
      box.style.width = `${r.width + 4}px`;
      box.style.height = `${r.height + 4}px`;
      box.addEventListener("click", () => this.onSelect(path));
      if (i === 0) {
        const tag = el(
          "button",
          {
            type: "button",
            class: "hl-label",
            onclick: (ev) => {
              ev.stopPropagation();
              this.onSelect(path);
            },
            onfocus: () => this.onPreview(path, "doc-focus"),
            onblur: () => this.onLeave(path, "doc-focus"),
          },
          [el("span", { class: "visually-hidden", text: "Przejdź do pola: " }), h.label],
        );
        box.append(tag);
      }
      page.hlLayer.append(box);
      h.boxes.push(box);
    });
  }

  /** Zaznacza podświetlenie pola i przewija do niego podgląd. */
  activate(path, { scroll = true } = {}) {
    if (this.active) for (const b of this.highlights.get(this.active)?.boxes || []) b.classList.remove("is-active");
    this.active = this.highlights.has(path) ? path : null;
    if (!this.active) return false;
    const h = this.highlights.get(path);
    if (!h.boxes.length) this._draw(path);
    for (const b of h.boxes) b.classList.add("is-active");
    if (scroll && h.boxes[0]) this._scrollTo(h.boxes[0]);
    return true;
  }

  /**
   * Lekkie podświetlenie fragmentu pola (podgląd) albo jego usunięcie (path = null).
   * Tylko przełącza klasy CSS gotowych obszarów: bez wyszukiwania i bez przewijania podglądu.
   */
  preview(path) {
    const next = path && this.highlights.has(path) ? path : null;
    if (next === this.previewed) return;
    for (const b of this.highlights.get(this.previewed)?.boxes || []) b.classList.remove("is-preview");
    this.previewed = next;
    for (const b of this.highlights.get(next)?.boxes || []) b.classList.add("is-preview");
  }

  /** Zakres widocznych stron ({first, last}, 0-based) albo null, gdy podgląd jest ukryty. */
  visibleRange() {
    const box = this.container.getBoundingClientRect();
    if (!box.height || !this.pages.length) return null;
    const spans = this.pages.map(({ div }) => {
      const r = div.getBoundingClientRect();
      return { top: r.top - box.top, bottom: r.bottom - box.top };
    });
    return visibleRange(spans, 0, box.height);
  }

  /** Przerysowuje podświetlenia (np. po pokazaniu ukrytego podglądu). */
  redraw() {
    for (const path of this.highlights.keys()) this._draw(path);
    if (this.active) this.activate(this.active, { scroll: false });
  }

  focusHighlight(path) {
    const h = this.highlights.get(path);
    h?.boxes[0]?.querySelector(".hl-label")?.focus({ preventScroll: true });
  }

  _scrollTo(box) {
    const page = box.closest(".pdf-page");
    const top = page.offsetTop + box.offsetTop - this.container.clientHeight / 3;
    this.container.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
  }

  _onResize() {
    if (!this.doc) return;
    const w = this.container.clientWidth;
    if (!w || Math.abs(w - this.width) < 24) return;
    window.clearTimeout(this._resizeTimer);
    this._resizeTimer = window.setTimeout(async () => {
      const scrollRatio = this.container.scrollTop / Math.max(1, this.container.scrollHeight);
      await this._renderAll();
      for (const path of this.highlights.keys()) this._draw(path);
      if (this.active) this.activate(this.active, { scroll: false });
      this.container.scrollTop = scrollRatio * this.container.scrollHeight;
    }, 200);
  }

  destroy() {
    this.destroyed = true;
    window.clearTimeout(this._resizeTimer);
    this._observer.disconnect();
    this.doc?.destroy();
    this.container.replaceChildren();
    this.highlights.clear();
  }
}
