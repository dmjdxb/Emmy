"""Per-product capability check — fail LOUDLY when a tool a product *requires* is
silently gated off.

The failure mode this exists to kill: a capability-gated tool (web_search, the office
builders, image_generate, ...) whose backend/key/registration isn't provisioned just
returns False from its ``check_fn`` and **vanishes from the model's toolset** — no build
error, no failed test, no startup warning. So an app ships "green" with a capability
quietly dead (Hilbert shipped with no web search this way; the office tools shipped
never actually registered).

Each product declares a ``required_tools`` manifest (in its config). This module audits
that manifest against the live registry and reports two classes of failure:

  * MISSING — the tool isn't registered at all (a discovery/registration bug, e.g. a
    ``registry.register`` call hidden inside try/except that ``discover_builtin_tools``
    can't see). Catchable in CI with NO keys — registration is environment-independent.
  * GATED  — the tool is registered but its ``check_fn`` returns False (its backend/key
    isn't provisioned). Only detectable in the real runtime environment, so this is the
    post-deploy / healthcheck assertion.

Run it two ways:
  * CI / build:   audit(..., check_availability=False) — asserts every required tool is
    at least REGISTERED. Fails the build on the registration-bug class.
  * Prod / deploy: audit(..., check_availability=True) — also asserts each is AVAILABLE.
    Fails (or loudly warns) when a backend wasn't provisioned.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class CapabilityError(RuntimeError):
    """Raised by assert_required_capabilities(strict=True) when a required tool is dead."""


@dataclass
class CapabilityReport:
    required: list[str]
    available: list[str] = field(default_factory=list)
    gated: list[str] = field(default_factory=list)      # registered but check_fn False (backend/key missing)
    invisible: list[str] = field(default_factory=list)  # registered + working but NOT core (model can't see it)
    missing: list[str] = field(default_factory=list)    # not registered at all (registration/discovery bug)

    @property
    def ok(self) -> bool:
        return not self.gated and not self.missing and not self.invisible

    def summary(self) -> str:
        if self.ok:
            return f"capability check OK — all {len(self.required)} required tools present, available, and visible"
        parts = ["‼ CAPABILITY CHECK FAILED — a required tool is not usable by the model:"]
        if self.missing:
            parts.append(
                f"  MISSING (not registered — registration/discovery bug): {', '.join(sorted(self.missing))}"
            )
        if self.invisible:
            parts.append(
                f"  INVISIBLE (registered + working but NOT in the core toolset, so the model never "
                f"sees it): {', '.join(sorted(self.invisible))}"
            )
        if self.gated:
            parts.append(
                f"  GATED OFF (registered but its backend/key/service is not provisioned): "
                f"{', '.join(sorted(self.gated))}"
            )
        return "\n".join(parts)


def _registered_entries() -> dict:
    from tools.registry import registry
    return {e.name: e for e in registry._snapshot_entries()}


def _model_visible(name: str) -> bool:
    """True when the model is actually allowed to SEE this tool — i.e. it is in the
    always-available core set. A tool can be registered AND pass its check_fn yet be
    invisible because it lives in a toolset that isn't enabled (exactly how
    deliver_artifact slipped through: registered + working, but not core)."""
    try:
        from toolsets import _HERMES_CORE_TOOLS
        return name in _HERMES_CORE_TOOLS
    except Exception:
        return True  # can't determine → don't false-alarm


def tool_status(name: str) -> str:
    """Return 'available' | 'gated' | 'invisible' | 'missing' for one tool.

    available  — registered, check_fn passes, AND in the model's core toolset.
    invisible  — registered + working but NOT core (the model can't see it; the
                 deliver_artifact bug class).
    gated      — registered but check_fn False (backend/key not provisioned).
    missing    — not registered at all (registration/discovery bug)."""
    entries = _registered_entries()
    entry = entries.get(name)
    if entry is None:
        return "missing"
    if getattr(entry, "check_fn", None) is not None:
        from tools.registry import _check_fn_cached
        try:
            if not _check_fn_cached(entry.check_fn):
                return "gated"
        except Exception:
            return "gated"
    return "available" if _model_visible(name) else "invisible"


def audit_required_tools(required, *, check_availability: bool = True) -> CapabilityReport:
    """Classify each required tool as available / gated / missing.

    check_availability=False → registration-only (CI mode): a registered tool counts as
    available regardless of its backend (we can't probe prod keys in CI).
    """
    rep = CapabilityReport(required=list(dict.fromkeys(required)))  # de-dupe, keep order
    entries = _registered_entries()
    for name in rep.required:
        if name not in entries:
            rep.missing.append(name)
        elif not _model_visible(name):
            # core-membership is environment-independent — catch this even in CI (no keys),
            # so 'registered but the model can't see it' fails the build, not prod.
            rep.invisible.append(name)
        elif not check_availability:
            rep.available.append(name)  # registration mode: skip only the backend probe
        else:
            st = tool_status(name)
            bucket = {"available": rep.available, "gated": rep.gated,
                      "invisible": rep.invisible, "missing": rep.missing}[st]
            bucket.append(name)
    return rep


def assert_required_capabilities(
    required,
    *,
    check_availability: bool = True,
    strict: bool = False,
) -> CapabilityReport:
    """Audit and, on failure, log LOUDLY (and raise if strict). Runs discovery first.

    strict=True is for CI / a deploy gate (fail the pipeline). strict=False is for a
    startup banner (warn loudly, don't crash the app)."""
    from tools.registry import discover_builtin_tools
    discover_builtin_tools()
    rep = audit_required_tools(required, check_availability=check_availability)
    if rep.ok:
        logger.info(rep.summary())
    else:
        logger.error(rep.summary())
        if strict:
            raise CapabilityError(rep.summary())
    return rep
