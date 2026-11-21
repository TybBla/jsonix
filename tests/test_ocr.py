"""OCR dla stron bez warstwy tekstowej (E2-T5): hook w ``ingest.load`` i silnik ``ocr.py``."""

from __future__ import annotations

from pathlib import Path

import pytest

from odw2json.contracts import Document
from odw2json.ingest import PAGE_SEPARATOR, _apply_ocr, load, ocr

ROOT = Path(__file__).resolve().parent.parent
NEG = ROOT / "data" / "train" / "negatywne"
SCANS = {
    "1648041143_1647951357decyzja-ministrasportu-pzn.pdf": 4,
    "Decyzja-Ministra-Sportu-i-Turystyki1.pdf": 1,
    "Minister-Sprawiedliwosci-pismo-RDSSP-z-11.03.2024-r..pdf": 2,
}
OCR_ON = {"enabled": True, "engine": "rapidocr", "min_chars_per_page": 30}
OCR_OFF = {"enabled": False}
POLISH = set("ąęłśżźćńó")


def _cfg(ocr_cfg: dict) -> dict:
    return {"backend": "pypdf", "fallback_backends": ["pypdfium2"], "clean": [], "ocr": ocr_cfg}


def _scan(name: str) -> Path:
    path = NEG / name
    if not path.exists():
        pytest.skip(f"brak pliku {name}")
    return path


@pytest.fixture
def ocr_calls(monkeypatch) -> list[tuple[str, int]]:
    """Podmienia ``ocr_page`` licznikiem (zwraca stały tekst) i zgłasza dostępność OCR."""
    calls: list[tuple[str, int]] = []

    def fake(path, page_index, cfg=None):
        calls.append((Path(path).name, page_index))
        return "TEKST Z OCR ąę"

    monkeypatch.setattr(ocr, "ocr_page", fake)
    monkeypatch.setattr(ocr, "ocr_available", lambda engine=None: True)
    return calls


def test_ocr_nie_rusza_stron_z_tekstem(ocr_calls):
    pdfs = sorted((ROOT / "data" / "train" / "przyklad_01").glob("*.pdf"))
    assert pdfs
    for pdf in pdfs:
        doc = load(pdf, cfg=_cfg(OCR_ON))
        assert all(len(p.strip()) >= 30 for p in doc.pages), pdf.name
        assert doc.ocr_used is False
        assert "ocr" not in doc.backend
        assert not any("OCR" in w for w in doc.warnings)
    assert ocr_calls == []


def test_skany_to_dokladnie_trzy_pliki_bez_tekstu():
    for name, n_pages in SCANS.items():
        doc = load(_scan(name), cfg=_cfg(OCR_OFF))
        assert len(doc.pages) == n_pages
        assert doc.text.replace(PAGE_SEPARATOR, "").strip() == ""
        assert doc.ocr_used is False


def test_brak_ocr_ostrzezenie_zamiast_wyjatku(monkeypatch):
    monkeypatch.setattr(ocr, "ocr_available", lambda engine=None: False)

    def boom(*a, **k):
        raise AssertionError("OCR nie powinien się uruchomić")

    monkeypatch.setattr(ocr, "ocr_page", boom)
    doc = load(_scan("Minister-Sprawiedliwosci-pismo-RDSSP-z-11.03.2024-r..pdf"), cfg=_cfg(OCR_ON))
    assert isinstance(doc, Document)
    assert doc.ocr_used is False
    assert doc.text.replace(PAGE_SEPARATOR, "").strip() == ""
    assert "OCR niedostępny – strona 1 bez tekstu" in doc.warnings
    assert "OCR niedostępny – strona 2 bez tekstu" in doc.warnings
    assert "ocr" not in doc.backend


def test_ocr_wylaczony_w_konfiguracji_nic_nie_robi(ocr_calls):
    doc = load(_scan("Decyzja-Ministra-Sportu-i-Turystyki1.pdf"), cfg=_cfg(OCR_OFF))
    assert ocr_calls == []
    assert not any("OCR" in w for w in doc.warnings)
    doc = load(_scan("Decyzja-Ministra-Sportu-i-Turystyki1.pdf"), cfg={"backend": "pypdf", "clean": []})
    assert ocr_calls == []
    assert doc.ocr_used is False


def test_ocr_zastepuje_tekst_skanu_offsety_scisle(ocr_calls):
    name = "1648041143_1647951357decyzja-ministrasportu-pzn.pdf"
    doc = load(_scan(name), cfg=_cfg(OCR_ON))
    assert sorted(i for _, i in ocr_calls) == [0, 1, 2, 3]
    assert doc.ocr_used is True
    assert doc.backend == "pypdf+ocr:rapidocr" or doc.backend.endswith("+ocr:rapidocr")
    assert doc.pages == ["TEKST Z OCR ąę"] * 4
    assert "TEKST Z OCR ąę" in doc.text
    assert [w for w in doc.warnings if w.startswith("OCR strony")] == [
        f"OCR strony {i}" for i in (1, 2, 3, 4)
    ]
    # offsety dokładne: tekst strony i zaczyna się dokładnie w page_offsets[i]
    for i, page in enumerate(doc.pages):
        off = doc.page_offsets[i]
        assert doc.text[off : off + len(page)] == page
        assert doc.page_of(off) == i
        assert doc.page_of(off + len(page) - 1) == i


def test_ocr_czyszczenie_dziala_na_tekscie_ocr(monkeypatch, ocr_calls):
    monkeypatch.setattr(ocr, "ocr_page", lambda path, i, cfg=None: "Zam awiający   Ł")
    cfg = _cfg(OCR_ON) | {"clean": ["nbsp_to_space", "collapse_spaces"]}
    doc = load(_scan("Decyzja-Ministra-Sportu-i-Turystyki1.pdf"), cfg=cfg)
    assert doc.pages == ["Zam awiający Ł"]


def test_pusty_wynik_ocr_nie_ustawia_ocr_used(monkeypatch, ocr_calls):
    monkeypatch.setattr(ocr, "ocr_page", lambda path, i, cfg=None: "")
    doc = load(_scan("Decyzja-Ministra-Sportu-i-Turystyki1.pdf"), cfg=_cfg(OCR_ON))
    assert doc.ocr_used is False
    assert "ocr" not in doc.backend
    assert "OCR strony 1: nie rozpoznano tekstu" in doc.warnings


def test_blad_ocr_to_ostrzezenie(monkeypatch, ocr_calls):
    def boom(path, i, cfg=None):
        raise RuntimeError("model uszkodzony")

    monkeypatch.setattr(ocr, "ocr_page", boom)
    doc = load(_scan("Decyzja-Ministra-Sportu-i-Turystyki1.pdf"), cfg=_cfg(OCR_ON))
    assert doc.ocr_used is False
    assert any(w.startswith("OCR strony 1 nieudany") and "model uszkodzony" in w for w in doc.warnings)


def test_ocr_nie_zastepuje_dluzszego_tekstu(monkeypatch, ocr_calls):
    """Strona z 5 znakami tekstu (< progu) i OCR krótszym od niej zostaje bez zmian."""
    monkeypatch.setattr(ocr, "ocr_page", lambda path, i, cfg=None: "ab")
    pages, engine = _apply_ocr(Path("x.pdf"), ["abcde"], OCR_ON, [])
    assert pages == ["abcde"] and engine is None


def test_nieznany_silnik_to_brak_ocr_bez_wyjatku():
    assert ocr.ocr_available("nie-ma-takiego") is False
    with pytest.raises(ValueError, match="rapidocr"):
        ocr.ocr_page(NEG / "x.pdf", 0, {"engine": "nie-ma-takiego"})


def test_group_lines_porzadek_gora_dol_lewo_prawo():
    def box(x, y, w=50, h=10):
        return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]

    boxes = [box(200, 52), box(10, 100), box(10, 50), box(100, 49)]
    texts = ["trzy", "cztery", "raz", "dwa"]
    assert ocr._group_lines(boxes, texts) == "raz dwa trzy\ncztery"


def test_cache_dysku_nie_liczy_strony_dwa_razy(tmp_path, monkeypatch):
    runs: list[int] = []

    def fake_run(image, cfg):
        runs.append(1)
        return "z silnika"

    monkeypatch.setitem(ocr.OCR_ENGINES, "fake", ocr.OcrEngine(available=lambda: True, run=fake_run))
    monkeypatch.setattr(ocr, "render_page", lambda path, i, dpi=200: object())
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    cfg = {"engine": "fake", "cache_dir": str(tmp_path / "cache")}
    assert ocr.ocr_page(pdf, 0, cfg) == "z silnika"
    assert ocr.ocr_page(pdf, 0, cfg) == "z silnika"  # pamięć procesu
    assert len(runs) == 1
    ocr._MEMO.clear()
    assert ocr.ocr_page(pdf, 0, cfg) == "z silnika"  # cache na dysku
    assert len(runs) == 1
    assert ocr.ocr_page(pdf, 1, cfg) == "z silnika"
    assert len(runs) == 2


# --- prawdziwy silnik -----------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.parametrize("name", list(SCANS))
def test_prawdziwy_silnik_czyta_skany(name):
    pytest.importorskip("rapidocr")
    pytest.importorskip("onnxruntime")
    assert ocr.ocr_available()
    doc = load(_scan(name), cfg=_cfg(OCR_ON))
    assert doc.ocr_used is True
    assert doc.backend.endswith("+ocr:rapidocr")
    assert len(doc.text.strip()) > 200
    # RapidOCR (PP-OCRv6 multi) obsługuje polskie znaki diakrytyczne
    assert len(POLISH & set(doc.text)) >= 4, sorted(POLISH & set(doc.text))
    assert "Warszawa" in doc.text or "Minister" in doc.text or "MINISTER" in doc.text
