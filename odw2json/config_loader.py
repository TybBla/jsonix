"""Ładowanie konfiguracji: typy dokumentów (config/doctypes/*.yaml), lookupy, app.yaml."""

from __future__ import annotations

import copy
import json
import re
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT_DIR / "config"
REGEX_PREFIX = "re:"  # prefiks wpisu required_any traktowanego jako regex


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


class ClassifyConfig(BaseModel):
    """Cechy rozpoznawania typu dokumentu (wszystko poza ``strong/weak/negative/min_score`` opcjonalne).

    ``title`` - frazy szukane w nagłówku (pierwsze ``header_chars`` znaków, z zwijaniem rozstrzelonych liter);
    ``patterns`` - regexy z wagami; ``required_any`` - frazy lub ``re:<regex>``, bez trafienia typ odpada;
    ``min_score`` - minimalny wynik; ``min_margin`` - minimalna przewaga nad drugim typem.
    """

    model_config = ConfigDict(extra="forbid")

    strong: list[str] = Field(default_factory=list)
    weak: list[str] = Field(default_factory=list)
    negative: list[str] = Field(default_factory=list)
    title: list[str] = Field(default_factory=list)
    patterns: list[PatternSpec] = Field(default_factory=list)
    required_any: list[str] = Field(default_factory=list)
    min_score: float = 3.0
    min_margin: float = Field(0.0, ge=0)
    header_chars: int = Field(600, gt=0)
    weights: ClassifyWeights = Field(default_factory=ClassifyWeights)

    @field_validator("required_any")
    @classmethod
    def _valid_required(cls, items: list[str]) -> list[str]:
        for item in items:
            if item.startswith(REGEX_PREFIX):
                try:
                    re.compile(item[len(REGEX_PREFIX) :])
                except re.error as e:
                    raise ValueError(f"niepoprawny regex w required_any {item!r}: {e}") from e
        return items


class DocTypeConfig(BaseModel):
    id: str
    title: str = ""
    output_template: str
    classify: ClassifyConfig = Field(default_factory=ClassifyConfig)
    fields: dict[str, Any] = Field(default_factory=dict)
    llm: dict[str, Any] = Field(default_factory=dict)
    config_dir: Path = CONFIG_DIR

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
        cfg = DocTypeConfig(**_read_yaml(f), config_dir=config_dir)
        if cfg.id in reg:
            raise ValueError(f"Zduplikowane id typu dokumentu: {cfg.id} ({f})")
        reg[cfg.id] = cfg
    return reg


def load_lookup(name: str, config_dir: Path = CONFIG_DIR) -> dict:
    return _read_yaml(config_dir / "lookups" / f"{name}.yaml")


def load_app_config(config_dir: Path = CONFIG_DIR) -> dict:
    return _read_yaml(config_dir / "app.yaml")


def load_llm_config(config_dir: Path = CONFIG_DIR) -> dict:
    return _read_yaml(config_dir / "llm.yaml")
