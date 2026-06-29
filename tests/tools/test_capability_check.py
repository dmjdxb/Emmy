"""Per-product capability check — guards against shipping a tool the model can't use:
MISSING (not registered), INVISIBLE (registered but not core), GATED (no backend)."""

from __future__ import annotations

import pytest

from tools.capability_check import CapabilityReport, audit_required_tools


def test_audit_classifies_missing_gated_available(monkeypatch):
    class _E:
        def __init__(self, name, check):
            self.name = name
            self.check_fn = check

    entries = {"good": _E("good", None), "keyed": _E("keyed", lambda: False)}
    import tools.capability_check as cc
    monkeypatch.setattr(cc, "_registered_entries", lambda: entries)
    monkeypatch.setattr(cc, "_model_visible", lambda n: True)  # isolate the backend dimension
    import tools.registry as reg
    monkeypatch.setattr(reg, "_check_fn_cached", lambda fn: fn())

    rep = audit_required_tools(["good", "keyed", "ghost"], check_availability=True)
    assert rep.available == ["good"] and rep.gated == ["keyed"] and rep.missing == ["ghost"]
    assert rep.ok is False


def test_invisible_when_registered_but_not_core(monkeypatch):
    """deliver_artifact bug class: registered + working but not core → model can't see it."""
    class _E:
        def __init__(self, name):
            self.name = name
            self.check_fn = lambda: True
    import tools.capability_check as cc
    monkeypatch.setattr(cc, "_registered_entries", lambda: {"t": _E("t")})
    monkeypatch.setattr(cc, "_model_visible", lambda n: False)
    rep = audit_required_tools(["t"], check_availability=False)  # caught even in CI
    assert rep.invisible == ["t"] and not rep.ok and "INVISIBLE" in rep.summary()


def test_registration_mode_ignores_backend(monkeypatch):
    class _E:
        def __init__(self, name, check):
            self.name = name
            self.check_fn = check
    import tools.capability_check as cc
    monkeypatch.setattr(cc, "_registered_entries", lambda: {"keyed": _E("keyed", lambda: False)})
    monkeypatch.setattr(cc, "_model_visible", lambda n: True)
    rep = audit_required_tools(["keyed"], check_availability=False)
    assert rep.ok and rep.available == ["keyed"]


def test_ok_report_summary():
    rep = CapabilityReport(required=["a"], available=["a"])
    assert rep.ok and "OK" in rep.summary()


def test_required_tools_are_registered_and_visible():
    """CI guard: every required tool is registered AND core-visible (catches both bug classes)."""
    from tools.registry import discover_builtin_tools
    discover_builtin_tools()
    from robin.config import load_config
    required = load_config().get("required_tools") or []
    assert required, "this product should declare a required_tools manifest"
    rep = audit_required_tools(required, check_availability=False)
    assert rep.ok, rep.summary()


def test_delivery_and_research_in_required():
    from robin.config import load_config
    required = set(load_config().get("required_tools") or [])
    assert "deliver_artifact" in required  # every product must be able to deliver a file
    assert "web_search" in required        # research agent needs the live web
