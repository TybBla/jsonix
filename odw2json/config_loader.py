"""Ładowanie konfiguracji: typy dokumentów (config/doctypes/*.yaml), lookupy, app.yaml."""

from __future__ import annotations

import copy
import json
import re
from functools import cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT_DIR / "config"
REGEX_PREFIX = "re:"  # prefiks wpisu required_any traktowanego jako regex
TITLE_TOKEN = "@title"  # wpis grupy required_any: trafienie cechy ``title`` tego typu


class ClassifyWeights(BaseModel):
    """Wagi cech klasyfikatora (punkty za trafienie; ``negative`` zwykle ujemna)."""

    model_config = ConfigDict(extra="forbid")

    strong: float = 2.0
    weak: float = 1.0
    negative: float = -3.0
    title: float = 4.0


class PatternSpec(BaseModel):
    """Cecha strukturalna: regex na tekście znormalizowanym (małe litery, bez polskich znaków)."""

    model_config = ConfigDict(extra="forbid")

    regex: str
    weight: float = 1.0

    @field_validator("regex")
    @classmethod
    def _valid_regex(cls, v: str) -> str:
        try:
            re.compile(v)
        except re.error as e:
            raise ValueError(f"niepoprawny regex {v!r}: {e}") from e
        return v


def _check_required_item(item: str) -> None:
    if item.startswith(REGEX_PREFIX):
        try:
            re.compile(item[len(REGEX_PREFIX) :])
        except re.error as e:
            raise ValueError(f"niepoprawny regex w required_any {item!r}: {e}") from e


class RequiredGroup(BaseModel):
    """Grupa wymagań ``required_any``: spełniona, gdy trafią **wszystkie** wpisy ``all_of``.

    Wpis to fraza, ``re:<regex>`` albo ``@title`` (trafiła cecha ``title`` tego typu).
    """

    model_config = ConfigDict(extra="forbid")

    all_of: list[str] = Field(min_length=1)

    @field_validator("all_of")
    @classmethod
    def _valid_items(cls, items: list[str]) -> list[str]:
        for item in items:
            _check_required_item(item)
        return items


class ClassifyConfig(BaseModel):
    """Cechy rozpoznawania typu dokumentu (wszystko poza ``strong/weak/negative/min_score`` opcjonalne).

    ``title`` - frazy szukane w nagłówku (pierwsze ``header_chars`` znaków, z zwijaniem rozstrzelonych liter);
    ``title_mode`` - ``anywhere`` (domyślnie: fraza gdziekolwiek w nagłówku) albo ``line`` (fraza musi
    być tytułem, czyli prawie całą krótką linią: linia <= ``title_line_max_chars`` znaków, a fraza
    zajmuje >= ``title_line_min_cover`` jej długości);
    ``patterns`` - regexy z wagami; ``required_any`` - lista wpisów: fraza, ``re:<regex>`` albo grupa
    ``{all_of: [...]}`` (wszystkie wpisy grupy naraz; wpis ``@title`` = trafił tytuł); bez trafienia
    któregokolwiek wpisu typ odpada; ``min_score`` - minimalny wynik; ``min_margin`` - minimalna
    przewaga nad drugim typem; ``ignore_foreign`` - frazy z ``foreign_titles`` (config/classify.yaml),
    za które ten typ nie jest karany (fraza pokrywająca się z własnym ``title`` jest zwalniana
    automatycznie).
    """

    model_config = ConfigDict(extra="forbid")

    strong: list[str] = Field(default_factory=list)
    weak: list[str] = Field(default_factory=list)
    negative: list[str] = Field(default_factory=list)
    title: list[str] = Field(default_factory=list)
    title_mode: Literal["line", "anywhere"] = "anywhere"
    title_line_max_chars: int = Field(60, gt=0)
    title_line_min_cover: float = Field(0.6, gt=0, le=1)
    patterns: list[PatternSpec] = Field(default_factory=list)
    required_any: list[str | RequiredGroup] = Field(default_factory=list)
    min_score: float = 3.0
    min_margin: float = Field(0.0, ge=0)
    header_chars: int = Field(600, gt=0)
    weights: ClassifyWeights = Field(default_factory=ClassifyWeights)
    ignore_foreign: list[str] = Field(default_factory=list)

    @field_validator("required_any")
    @classmethod
    def _valid_required(cls, items: list[str | RequiredGroup]) -> list[str | RequiredGroup]:
        for item in items:
            if isinstance(item, str):
                _check_required_item(item)
        return items


class ForeignTitles(BaseModel):
    """Nagłówki dokumentów obcych (wyrok, faktura...): kara liczona dla każdego typu osobno.

    Fraza liczy się, gdy któraś z linii w pierwszych ``header_chars`` znakach **zaczyna się** od niej
    (granica słowa). Kara ``weight`` (ujemna) jest naliczana raz na typ, niezależnie od liczby trafień.
    Typ nie jest karany za frazę pokrywającą się z jego ``title`` (jedna zaczyna drugą) ani za frazy
    z jego ``ignore_foreign``.
    """

    model_config = ConfigDict(extra="forbid")

    weight: float = Field(-10.0, le=0)
    header_chars: int = Field(600, gt=0)
    phrases: list[str] = Field(default_factory=list)


class ClassifySettings(BaseModel):
    """Ustawienia globalne klasyfikatora (config/classify.yaml)."""

    model_config = ConfigDict(extra="forbid")

    foreign_titles: ForeignTitles = Field(default_factory=ForeignTitles)


FieldType = Literal[
    "str", "int", "amount", "date", "iban", "digits", "email", "name", "company", "enum", "lookup"
]


def _engine():
    """Rejestry silnika (import leniwy: engine importuje ten moduł)."""
    from odw2json.extract import engine

    return engine


def _check_phrases(v: str | list[str] | None) -> str | list[str] | None:
    items = [v] if isinstance(v, str) else (v or [])
    for p in items:
        _engine().check_phrase(p)
    return v


class ScopeSpec(BaseModel):
    """Zakres wyszukiwania pola: od końca frazy ``after`` do początku ``before`` / ``max_chars`` znaków.

    Frazy jak w ``classify`` (``re:<regex>`` na tekście złożonym). Brak frazy ``after`` = pole ``null``.
    """

    model_config = ConfigDict(extra="forbid")

    after: str | list[str] | None = None
    before: str | list[str] | None = None
    max_chars: int | None = Field(None, gt=0)

    @field_validator("after", "before")
    @classmethod
    def _valid_phrases(cls, v: str | list[str] | None) -> str | list[str] | None:
        return _check_phrases(v)


class DerivedSpec(BaseModel):
    """Pole wyliczane z innego pola: ``{lookup: <słownik z config/lookups>, from: <ścieżka>}``."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    lookup: str | None = None
    from_: str = Field(alias="from")


class FieldSpec(BaseModel):
    """Reguła jednego pola (klucz = ścieżka w szablonie, listy: ``Odwolujacy[].nip``)."""

    model_config = ConfigDict(extra="forbid")

    type: FieldType = "str"
    scope: ScopeSpec | None = None
    extract: list[dict[str, Any]] = Field(default_factory=list)
    normalize: list[str] | None = None
    validate_: dict[str, Any] = Field(default_factory=dict, alias="validate")
    derived: DerivedSpec | None = None

    @model_validator(mode="after")
    def _check(self) -> FieldSpec:
        eng = _engine()
        if not self.extract and self.derived is None:
            raise ValueError("pole musi mieć 'extract' (lista ekstraktorów) albo 'derived'")
        for i, entry in enumerate(self.extract):
            try:
                eng.parse_extractor_entry(entry)
            except ValueError as e:
                raise ValueError(f"extract[{i}]: {e}") from e
        for name in self.normalize or []:
            if name not in eng.NORMALIZERS:
                raise ValueError(
                    f"nieznany normalizator {name!r} (dostępne: {', '.join(sorted(eng.NORMALIZERS))})"
                )
        for name in self.validate_:
            if name not in eng.VALIDATORS:
                raise ValueError(
                    f"nieznany walidator {name!r} (dostępne: {', '.join(sorted(eng.VALIDATORS))})"
                )
        if "regex" in self.validate_:
            try:
                re.compile(self.validate_["regex"])
            except re.error as e:
                raise ValueError(f"validate.regex: niepoprawny regex: {e}") from e
        return self


class SplitSpec(BaseModel):
    """Podział tekstu na elementy listy: blok od ``start`` do ``end``, elementy od ``item_sep``."""

    model_config = ConfigDict(extra="forbid")

    start: str | None = None
    end: str | None = None
    item_sep: str | None = None

    @field_validator("start", "end", "item_sep")
    @classmethod
    def _valid_phrases(cls, v: str | None) -> str | None:
        return _check_phrases(v)


class ListSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    split: SplitSpec | None = None
    max_items: int | None = Field(None, gt=0)


class DocTypeConfig(BaseModel):
    id: str
    title: str = ""
    output_template: str
    classify: ClassifyConfig = Field(default_factory=ClassifyConfig)
    fields: dict[str, FieldSpec] = Field(default_factory=dict)
    lists: dict[str, ListSpec] = Field(default_factory=dict)
    llm: dict[str, Any] = Field(default_factory=dict)
    config_dir: Path = CONFIG_DIR

    def check_paths(self) -> None:
        """Ścieżki ``fields``/``lists`` muszą istnieć w szablonie wyniku (czytelny błąd przy starcie)."""
        eng = _engine()
        tmpl = self.template()
        bad = [p for p in self.fields if not eng.template_has_path(tmpl, p)]
        bad += [p for p in self.lists if not eng.template_has_path(tmpl, p + eng.LIST_MARK)]
        if bad:
            raise ValueError(f"typ {self.id!r}: ścieżki spoza szablonu {self.output_template}: {bad}")

    def template(self) -> dict:
        """Świeża kopia szablonu wyniku (wszystkie wartości null)."""
        return copy.deepcopy(_read_json(self.config_dir / self.output_template))

    def prompt_text(self) -> str | None:
        p = self.llm.get("prompt")
        return (self.config_dir / p).read_text(encoding="utf-8") if p else None


@cache
def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_registry(config_dir: Path = CONFIG_DIR) -> dict[str, DocTypeConfig]:
    """Wszystkie typy dokumentów z config/doctypes. Nowy typ = nowy plik YAML."""
    reg: dict[str, DocTypeConfig] = {}
    for f in sorted((config_dir / "doctypes").glob("*.yaml")):
        cfg = DocTypeConfig(**_read_yaml(f), config_dir=config_dir)  # błąd -> pydantic ValidationError
        cfg.check_paths()
        if cfg.id in reg:
            raise ValueError(f"Zduplikowane id typu dokumentu: {cfg.id} ({f})")
        reg[cfg.id] = cfg
    return reg


def load_lookup(name: str, config_dir: Path = CONFIG_DIR) -> dict:
    return _read_yaml(config_dir / "lookups" / f"{name}.yaml")


def load_app_config(config_dir: Path = CONFIG_DIR) -> dict:
    return _read_yaml(config_dir / "app.yaml")


def load_classify_settings(config_dir: Path = CONFIG_DIR) -> ClassifySettings:
    """Globalne ustawienia klasyfikatora (``config/classify.yaml``); brak pliku = bez ustawień."""
    path = config_dir / "classify.yaml"
    return ClassifySettings(**_read_yaml(path)) if path.exists() else ClassifySettings()


def load_llm_config(config_dir: Path = CONFIG_DIR) -> dict:
    return _read_yaml(config_dir / "llm.yaml")
