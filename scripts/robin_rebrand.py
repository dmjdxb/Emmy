#!/usr/bin/env python3
"""Robin (by EnergyIR) deterministic rebrand pass.

This applies the *safe, unambiguous* string replacements that turn the upstream
Hermes Agent fork into Robin: provisioning/update repo URLs, the bundle id,
support email, marketing domain, copyright, and the full product name
"Hermes Agent" -> "Robin". It is idempotent (re-running is a no-op) and is
re-run on every upstream re-sync so the fork stays cheap to maintain
(PRD R-fork mitigation).

It deliberately does NOT blanket-replace the bare word "Hermes", because that
also appears in internal identifiers (HERMES_HOME, hermesDesktop, the `hermes`
venv entry point, robin module paths) that must keep working. Bare-word
user-visible occurrences in the shipped UI are fixed by targeted edits and
enforced by the CI string gate (scripts/check_brand.py) against the built
renderer output — the falsification instrument for PRD acceptance gate #7.

Usage:
    python scripts/robin_rebrand.py          # apply
    python scripts/robin_rebrand.py --check   # report only, non-zero if changes pending
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Directories never touched: upstream's own marketing site + docs, vendored
# deps, VCS, build output, and the test suite (tests assert on upstream repo
# strings; rewriting them would break unrelated assertions and they never ship).
EXCLUDE_DIRS = {
    "node_modules", ".git", "website", "site", "dist", "build", "release",
    "out", ".venv", "venv", "__pycache__", ".mypy_cache", ".ruff_cache",
    ".pytest_cache", "tests", "test", "paper",
}

# Only these file extensions are scanned.
INCLUDE_EXT = {
    ".py", ".ts", ".tsx", ".js", ".cjs", ".mjs", ".jsx", ".json", ".yaml",
    ".yml", ".sh", ".ps1", ".md", ".html", ".plist", ".desktop", ".cfg",
    ".toml", ".txt",
}

# Ordered replacements — MOST SPECIFIC FIRST so the broad domain rule does not
# clobber the repo/email/docs rules.
REPLACEMENTS: list[tuple[str, str]] = [
    # provisioning + self-update repo (clone/zip/raw URLs)
    ("NousResearch/hermes-agent", "dmjdxb/Robin"),
    ("NousResearch/Hermes-Agent", "dmjdxb/Robin"),
    ("nousresearch/hermes-agent", "dmjdxb/Robin"),
    # bundle / app identifier
    ("com.nousresearch.hermes", "com.energyir.robin"),
    # support + docs + marketing domains
    ("support@nousresearch.com", "hello@energyir.com"),
    ("hermes-agent.nousresearch.com", "robin.energyir.com"),
    ("www.nousresearch.com", "energyir.com"),
    ("nousresearch.com", "energyir.com"),
    # full product name (safe: no identifier is the two-word phrase)
    ("Hermes Agent", "Robin"),
    # UI display phrases — multi-word / punctuation-bounded value text only, so
    # they never collide with code identifiers or i18n keys. "Hermes Desktop"
    # first so it wins over the bare-word phrases below.
    ("Hermes Desktop", "Robin"),
    ("Hermes backend", "Robin backend"),
    ("Hermes inference", "Robin inference"),
    ("Hermes configuration", "Robin configuration"),
    ("Hermes sessions", "Robin sessions"),
    ("Hermes session", "Robin session"),
    ("Starting Hermes", "Starting Robin"),
    ("Updating Hermes", "Updating Robin"),
    ("Restart Hermes", "Restart Robin"),
    ("restart Hermes", "restart Robin"),
    ("About Hermes", "About Robin"),
    ("Ask Hermes", "Ask Robin"),
    ("Hermes is restarting", "Robin is restarting"),
    ("Hermes is loading", "Robin is loading"),
    ("Hermes is ready", "Robin is ready"),
    ("Hermes will only", "Robin will only"),
    ("Hermes Teal", "Robin Green"),
    ("URL at Hermes", "URL at Robin"),
    ("history of Hermes", "history of Robin"),
    # publisher / copyright holder
    ("Nous Research", "EnergyIR"),
]


def _skip(path: Path) -> bool:
    parts = set(path.parts)
    if parts & EXCLUDE_DIRS:
        return True
    if path.suffix.lower() not in INCLUDE_EXT:
        return True
    # never rewrite this script, the brand checker, or the brand-gate workflow —
    # they all intentionally contain the literal brand words (as detection
    # patterns / an attribution-retention check), which are not rebrand targets.
    if path.name in {"robin_rebrand.py", "check_brand.py", "brand-gate.yml"}:
        return True
    # never scrub attribution / licence files — MIT REQUIRES retaining the
    # upstream Hermes Agent (Nous Research) copyright + permission notice.
    upper = path.name.upper()
    if upper.startswith(("LICENSE", "LICENCE", "NOTICE", "COPYING", "THIRD_PARTY")):
        return True
    return False


def apply(check_only: bool) -> int:
    changed_files = 0
    total_subs = 0
    for path in REPO.rglob("*"):
        if not path.is_file() or _skip(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        new = text
        for old, repl in REPLACEMENTS:
            if old in new:
                new = new.replace(old, repl)
        if new != text:
            changed_files += 1
            # crude sub count
            for old, _ in REPLACEMENTS:
                total_subs += text.count(old)
            rel = path.relative_to(REPO)
            if check_only:
                print(f"  would update: {rel}")
            else:
                path.write_text(new, encoding="utf-8")
                print(f"  updated: {rel}")
    print(f"\n{'pending' if check_only else 'applied'}: "
          f"{total_subs} replacements across {changed_files} files")
    if check_only and changed_files:
        return 1
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report only; exit 1 if changes pending")
    args = ap.parse_args()
    sys.exit(apply(check_only=args.check))
