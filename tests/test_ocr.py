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
    doc = load(
        _scan("Decyzja-Ministra-Sportu-i-Turystyki1.pdf"), cfg={"backend": "pypdf", "clean": [], "ocr": {}}
    )
    assert ocr_calls == []  # sekcja ocr podana jawnie (bez enabled) = OCR wyłączony
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
    assert any(w.startswith("OCR nieudany – strona 1") and "model uszkodzony" in w for w in doc.warnings)


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
@pytest.mark.ocr_live
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


# --- poprawki po review etapu E2 ---


def test_stale_empty_text_warning_removed_when_ocr_recovers_all_pages(ocr_calls):
    doc = load(_scan("1648041143_1647951357decyzja-ministrasportu-pzn.pdf"), cfg=_cfg(OCR_ON))
    assert doc.ocr_used is True
    assert not any("żaden backend nie wyciągnął tekstu" in w for w in doc.warnings)
    assert "OCR strony 1" in doc.warnings


def test_stale_warning_kept_when_ocr_recovers_nothing(monkeypatch, ocr_calls):
    monkeypatch.setattr(ocr, "ocr_page", lambda path, i, cfg=None: "")
    doc = load(_scan("Decyzja-Ministra-Sportu-i-Turystyki1.pdf"), cfg=_cfg(OCR_ON))
    assert any("żaden backend nie wyciągnął tekstu" in w for w in doc.warnings)


def test_resolve_cache_dir_relative_vs_absolute(tmp_path, monkeypatch):
    from odw2json import config_loader

    monkeypatch.setattr(config_loader, "ROOT_DIR", tmp_path / "root")
    monkeypatch.chdir(tmp_path)
    assert ocr.resolve_cache_dir("output/.cache/ocr") == tmp_path / "root" / "output" / ".cache" / "ocr"
    absolute = tmp_path / "abs"
    assert ocr.resolve_cache_dir(str(absolute)) == absolute


def _fake_engine(monkeypatch, runs):
    def fake_run(image, cfg):
        runs.append(1)
        return "z silnika"

    monkeypatch.setitem(ocr.OCR_ENGINES, "fake", ocr.OcrEngine(available=lambda: True, run=fake_run))
    monkeypatch.setattr(ocr, "render_page", lambda path, i, dpi=200: object())
    ocr._MEMO.clear()
    ocr._file_digest.cache_clear()


def test_relative_cache_dir_resolved_against_root_not_cwd(tmp_path, monkeypatch):
    from odw2json import config_loader

    root = tmp_path / "root"
    monkeypatch.setattr(config_loader, "ROOT_DIR", root)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    runs: list[int] = []
    _fake_engine(monkeypatch, runs)
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    ocr.ocr_page(pdf, 0, {"engine": "fake", "cache_dir": "cache/ocr"})
    assert list((root / "cache" / "ocr").glob("*.txt"))
    assert not (elsewhere / "cache").exists()


def test_cache_filename_has_version_and_package_version(tmp_path, monkeypatch):
    runs: list[int] = []
    _fake_engine(monkeypatch, runs)
    monkeypatch.setattr(ocr, "_package_version", lambda: "9.9.9")
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    ocr.ocr_page(pdf, 0, {"engine": "fake", "cache_dir": str(tmp_path / "c")})
    (f,) = (tmp_path / "c").glob("*.txt")
    assert ocr.OCR_CACHE_VERSION == "2"
    assert ".v2." in f.name and "9.9.9" in f.name


def test_package_version_na_when_missing(monkeypatch):
    import importlib.metadata as md

    def boom(name):
        raise md.PackageNotFoundError(name)

    monkeypatch.setattr(md, "version", boom)
    ocr._package_version.cache_clear()
    try:
        assert ocr._package_version() == "na"
    finally:
        ocr._package_version.cache_clear()


@pytest.mark.parametrize("content", [b"", b"\xff\xfe\x00bad"])
def test_corrupt_or_empty_cache_is_miss_and_overwritten(tmp_path, monkeypatch, content):
    runs: list[int] = []
    _fake_engine(monkeypatch, runs)
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    cfg = {"engine": "fake", "cache_dir": str(tmp_path / "c")}
    ocr.ocr_page(pdf, 0, cfg)
    (f,) = (tmp_path / "c").glob("*.txt")
    f.write_bytes(content)
    ocr._MEMO.clear()
    assert ocr.ocr_page(pdf, 0, cfg) == "z silnika"
    assert len(runs) == 2
    assert f.read_text(encoding="utf-8") == "z silnika"
    assert not list((tmp_path / "c").glob("*.tmp"))


def test_cache_write_is_atomic_via_replace(tmp_path, monkeypatch):
    runs: list[int] = []
    _fake_engine(monkeypatch, runs)
    replaced: list[tuple] = []
    real = ocr.os.replace
    monkeypatch.setattr(ocr.os, "replace", lambda a, b: (replaced.append((str(a), str(b))), real(a, b))[1])
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    ocr.ocr_page(pdf, 0, {"engine": "fake", "cache_dir": str(tmp_path / "c")})
    assert len(replaced) == 1
    assert replaced[0][0].endswith(".tmp") and replaced[0][1].endswith(".txt")


def test_file_hashed_once_per_document(tmp_path, monkeypatch):
    runs: list[int] = []
    _fake_engine(monkeypatch, runs)
    hashed: list[int] = []
    real = ocr._hash_file
    monkeypatch.setattr(ocr, "_hash_file", lambda p: (hashed.append(1), real(p))[1])
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    for i in range(4):
        ocr.ocr_page(pdf, i, {"engine": "fake"})
    assert len(hashed) == 1
    pdf.write_bytes(b"%PDF-1.4 fake changed content")  # zmiana pliku = nowy hash
    ocr.ocr_page(pdf, 0, {"engine": "fake"})
    assert len(hashed) == 2


def test_memo_is_bounded(tmp_path, monkeypatch):
    runs: list[int] = []
    _fake_engine(monkeypatch, runs)
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    for i in range(ocr.MEMO_MAX + 20):
        ocr.ocr_page(pdf, i, {"engine": "fake"})
    assert len(ocr._MEMO) == ocr.MEMO_MAX


# --- E2b-T3: parametry silnika, klucz cache, walidacja ---


def test_cache_version_bumped_for_engine_params():
    assert int(ocr.OCR_CACHE_VERSION) >= 2  # v1 nie znal engine_params: stare wpisy sa niewazne


def test_cache_key_includes_engine_params(tmp_path, monkeypatch):
    runs: list[int] = []
    _fake_engine(monkeypatch, runs)
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    base = {"engine": "fake", "cache_dir": str(tmp_path / "c")}
    ocr.ocr_page(pdf, 0, base | {"engine_params": {"Global.use_cls": False}})
    ocr.ocr_page(pdf, 0, base | {"engine_params": {"Global.use_cls": False}})  # ten sam klucz
    assert len(runs) == 1
    ocr.ocr_page(pdf, 0, base | {"engine_params": {"Global.use_cls": True}})  # inny parametr = miss
    assert len(runs) == 2
    ocr.ocr_page(pdf, 0, base)  # brak parametrow to tez inny klucz
    assert len(runs) == 3
    assert len(list((tmp_path / "c").glob("*.txt"))) == 3


def test_engine_params_order_does_not_change_key(tmp_path, monkeypatch):
    runs: list[int] = []
    _fake_engine(monkeypatch, runs)
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    base = {"engine": "fake", "cache_dir": str(tmp_path / "c")}
    ocr.ocr_page(pdf, 0, base | {"engine_params": {"a.b": 1, "c.d": 2}})
    ocr.ocr_page(pdf, 0, base | {"engine_params": {"c.d": 2, "a.b": 1}})
    assert len(runs) == 1


def test_dpi_still_part_of_cache_key(tmp_path, monkeypatch):
    runs: list[int] = []
    _fake_engine(monkeypatch, runs)
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    base = {"engine": "fake", "cache_dir": str(tmp_path / "c")}
    ocr.ocr_page(pdf, 0, base | {"dpi": 150})
    ocr.ocr_page(pdf, 0, base | {"dpi": 200})
    assert len(runs) == 2


def test_engine_params_passed_to_rapidocr(monkeypatch):
    seen: list[dict | None] = []

    class FakeRapid:
        def __init__(self, params=None):
            seen.append(params)

        def __call__(self, img):
            return type("R", (), {"boxes": None, "txts": None})()

    import sys
    import types

    from PIL import Image

    monkeypatch.setitem(sys.modules, "rapidocr", types.SimpleNamespace(RapidOCR=FakeRapid))
    ocr._rapidocr_engine.cache_clear()
    try:
        params = {"Global.use_cls": False, "Rec.rec_batch_num": 1}
        assert ocr._rapidocr_run(Image.new("RGB", (4, 4)), {"engine_params": params}) == ""
        ocr._rapidocr_run(Image.new("RGB", (4, 4)), {"engine_params": dict(params)})  # ten sam silnik
        ocr._rapidocr_run(Image.new("RGB", (4, 4)), {})
        assert seen == [params, None]
    finally:
        ocr._rapidocr_engine.cache_clear()


@pytest.mark.parametrize(
    ("ocr_cfg", "fragment"),
    [
        ({"engine_params": ["a"]}, "ocr.engine_params"),
        ({"engine_params": {"": 1}}, "ocr.engine_params"),
        ({"engine_params": {1: 1}}, "ocr.engine_params"),
        ({"engine_params": {"Global": 1}}, "ocr.engine_params"),
        ({"engine_params": {"Global.use_cls": {"a": 1}}}, "ocr.engine_params"),
    ],
)
def test_validate_ocr_engine_params_odrzucone(ocr_cfg, fragment):
    from odw2json import ingest

    with pytest.raises(ValueError, match=fragment):
        ingest.validate_ingest_cfg({"ocr": ocr_cfg})


def test_validate_ocr_engine_params_poprawne():
    from odw2json import ingest

    ingest.validate_ingest_cfg(
        {
            "ocr": {
                "enabled": True,
                "dpi": 150,
                "engine_params": {
                    "Global.use_cls": False,
                    "EngineConfig.onnxruntime.intra_op_num_threads": 4,
                },
            }
        }
    )


def test_konfiguracja_aplikacji_ma_poprawna_sekcje_ocr():
    from odw2json import ingest
    from odw2json.config_loader import load_app_config

    cfg = load_app_config()["ingest"]
    ingest.validate_ingest_cfg(cfg)
    assert cfg["ocr"]["enabled"] is True
    assert cfg["ocr"]["dpi"] == 150
    assert cfg["ocr"]["engine_params"]["Global.use_cls"] is False
    assert "ocr_artifacts" not in cfg["clean"]  # tylko dla tekstu z OCR
    assert cfg["ocr"]["postprocess"] == ["ocr_artifacts"]


@pytest.mark.slow
@pytest.mark.ocr_live
def test_prawdziwy_silnik_z_parametrami_z_konfiguracji():
    pytest.importorskip("rapidocr")
    from odw2json.config_loader import load_app_config

    cfg = dict(load_app_config()["ingest"]["ocr"]) | {"cache_dir": None}
    text = ocr.ocr_page(_scan("Decyzja-Ministra-Sportu-i-Turystyki1.pdf"), 0, cfg)
    assert len(text.strip()) > 200


# --- ocr.postprocess: ocr_artifacts tylko dla tekstu z OCR ----------------------------------------


def test_postprocess_ocr_naprawia_artefakty_tylko_w_tekscie_ocr(monkeypatch, ocr_calls):
    monkeypatch.setattr(ocr, "ocr_page", lambda path, i, cfg=None: "Zamawıający Ñowak")
    cfg = _cfg(OCR_ON | {"postprocess": ["ocr_artifacts"]})
    doc = load(_scan("Decyzja-Ministra-Sportu-i-Turystyki1.pdf"), cfg=cfg)
    assert doc.pages == ["Zamawiający Ńowak"]


def test_bez_postprocess_artefakty_ocr_zostaja(monkeypatch, ocr_calls):
    monkeypatch.setattr(ocr, "ocr_page", lambda path, i, cfg=None: "Zamawıający")
    doc = load(_scan("Decyzja-Ministra-Sportu-i-Turystyki1.pdf"), cfg=_cfg(OCR_ON))
    assert doc.pages == ["Zamawıający"]


def test_warstwa_tekstowa_nie_przechodzi_przez_ocr_artifacts(monkeypatch, ocr_calls):
    from odw2json.ingest import backends, clean

    text = "Zamawiający: José Škoda, Ñandú sp. z o.o., ul. Długa 1, 00-001 Warszawa"
    monkeypatch.setitem(backends.BACKENDS, "pypdf", lambda path: [text])
    cfg = _cfg(OCR_ON | {"postprocess": ["ocr_artifacts"]}) | {"clean": list(clean.DEFAULT_ORDER)}
    doc = load(_scan("Decyzja-Ministra-Sportu-i-Turystyki1.pdf"), cfg=cfg)
    assert ocr_calls == []
    assert doc.ocr_used is False
    assert "José Škoda" in doc.text and "Ñandú" in doc.text


@pytest.mark.parametrize("bad", ["ocr_artifacts", ["nie_ma_takiego"], [1]])
def test_validate_postprocess_odrzucone(bad):
    from odw2json import ingest

    with pytest.raises(ValueError, match="postprocess"):
        ingest.validate_ingest_cfg({"ocr": {"postprocess": bad}})


def test_validate_postprocess_poprawne():
    from odw2json import ingest

    ingest.validate_ingest_cfg({"ocr": {"postprocess": ["ocr_artifacts", "collapse_spaces"]}})
    ingest.validate_ingest_cfg({"ocr": {"postprocess": []}})


# --- stabilność pod obciążeniem: ponowienia, brak cache pustych wyników, blokada silnika ----------


def _flaky_engine(monkeypatch, outcomes, seen_cfgs=None):
    """Silnik ``fake``: wywołania wg ``outcomes`` (wyjątek = rzuć, tekst = zwróć; ostatni się powtarza)."""
    calls: list[int] = []

    def fake_run(image, cfg):
        calls.append(1)
        if seen_cfgs is not None:
            seen_cfgs.append(cfg)
        out = outcomes[min(len(calls), len(outcomes)) - 1]
        if isinstance(out, BaseException):
            raise out
        return out

    monkeypatch.setitem(ocr.OCR_ENGINES, "fake", ocr.OcrEngine(available=lambda: True, run=fake_run))
    monkeypatch.setattr(ocr, "render_page", lambda path, i, dpi=200: object())
    monkeypatch.setattr(ocr.time, "sleep", lambda s: None)
    ocr._MEMO.clear()
    ocr._file_digest.cache_clear()
    return calls


def _pdf(tmp_path) -> Path:
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    return pdf


def test_blad_silnika_co_drugie_wywolanie_jest_ponawiany(tmp_path, monkeypatch):
    bad = RuntimeError("[ONNXRuntimeError] : 1 : FAIL : bad allocation")
    calls = _flaky_engine(monkeypatch, [bad, "tekst 1", bad, "tekst 2"])
    cfg = {"engine": "fake", "cache_dir": str(tmp_path / "c")}
    pdf = _pdf(tmp_path)
    assert ocr.ocr_page(pdf, 0, cfg) == "tekst 1"
    assert ocr.ocr_page(pdf, 1, cfg) == "tekst 2"
    assert len(calls) == 4
    assert len(list((tmp_path / "c").glob("*.txt"))) == 2


def test_ponowienie_po_przerwie(tmp_path, monkeypatch):
    calls = _flaky_engine(monkeypatch, [MemoryError("Unable to allocate"), "ok"])
    slept: list[float] = []
    monkeypatch.setattr(ocr.time, "sleep", slept.append)
    assert ocr.ocr_page(_pdf(tmp_path), 0, {"engine": "fake"}) == "ok"
    assert len(calls) == 2
    assert slept and all(s > 0 for s in slept)


def test_ponowienia_ta_sama_konfiguracja_az_do_sukcesu(tmp_path, monkeypatch):
    """Mniej wątków ORT nie obniża szczytu pamięci (pomiar E2b), więc ponowienia nie tworzą nowego silnika."""
    seen: list[dict] = []
    bad = RuntimeError("bad allocation")
    calls = _flaky_engine(monkeypatch, [bad] * (ocr.OCR_ATTEMPTS - 1) + ["ok"], seen)
    params = {"EngineConfig.onnxruntime.intra_op_num_threads": 4, "Global.use_cls": False}
    cfg = {"engine": "fake", "engine_params": params}
    assert ocr.ocr_page(_pdf(tmp_path), 0, cfg) == "ok"
    assert len(calls) == ocr.OCR_ATTEMPTS
    assert all(c["engine_params"] == params for c in seen)


def test_nieudany_po_ponowieniach_nie_trafia_do_cache(tmp_path, monkeypatch):
    calls = _flaky_engine(monkeypatch, [RuntimeError("bad allocation")])
    cfg = {"engine": "fake", "cache_dir": str(tmp_path / "c")}
    pdf = _pdf(tmp_path)
    with pytest.raises(ocr.OcrError, match="bad allocation"):
        ocr.ocr_page(pdf, 2, cfg)
    assert len(calls) == ocr.OCR_ATTEMPTS
    assert not list((tmp_path / "c").glob("*.txt"))
    assert not list((tmp_path / "c").glob("*.tmp"))
    assert not ocr._MEMO
    with pytest.raises(ocr.OcrError):  # kolejne wywołanie znów próbuje silnika, nie serwuje porażki
        ocr.ocr_page(pdf, 2, cfg)
    assert len(calls) == 2 * ocr.OCR_ATTEMPTS


def test_pusty_wynik_nie_trafia_do_cache_ani_pamieci(tmp_path, monkeypatch):
    calls = _flaky_engine(monkeypatch, ["  \n", "tekst"])
    cfg = {"engine": "fake", "cache_dir": str(tmp_path / "c")}
    pdf = _pdf(tmp_path)
    assert ocr.ocr_page(pdf, 0, cfg).strip() == ""
    assert not list((tmp_path / "c").glob("*.txt"))
    assert not ocr._MEMO
    assert ocr.ocr_page(pdf, 0, cfg) == "tekst"
    assert len(calls) == 2


def test_apply_ocr_ostrzezenie_nieudany_krotkie(monkeypatch, ocr_calls):
    def boom(path, i, cfg=None):
        raise ocr.OcrError("Traceback (most recent call last):\n  File x\nFail: bad allocation\n")

    monkeypatch.setattr(ocr, "ocr_page", boom)
    warnings: list[str] = []
    text_page = "dość długi tekst strony z warstwą tekstową, ponad próg"
    pages, engine = _apply_ocr(Path("x.pdf"), ["", text_page], OCR_ON, warnings)
    assert engine is None and pages[0] == ""
    (w,) = [w for w in warnings if "nieudany" in w]
    assert w.startswith("OCR nieudany – strona 1")
    assert "bad allocation" in w and "\n" not in w and "Traceback" not in w


@pytest.mark.parametrize(("preset", "expected"), [(None, "1"), ("4", "4")])
def test_import_pakietu_ogranicza_watki_openblas(preset, expected):
    """numpy z 16 wątkami OpenBLAS rezerwuje ok. 490 MB przy imporcie (zmierzone), a pod brakiem pamięci
    przerywa interpreter. Import odw2json ustawia 1 wątek (setdefault: wartość użytkownika wygrywa)."""
    import os
    import subprocess
    import sys

    env = {k: v for k, v in os.environ.items() if k != "OPENBLAS_NUM_THREADS"}
    if preset is not None:
        env["OPENBLAS_NUM_THREADS"] = preset
    code = "import os, odw2json; print(os.environ.get('OPENBLAS_NUM_THREADS'))"
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == expected


def test_slot_miedzyprocesowy_wylacznosc_i_zwolnienie(tmp_path):
    first = ocr._try_acquire_slot(tmp_path, 1)
    assert first is not None
    assert ocr._try_acquire_slot(tmp_path, 1) is None  # jedyny slot zajęty (inny uchwyt = inny proces)
    two = ocr._try_acquire_slot(tmp_path, 2)  # drugi slot wolny
    assert two is not None
    ocr._release_slot(first)
    again = ocr._try_acquire_slot(tmp_path, 1)
    assert again is not None
    ocr._release_slot(again)
    ocr._release_slot(two)


def test_slot_czeka_az_sie_zwolni(tmp_path, monkeypatch):
    import threading

    held = ocr._try_acquire_slot(tmp_path, 1)
    got: list[bool] = []

    def worker():
        with ocr._ocr_slot({"max_concurrent_processes": 1}, lock_dir=tmp_path, poll_s=0.01):
            got.append(True)

    t = threading.Thread(target=worker)
    t.start()
    t.join(0.2)
    assert got == []  # czeka na slot
    ocr._release_slot(held)
    t.join(5)
    assert got == [True]


def test_slot_po_limicie_czasu_przetwarza_mimo_wszystko(tmp_path):
    held = ocr._try_acquire_slot(tmp_path, 1)
    try:
        with ocr._ocr_slot(
            {"max_concurrent_processes": 1, "slot_timeout_s": 0.05}, lock_dir=tmp_path, poll_s=0.01
        ):
            pass  # nie wisi w nieskończoność
    finally:
        ocr._release_slot(held)


def test_slot_wylaczony_zerem(tmp_path):
    held = ocr._try_acquire_slot(tmp_path, 1)
    try:
        with ocr._ocr_slot({"max_concurrent_processes": 0}, lock_dir=tmp_path, poll_s=0.01):
            pass
    finally:
        ocr._release_slot(held)


@pytest.mark.parametrize(
    "ocr_cfg",
    [
        {"max_concurrent_processes": -1},
        {"max_concurrent_processes": "1"},
        {"max_concurrent_processes": True},
        {"slot_timeout_s": 0},
        {"slot_timeout_s": "x"},
    ],
)
def test_validate_limit_procesow_odrzucony(ocr_cfg):
    from odw2json import ingest

    with pytest.raises(ValueError, match="ocr\\."):
        ingest.validate_ingest_cfg({"ocr": ocr_cfg})


def test_konfiguracja_ma_limit_procesow_ocr():
    from odw2json.config_loader import load_app_config

    cfg = load_app_config()["ingest"]["ocr"]
    assert cfg["max_concurrent_processes"] == 1


def test_blokada_silnika_jedno_wywolanie_naraz(tmp_path, monkeypatch):
    import threading
    import time as _time

    active = [0]
    peak = [0]
    guard = threading.Lock()

    def fake_run(image, cfg):
        with guard:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        _time.sleep(0.02)
        with guard:
            active[0] -= 1
        return "tekst"

    monkeypatch.setitem(ocr.OCR_ENGINES, "fake", ocr.OcrEngine(available=lambda: True, run=fake_run))
    monkeypatch.setattr(ocr, "render_page", lambda path, i, dpi=200: object())
    ocr._MEMO.clear()
    pdf = _pdf(tmp_path)
    threads = [threading.Thread(target=ocr.ocr_page, args=(pdf, i, {"engine": "fake"})) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak[0] == 1
