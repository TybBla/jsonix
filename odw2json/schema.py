"""Kontrakt ksztaltu wyniku: JSON Schema z szablonu + lekka walidacja wlasna."""

from __future__ import annotations

from typing import Any

from odw2json.config_loader import DocTypeConfig

SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"
DEFAULT_LEAF_TYPES = ["string", "number", "integer", "null"]
_SCALARS = (str, int, float, bool)


def _json_type(v: Any) -> str | None:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        return "integer"
    if isinstance(v, float):
        return "number"
    if isinstance(v, str):
        return "string"
    return None


def _build(tmpl: Any, samples: list[Any]) -> dict:
    if isinstance(tmpl, dict):
        sub = [s for s in samples if isinstance(s, dict)]
        props = {k: _build(v, [s[k] for s in sub if k in s]) for k, v in tmpl.items()}
        return {
            "type": "object",
            "properties": props,
            "required": list(tmpl),
            "additionalProperties": False,
        }
    if isinstance(tmpl, list):
        out: dict = {"type": "array"}
        if tmpl:
            items = [i for s in samples if isinstance(s, list) for i in s]
            out["items"] = _build(tmpl[0], items)
        return out
    types = {t for t in map(_json_type, samples) if t}
    if not types - {"null"}:
        return {"type": list(DEFAULT_LEAF_TYPES)}
    if "integer" in types and "number" in types:
        types.discard("integer")
    types.add("null")
    return {"type": sorted(types)}


def build_json_schema(template: dict, samples: list[dict] | None = None) -> dict:
    """JSON Schema (2020-12) z szablonu; typy lisci opcjonalnie wnioskowane z `samples`."""
    schema = _build(template, list(samples or []))
    return {"$schema": SCHEMA_DRAFT, **schema}


def _walk(tmpl: Any, data: Any, path: str, errors: list[str]) -> None:
    where = path or "$"
    if isinstance(tmpl, dict):
        if not isinstance(data, dict):
            errors.append(f"{where}: expected object, got {type(data).__name__}")
            return
        for k in tmpl:
            if k not in data:
                errors.append(f"{where}: missing key '{k}'")
        for k in data:
            if k not in tmpl:
                errors.append(f"{where}: unexpected key '{k}'")
        for k, v in tmpl.items():
            if k in data:
                _walk(v, data[k], f"{path}.{k}" if path else k, errors)
    elif isinstance(tmpl, list):
        if not isinstance(data, list):
            errors.append(f"{where}: expected array, got {type(data).__name__}")
            return
        if tmpl:
            for i, item in enumerate(data):
                _walk(tmpl[0], item, f"{path}[{i}]", errors)
    elif data is not None and not isinstance(data, _SCALARS):
        errors.append(f"{where}: expected scalar or null, got {type(data).__name__}")


def validate_output(data: dict, cfg: DocTypeConfig) -> list[str]:
    """Bledy ksztaltu wyniku wzgledem szablonu typu (pusta lista = OK)."""
    errors: list[str] = []
    _walk(cfg.template(), data, "", errors)
    return errors


def is_unknown_output(data: Any) -> bool:
    """Dokument nieznany = dokladnie pusty obiekt."""
    return isinstance(data, dict) and not data
