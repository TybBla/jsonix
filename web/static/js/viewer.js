// Podgląd PDF (PDF.js dołączony lokalnie w /static/vendor/pdfjs) z warstwą tekstową
// i podświetleniami fragmentów źródłowych.

import { el } from "./ui.js";

const PDFJS_URL = "/static/vendor/pdfjs/pdf.min.mjs";
const WORKER_URL = "/static/vendor/pdfjs/pdf.worker.min.mjs";

let pdfjsPromise = null;

function loadPdfjs() {
  if (!pdfjsPromise) {
    pdfjsPromise = import(PDFJS_URL).then((lib) => {
      lib.GlobalWorkerOptions.workerSrc = WORKER_URL;
      return lib;
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
   * @param {{onSelect: (path: string) => void}} options
   */
  constructor(container, { onSelect }) {
    this.container = container;
    this.onSelect = onSelect;
    this.pages = []; // {div, layer, hlLayer, text, nodes, viewportWidth}
    this.highlights = new Map(); // path -> {page, start, end, label, boxes: []}
    this.active = null;
    this.doc = null;
    this.width = 0;
    this._resizeTimer = null;
    this._observer = new ResizeObserver(() => this._onResize());
  }

  async open(url) {
    const pdfjs = await loadPdfjs();
    this.doc = await pdfjs.getDocument({ url, isEvalSupported: false }).promise;
    await this._renderAll();
    this._observer.observe(this.container);
    return this.doc.numPages;
  }

  pageTexts() {
    return this.pages.map((p) => p.text);
  }

  async _renderAll() {
    const pdfjs = await loadPdfjs();
    this.container.replaceChildren();
    this.pages = [];
    this.width = this.container.clientWidth;
    const available = Math.max(200, this.width - 24);
    for (let i = 1; i <= this.doc.numPages; i += 1) {
      const page = await this.doc.getPage(i);
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
      const { text, nodes } = collectText(layer);
      this.pages.push({ div, layer, hlLayer, text, nodes });
    }
  }

  /** Dodaje podświetlenie pola (hit = wynik locateInDocument). */
  addHighlight(path, label, hit) {
    this.highlights.set(path, { ...hit, label, boxes: [] });
    this._draw(path);
  }

  _draw(path) {
    const h = this.highlights.get(path);
    const page = this.pages[h.page];
    if (!page) return;
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
    this._observer.disconnect();
    this.doc?.destroy();
    this.container.replaceChildren();
    this.highlights.clear();
  }
}
