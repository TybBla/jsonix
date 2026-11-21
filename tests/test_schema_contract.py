"""Kontrakt ksztaltu wyniku: szablony i GT organizatora."""

import copy
import json
from pathlib import Path

import pytest

from odw2json import pipeline
from odw2json.config_loader import ROOT_DIR, load_registry
from odw2json.schema import build_json_schema, is_unknown_output, validate_output

TRAIN = ROOT_DIR / "data" / "train"
STEM_TO_TYPE = {"odwolanie": "odwolanie", "pelnomocnictwo": "pelnomocnictwo", "przelew": "przelew"}
GT_FILES = sorted(p for p in TRAIN.glob("przyklad_*/*.json") if p.stem in STEM_TO_TYPE)
REG = load_registry()


def test_registry_has_types():
    assert set(STEM_TO_TYPE.values()) <= set(REG)


@pytest.mark.parametrize("type_id", sorted(REG))
def test_template_valid_against_itself(type_id):
    cfg = REG[type_id]
    assert validate_output(cfg.template(), cfg) == []


@pytest.mark.parametrize("type_id", sorted(REG))
def test_build_json_schema_shape(type_id):
    schema = build_json_schema(REG[type_id].template())
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert sorted(schema["required"]) == sorted(schema["properties"])


def test_gt_files_found():
    assert len(GT_FILES) > 20


@pytest.mark.parametrize("gt", GT_FILES, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_gt_validates(gt: Path):
    data = json.loads(gt.read_text(encoding="utf-8"))
    cfg = REG[STEM_TO_TYPE[gt.stem]]
    assert validate_output(data, cfg) == []


def test_pipeline_output_validates():
    pdf = TRAIN / "przyklad_01" / "odwolanie.pdf"
    _cls, res = pipeline.process_file(pdf, REG)
    assert res is not None
    assert validate_output(res.data, REG[res.doc_type]) == []


def _odw():
    return REG["odwolanie"], REG["odwolanie"].template()


def test_extra_key_is_error():
    cfg, d = _odw()
    d["Odwolujacy"][0]["obcy"] = None
    errs = validate_output(d, cfg)
    assert any("Odwolujacy[0]" in e and "obcy" in e for e in errs)


def test_missing_key_is_error():
    cfg, d = _odw()
    del d["Odwolujacy"][0]["pelnomocnik"]["mail"]
    errs = validate_output(d, cfg)
    assert any("Odwolujacy[0].pelnomocnik" in e and "missing key 'mail'" in e for e in errs)


def test_list_instead_of_dict_is_error():
    cfg, d = _odw()
    d["ZamowieniePubliczne"] = []
    assert any("ZamowieniePubliczne" in e for e in validate_output(d, cfg))


def test_dict_instead_of_list_is_error():
    cfg, d = _odw()
    d["Zamawiajacy"] = {}
    assert any("Zamawiajacy" in e for e in validate_output(d, cfg))


def test_dict_instead_of_scalar_is_error():
    cfg, d = _odw()
    d["OdwolanieKIO"]["data"] = {"x": 1}
    assert any("OdwolanieKIO.data" in e for e in validate_output(d, cfg))


def test_list_instead_of_scalar_is_error():
    cfg, d = _odw()
    d["OdwolanieKIO"]["data"] = ["x"]
    assert any("OdwolanieKIO.data" in e for e in validate_output(d, cfg))


def test_scalar_instead_of_container_is_error():
    cfg, d = _odw()
    d["Odwolujacy"][0]["pelnomocnik"] = "x"
    assert any("Odwolujacy[0].pelnomocnik" in e for e in validate_output(d, cfg))


def test_empty_list_and_many_items_ok():
    cfg, d = _odw()
    d["Zamawiajacy"] = []
    assert validate_output(d, cfg) == []
    d["Odwolujacy"] = [copy.deepcopy(d["Odwolujacy"][0]) for _ in range(3)]
    assert validate_output(d, cfg) == []


def test_scalar_values_ok():
    cfg, d = _odw()
    d["OdwolanieKIO"]["data"] = "2024-01-01"
    d["Odwolujacy"][0]["nip"] = 123
    d["Odwolujacy"][0]["przez-pelnomocnika"] = True
    d["Odwolujacy"][0]["krs"] = 1.5
    assert validate_output(d, cfg) == []


def test_non_dict_root():
    cfg, _ = _odw()
    assert validate_output([], cfg)


def test_is_unknown_output():
    assert is_unknown_output({}) is True
    assert is_unknown_output(REG["odwolanie"].template()) is False
    assert is_unknown_output([]) is False


def test_empty_object_invalid_for_known_type():
    cfg, _ = _odw()
    assert validate_output({}, cfg) != []


def test_samples_infer_leaf_types():
    schema = build_json_schema({"a": None, "b": None}, samples=[{"a": "x", "b": 1}, {"a": None, "b": 2}])
    assert set(schema["properties"]["a"]["type"]) == {"string", "null"}
    assert set(schema["properties"]["b"]["type"]) == {"integer", "null"}


def _check(schema: dict, data, path: str = "$") -> list[str]:
    """Minimalny walidator JSON Schema: type / required / additionalProperties / items."""
    errs: list[str] = []
    t = schema.get("type")
    types = t if isinstance(t, list) else [t]
    py = {
        "object": lambda v: isinstance(v, dict),
        "array": lambda v: isinstance(v, list),
        "string": lambda v: isinstance(v, str),
        "boolean": lambda v: isinstance(v, bool),
        "null": lambda v: v is None,
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    }
    if not any(py[x](data) for x in types):
        return [f"{path}: {type(data).__name__} not in {types}"]
    if isinstance(data, dict) and "object" in types:
        for k in schema.get("required", []):
            if k not in data:
                errs.append(f"{path}: missing {k}")
        props = schema.get("properties", {})
        for k, v in data.items():
            if k in props:
                errs += _check(props[k], v, f"{path}.{k}")
            elif schema.get("additionalProperties") is False:
                errs.append(f"{path}: unexpected {k}")
    if isinstance(data, list) and "items" in schema:
        for i, item in enumerate(data):
            errs += _check(schema["items"], item, f"{path}[{i}]")
    return errs


@pytest.mark.parametrize("type_id", sorted(STEM_TO_TYPE.values()))
def test_gt_conforms_to_built_json_schema(type_id):
    gts = [json.loads(p.read_text(encoding="utf-8")) for p in GT_FILES if STEM_TO_TYPE[p.stem] == type_id]
    assert gts
    schema = build_json_schema(REG[type_id].template(), samples=gts)
    for gt in gts:
        assert _check(schema, gt) == []
    bad = dict(gts[0], dodatkowy_klucz=1)
    assert _check(schema, bad) != []
