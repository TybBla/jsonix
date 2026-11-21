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
const MAX_SNIPPET = 200;

function asHay(pageText) {
  return typeof pageText === "string" ? normalize(pageText) : pageText;
}

/** Długość wspólnego fragmentu wokół wartości: snip[vi..] ≡ hay[pos..], rozszerzanie w lewo i w prawo. */
function extendAround(hay, snip, vi, vlen, pos) {
  let left = 0;
  while (vi - left > 0 && pos - left > 0 && snip[vi - left - 1] === hay[pos - left - 1]) left += 1;
  let right = 0;
  while (vi + vlen + right < snip.length && pos + vlen + right < hay.length && snip[vi + vlen + right] === hay[pos + vlen + right]) {
    right += 1;
  }
  return left + vlen + right;
}

/** Najdłuższy wspólny podciąg snip i hay (programowanie dynamiczne, O(|snip|·|hay|), |snip| ≤ 200). */
function longestCommon(hay, snip) {
  let prev = new Uint16Array(snip.length + 1);
  let cur = new Uint16Array(snip.length + 1);
  let best = 0;
  let bestEnd = -1;
  for (let i = 0; i < hay.length; i += 1) {
    const ch = hay[i];
    for (let j = 1; j <= snip.length; j += 1) {
      const len = snip[j - 1] === ch ? prev[j - 1] + 1 : 0;
      cur[j] = len;
      if (len > best) {
        best = len;
        bestEnd = i;
      }
    }
    [prev, cur] = [cur, prev];
  }
  return best ? { pos: bestEnd - best + 1, len: best } : null;
}

/**
 * Szuka fragmentu w tekście strony.
 * Zwraca {start, end, kind} (indeksy w ORYGINALNYM tekście strony) albo null.
 *  kind = "value"    — znaleziono fragment i wartość w nim (podświetlamy wartość)
 *  kind = "snippet"  — znaleziono cały fragment, bez wartości w nim
 *  kind = "partial"  — znaleziono najdłuższą część fragmentu (z wartością, jeśli się da)
 * Wyszukiwanie częściowe jest liniowe względem długości strony (bez pętli po wszystkich podciągach).
 */
export function locate(pageText, snippet, value) {
  const exact = locateExact(pageText, snippet, value);
  if (exact !== undefined) return exact;
  const hay = asHay(pageText);
  const snip = normalize(snippet).norm.slice(0, MAX_SNIPPET);
  const needles = valueNeedles(value);

  // Najdłuższy wspólny fragment zawierający wartość (jeśli wartość jest w snippecie).
  for (const needle of needles) {
    const v = normalize(needle).norm;
    const vi = v ? snip.indexOf(v) : -1;
    if (vi < 0) continue;
    const minLen = Math.max(v.length, Math.min(MIN_PARTIAL, snip.length));
    let best = null;
    for (let pos = hay.norm.indexOf(v); pos >= 0; pos = hay.norm.indexOf(v, pos + 1)) {
      const len = extendAround(hay.norm, snip, vi, v.length, pos);
      if (len >= minLen && (!best || len > best.len)) best = { pos, len };
    }
    if (best) return { ...toRange(hay, best.pos, v.length), kind: "partial" };
  }

  // Najdłuższa część snippetu (bez wartości), nie krótsza niż MIN_PARTIAL znaków.
  if (snip.length > MIN_PARTIAL) {
    const common = longestCommon(hay.norm, snip);
    if (common && common.len >= MIN_PARTIAL) return { ...toRange(hay, common.pos, common.len), kind: "partial" };
  }
  return null;
}

/**
 * Tylko dokładne wystąpienie całego (znormalizowanego) fragmentu — jedno indexOf na stronę.
 * Zwraca {start, end, kind} albo null; undefined = brak dokładnego trafienia (dla `locate`).
 */
function locateExact(pageText, snippet, value) {
  const hay = asHay(pageText);
  const snip = normalize(snippet).norm.slice(0, MAX_SNIPPET);
  if (!snip || !hay.norm) return null;
  const at = hay.norm.indexOf(snip);
  if (at < 0) return undefined;
  const inner = findValueInside(hay, at, at + snip.length, valueNeedles(value));
  if (inner) return { ...inner, kind: "value" };
  return { ...toRange(hay, at, snip.length), kind: "snippet" };
}

/**
 * Szuka na wskazanej stronie (także dopasowanie częściowe), a gdy się nie uda — na pozostałych
 * stronach już tylko dokładnego fragmentu (bez kosztownego wyszukiwania częściowego wszędzie).
 * pages: tablica tekstów stron (albo wyników normalize). Zwraca {page, start, end, kind} albo null.
 */
export function locateInDocument(pages, page, snippet, value) {
  const home = Number.isInteger(page) && page >= 0 && page < pages.length ? page : null;
  if (home !== null) {
    const hit = locate(pages[home], snippet, value);
    if (hit) return { page: home, ...hit };
  }
  for (let p = 0; p < pages.length; p += 1) {
    if (p === home) continue;
    const hit = locateExact(pages[p], snippet, value);
    if (hit) return { page: p, ...hit };
  }
  return null;
}

/**
 * Mapa pole → obszar na stronie, liczona RAZ po wczytaniu dokumentu (każda strona normalizowana raz).
 * entries: [{path, page, snippet, value, skip?}]; skip = strona-skan bez warstwy tekstowej → null.
 * Zwraca Map(path → {page, start, end, kind} | null).
 */
export function buildSourceMap(pages, entries) {
  const hays = pages.map(asHay);
  const map = new Map();
  for (const e of entries) {
    map.set(e.path, e.skip || !e.snippet ? null : locateInDocument(hays, e.page, e.snippet, e.value));
  }
  return map;
}
