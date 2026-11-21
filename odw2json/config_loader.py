"""Ładowanie konfiguracji: typy dokumentów (config/doctypes/*.yaml), lookupy, app.yaml."""

from __future__ import annotations

import copy
import json
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT_DIR / "config"


class ClassifyConfig(BaseModel):
    strong: list[str] = Field(default_factory=list)
    weak: list[str] = Field(default_factory=list)
    negative: list[str] = Field(default_factory=list)
    min_score: float = 3.0


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
