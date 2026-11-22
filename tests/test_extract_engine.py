"""Silnik ekstrakcji sterowany YAML (DSL ``fields``/``lists``): ekstraktory, scope, normalize, validate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from odw2json.config_loader import DocTypeConfig, load_registry
from odw2json.contracts import Document
from odw2json.extract import engine
from odw2json.extract.engine import (
    EXTRACTORS,
    NORMALIZERS,
    VALIDATORS,
    extract,
    fold,
    register_extractor,
    register_normalizer,
)


def _doc(*pages: str) -> Document:
    text, offsets, pos = "", [], 0
    for i, p in enumerate(pages):
        if i:
            text += "\n"
            pos += 1
        offsets.append(pos)
        text += p
        pos += len(p)
    return Document(path=Path("x.pdf"), text=text, pages=list(pages), page_offsets=offsets)


@pytest.fixture
def make_cfg(tmp_path):
    def _make(template: dict, fields: dict, lists: dict | None = None) -> DocTypeConfig:
        (tmp_path / "schemas").mkdir(exist_ok=True)
        (tmp_path / "lookups").mkdir(exist_ok=True)
        (tmp_path / "schemas" / "t.json").write_text(json.dumps(template), encoding="utf-8")
        (tmp_path / "lookups" / "kolory.yaml").write_text("1: czerwony\n2: zielony\n", encoding="utf-8")
        return DocTypeConfig(
            id="t",
            output_template="schemas/t.json",
            fields=fields,
            lists=lists or {},
            config_dir=tmp_path,
        )

    return _make


T = {"a": {"x": None, "y": None}}


# ---------------------------------------------------------------- pomocnicze


def test_fold_keeps_length_and_strips_polish_chars():
    s = "Tytuł PRZELEWU: Łódź ąę"
    f = fold(s)
    assert len(f) == len(s)
    assert f == "tytul przelewu: lodz ae"


def test_registries_have_core_entries():
    assert {"label", "regex", "section_line", "near", "const"} <= set(EXTRACTORS)
    assert {"date", "amount", "iban", "ws"} <= set(NORMALIZERS)
    assert {"regex", "min_len", "max_len"} <= set(VALIDATORS)


# ---------------------------------------------------------------- ekstraktory


def test_label_value_on_same_line_and_next_line(make_cfg):
    cfg = make_cfg(
        T,
        {
            "a.x": {"extract": [{"label": ["kwota operacji"]}]},
            "a.y": {"extract": [{"label": ["Tytuł"]}]},
        },
    )
    res = extract(_doc("Kwota operacji: 12,50 PLN\nTYTUŁ\n  opłata  skarbowa \nStatus OK"), cfg)
    assert res.data == {"a": {"x": "12,50 PLN", "y": "opłata skarbowa"}}


def test_label_with_dot_leaders(make_cfg):
    cfg = make_cfg(T, {"a.x": {"extract": [{"label": "nr ref."}]}})
    res = extract(_doc("NR REF. ................ CEN123456789"), cfg)
    assert res.data["a"]["x"] == "CEN123456789"


def test_label_respects_word_boundary(make_cfg):
    cfg = make_cfg(T, {"a.x": {"extract": [{"label": ["tytul"]}]}})
    res = extract(_doc("Bank nie odpowiada za treść tytułu przelewu"), cfg)
    assert res.data["a"]["x"] is None


def test_label_uses_type_pattern_within_window(make_cfg):
    cfg = make_cfg(T, {"a.x": {"type": "amount", "extract": [{"label": ["kwota"]}]}})
    res = extract(_doc("Kwota operacji\nPLN 1 200.00\nData 2026-01-01"), cfg)
    assert res.data["a"]["x"] == 1200.0


def test_amount_pattern_skips_dates(make_cfg):
    cfg = make_cfg(T, {"a.x": {"type": "amount", "extract": [{"label": ["kwota"]}]}})
    res = extract(_doc("Kwota 11.09.2026 CEN1\n7 500,00 PLN"), cfg)
    assert res.data["a"]["x"] == 7500.0


@pytest.mark.parametrize(
    ("tekst", "oczekiwana"),
    [
        ("Kwota 10.000,00 zł", 10000.0),
        ("Kwota 10 000 PLN", 10000.0),
        ("Kwota 17 zł", 17.0),
        ("Kwota PLN 17,00", 17.0),
        ("Kwota 1.234.567,89 PLN", 1234567.89),
        ("Kwota 10 000,00 PLN", 10000.0),
        ("Kwota 7 500,00 PLN", 7500.0),
    ],
)
def test_amount_pattern_formy(make_cfg, tekst, oczekiwana):
    cfg = make_cfg(T, {"a.x": {"type": "amount", "extract": [{"label": ["kwota"]}]}})
    assert extract(_doc(tekst), cfg).data["a"]["x"] == oczekiwana


@pytest.mark.parametrize(
    "tekst",
    ["Kwota 11.09.2026", "Kwota 2026-09-11", "Kwota 61 1090 1014 0000 0712 1981 2874", "Kwota ZP.1.2026"],
)
def test_amount_pattern_nie_lapie_dat_i_numerow(make_cfg, tekst):
    cfg = make_cfg(T, {"a.x": {"type": "amount", "extract": [{"label": ["kwota"]}]}})
    assert extract(_doc(tekst), cfg).data["a"]["x"] is None


def test_label_multiline_until_stop(make_cfg):
    fields = {
        "a.x": {
            "extract": [
                {"label": {"labels": ["tytułem"], "multiline": True, "stop": ["status", "re:^nr\\b"]}}
            ]
        }
    }
    cfg = make_cfg(T, fields)
    text = "Tytułem opłata za\nKIO w przetargu ZP.1.2026\nCEN1\nStatus wykonany"
    assert extract(_doc(text), cfg).data["a"]["x"] == "opłata za KIO w przetargu ZP.1.2026 CEN1"
    text2 = "Tytułem\nopłata\nNr ref. X\n"
    assert extract(_doc(text2), cfg).data["a"]["x"] == "opłata"
    text3 = "Tytułem abc\ndef\n\nghi"
    assert extract(_doc(text3), cfg).data["a"]["x"] == "abc def"


def test_label_line_start_option(make_cfg):
    cfg = make_cfg(T, {"a.x": {"extract": [{"label": {"labels": ["opis"], "line_start": True}}]}})
    assert extract(_doc("Pełny opis zdarzenia\nOpis: właściwy"), cfg).data["a"]["x"] == "właściwy"


def test_regex_named_group_and_nth(make_cfg):
    fields = {
        "a.x": {"extract": [{"regex": r"nr (?P<v>\d+)"}]},
        "a.y": {"extract": [{"regex": {"pattern": r"nr (?P<v>\d+)", "nth": 2}}]},
    }
    res = extract(_doc("NR 11 i nr 22 i nr 33"), make_cfg(T, fields))
    assert res.data["a"] == {"x": "11", "y": "22"}


def test_regex_case_sensitive_option(make_cfg):
    fields = {"a.x": {"extract": [{"regex": {"pattern": r"\b[A-Z]{3}\d+", "case": True}}]}}
    res = extract(_doc("abc123 CEN99"), make_cfg(T, fields))
    assert res.data["a"]["x"] == "CEN99"


def test_section_line(make_cfg):
    fields = {
        "a.x": {"extract": [{"section_line": "Beneficjent"}]},
        "a.y": {"extract": [{"section_line": {"header": "Beneficjent", "n": 2}}]},
    }
    res = extract(_doc("Beneficjent\n\nFirma X sp. z o.o.\nul. Polna 1\n"), make_cfg(T, fields))
    assert res.data["a"] == {"x": "Firma X sp. z o.o.", "y": "ul. Polna 1"}


def test_near_picks_closest_value_of_type(make_cfg):
    fields = {"a.x": {"type": "iban", "extract": [{"near": {"phrases": ["odbiorca"], "direction": "after"}}]}}
    text = (
        "Nadawca\nA\n11 1111 1111 1111 1111 1111 1111\n"
        "Odbiorca\nB\nul. X\n22 2222 2222 2222 2222 2222 2222\n33 3333 3333 3333 3333 3333 3333"
    )
    res = extract(_doc(text), make_cfg(T, fields))
    assert res.data["a"]["x"] == "22222222222222222222222222"


def test_const(make_cfg):
    cfg = make_cfg(T, {"a.x": {"type": "int", "extract": [{"const": 7}]}})
    res = extract(_doc("cokolwiek"), cfg)
    assert res.data["a"]["x"] == 7
    assert res.trace[0].method == "const"


def test_derived_lookup(make_cfg):
    fields = {
        "a.x": {"type": "int", "extract": [{"regex": r"kolor (?P<v>\d)"}]},
        "a.y": {"derived": {"lookup": "kolory", "from": "a.x"}},
    }
    res = extract(_doc("kolor 2"), make_cfg(T, fields))
    assert res.data["a"] == {"x": 2, "y": "zielony"}
    assert any(t.path == "a.y" and t.method == "derived" for t in res.trace)


def test_shipped_odwolanie_derived_still_works():
    cfg = load_registry()["odwolanie"]
    data = cfg.template()
    data["OdwolanieKIO"]["czynnosc_powod_id"] = 9
    from odw2json.extract import apply_derived

    trace = apply_derived(data, cfg)
    assert data["OdwolanieKIO"]["czynnosc_opis"] == "Decyzja o unieważnieniu postępowania"
    assert trace and trace[0].method == "derived"


# ---------------------------------------------------------------- kolejność, scope, validate


def test_extractor_order_first_with_result_wins(make_cfg):
    fields = {
        "a.x": {"extract": [{"label": ["brak etykiety"]}, {"regex": r"(?P<v>B\d)"}, {"regex": r"(?P<v>A\d)"}]}
    }
    res = extract(_doc("A1 B2"), make_cfg(T, fields))
    assert res.data["a"]["x"] == "B2"
    assert res.trace[0].method == "regex"


def test_scope_limits_search_region(make_cfg):
    fields = {
        "a.x": {
            "type": "amount",
            "scope": {"after": "re:odbiorca", "before": "status"},
            "extract": [{"regex": r"(?P<v>\d+,\d{2})"}],
        },
        "a.y": {
            "type": "amount",
            "scope": {"after": "nie ma takiej frazy"},
            "extract": [{"regex": r"(?P<v>\d+,\d{2})"}],
        },
    }
    res = extract(_doc("Nadawca 1,00\nOdbiorca 2,00\nStatus 3,00"), make_cfg(T, fields))
    assert res.data["a"] == {"x": 2.0, "y": None}


def test_scope_max_chars(make_cfg):
    fields = {"a.x": {"scope": {"after": "start", "max_chars": 5}, "extract": [{"regex": r"(?P<v>X\d)"}]}}
    assert extract(_doc("start ...... X1"), make_cfg(T, fields)).data["a"]["x"] is None


def test_validate_failure_gives_null_or_next_candidate(make_cfg):
    fields = {
        "a.x": {"extract": [{"regex": r"(?P<v>\d+)"}], "validate": {"regex": r"^\d{3}$"}},
        "a.y": {"extract": [{"regex": r"(?P<v>\d+)"}], "validate": {"min_len": 9}},
    }
    res = extract(_doc("12 345 6789"), make_cfg(T, fields))
    assert res.data["a"] == {"x": "345", "y": None}


def test_normalize_chain_and_failed_normalizer(make_cfg):
    fields = {
        "a.x": {"extract": [{"label": "rachunek"}], "normalize": ["iban"]},
        "a.y": {"extract": [{"label": "data"}], "normalize": ["date"]},
    }
    res = extract(_doc("Rachunek: 12 34\nData 31.02.2026"), make_cfg(T, fields))
    assert res.data["a"] == {"x": None, "y": None}


def test_custom_registered_extractor_and_normalizer(make_cfg):
    @register_extractor("pierwsze_slowo", primary="enabled")
    def _first_word(ctx, opts):
        m = ctx.search(r"\w+")
        if m:
            yield engine.Hit(m.group(0), m.start(), m.end())

    @register_normalizer("odwroc")
    def _rev(v):
        return v[::-1]

    try:
        cfg = make_cfg(T, {"a.x": {"extract": [{"pierwsze_slowo": True}], "normalize": ["odwroc"]}})
        assert extract(_doc("abc def"), cfg).data["a"]["x"] == "cba"
    finally:
        EXTRACTORS.pop("pierwsze_slowo")
        NORMALIZERS.pop("odwroc")


# ---------------------------------------------------------------- wynik i trace


def test_result_exactly_template_with_nulls(make_cfg):
    tmpl = {"a": {"x": None, "y": None}, "b": {"z": None}}
    cfg = make_cfg(tmpl, {"a.x": {"extract": [{"label": "x"}]}})
    res = extract(_doc("nic"), cfg)
    assert res.data == tmpl
    assert list(res.data) == ["a", "b"]


def test_trace_has_page_and_snippet(make_cfg):
    cfg = make_cfg(T, {"a.x": {"type": "amount", "extract": [{"label": "kwota"}]}})
    res = extract(_doc("Strona pierwsza", "Nagłówek\nKwota przelewu 5,00 PLN\nkoniec"), cfg)
    tr = res.trace[0]
    assert (tr.path, tr.value, tr.method, tr.page) == ("a.x", 5.0, "label", 1)
    assert tr.source_snippet == "Kwota przelewu 5,00 PLN"


# ---------------------------------------------------------------- listy


LT = {"L": [{"nip": None, "nazwa": None}], "k": {"n": None}}


def test_lists_split_items(make_cfg):
    fields = {
        "L[].nip": {"type": "digits", "extract": [{"label": "nip"}]},
        "L[].nazwa": {"extract": [{"section_line": {"header": "re:^\\d+\\)", "n": 0}}]},
        "k.n": {"extract": [{"label": "koniec"}]},
    }
    lists = {
        "L": {
            "split": {"start": "re:^odwolujacy", "end": "re:^zamawiajacy", "item_sep": "re:^\\d+\\)"},
            "max_items": 5,
        }
    }
    text = (
        "Odwołujący:\n1) Alfa sp. z o.o.\nNIP: 111-111-11-11\n2) Beta S.A.\nNIP 2222222222\n"
        "Zamawiający:\n3) Gamma\nNIP 3333333333\nKoniec: tak"
    )
    res = extract(_doc(text), make_cfg(LT, fields, lists))
    assert res.data["L"] == [
        {"nip": "1111111111", "nazwa": "1) Alfa sp. z o.o."},
        {"nip": "2222222222", "nazwa": "2) Beta S.A."},
    ]
    assert res.data["k"]["n"] == "tak"
    assert {t.path for t in res.trace} >= {"L[0].nip", "L[1].nip", "k.n"}


def test_lists_without_matches_keep_single_null_item(make_cfg):
    fields = {"L[].nip": {"type": "digits", "extract": [{"label": "nip"}]}}
    lists = {"L": {"split": {"start": "re:^odwolujacy"}}}
    res = extract(_doc("NIP 123"), make_cfg(LT, fields, lists))
    assert res.data["L"] == [{"nip": None, "nazwa": None}]


def test_lists_undeclared_is_single_item_over_parent(make_cfg):
    fields = {"L[].nip": {"type": "digits", "extract": [{"label": "nip"}]}}
    res = extract(_doc("NIP 1234567890"), make_cfg(LT, fields))
    assert res.data["L"] == [{"nip": "1234567890", "nazwa": None}]


def test_lists_max_items(make_cfg):
    fields = {"L[].nip": {"type": "digits", "extract": [{"label": "nip"}]}}
    lists = {"L": {"split": {"item_sep": "re:^- "}, "max_items": 2}}
    res = extract(_doc("- NIP 1\n- NIP 2\n- NIP 3"), make_cfg(LT, fields, lists))
    assert [i["nip"] for i in res.data["L"]] == ["1", "2"]


def test_nested_lists_trace_has_concrete_indexes(make_cfg):
    tmpl = {"M": [{"nazwa": None, "P": [{"imie": None}]}]}
    fields = {
        "M[].nazwa": {"extract": [{"label": "firma"}]},
        "M[].P[].imie": {"extract": [{"label": "osoba"}]},
    }
    lists = {"M": {"split": {"item_sep": "re:^firma"}}, "M[].P": {"split": {"item_sep": "re:^osoba"}}}
    text = "Firma A\nOsoba Jan\nOsoba Ewa\nFirma B\nOsoba Adam"
    res = extract(_doc(text), make_cfg(tmpl, fields, lists))
    assert res.data == {
        "M": [
            {"nazwa": "A", "P": [{"imie": "Jan"}, {"imie": "Ewa"}]},
            {"nazwa": "B", "P": [{"imie": "Adam"}]},
        ]
    }
    paths = {t.path for t in res.trace}
    assert paths == {"M[0].nazwa", "M[0].P[0].imie", "M[0].P[1].imie", "M[1].nazwa", "M[1].P[0].imie"}
    assert not any("[]" in p for p in paths)


# ---------------------------------------------------------------- walidacja DSL


@pytest.mark.parametrize(
    ("fields", "fragment"),
    [
        ({"a.x": {"extract": [{"nieznany": 1}]}}, "nieznany"),
        ({"a.x": {"extract": [{"label": "x", "regex": "y"}]}}, "dokładnie jeden"),
        ({"a.x": {"extract": [{"label": {"labels": ["x"], "zla_opcja": 1}}]}}, "zla_opcja"),
        ({"a.x": {"extract": [{"label": "x"}], "normalize": ["brak_takiego"]}}, "brak_takiego"),
        ({"a.x": {"extract": [{"label": "x"}], "validate": {"brak_walidatora": 1}}}, "brak_walidatora"),
        ({"a.x": {"extract": [{"regex": "(nawias"}]}}, "regex"),
        ({"a.x": {"extract": [{"label": "x"}], "typ": "str"}}, "typ"),
        ({"a.x": {"type": "kolor", "extract": [{"label": "x"}]}}, "type"),
        ({"a.x": {}}, "extract"),
        ({"a.x": {"extract": [{"label": "x"}], "scope": {"after": "re:(zly"}}}, "regex"),
    ],
)
def test_dsl_validation_errors(make_cfg, fields, fragment):
    with pytest.raises(ValidationError) as ei:
        make_cfg(T, fields)
    assert fragment in str(ei.value)


def test_lists_spec_validation(make_cfg):
    with pytest.raises(ValidationError):
        make_cfg(LT, {}, {"L": {"split": {"start": "x", "koniec": "y"}}})


def test_unknown_field_path_rejected_by_registry(tmp_path):
    (tmp_path / "doctypes").mkdir()
    (tmp_path / "schemas").mkdir()
    (tmp_path / "schemas" / "t.json").write_text(json.dumps(T), encoding="utf-8")
    (tmp_path / "doctypes" / "t.yaml").write_text(
        "id: t\noutput_template: schemas/t.json\nfields:\n  a.zz:\n    extract: [{label: x}]\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"a\.zz"):
        load_registry(tmp_path)


def test_shipped_registry_loads():
    reg = load_registry()
    assert "przelew_bankowy.kwota" in reg["przelew"].fields


def test_label_multiline_przepuszcza_jedna_pusta_linie(make_cfg):
    fields = {
        "a.x": {
            "extract": [
                {
                    "label": {
                        "labels": ["tytul platnosci"],
                        "multiline": True,
                        "blank_lines": 1,
                        "stop": ["status"],
                    }
                }
            ]
        }
    }
    cfg = make_cfg(T, fields)
    text = "Tytuł płatności: opłata za\n\nodwołanie KIO\n\n\nStatus wykonany"
    assert extract(_doc(text), cfg).data["a"]["x"] == "opłata za odwołanie KIO"
    # pusta linia przed etykietą (stop) nadal kończy wartość
    text2 = "Tytuł płatności: opłata\n\nStatus wykonany"
    assert extract(_doc(text2), cfg).data["a"]["x"] == "opłata"


def test_trim_quotes_niesparowany_cudzyslow():
    f = NORMALIZERS["trim_quotes"]
    assert f('"opłata za KIO') == "opłata za KIO"
    assert f('opłata za KIO"') == "opłata za KIO"
    assert f("„opłata za KIO") == "opłata za KIO"
    assert f("„opłata za KIO”.") == "opłata za KIO"
    assert f('opłata "specjalna" KIO') == 'opłata "specjalna" KIO'
