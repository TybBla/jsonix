// Budowanie listy pól z wynikowego JSON (data) i powiązanie z trace (źródło wartości).
// Działa dla dowolnego typu dokumentu: nieznane klucze dostają etykietę z nazwy klucza.

const LABELS = {
  OdwolanieKIO: "Odwołanie do KIO",
  Odwolujacy: "Odwołujący",
  Zamawiajacy: "Zamawiający",
  ZamowieniePubliczne: "Zamówienie publiczne",
  pelnomocnik: "Pełnomocnik",
  mocodawca: "Mocodawca",
  pelnomocnicy: "Pełnomocnicy",
  podpisujacy: "Podpisujący",
  przelew_bankowy: "Przelew bankowy",
  data: "Data",
  czynnosc_dzien: "Dzień czynności",
  czynnosc_powod_id: "Powód czynności (kod)",
  czynnosc_opis: "Opis czynności",
  miejscowosc: "Miejscowość",
  krs: "KRS",
  nip: "NIP",
  regon: "REGON",
  pesel: "PESEL",
  nazwa: "Nazwa",
  "przez-pelnomocnika": "Przez pełnomocnika",
  imie_nazwisko: "Imię i nazwisko",
  mail: "Adres e-mail",
  prowadzacy_postepowanie: "Prowadzący postępowanie",
  numer_bzp: "Numer ogłoszenia BZP",
  numer_postepowania: "Numer postępowania",
  numer_ted: "Numer ogłoszenia TED",
  tytul: "Tytuł",
  typ: "Typ",
  data_operacji: "Data operacji",
  kwota: "Kwota",
  na_rachunek: "Na rachunek",
  z_rachunku: "Z rachunku",
  numer_transakcji: "Numer transakcji",
};

/** Etykieta pola: ze słownika albo z nazwy klucza („numer_umowy” → „Numer umowy”). */
export function labelFor(key, parentKey) {
  if (key === "data" && parentKey === "mocodawca") return "Dane mocodawcy";
  if (LABELS[key]) return LABELS[key];
  const text = String(key)
    .replace(/([a-ząćęłńóśźż])([A-ZĄĆĘŁŃÓŚŹŻ])/g, "$1 $2")
    .replace(/[_-]+/g, " ")
    .trim()
    .toLowerCase();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Wartość do wyświetlenia; null/pusty tekst → null (GUI pokaże „Nie podano”). */
export function displayValue(value) {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "boolean") return value ? "Tak" : "Nie";
  if (typeof value === "number") return value.toLocaleString("pl-PL", { maximumFractionDigits: 2 });
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

/**
 * Drzewo do wyświetlenia. Węzły:
 *  {kind: "group", key, label, path, children}  — obiekt albo element listy
 *  {kind: "list", key, label, path, children}   — lista (elementy numerowane od 1)
 *  {kind: "field", key, label, path, value}     — wartość prosta
 * path ma format trace: „Odwolujacy[0].pelnomocnik.nazwa”.
 */
export function buildTree(data) {
  const walk = (value, key, path, parentKey) => {
    if (Array.isArray(value)) {
      return {
        kind: "list",
        key,
        label: labelFor(key, parentKey),
        path,
        children: value.map((item, i) => {
          const node = walk(item, key, `${path}[${i}]`, parentKey);
          node.label = `${labelFor(key, parentKey)} ${i + 1}`;
          node.index = i + 1;
          return node;
        }),
      };
    }
    if (value !== null && typeof value === "object") {
      return {
        kind: "group",
        key,
        label: labelFor(key, parentKey),
        path,
        children: Object.entries(value).map(([k, v]) => walk(v, k, path ? `${path}.${k}` : k, key)),
      };
    }
    return { kind: "field", key, label: labelFor(key, parentKey), path, value };
  };
  return Object.entries(data || {}).map(([k, v]) => walk(v, k, k, null));
}

/** Wszystkie pola (liście) w kolejności wyświetlania. */
export function leaves(tree) {
  const out = [];
  const visit = (node) => {
    if (node.kind === "field") out.push(node);
    else node.children.forEach(visit);
  };
  tree.forEach(visit);
  return out;
}

/** Mapa path → wpis trace. */
export function traceIndex(trace) {
  const index = new Map();
  for (const t of trace || []) index.set(t.path, t);
  return index;
}

/**
 * Stan źródła pola:
 *  "empty"   — brak wartości (Nie podano), bez podświetlenia
 *  "source"  — jest strona i fragment: można szukać w PDF
 *  "missing" — wartość bez strony lub fragmentu: komunikat ostrzegawczy
 */
export function sourceState(field, trace) {
  if (displayValue(field.value) === null) return "empty";
  if (trace && trace.page !== null && trace.page !== undefined && trace.source_snippet) return "source";
  return "missing";
}

/** Strony bez warstwy tekstowej (OCR) na podstawie ostrzeżeń, np. „OCR strony 2” → indeks 1. */
export function ocrPages(warnings) {
  const pages = new Set();
  for (const w of warnings || []) {
    const m = /^OCR strony (\d+)/.exec(w);
    if (m) pages.add(Number(m[1]) - 1);
  }
  return pages;
}

/** Skraca fragment do czytnika ekranu / opisu pola. */
export function shortSnippet(text, max = 80) {
  const clean = String(text || "")
    .replace(/\s+/g, " ")
    .trim();
  return clean.length > max ? `${clean.slice(0, max - 1)}…` : clean;
}

/** Ustawia wartość w kopii data wg ścieżki trace (np. „Odwolujacy[0].nip”). */
export function setByPath(data, path, value) {
  const parts = path.match(/[^.[\]]+/g);
  let cur = data;
  for (let i = 0; i < parts.length - 1; i += 1) {
    const key = /^\d+$/.test(parts[i]) ? Number(parts[i]) : parts[i];
    cur = cur[key];
  }
  const last = parts[parts.length - 1];
  cur[/^\d+$/.test(last) ? Number(last) : last] = value;
}

/**
 * Wartość wpisana przez użytkownika, z typem jak w oryginale:
 * pusty tekst → null; liczba, gdy oryginał był liczbą i tekst da się odczytać („7 500,50” → 7500.5).
 */
export function parseEditedValue(text, original) {
  const trimmed = String(text ?? "").trim();
  if (!trimmed) return null;
  if (typeof original === "number") {
    const num = Number(trimmed.replace(/[\s ]/g, "").replace(",", "."));
    if (Number.isFinite(num)) return num;
  }
  return trimmed;
}

/** Kopia data z naniesionymi edycjami (Map path → wartość); oryginał bez zmian. */
export function applyEdits(data, edits) {
  const copy = structuredClone(data);
  for (const [path, value] of edits || []) setByPath(copy, path, value);
  return copy;
}
