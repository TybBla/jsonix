// Podgląd przy najechaniu / fokusie (rubryka ↔ fragment w PDF): czysta logika stanów, bez DOM.
// Zaznaczenie z kliknięcia (`selected`) i podgląd (`previews`) są niezależne: zejście kursorem
// lub fokusem usuwa tylko podgląd, a widok wraca do zaznaczenia z kliknięcia.
//
// Źródła podglądu: "field-pointer", "field-focus" (rubryka po lewej), "doc-pointer", "doc-focus"
// (podświetlony fragment w PDF). Kilka źródeł może działać naraz (np. fokus na jednej rubryce,
// kursor na drugiej) — obowiązuje ostatnio wskazane, a po jego zejściu wraca poprzednie.

export function createHoverState() {
  return { selected: null, previews: [] };
}

/**
 * akcje: {type: "select", path} | {type: "enter", source, path} | {type: "leave", source, path?} | {type: "reset"}
 * "leave" z innym `path` niż aktualny podgląd tego źródła jest ignorowane (spóźnione zdarzenie).
 */
export function hoverReducer(state, action) {
  switch (action.type) {
    case "select":
      return { ...state, selected: action.path ?? null };
    case "enter": {
      const previews = state.previews.filter((p) => p.source !== action.source);
      if (action.path) previews.push({ source: action.source, path: action.path });
      return { ...state, previews };
    }
    case "leave": {
      const previews = state.previews.filter(
        (p) => !(p.source === action.source && (action.path == null || p.path === action.path)),
      );
      return previews.length === state.previews.length ? state : { ...state, previews };
    }
    case "reset":
      return createHoverState();
    default:
      return state;
  }
}

function topPreview(state) {
  return state.previews.length ? state.previews[state.previews.length - 1] : null;
}

/** Pole aktualnie w podglądzie (albo null). */
export function previewPath(state) {
  return topPreview(state)?.path ?? null;
}

/**
 * Co pokazać na ekranie.
 * sourceMap: Map(path → {page, …} | null) z buildSourceMap; visible: {first, last} widocznych stron albo null.
 *  - preview:     rubryka z lekkim wyróżnieniem,
 *  - docPreview:  pole, którego fragment w PDF dostaje lekkie podświetlenie (tylko gdy fragment znaleziono),
 *  - badgePage:   strona (0-based) dla znacznika „strona N” przy rubryce, gdy fragment jest poza widokiem,
 *  - revealField: rubryka do dyskretnego przewinięcia listy (podgląd wywołany z dokumentu).
 */
export function hoverView(state, sourceMap, visible) {
  const top = topPreview(state);
  const preview = top?.path ?? null;
  const hit = preview ? (sourceMap.get(preview) ?? null) : null;
  const fromField = Boolean(top?.source.startsWith("field"));
  const offPage = Boolean(hit && visible && (hit.page < visible.first || hit.page > visible.last));
  return {
    selected: state.selected,
    preview,
    docPreview: hit ? preview : null,
    badgePage: fromField && offPage ? hit.page : null,
    revealField: top && !fromField ? preview : null,
  };
}

/**
 * Zakres stron widocznych w przewijanym kontenerze.
 * spans: [{top, bottom}] stron w układzie współrzędnych treści kontenera (rosnąco).
 */
export function visibleRange(spans, scrollTop, height) {
  const bottom = scrollTop + height;
  let first = null;
  let last = null;
  spans.forEach((s, i) => {
    if (s.bottom > scrollTop && s.top < bottom) {
      if (first === null) first = i;
      last = i;
    }
  });
  return first === null ? null : { first, last };
}
