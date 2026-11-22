// „Dlaczego ten typ?” — zamiana technicznych opisów cech klasyfikatora (classification.evidence,
// np. "strong: 'odwolanie' (+2)") na zdania po polsku. Czysta funkcja bez DOM (testy w Node).
//
// Formaty z odw2json/classify (E3):
//   "<rodzaj>: <frazy w apostrofach> (<punkty>)"  rodzaj: strong | weak | negative | title | pattern | foreign title
//   "odrzucono: wynik X < min_score Y (najlepszy: <typ>)"
//   "odrzucono: margines X < min_margin Y (najlepszy: <typ>)"
//   "odrzucono: <typ>: brak wymaganej cechy (required_any: …); <typ>: …"
// Nieznany format jest pokazywany bez zmian (nowe cechy klasyfikatora nie znikają z GUI).

const FEATURE = /^(strong|weak|negative|title|pattern|foreign title): (.*) \(([+-]?[\d.]+)\)$/;
const QUOTED = /'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)"/g;
const NONE_FOUND = "Nie znaleziono cech żadnego z obsługiwanych typów dokumentów.";

function phrases(text) {
  return [...text.matchAll(QUOTED)].map((m) => m[1] ?? m[2]);
}

function quoteList(items) {
  return items.map((p) => `„${p}”`).join(", ");
}

/** Powód odrzucenia → {text, best}; best = najbliższy typ (cechy w evidence dotyczą właśnie jego). */
function rejection(rest, label, hasFeatures) {
  let m = rest.match(/^wynik (-?[\d.]+) < min_score [\d.]+ \(najlepszy: ([\w-]+)\)$/);
  if (m) {
    const some = Number(m[1]) > 0 || hasFeatures;
    return {
      text: some ? `Za mało cech, żeby rozpoznać typ. Najbliżej było: ${label(m[2])}.` : NONE_FOUND,
      best: m[2],
    };
  }
  m = rest.match(/^margines [-\d.]+ < min_margin [\d.]+ \(najlepszy: ([\w-]+)\)$/);
  if (m) {
    const text = `Dokument pasuje do kilku typów podobnie: przewaga typu ${label(m[1])} jest za mała, żeby go wybrać.`;
    return { text, best: m[1] };
  }
  const types = [...rest.matchAll(/([\w-]+): brak wymaganej cechy/g)].map((x) => label(x[1]));
  if (types.length) return { text: `Brak cechy wymaganej dla typów: ${types.join(", ")}.`, best: null };
  return null;
}

/**
 * evidence: lista tekstów z classification.evidence.
 * options: {known: czy typ rozpoznano, label: (id typu) => nazwa do wyświetlenia}.
 * Zwraca [{text, tone}], tone: "plus" (za typem), "minus" (przeciw), "info".
 */
export function explainEvidence(evidence, { known = true, label = (id) => id } = {}) {
  const list = Array.isArray(evidence) ? evidence.filter((e) => typeof e === "string" && e) : [];
  const groups = { title: [], strong: [], weak: [], pattern: 0, negative: [], foreign: [] };
  const head = [];
  const other = [];
  const hasFeatures = list.some((e) => FEATURE.test(e));
  let best = null;
  for (const raw of list) {
    if (raw.startsWith("odrzucono: ")) {
      const why = rejection(raw.slice("odrzucono: ".length), label, hasFeatures);
      head.push({ text: why?.text ?? raw, tone: "info" });
      best = why?.best ?? best;
      continue;
    }
    const m = raw.match(FEATURE);
    if (!m) {
      other.push({ text: raw, tone: "info" });
      continue;
    }
    const [, kind, body] = m;
    if (kind === "pattern") groups.pattern += 1;
    else if (kind === "foreign title") groups.foreign.push(...phrases(body));
    else groups[kind].push(...phrases(body));
  }
  const out = [...head];
  // rozpoznany typ: „tego typu”; odrzucony dokument: cechy najbliższego typu, nazwane wprost
  const ofType = best ? `typu ${label(best)}` : "tego typu";
  if (groups.title.length) out.push({ text: `Tytuł w nagłówku dokumentu: ${quoteList(groups.title)}.`, tone: "plus" });
  if (groups.strong.length) out.push({ text: `Słowa kluczowe ${ofType}: ${quoteList(groups.strong)}.`, tone: "plus" });
  if (groups.weak.length) out.push({ text: `Słowa pomocnicze: ${quoteList(groups.weak)}.`, tone: "plus" });
  if (groups.pattern) out.push({ text: `Pasujące wzorce tekstu: ${groups.pattern}.`, tone: "plus" });
  if (groups.negative.length) {
    out.push({
      text: `Słowa typowe dla innego dokumentu (obniżają wynik): ${quoteList(groups.negative)}.`,
      tone: "minus",
    });
  }
  if (groups.foreign.length) {
    out.push({ text: `Nagłówek innego rodzaju pisma (obniża wynik): ${quoteList(groups.foreign)}.`, tone: "minus" });
  }
  out.push(...other);
  if (!out.length && !known) out.push({ text: NONE_FOUND, tone: "info" });
  // „Nic nie znaleziono” jako jedyny powód: bez powtarzania tej samej informacji
  return out.filter((s, i) => s.text !== NONE_FOUND || out.findIndex((x) => x.text === NONE_FOUND) === i);
}
