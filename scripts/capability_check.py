#!/usr/bin/env python3
"""Run the per-product capability check. Exits non-zero if a required tool is dead.

This is the guard against silently shipping a broken capability (web search with no
backend, an office tool that never registered). Run it in CI (registration mode) and
as a post-deploy healthcheck (availability mode).

Usage:
    python scripts/capability_check.py                    # prod: registered AND available
    python scripts/capability_check.py --registration-only  # CI: registered only (no keys needed)
    python scripts/capability_check.py --tools a,b,c      # override the required list
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    reg_only = "--registration-only" in sys.argv
    override = None
    for i, a in enumerate(sys.argv):
        if a == "--tools" and i + 1 < len(sys.argv):
            override = [t.strip() for t in sys.argv[i + 1].split(",") if t.strip()]

    if override is not None:
        required = override
    else:
        from robin.config import load_config
        required = load_config().get("required_tools") or []
    if not required:
        print("No required_tools manifest configured — nothing to check.")
        return 0

    from tools.capability_check import assert_required_capabilities

    rep = assert_required_capabilities(
        required, check_availability=not reg_only, strict=False
    )
    print(rep.summary())
    if not rep.ok:
        print(
            "\nMode:",
            "registration-only (run without --registration-only in prod to also check backends)"
            if reg_only
            else "availability (prod) — GATED tools need their backend/key/service provisioned",
        )
    return 0 if rep.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
