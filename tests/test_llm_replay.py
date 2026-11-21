"""Testy trybow record/replay/auto/live klienta LLM. Bez sieci: podmieniony klient."""

import json
from types import SimpleNamespace

import pytest

from odw2json.llm import CassetteCorrupt, CassetteMissing, LLMClient, cassette_key


class FakeClient:
    def __init__(self, content='{"a": "zażółć"}', pt=10, ct=5):
        self.calls = 0
        self.content, self.pt, self.ct = content, pt, ct
        self.kwargs = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls += 1
        self.kwargs.append(kw)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))],
            usage=SimpleNamespace(prompt_tokens=self.pt, completion_tokens=self.ct),
        )


def make(tmp_path, mode, fake=None, **kw):
    fake = fake or FakeClient()
    c = LLMClient(model="m", mode=mode, cassette_dir=str(tmp_path), client=fake, **kw)
    return c, fake


def test_record_writes_cassette(tmp_path):
    c, fake = make(tmp_path, "record")
    assert c.complete_json("sys", "usr") == {"a": "zażółć"}
    path = tmp_path / f"{cassette_key('m', 'sys', 'usr', 0)}.json"
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    assert data["model"] == "m" and data["system"] == "sys" and data["user"] == "usr"
    assert data["response"] == {"a": "zażółć"}
    assert data["usage"] == {"prompt_tokens": 10, "completion_tokens": 5}
    assert "created" in data and "temperature" in data
    assert "zażółć" in text
    assert fake.calls == 1


def test_replay_reads_without_calling_client(tmp_path):
    rec, _ = make(tmp_path, "record")
    rec.complete_json("s", "u")
    rep, fake = make(tmp_path, "replay")
    assert rep.complete_json("s", "u") == {"a": "zażółć"}
    assert fake.calls == 0
    assert rep.usage["cached_calls"] == 1 and rep.usage["calls"] == 0


def test_replay_missing_raises(tmp_path):
    c, fake = make(tmp_path, "replay")
    with pytest.raises(CassetteMissing) as e:
        c.complete_json("s", "u")
    assert cassette_key("m", "s", "u", 0) in str(e.value)
    assert "LLM_MODE=record" in str(e.value)
    assert isinstance(e.value, RuntimeError) and fake.calls == 0


def test_auto_records_then_replays(tmp_path):
    c, fake = make(tmp_path, "auto")
    c.complete_json("s", "u")
    c.complete_json("s", "u")
    assert fake.calls == 1
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_live_never_writes(tmp_path):
    c, fake = make(tmp_path, "live")
    c.complete_json("s", "u")
    c.complete_json("s", "u")
    assert fake.calls == 2
    assert list(tmp_path.glob("*.json")) == []


def test_usage_sums(tmp_path):
    c, _ = make(tmp_path, "live")
    c.complete_json("s", "u1")
    c.complete_json("s", "u2")
    assert c.usage_report() == {"prompt_tokens": 20, "completion_tokens": 10, "calls": 2, "cached_calls": 0}


def test_json_mode_configurable(tmp_path):
    c, fake = make(tmp_path, "live")
    c.complete_json("s", "u")
    assert fake.kwargs[0]["response_format"] == {"type": "json_object"}
    c2, fake2 = make(tmp_path, "live", json_mode=False)
    c2.complete_json("s", "u")
    assert "response_format" not in fake2.kwargs[0]


def test_key_depends_on_temperature():
    assert cassette_key("m", "s", "u", 0) != cassette_key("m", "s", "u", 0.5)


def _patch(monkeypatch, cfg):
    for k in ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY", "LLM_MODE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr("odw2json.llm.load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr("odw2json.llm.load_llm_config", lambda: cfg)


def test_from_config_replay_without_env(tmp_path, monkeypatch):
    _patch(monkeypatch, {"model": "m", "cassette_dir": str(tmp_path)})
    c = LLMClient.from_config()
    assert c.mode == "replay"  # w pytest domyslnie replay
    with pytest.raises(CassetteMissing):
        c.complete_json("s", "u")


def test_from_config_network_mode_requires_env(tmp_path, monkeypatch):
    _patch(monkeypatch, {"cassette_dir": str(tmp_path)})
    monkeypatch.setenv("LLM_MODE", "record")
    with pytest.raises(RuntimeError) as e:
        LLMClient.from_config()
    for name in ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY"):
        assert name in str(e.value)


def test_env_mode_wins_over_config(tmp_path, monkeypatch):
    _patch(monkeypatch, {"model": "m", "mode": "live", "cassette_dir": str(tmp_path)})
    monkeypatch.setenv("LLM_MODE", "replay")
    assert LLMClient.from_config().mode == "replay"


def test_key_int_and_float_temperature_equal():
    assert cassette_key("m", "s", "u", 0) == cassette_key("m", "s", "u", 0.0)


def test_from_config_default_model_from_yaml(monkeypatch):
    for k in ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY", "LLM_MODE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr("odw2json.llm.load_dotenv", lambda *a, **k: None)
    assert LLMClient.from_config().model == "ministral-8b-latest"


def test_corrupt_cassette_raises_named_error(tmp_path):
    path = tmp_path / f"{cassette_key('m', 's', 'u', 0)}.json"
    path.write_text("{nie json", encoding="utf-8")
    c, fake = make(tmp_path, "replay")
    with pytest.raises(CassetteCorrupt) as e:
        c.complete_json("s", "u")
    assert path.name in str(e.value) and isinstance(e.value, RuntimeError) and fake.calls == 0


def test_cassette_written_atomically(tmp_path):
    c, _ = make(tmp_path, "record")
    c.complete_json("s", "u")
    assert list(tmp_path.glob("*.tmp")) == []
    assert len(list(tmp_path.glob("*.json"))) == 1
