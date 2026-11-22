"""Nakładka konfiguracji aplikacji: JSONIX_APP_CONFIG (profil jury, config/app.jury.yaml)."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

import pytest
import yaml

from odw2json import config_loader
from odw2json.config_loader import CONFIG_DIR, load_app_config
from odw2json.ingest.ocr import resolve_cache_dir

ENV = "JSONIX_APP_CONFIG"
JURY = CONFIG_DIR / "app.jury.yaml"


def _base() -> dict:
    return yaml.safe_load((CONFIG_DIR / "app.yaml").read_text(encoding="utf-8"))


def test_no_env_means_plain_app_yaml(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    assert load_app_config() == _base()


def test_empty_env_means_no_overlay(monkeypatch):
    monkeypatch.setenv(ENV, "  ")
    assert load_app_config() == _base()


def test_overlay_is_deep_merged(monkeypatch, tmp_path):
    overlay = tmp_path / "o.yaml"
    overlay.write_text(
        "write_trace: false\n"
        "ingest:\n"
        "  fallback_backends: [pypdf]\n"
        "  ocr:\n"
        "    cache_dir: /gdzie/indziej\n"
        "    engine_params:\n"
        "      EngineConfig.onnxruntime.intra_op_num_threads: 2\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(ENV, str(overlay))
    cfg, base = load_app_config(), _base()
    assert cfg["write_trace"] is False
    assert cfg["ingest"]["ocr"]["cache_dir"] == "/gdzie/indziej"
    assert cfg["ingest"]["fallback_backends"] == ["pypdf"]  # lista: nadpisana, nie sklejona
    params = cfg["ingest"]["ocr"]["engine_params"]
    assert params["EngineConfig.onnxruntime.intra_op_num_threads"] == 2
    assert params["Global.use_cls"] is False  # reszta słownika zachowana
    assert cfg["ingest"]["backend"] == base["ingest"]["backend"]
    assert cfg["ingest"]["ocr"]["enabled"] == base["ingest"]["ocr"]["enabled"]
    assert cfg["unknown_output"] == base["unknown_output"]


def test_relative_path_is_resolved_from_repo_root(monkeypatch, tmp_path):
    """Ścieżka względna liczona od katalogu nadrzędnego config_dir (korzeń repo; w kontenerze /app)."""
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    (cfg_dir / "app.yaml").write_text("write_trace: true\nlog_dir: null\n", encoding="utf-8")
    (cfg_dir / "profil.yaml").write_text("write_trace: false\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path.parent)  # cwd bez znaczenia
    monkeypatch.setenv(ENV, "config/profil.yaml")
    assert load_app_config(cfg_dir) == {"write_trace": False, "log_dir": None}


def test_missing_overlay_file_is_clear_error(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV, str(tmp_path / "nie-ma.yaml"))
    with pytest.raises(FileNotFoundError, match=ENV):
        load_app_config()


def test_overlay_must_be_a_mapping(monkeypatch, tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("- a\n- b\n", encoding="utf-8")
    monkeypatch.setenv(ENV, str(bad))
    with pytest.raises(ValueError, match=ENV):
        load_app_config()


def test_deep_merge_does_not_mutate_inputs():
    base = {"a": {"b": 1, "c": [1]}, "d": 1}
    over = {"a": {"b": 2}, "e": 3}
    out = config_loader.deep_merge(base, over)
    assert out == {"a": {"b": 2, "c": [1]}, "d": 1, "e": 3}
    assert base == {"a": {"b": 1, "c": [1]}, "d": 1} and over == {"a": {"b": 2}, "e": 3}


def test_jury_profile_keeps_output_clean(monkeypatch):
    monkeypatch.setenv(ENV, str(JURY))
    cfg, base = load_app_config(), _base()
    assert cfg["write_trace"] is False
    assert cfg["ingest"]["ocr"]["engine_params"]["EngineConfig.onnxruntime.intra_op_num_threads"] == 2
    # profil nie może zmieniać wyników: reszta ingest identyczna jak w app.yaml
    for key in ("backend", "fallback_backends", "clean"):
        assert cfg["ingest"][key] == base["ingest"][key]
    assert cfg["llm_enabled"] is False
    # cache OCR i logi poza output (ścieżki bezwzględne linuksowe: /tmp/...)
    for path in (cfg["ingest"]["ocr"]["cache_dir"], cfg["log_dir"]):
        p = PurePosixPath(path)
        assert p.is_absolute() and p.parts[:2] == ("/", "tmp")


def test_jury_cache_dir_resolves_outside_output(monkeypatch, tmp_path):
    """resolve_cache_dir z profilem jury: katalog bezwzględny zostaje bez zmian."""
    monkeypatch.setenv(ENV, str(JURY))
    cache = load_app_config()["ingest"]["ocr"]["cache_dir"]
    assert resolve_cache_dir(cache) == Path(cache) or resolve_cache_dir(cache).as_posix().endswith(cache)
    abs_dir = tmp_path / "ocr"
    assert resolve_cache_dir(abs_dir) == abs_dir
    # bez profilu: względny, pod korzeniem repo
    monkeypatch.delenv(ENV)
    default = load_app_config()["ingest"]["ocr"]["cache_dir"]
    assert resolve_cache_dir(default) == config_loader.ROOT_DIR / default
