"""Test statyczny GUI (etap E8E9, A2): strona się serwuje i ma wymagane landmarki/ARIA/teksty Gov.pl."""

from __future__ import annotations

import re
from html.parser import HTMLParser

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
    assert "Odwołania2JSON" in page.title


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
