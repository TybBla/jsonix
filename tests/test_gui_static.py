"""Test statyczny GUI (etap E8E9, A2): strona się serwuje i ma wymagane landmarki/ARIA/teksty Gov.pl."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from odw2json import api


class _Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str]]] = []
        self.text: list[str] = []
        self._title = False
        self.title = ""

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, {k: v or "" for k, v in attrs}))
        self._title = tag == "title"

    def handle_endtag(self, tag):
        if tag == "title":
            self._title = False

    def handle_data(self, data):
        self.text.append(data)
        if self._title:
            self.title += data

    def find(self, tag=None, **attrs) -> list[dict[str, str]]:
        def ok(a: dict[str, str], key: str, val: str) -> bool:
            key = key.rstrip("_")
            if key == "class":
                return val in a.get("class", "").split()
            return a.get(key) == val

        return [
            a
            for t, a in self.tags
            if (tag is None or t == tag) and all(ok(a, k, v) for k, v in attrs.items())
        ]

    def by_id(self, el_id: str) -> dict[str, str]:
        found = self.find(id=el_id)
        assert found, f"brak elementu #{el_id}"
        return found[0]

    @property
    def all_text(self) -> str:
        return " ".join(" ".join(self.text).split())


@pytest.fixture(scope="module")
def client():
    return TestClient(api.app)


@pytest.fixture(scope="module")
def page(client) -> _Tree:
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    tree = _Tree()
    tree.raw = r.text
    tree.feed(r.text)
    return tree


def test_document_basics(page):
    html = page.find("html")[0]
    assert html.get("lang") == "pl"
    assert page.find("meta", charset="utf-8") or page.find("meta", charset="UTF-8")
    assert page.find("meta", name="viewport")
    assert "jsonix" in page.title
    assert "jsonix" in page.raw
    assert "Odwołania2JSON" not in page.raw


def test_landmarks_and_skip_link(page):
    assert page.find("header")
    assert page.find("footer")
    mains = page.find("main")
    assert len(mains) == 1 and mains[0].get("id")
    skip = page.find("a", class_="skip-link")
    assert skip and skip[0]["href"] == "#" + mains[0]["id"]
    navs = page.find("nav")
    assert navs and all(n.get("aria-label") for n in navs)


def test_stepper_has_four_steps(page):
    stepper = page.by_id("stepper")
    assert stepper
    assert any("Etapy" in n.get("aria-label", "") for n in page.find("nav"))
    steps = page.find("li", class_="step")
    assert len(steps) == 4
    text = page.all_text
    for label in ("Dodaj pliki", "Wyniki klasyfikacji", "Sprawdź dane", "Pobierz JSON"):
        assert label in text


def test_uploader_follows_govpl(page):
    text = page.all_text
    assert "Przeciągnij i upuść pliki na to pole albo załaduj z dysku" in text
    assert re.search(r'<label[^>]*for="file-input"[^>]*>\s*Dodaj plik\s*</label>', page.raw)
    inp = page.by_id("file-input")
    assert inp.get("type") == "file"
    assert "multiple" in inp
    assert ".pdf" in inp.get("accept", "")
    hint_ids = inp.get("aria-describedby", "").split()
    assert "upload-error" in hint_ids, "komunikat błędu powiązany z polem"
    for hid in hint_ids:
        page.by_id(hid)
    assert page.find("label", for_="file-input")
    assert "PDF" in text and "25 MB" in text


def test_error_summary_and_live_regions(page):
    summary = page.by_id("error-summary")
    assert summary.get("role") == "alert"
    assert summary.get("tabindex") == "-1"
    status = page.by_id("status")
    assert status.get("role") == "status" or status.get("aria-live") == "polite"
    assert page.find("progress")


def test_single_primary_button_per_screen(page):
    primaries = [
        a for t, a in page.tags if t in ("a", "button") and "btn-primary" in a.get("class", "").split()
    ]
    screens = [a.get("data-screen") for a in primaries]
    assert all(screens), "każdy Primary ma data-screen"
    assert len(screens) == len(set(screens)), "jeden przycisk Primary na ekran"
    analyse = page.by_id("analyse-btn")
    assert "btn-primary" in analyse.get("class", "")


def test_results_table_is_accessible(page):
    assert page.by_id("results-table")
    assert page.find("caption")
    ths = page.find("th")
    assert ths and all(th.get("scope") in ("col", "row") for th in ths)
    assert page.by_id("zip-btn")


def test_footer_links_to_html_accessibility_statement(client, page):
    links = [a["href"] for a in page.find("a") if "href" in a]
    target = next(h for h in links if "deklaracja-dostepnosci" in h)
    assert target.endswith(".html")
    r = client.get(target)
    assert r.status_code == 200 and "Deklaracja dostępności" in r.text


def test_static_assets_are_served(client, page):
    refs = [a["href"] for a in page.find("link", rel="stylesheet")]
    refs += [a["src"] for a in page.find("script") if a.get("src")]
    assert refs
    for ref in refs:
        assert not ref.startswith("http"), f"zasób z sieci: {ref} (GUI ma działać offline)"
        r = client.get(ref)
        assert r.status_code == 200, ref


def test_every_aria_reference_points_to_existing_id(page):
    ids = {a["id"] for _, a in page.tags if a.get("id")}
    for _, a in page.tags:
        for attr in ("aria-labelledby", "aria-describedby", "aria-controls"):
            for ref in a.get(attr, "").split():
                assert ref in ids, f"{attr}={ref} wskazuje na nieistniejący element"


def test_accessibility_statement_applies_saved_view_settings(client):
    html = client.get("/static/deklaracja-dostepnosci.html").text
    assert re.search(r'<script[^>]+src="/static/js/[^"]+\.js"', html)


# --- logika JS (A3): dopasowanie fragmentu źródłowego i budowa listy pól; wymaga Node ---

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "web" / "static" / "js"
FIXTURES = ROOT / "tests" / "fixtures" / "gui"
P01 = ROOT / "data" / "train" / "przyklad_01"
FIXTURE_PDF = {
    "przyklad_01_odwolanie.result.json": "odwolanie.pdf",
    "przyklad_01_pelnomocnictwo.result.json": "pelnomocnictwo.pdf",
    "przyklad_01_potwierdzenie_przelewu.result.json": "potwierdzenie_przelewu.pdf",
}
needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="brak Node.js")


def _node(script: str, payload) -> object:
    """Uruchamia moduł ES w Node; skrypt dostaje `input` i zwraca wynik przez `output(...)`."""
    prelude = (
        f"const input = JSON.parse(process.env.O2J_INPUT);"
        f"const output = (v) => process.stdout.write(JSON.stringify(v));"
        f"const js = (name) => import({json.dumps((JS).as_uri())} + '/' + name);"
    )
    r = subprocess.run(
        ["node", "--input-type=module", "-e", prelude + script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "O2J_INPUT": json.dumps(payload, ensure_ascii=False)},
        timeout=60,
    )
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _pdf_pages(pdf: Path) -> list[str]:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(pdf))
    try:
        return [doc[i].get_textpage().get_text_range() for i in range(len(doc))]
    finally:
        doc.close()


@needs_node
def test_normalize_ignores_whitespace_quotes_and_line_hyphens():
    out = _node(
        """const m = await js('match.js');
        output(input.map((t) => m.normalize(t).norm));""",
        ["KRS:  9999\n405188", "„Zakup”", "postępo-\nwania", "A–B"],
    )
    assert out == ["krs:9999405188", '"zakup"', "postępowania", "a-b"]


@needs_node
def test_locate_prefers_value_inside_snippet_and_falls_back_to_partial():
    out = _node(
        """const m = await js('match.js');
        const page = `Odwołujący: Belmoria S.A.\nKRS: 9999405188, NIP:\n9999284065, REGON: 1`;
        const r1 = m.locate(page, 'KRS: 9999405188, NIP: 9999284065, REGON: 1', '9999284065');
        const r2 = m.locate(page, 'NIP: 9999284065, REGON: 1, tekst spoza strony', '9999284065');
        const r3 = m.locate(page, 'zupełnie inny tekst', 'x');
        output([page.slice(r1.start, r1.end), r1.kind, page.slice(r2.start, r2.end), r2.kind, r3]);""",
        None,
    )
    assert out == ["9999284065", "value", "9999284065", "partial", None]


@needs_node
@pytest.mark.parametrize("fixture", sorted(FIXTURE_PDF))
def test_every_traced_field_is_found_in_pdf_text(fixture):
    result = json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))
    pages = _pdf_pages(P01 / FIXTURE_PDF[fixture])
    traced = [t for t in result["trace"] if t["page"] is not None and t["source_snippet"]]
    assert traced
    hits = _node(
        """const m = await js('match.js');
        const find = (t) => m.locateInDocument(input.pages, t.page, t.source_snippet, t.value);
        output(input.trace.map(find));""",
        {"pages": pages, "trace": traced},
    )
    missing = [t["path"] for t, h in zip(traced, hits, strict=True) if h is None]
    assert not missing, f"nie znaleziono w PDF: {missing}"
    for t, h in zip(traced, hits, strict=True):
        assert h["page"] == t["page"], t["path"]


@needs_node
def test_tree_is_built_from_data_and_marks_sources():
    result = json.loads((FIXTURES / "przyklad_01_odwolanie.result.json").read_text(encoding="utf-8"))
    out = _node(
        """const f = await js('fields.js');
        const tree = f.buildTree(input.data);
        const idx = f.traceIndex(input.trace);
        const leaves = f.leaves(tree);
        output({
          sections: tree.map((n) => n.label),
          paths: leaves.map((l) => l.path),
          states: Object.fromEntries(leaves.map((l) => [l.path, f.sourceState(l, idx.get(l.path))])),
          item: tree[1].children[0].label,
          fallback: f.labelFor('numer_umowy'),
          ocr: [...f.ocrPages(['OCR strony 2', 'Ingest: cos'])],
        });""",
        result,
    )
    assert out["sections"] == ["Odwołanie do KIO", "Odwołujący", "Zamawiający", "Zamówienie publiczne"]
    assert "Odwolujacy[0].pelnomocnik.mail" in out["paths"]
    assert out["states"]["OdwolanieKIO.data"] == "empty"
    assert out["states"]["OdwolanieKIO.czynnosc_opis"] == "missing"
    assert out["states"]["Odwolujacy[0].nip"] == "source"
    assert out["item"] == "Odwołujący 1"
    assert out["fallback"] == "Numer umowy"
    assert out["ocr"] == [1]


def test_vendored_libraries_are_served_with_licenses(client):
    for path in ("/static/vendor/pdfjs/pdf.min.mjs", "/static/vendor/pdfjs/pdf.worker.min.mjs"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert "javascript" in r.headers["content-type"], "moduły ES muszą mieć typ JavaScript"
    vendor = JS.parent / "vendor"
    assert "Apache License" in (vendor / "pdfjs" / "LICENSE").read_text(encoding="utf-8")
    assert "SIL OPEN FONT LICENSE" in (vendor / "fonts" / "LICENSE").read_text(encoding="utf-8").upper()
    assert client.get("/static/vendor/fonts/open-sans-latin-ext-400-normal.woff2").status_code == 200


@needs_node
def test_edits_are_applied_to_a_copy_with_original_types():
    out = _node(
        """const f = await js('fields.js');
        const data = {a: {kwota: 200, nip: '1', puste: null}, l: [{x: 'y'}]};
        const edits = new Map([
          ['a.kwota', f.parseEditedValue('7 500,50', 200)],
          ['a.nip', f.parseEditedValue('  999  ', '1')],
          ['a.puste', f.parseEditedValue('nowa', null)],
          ['l[0].x', f.parseEditedValue('', 'y')],
        ]);
        const result = f.applyEdits(data, edits);
        output({result, original: data, bad: f.parseEditedValue('abc', 5)});""",
        None,
    )
    assert out["result"] == {"a": {"kwota": 7500.5, "nip": "999", "puste": "nowa"}, "l": [{"x": None}]}
    assert out["original"]["a"]["kwota"] == 200, "oryginał bez zmian"
    assert out["bad"] == "abc", "tekst, którego nie da się odczytać jako liczba, zostaje tekstem"


def test_review_offers_edit_and_restore(client):
    js = client.get("/static/js/review.js").text
    for text in ("Zmień", "Przywróć wartość z dokumentu", "Zmieniono ręcznie"):
        assert text in js


# --- podgląd przy najechaniu (E8E9 v2): mapa pole ↔ obszary liczona raz, logika stanów hover ---


@needs_node
@pytest.mark.parametrize("fixture", sorted(FIXTURE_PDF))
def test_source_map_is_built_once_for_all_traced_fields(fixture):
    result = json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))
    pages = _pdf_pages(P01 / FIXTURE_PDF[fixture])
    traced = [t for t in result["trace"] if t["page"] is not None and t["source_snippet"]]
    out = _node(
        """const m = await js('match.js');
        const entries = input.trace.map((t) => (
          {path: t.path, page: t.page, snippet: t.source_snippet, value: t.value}));
        const first = input.trace[0].source_snippet;
        entries.push({path: 'skan', page: 0, snippet: first, value: null, skip: true});
        const map = m.buildSourceMap(input.pages, entries);
        output({size: map.size, hits: Object.fromEntries(map), isMap: map instanceof Map});""",
        {"pages": pages, "trace": traced},
    )
    assert out["isMap"] and out["size"] == len(traced) + 1
    assert out["hits"]["skan"] is None, "skan bez warstwy tekstu: brak dopasowania zamiast zgadywania"
    for t in traced:
        hit = out["hits"][t["path"]]
        assert hit and hit["page"] == t["page"], t["path"]
        assert hit["end"] > hit["start"]


@needs_node
def test_other_pages_are_searched_only_for_the_exact_snippet():
    out = _node(
        """const m = await js('match.js');
        const snippet = 'Zamawiający: Gmina Przykładowo, ul. Długa 1';
        const partialOnly = ['brak', 'Zamawiający: Gmina Przykładowo, ul. Krótka 9', 'brak'];
        const exactLater = ['brak', 'brak', 'xx Zamawiający: Gmina Przykładowo, ul. Długa 1 yy'];
        output([
          m.locateInDocument(partialOnly, 0, snippet, null),
          m.locateInDocument(exactLater, 0, snippet, null)?.page,
          m.locateInDocument(partialOnly, 1, snippet, null)?.kind,
        ]);""",
        None,
    )
    assert out == [None, 2, "partial"]


@needs_node
def test_source_map_is_fast_for_long_documents_without_matches():
    out = _node(
        """const m = await js('match.js');
        let seed = 7;
        const rnd = () => (seed = (seed * 48271) % 2147483647) / 2147483647;
        const abc = 'abcdefghijklmnoprstuwyz';
        const letter = () => abc[Math.floor(rnd() * abc.length)];
        const word = () => Array.from({length: 3 + Math.floor(rnd() * 8)}, letter).join('');
        const pages = Array.from({length: 40}, () => Array.from({length: 900}, word).join(' '));
        const entries = Array.from({length: 40}, (_, i) => ({
          path: `p${i}`, page: i % 40, value: `9${i}9284065`,
          snippet: `NIP: 9${i}9284065, REGON: 999642785, KRS 0000${i} pozostała treść fragmentu `
            + `źródłowego ${'q'.repeat(150)}`,
        }));
        const t0 = performance.now();
        const map = m.buildSourceMap(pages, entries);
        output({ms: performance.now() - t0, found: [...map.values()].filter(Boolean).length});""",
        None,
    )
    assert out["found"] == 0
    assert out["ms"] < 3000, f"budowa mapy trwała {out['ms']:.0f} ms"


@needs_node
def test_hover_on_field_previews_fragment_and_marks_other_page():
    out = _node(
        """const h = await js('hover.js');
        const map = new Map([
          ['a', {page: 3, start: 0, end: 5}], ['b', {page: 0, start: 1, end: 4}], ['c', null]]);
        const range = {first: 0, last: 1};
        let s = h.hoverReducer(h.createHoverState(), {type: 'select', path: 'b'});
        const views = [];
        s = h.hoverReducer(s, {type: 'enter', source: 'field-pointer', path: 'a'});
        views.push(h.hoverView(s, map, range));
        s = h.hoverReducer(s, {type: 'enter', source: 'field-pointer', path: 'b'});
        views.push(h.hoverView(s, map, range));
        s = h.hoverReducer(s, {type: 'enter', source: 'field-pointer', path: 'c'});
        views.push(h.hoverView(s, map, range));
        s = h.hoverReducer(s, {type: 'leave', source: 'field-pointer', path: 'c'});
        views.push(h.hoverView(s, map, range));
        output(views);""",
        None,
    )
    a, b, c, gone = out
    assert a == {"selected": "b", "preview": "a", "docPreview": "a", "badgePage": 3, "revealField": None}
    assert b["docPreview"] == "b" and b["badgePage"] is None, "fragment na widocznej stronie: bez znacznika"
    assert c["preview"] == "c" and c["docPreview"] is None and c["badgePage"] is None
    assert gone == {
        "selected": "b",
        "preview": None,
        "docPreview": None,
        "badgePage": None,
        "revealField": None,
    }


@needs_node
def test_hover_on_document_fragment_reveals_field_and_sources_stack():
    out = _node(
        """const h = await js('hover.js');
        const map = new Map([['a', {page: 3}], ['b', {page: 0}]]);
        const range = {first: 3, last: 3};
        let s = h.createHoverState();
        s = h.hoverReducer(s, {type: 'enter', source: 'doc-pointer', path: 'a'});
        const doc = h.hoverView(s, map, range);
        s = h.hoverReducer(s, {type: 'leave', source: 'doc-pointer', path: 'a'});
        s = h.hoverReducer(s, {type: 'enter', source: 'field-focus', path: 'b'});
        s = h.hoverReducer(s, {type: 'enter', source: 'field-pointer', path: 'a'});
        const top = h.previewPath(s);
        // zejście z innego elementu niż ten w podglądzie: bez zmian
        s = h.hoverReducer(s, {type: 'leave', source: 'field-pointer', path: 'b'});
        const still = h.previewPath(s);
        s = h.hoverReducer(s, {type: 'leave', source: 'field-pointer', path: 'a'});
        const back = h.hoverView(s, map, range);
        s = h.hoverReducer(s, {type: 'reset'});
        output({doc, top, still, back, reset: h.hoverView(s, map, range)});""",
        None,
    )
    assert out["doc"]["revealField"] == "a" and out["doc"]["badgePage"] is None
    assert out["top"] == "a" and out["still"] == "a"
    assert out["back"]["preview"] == "b" and out["back"]["badgePage"] == 0, "wraca podgląd z fokusu"
    assert out["reset"]["preview"] is None and out["reset"]["selected"] is None


@needs_node
def test_visible_range_of_pages_in_scroll_container():
    out = _node(
        """const h = await js('hover.js');
        const spans = [{top: 0, bottom: 1000}, {top: 1012, bottom: 2012}, {top: 2024, bottom: 3024}];
        const at = (top) => h.visibleRange(spans, top, 800);
        output([at(0), at(900), at(2500), h.visibleRange([], 0, 800)]);""",
        None,
    )
    assert out == [{"first": 0, "last": 0}, {"first": 0, "last": 1}, {"first": 2, "last": 2}, None]


def test_hover_preview_styles_are_lighter_than_selection_and_not_color_only(client):
    css = client.get("/static/css/app.css").text
    for sel in (".hl-box.is-preview", ".field.is-preview", ".page-badge"):
        assert sel in css, sel
    rule = re.search(r"\.hl-box\.is-preview\s*\{([^}]*)\}", css).group(1)
    assert "border" in rule, "podgląd nie tylko kolorem: obramowanie"
    order = css.index(".hl-box.is-preview") < css.index(".hl-box.is-active")
    assert order, "zaznaczenie z kliknięcia wygrywa"
    js = client.get("/static/js/review.js").text
    for text in ("mouseenter", "mouseleave", "focus", "blur", "strona "):
        assert text in js, text


# --- poprawki z review PR #4 (GUI) ---


@needs_node
def test_plural_forms_in_polish():
    out = _node(
        """const u = await js('ui.js');
        output([1, 2, 4, 5, 12, 22, 25, 101, 0].map((n) => u.plural(n, 'pola', 'pól', 'pól')
          + '|' + u.plural(n, 'plik', 'pliki', 'plików')));""",
        None,
    )
    assert out == [
        "pola|plik",
        "pól|pliki",
        "pól|pliki",
        "pól|plików",
        "pól|plików",
        "pól|pliki",
        "pól|plików",
        "pól|plików",
        "pól|plików",
    ]


def test_no_hardcoded_plural_after_number(client):
    for name in ("app.js", "review.js"):
        js = client.get(f"/static/js/{name}").text
        assert not re.search(r"\$\{[^}]+\} (pól|plików)", js), f"{name}: odmiana przez plural()"


def test_results_explain_document_type(client):
    js = client.get("/static/js/app.js").text
    assert "Dlaczego ten typ?" in js
    assert "evidence" in js
    assert re.search(r'el\(\s*"details"', js) and re.search(r'el\(\s*"summary"', js)


def test_gui_limits_number_of_files_like_api(client):
    js = client.get("/static/js/app.js").text
    assert re.search(r"MAX_FILES\s*=\s*50\b", js)
    assert api.MAX_FILES == 50


# --- czytelne „Dlaczego ten typ?” (evidence z klasyfikatora E3) ---

EVIDENCE_ODWOLANIE = [
    "strong: 'odwolanie' (+2)",
    "strong: 'odwolujacy' (+2)",
    "strong: 'zarzut' (+2)",
    "weak: 'zamawiajacy' (+1)",
    "weak: 'wnosze o' (+1)",
    "negative: 'ogloszenie o zamowieniu' (-3)",
    "title: 'odwolanie' (+4)",
    "pattern: 'odwolujacy:' (+3)",
    "pattern: 'zarzut nr \\d+' (+3)",
]


@needs_node
def test_evidence_is_explained_in_plain_polish():
    out = _node(
        """const e = await js('evidence.js');
        const label = (id) => ({odwolanie: 'Odwołanie', pelnomocnictwo: 'Pełnomocnictwo'})[id] || id;
        const no = (ev) => e.explainEvidence(ev, {known: false, label});
        const best = (b) => `(najlepszy: ${b})`;
        output({
          known: e.explainEvidence(input.ev, {known: true, label}),
          low: no([`odrzucono: wynik 3 < min_score 5 ${best('pelnomocnictwo')}`, "strong: 'udzielam' (+2)"]),
          zero: no([`odrzucono: wynik 0 < min_score 5 ${best('pelnomocnictwo')}`]),
          margin: no([`odrzucono: margines 0.5 < min_margin 1 ${best('odwolanie')}`]),
          required: no(['odrzucono: odwolanie: brak wymaganej cechy (required_any: zarzut); '
                        + 'przelew: brak wymaganej cechy (required_any: kwota)']),
          foreign: no(["foreign title: 'wyrok' (-10)"]),
          negScore: no([`odrzucono: wynik -11 < min_score 5 ${best('pelnomocnictwo')}`,
                        "strong: 'udzielaja' (+2)", "foreign title: 'ogloszenie o' (-10)"]),
          empty: no([]),
          odd: e.explainEvidence(['nowy format cechy'], {known: true, label}),
        });""",
        {"ev": EVIDENCE_ODWOLANIE},
    )
    known = [s["text"] for s in out["known"]]
    assert known[0] == "Tytuł w nagłówku dokumentu: „odwolanie”."
    assert "Słowa kluczowe tego typu: „odwolanie”, „odwolujacy”, „zarzut”." in known
    assert "Słowa pomocnicze: „zamawiajacy”, „wnosze o”." in known
    assert "Pasujące wzorce tekstu: 2." in known
    assert "Słowa typowe dla innego dokumentu (obniżają wynik): „ogloszenie o zamowieniu”." in known
    assert all("(+" not in t and "strong" not in t for t in known), "bez technicznych etykiet i punktów"
    assert {s["tone"] for s in out["known"]} <= {"plus", "minus", "info"}

    low = [s["text"] for s in out["low"]]
    assert low[0] == "Za mało cech, żeby rozpoznać typ. Najbliżej było: Pełnomocnictwo."
    assert "Słowa kluczowe typu Pełnomocnictwo: „udzielam”." in low
    zero = [s["text"] for s in out["zero"]]
    assert zero == ["Nie znaleziono cech żadnego z obsługiwanych typów dokumentów."]
    assert out["margin"][0]["text"].startswith("Dokument pasuje do kilku typów podobnie")
    assert "Odwołanie" in out["margin"][0]["text"]
    req = out["required"][0]["text"]
    assert req.startswith("Brak cechy wymaganej dla typów:") and "Odwołanie" in req and "przelew" in req
    assert out["foreign"][0]["text"] == "Nagłówek innego rodzaju pisma (obniża wynik): „wyrok”."
    nothing = "Nie znaleziono cech żadnego z obsługiwanych typów dokumentów."
    assert [s["text"] for s in out["empty"]] == [nothing]
    neg = [s["text"] for s in out["negScore"]]
    closest = "Za mało cech, żeby rozpoznać typ. Najbliżej było: Pełnomocnictwo."
    assert neg[0] == closest, "cechy są, więc nie „nic”"
    assert "Słowa kluczowe typu Pełnomocnictwo: „udzielaja”." in neg
    assert out["odd"][0]["text"] == "nowy format cechy", "nieznany format: pokaż bez zmian"


def test_results_show_readable_reasons_and_raw_details(client):
    js = client.get("/static/js/app.js").text
    assert "explainEvidence" in js
    assert "Szczegóły techniczne" in js


def test_pdf_highlights_keep_contrast_on_white_page_in_high_contrast_mode(client):
    """Strona PDF zostaje biała: obramowania nie mogą brać koloru motywu (#ff0 na bieli ≈ 1,1:1)."""
    css = client.get("/static/css/app.css").text
    rules = re.findall(r"([^{}]*\.hl-box[^{}]*)\{([^}]*)\}", css)
    assert rules
    for selector, body in rules:
        if "border" in body:
            assert "var(--" not in body.split("background")[0], f"kolor z motywu w {selector.strip()}"
            assert "#ff0" not in body.lower(), f"żółte obramowanie na białej stronie: {selector.strip()}"
    high = [b for s, b in rules if 'data-contrast="high"' in s and ".is-preview" in s]
    assert high and "#000" in high[0]
