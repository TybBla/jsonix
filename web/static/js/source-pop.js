// Źródło wartości w dymku: opis źródła (czysta logika), stany dymka, położenie w oknie i podpięcie zdarzeń.
// Ikonka „i” / „!” stoi przy wartości; szczegóły (strona, fragment, ostrzeżenia) pokazuje dymek po najechaniu
// (z krótkim opóźnieniem) albo po kliknięciu / Enter / spacji. Esc, kliknięcie poza dymkiem i przewinięcie listy zamykają.

import { shortSnippet } from "./fields.js";

export const NOT_FOUND = "Nie znaleziono tego fragmentu w dokumencie.";
const OPEN_DELAY_MS = 350;
const CLOSE_DELAY_MS = 200;
const MARGIN_PX = 8;

/**
 * Opis źródła pola do ikonki i dymka (bez DOM).
 * input: {label, state: "empty"|"source"|"missing", trace, located, ocr}
 * Zwraca null (brak wartości = brak ikonki) albo
 * {variant: "source"|"warning", ariaLabel, srText, rows: [{term, text}], notes: [string]}.
 */
export function describeSource({ label, state, trace, located, ocr }) {
  if (state === "empty") return null;
  const hasPage = trace && trace.page !== null && trace.page !== undefined;
  const page = hasPage ? String(trace.page + 1) : null;
  const snippet = trace?.source_snippet ? `„${shortSnippet(trace.source_snippet, 200)}”` : null;
  const rows = [];
  if (page) rows.push({ term: "Strona", text: page });
  if (snippet) rows.push({ term: "Fragment", text: snippet });

  if (state === "source" && located !== false) {
    return {
      variant: "source",
      ariaLabel: `Źródło wartości „${label}”: strona ${page}`,
      srText: `Źródło: strona ${page}, „${shortSnippet(trace.source_snippet)}”`,
      rows,
      notes: [],
    };
  }
  const derived = trace?.method === "derived";
  const reason = derived
    ? "Wartość wyliczono z innych danych dokumentu."
    : ocr
      ? "Ta strona jest skanem bez warstwy tekstowej."
      : null;
  const short = derived
    ? "wartość wyliczona, bez fragmentu w dokumencie"
    : ocr
      ? "strona skanowana bez warstwy tekstowej"
      : "nie znaleziono fragmentu w dokumencie";
  const notes = [NOT_FOUND, ...(reason ? [reason] : [])];
  return {
    variant: "warning",
    ariaLabel: `Źródło wartości „${label}”: ostrzeżenie, ${short}`,
    srText: `Ostrzeżenie o źródle: ${notes.join(" ")}`,
    rows,
    notes,
  };
}

// --- stany dymka ---

export function createPopState() {
  return { open: false, pinned: false };
}

/**
 * Akcje: "hover-open" (najechanie po opóźnieniu), "hover-close" (zjechanie; nie chowa otwartego kliknięciem),
 * "toggle" (kliknięcie / Enter / spacja: otwiera i utrwala albo zamyka), "dismiss" (Esc, kliknięcie poza, przewinięcie).
 */
export function popReducer(state, action) {
  switch (action) {
    case "hover-open":
      return state.open ? state : { open: true, pinned: false };
    case "hover-close":
      return state.pinned ? state : createPopState();
    case "toggle":
      return state.open && state.pinned ? createPopState() : { open: true, pinned: true };
    case "dismiss":
      return createPopState();
    default:
      return state;
  }
}

/**
 * Korekta położenia dymka w oknie. anchor / pop: prostokąty (left, right, top, bottom, width, height)
 * dymka w położeniu domyślnym (pod ikonką, wyrównany do jej prawej krawędzi).
 * Zwraca {shiftX: przesunięcie w poziomie w px, above: czy pokazać nad ikonką}.
 */
export function placePopover(anchor, pop, viewport, margin = MARGIN_PX) {
  let shiftX = 0;
  if (pop.right > viewport.width - margin) shiftX = viewport.width - margin - pop.right;
  if (pop.left + shiftX < margin) shiftX = margin - pop.left;
  const fitsBelow = pop.bottom <= viewport.height - margin;
  const fitsAbove = anchor.top - pop.height - 2 * 4 >= margin;
  return { shiftX, above: !fitsBelow && fitsAbove };
}

// --- podpięcie do DOM ---

let active = null; // sterownik aktualnie otwartego dymka (naraz jeden)
let globalsBound = false;

function bindGlobals() {
  if (globalsBound) return;
  globalsBound = true;
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && active) active.dismiss({ restoreFocus: true });
  });
  document.addEventListener("pointerdown", (ev) => {
    if (active && !active.contains(ev.target)) active.dismiss();
  });
  document.addEventListener(
    "scroll",
    (ev) => {
      // przewijanie podglądu PDF (np. po zaznaczeniu pola) nie zamyka dymka; przewinięcie listy — tak
      if (!active || ev.target?.closest?.("#pdf-view")) return;
      active.dismiss();
    },
    true,
  );
  window.addEventListener?.("resize", () => active?.dismiss());
}

/**
 * Podpina dymek: {wrap (kontener ikonki i dymka), button, pop, onActivate}.
 * Zwraca {open, close, isOpen, destroy}. Czasy opóźnień można skrócić w testach.
 */
export function bindSourcePopover({
  wrap,
  button,
  pop,
  onActivate = null,
  openDelay = OPEN_DELAY_MS,
  closeDelay = CLOSE_DELAY_MS,
}) {
  let state = createPopState();
  let openTimer = 0;
  let closeTimer = 0;

  const clearTimers = () => {
    window.clearTimeout(openTimer);
    window.clearTimeout(closeTimer);
    openTimer = 0;
    closeTimer = 0;
  };

  function place() {
    pop.classList.remove("is-above");
    pop.style.setProperty("--shift-x", "0px");
    const { shiftX, above } = placePopover(button.getBoundingClientRect(), pop.getBoundingClientRect(), {
      width: window.innerWidth,
      height: window.innerHeight,
    });
    if (shiftX) pop.style.setProperty("--shift-x", `${shiftX}px`);
    if (above) pop.classList.add("is-above");
  }

  function apply(next) {
    const wasOpen = state.open;
    state = next;
    if (state.open === wasOpen) return;
    if (state.open) {
      if (active && active !== controller) active.dismiss();
      active = controller;
      pop.hidden = false;
      place();
    } else {
      pop.hidden = true;
      if (active === controller) active = null;
    }
    button.setAttribute("aria-expanded", String(state.open));
  }

  const controller = {
    isOpen: () => state.open,
    contains: (node) => wrap.contains(node),
    open: () => apply(popReducer(state, "toggle")),
    close: () => {
      clearTimers();
      apply(popReducer(state, "dismiss"));
    },
    dismiss({ restoreFocus = false } = {}) {
      const focusInside = restoreFocus && wrap.contains(document.activeElement);
      controller.close();
      if (focusInside) button.focus();
    },
    destroy() {
      controller.close();
      wrap.removeEventListener("mouseenter", onEnter);
      wrap.removeEventListener("mouseleave", onLeave);
      button.removeEventListener("click", onClick);
    },
  };

  function onEnter() {
    window.clearTimeout(closeTimer);
    if (state.open || openTimer) return;
    openTimer = window.setTimeout(() => {
      openTimer = 0;
      apply(popReducer(state, "hover-open"));
    }, openDelay);
  }

  function onLeave() {
    window.clearTimeout(openTimer);
    openTimer = 0;
    if (!state.open || state.pinned) return;
    window.clearTimeout(closeTimer);
    closeTimer = window.setTimeout(() => {
      closeTimer = 0;
      apply(popReducer(state, "hover-close"));
    }, closeDelay);
  }

  function onClick() {
    clearTimers();
    apply(popReducer(state, "toggle"));
    onActivate?.();
  }

  bindGlobals();
  wrap.addEventListener("mouseenter", onEnter);
  wrap.addEventListener("mouseleave", onLeave);
  button.addEventListener("click", onClick);
  return controller;
}
