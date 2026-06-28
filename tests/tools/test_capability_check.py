"""Per-product capability check — the guard against silently shipping a dead tool.

The registration-mode test would have caught the office-tools-never-discovered class;
the manifest test guards this product's reason-for-being tools (incl. live web search).
"""

from __future__ import annotations

import pytest

from tools.capability_check import (
    CapabilityReport,
    audit_required_tools,
)


def test_audit_classifies_missing_gated_available(monkeypatch):
    class _E:
        def __init__(self, name, check):
            self.name = name
            self.check_fn = check

    entries = {"good": _E("good", None), "keyed": _E("keyed", lambda: False)}
    import tools.capability_check as cc
    monkeypatch.setattr(cc, "_registered_entries", lambda: entries)
    import tools.registry as reg
    monkeypatch.setattr(reg, "_check_fn_cached", lambda fn: fn())

    rep = audit_required_tools(["good", "keyed", "ghost"], check_availability=True)
    assert rep.available == ["good"]
    assert rep.gated == ["keyed"]
    assert rep.missing == ["ghost"]
    assert rep.ok is False


def test_registration_mode_ignores_backend(monkeypatch):
    class _E:
        def __init__(self, name, check):
            self.name = name
            self.check_fn = check

    entries = {"keyed": _E("keyed", lambda: False)}
    import tools.capability_check as cc
    monkeypatch.setattr(cc, "_registered_entries", lambda: entries)
    rep = audit_required_tools(["keyed"], check_availability=False)
    assert rep.ok and rep.available == ["keyed"]


def test_ok_report_summary():
    rep = CapabilityReport(required=["a"], available=["a"])
    assert rep.ok and "OK" in rep.summary()


def test_required_tools_are_registered():
    """CI guard: every tool this product declares as required MUST be registered."""
    from tools.registry import discover_builtin_tools
    discover_builtin_tools()
    from robin.config import load_config
    required = load_config().get("required_tools") or []
    assert required, "this product should declare a required_tools manifest"
    rep = audit_required_tools(required, check_availability=False)
    assert rep.ok, rep.summary()


def test_research_tools_in_required():
    """Live web search is a reason-for-being for this research agent — guard it."""
    from robin.config import load_config
    required = set(load_config().get("required_tools") or [])
    assert "web_search" in required and "web_extract" in required
