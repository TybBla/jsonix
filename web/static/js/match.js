// Wyszukiwanie fragmentu źródłowego (source_snippet z trace) w tekście strony PDF.
// Tekst warstwy PDF.js różni się od tekstu po czyszczeniu (łamanie wierszy, odstępy,
// cudzysłowy, dzielenie wyrazów), więc porównujemy wersje znormalizowane:
// małe litery, ujednolicone cudzysłowy i myślniki, bez białych znaków.

const CHAR_MAP = {
  "„": '"', // „
  "”": '"', // ”
  "“": '"', // “
  "«": '"', // «
  "»": '"', // »
  "″": '"',
  "‘": "'",
  "’": "'",
  "‚": "'",
  "′": "'",
  "–": "-", // –
  "—": "-", // —
  "−": "-",
  "­": "", // miękki dywiz
};

/**
 * Normalizuje tekst i zwraca mapę: norm[i] pochodzi z oryginału na pozycji map[i].
 * Dywiz na końcu wiersza („postępo-⏎wania”) jest pomijany.
 */
export function normalize(text) {
  const src = String(text ?? "");
  let norm = "";
  const map = [];
  for (let i = 0; i < src.length; i += 1) {
    let ch = src[i];
    if (/\s/.test(ch)) continue;
    if (ch === "-" && i + 1 < src.length && /[\n\r]/.test(src[i + 1])) continue;
    if (ch in CHAR_MAP) ch = CHAR_MAP[ch];
    if (!ch) continue;
    for (const c of ch.toLocaleLowerCase("pl-PL")) {
      norm += c;
      map.push(i);
    }
  }
  return { norm, map };
}

/** Tekst wartości do wyszukania (liczby jak w dokumentach: przecinek dziesiętny). */
export function valueNeedles(value) {
  if (value === null || value === undefined || typeof value === "object") return [];
  if (typeof value === "number") {
    const plain = String(value);
    const comma = plain.replace(".", ",");
    const fixed = value.toFixed(2).replace(".", ",");
    return [...new Set([fixed, comma, plain])];
  }
  return [String(value)];
}

function toRange(hay, start, length) {
  return { start: hay.map[start], end: hay.map[start + length - 1] + 1 };
}

function findValueInside(hay, from, to, needles) {
  for (const needle of needles) {
    const v = normalize(needle).norm;
    if (!v) continue;
    const at = hay.norm.indexOf(v, from);
    if (at >= 0 && at + v.length <= to) return toRange(hay, at, v.length);
  }
  return null;
}

const MIN_PARTIAL = 12;

/**
 * Szuka fragmentu w tekście strony.
 * Zwraca {start, end, kind} (indeksy w ORYGINALNYM tekście strony) albo null.
 *  kind = "value"    — znaleziono fragment i wartość w nim (podświetlamy wartość)
 *  kind = "snippet"  — znaleziono cały fragment, bez wartości w nim
 *  kind = "partial"  — znaleziono najdłuższą część fragmentu (z wartością, jeśli się da)
 */
export function locate(pageText, snippet, value) {
  const hay = typeof pageText === "string" ? normalize(pageText) : pageText;
  const snip = normalize(snippet).norm;
  if (!snip || !hay.norm) return null;
  const needles = valueNeedles(value);

  const at = hay.norm.indexOf(snip);
  if (at >= 0) {
    const inner = findValueInside(hay, at, at + snip.length, needles);
    if (inner) return { ...inner, kind: "value" };
    return { ...toRange(hay, at, snip.length), kind: "snippet" };
  }

  // Najdłuższy wspólny fragment zawierający wartość (jeśli wartość jest w snippecie).
  for (const needle of needles) {
    const v = normalize(needle).norm;
    const vi = v ? snip.indexOf(v) : -1;
    if (vi < 0) continue;
    const minLen = Math.max(v.length, Math.min(MIN_PARTIAL, snip.length));
    for (let len = snip.length - 1; len >= minLen; len -= 1) {
      const first = Math.max(0, vi + v.length - len);
      const last = Math.min(vi, snip.length - len);
      for (let s = first; s <= last; s += 1) {
        const pos = hay.norm.indexOf(snip.slice(s, s + len));
        if (pos >= 0) {
          const valueAt = pos + (vi - s);
          return { ...toRange(hay, valueAt, v.length), kind: "partial" };
        }
      }
    }
  }

  // Najdłuższa część snippetu (bez wartości), nie krótsza niż MIN_PARTIAL znaków.
  if (snip.length > MIN_PARTIAL) {
    for (let len = snip.length - 1; len >= MIN_PARTIAL; len -= 1) {
      for (let s = 0; s + len <= snip.length; s += 1) {
        const pos = hay.norm.indexOf(snip.slice(s, s + len));
        if (pos >= 0) return { ...toRange(hay, pos, len), kind: "partial" };
      }
    }
  }
  return null;
}

/**
 * Szuka na wskazanej stronie, a gdy się nie uda — na pozostałych.
 * pages: tablica tekstów stron (albo wyników normalize). Zwraca {page, start, end, kind} albo null.
 */
export function locateInDocument(pages, page, snippet, value) {
  const order = [page, ...pages.keys()].filter((p, i, arr) => p >= 0 && p < pages.length && arr.indexOf(p) === i);
  for (const p of order) {
    const hit = locate(pages[p], snippet, value);
    if (hit) return { page: p, ...hit };
  }
  return null;
}
