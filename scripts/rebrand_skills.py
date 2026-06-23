#!/usr/bin/env python3
"""Rebrand user-facing Hermes leaks in shipped skill markdown.

Scope: skills/**/*.md only (docs the agent surfaces to users). Code (.py) is
left untouched so logic can't break. Three safe replacements:

  1. ~/.hermes            -> ~/.robin        (real home is ~/.robin)
  2. robin.energyir.com   -> energyir.io     (dead domain the old rebrand
                                              introduced -> the live site)
  3. CLI command `hermes` -> `robin`         (robin is a real entry point;
                                              hermes is only the retained alias)

The command rule uses a regex that matches the bare word `hermes` ONLY when it
is NOT followed by a separator that marks an internal identifier or path:
  - hermes-agent, hermes-gateway   (hyphen)  -> KEPT (real dir/service names)
  - hermes_state.py                (underscore) -> KEPT
  - hermesDesktop                  (word char) -> KEPT
  - hermes.py, hermes/...          (dot/slash) -> KEPT
  - HERMES_HOME                    (uppercase) -> KEPT (case-sensitive)
Run rules 1 & 2 FIRST so `.hermes/` paths are gone before the command rule.

Usage:
  python scripts/rebrand_skills.py --check   # dry-run: counts + samples
  python scripts/rebrand_skills.py           # apply
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"

# Order matters: paths + URL before the bare-command rule.
CMD_RE = re.compile(r"\bhermes(?![-\w./:])")


def transform(text: str) -> tuple[str, int]:
    subs = 0
    new = text.replace("~/.hermes", "~/.robin")
    subs += (text.count("~/.hermes"))
    before = new
    new = new.replace("robin.energyir.com", "energyir.io")
    subs += before.count("robin.energyir.com")
    new, n = CMD_RE.subn("robin", new)
    subs += n
    return new, subs


def main() -> int:
    check = "--check" in sys.argv
    files = sorted(SKILLS.rglob("*.md"))
    total_subs = 0
    changed = 0
    samples = []
    for f in files:
        text = f.read_text(encoding="utf-8")
        new, subs = transform(text)
        if new != text:
            changed += 1
            total_subs += subs
            if check and len(samples) < 6:
                # capture a couple of changed lines for review
                for o, t in zip(text.splitlines(), new.splitlines()):
                    if o != t:
                        samples.append(f"  {f.relative_to(ROOT)}\n    - {o.strip()[:90]}\n    + {t.strip()[:90]}")
                        break
            if not check:
                f.write_text(new, encoding="utf-8")
    print(f"{'[check] ' if check else ''}{total_subs} replacements across {changed} files (of {len(files)} md files)")
    if samples:
        print("sample changes:")
        print("\n".join(samples))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
