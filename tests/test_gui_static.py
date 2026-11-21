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
