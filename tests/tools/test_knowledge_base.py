"""Verified knowledge base: record/recall + the headline contradiction detection.

Each test runs against an isolated temp DB + project (env-scoped) so nothing touches
~/.emmy/knowledge.db.
"""
import importlib
import json

import pytest

import tools.knowledge_base as kb


@pytest.fixture()
def kbenv(tmp_path, monkeypatch):
    monkeypatch.setenv("EMMY_KB_PATH", str(tmp_path / "kb.db"))
    monkeypatch.setenv("EMMY_KB_PROJECT", "test")
    importlib.reload(kb)
    return kb


def _v(out):
    return json.loads(out)


def test_record_then_recall_by_key(kbenv):
    kbenv.kb_record("∫e^{-x²}dx = √π", "proved", key="gaussian_integral", value=1.7724538509)
    d = _v(kbenv.kb_recall(key="gaussian_integral"))
    assert d["verified"] == "cited" and len(d["findings"]) == 1
    assert d["findings"][0]["verified"] == "proved"


def test_recall_by_query_keyword(kbenv):
    kbenv.kb_record("water boils at 100°C at 1 atm", "computed", key="water_boiling", value=100.0)
    d = _v(kbenv.kb_recall(query="boiling point of water"))
    assert d["findings"] and "boils" in d["findings"][0]["claim"]


def test_recall_empty_is_honest(kbenv):
    assert _v(kbenv.kb_recall(query="nothing here"))["verified"] == "assumed"


def test_contradiction_on_conflicting_value(kbenv):
    kbenv.kb_record("g = 9.81 m/s²", "computed", key="grav", value=9.81)
    d = _v(kbenv.kb_record("g = 9.5 m/s²", "computed", key="grav", value=9.5))
    assert d["verified"] == "refuted" and d["contradictions"]
    assert d["contradictions"][0]["reason"] == "different value"


def test_contradiction_on_opposite_verdict(kbenv):
    kbenv.kb_record("P=NP", "proved", key="pnp")
    d = _v(kbenv.kb_record("P=NP is false", "refuted", key="pnp"))
    assert d["verified"] == "refuted" and d["contradictions"][0]["reason"] == "opposite verdict"


def test_no_false_positive_on_consistent_value(kbenv):
    kbenv.kb_record("√π", "proved", key="sp", value=1.7724538509)
    # same value (within tolerance) must NOT be flagged
    d = _v(kbenv.kb_record("√π again", "computed", key="sp", value=1.7724538509000001))
    assert d["verified"] == "computed" and d["contradictions"] == []


def test_project_isolation(kbenv, monkeypatch):
    kbenv.kb_record("local fact", "proved", key="x", value=1.0)
    monkeypatch.setenv("EMMY_KB_PROJECT", "other")
    assert _v(kbenv.kb_recall(key="x"))["findings"] == []


def test_rejects_bad_verdict(kbenv):
    assert _v(kbenv.kb_record("claim", "totally-sure"))["verified"] == "assumed"


def test_registered_in_science_toolset():
    from tools.registry import registry

    for name in ["kb_record", "kb_recall"]:
        e = registry.get_entry(name)
        assert e is not None and e.toolset == "science"
