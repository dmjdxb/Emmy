"""Verified knowledge base — a per-project ledger of Emmy's verified findings.

The leap from "verify one claim" to "run a verified research program": every durable
[proved]/[computed]/[cited] result can be RECORDED with its evidence, then RECALLED so
future work builds on it instead of re-deriving — and, crucially, a new result that
CONTRADICTS an earlier verified one is flagged automatically.

Token-disciplined: both tools are DEFERRED (not loaded per turn) and discovered via
tool_search only when needed; the only prompt nudge lives in Max-effort guidance.

Storage: SQLite at ~/.emmy/knowledge.db (override EMMY_KB_PATH), scoped by project
(EMMY_KB_PROJECT, else the basename of the working directory).
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from typing import Any

_TRUE_TAGS = {"proved", "computed", "cited"}
_STOP = set("a an the of to in on for and or is are was were be that this it its with by as at from "
            "= == equals equal value result we our you they".split())


def _result(verified: str, summary: str, **data: Any) -> str:
    return json.dumps({"verified": verified, "summary": summary, **data}, default=str)


def _db_path() -> str:
    p = os.environ.get("EMMY_KB_PATH")
    if p:
        return os.path.expanduser(p)
    home = os.path.expanduser("~/.emmy")
    os.makedirs(home, exist_ok=True)
    return os.path.join(home, "knowledge.db")


def _project() -> str:
    p = os.environ.get("EMMY_KB_PROJECT")
    if p:
        return p
    try:
        return os.path.basename(os.path.abspath(os.getcwd())) or "default"
    except Exception:
        return "default"


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_db_path(), timeout=10)
    c.execute(
        "CREATE TABLE IF NOT EXISTS findings ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT, key TEXT, claim TEXT, "
        "verified TEXT, value REAL, evidence TEXT, source TEXT, created_at TEXT)"
    )
    return c


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (s or "").strip().lower()).strip("_")


def _words(s: str) -> set:
    return {w for w in re.findall(r"[a-z0-9][a-z0-9\-]{1,}", (s or "").lower()) if w not in _STOP}


def _overlap(a: str, b: str) -> float:
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _num(v: Any):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _close(a: float, b: float, rtol: float = 1e-6, atol: float = 1e-9) -> bool:
    return abs(a - b) <= atol + rtol * max(abs(a), abs(b))


def _row(r) -> dict:
    return {
        "id": r[0], "key": r[2], "claim": r[3], "verified": r[4],
        "value": r[5], "evidence": r[6], "source": r[7], "created_at": r[8],
    }


def kb_record(claim: str, verified: str, key: str = "", value: Any = None,
              evidence: str = "", source: str = "") -> str:
    """Persist a verified finding; auto-flag contradictions with prior verified results."""
    claim = (claim or "").strip()
    verified = (verified or "").strip().lower()
    if not claim:
        return _result("assumed", "nothing recorded: provide the claim text")
    if verified not in _TRUE_TAGS | {"refuted", "assumed"}:
        return _result("assumed", f"nothing recorded: 'verified' must be proved/computed/cited/refuted/assumed, got {verified!r}")

    proj = _project()
    k = _slug(key) if key else ""
    val = _num(value)
    conn = _conn()
    try:
        # Look for prior findings about the SAME subject (same key, or — when no key —
        # a strongly overlapping claim) to detect contradictions before we store.
        existing = [_row(r) for r in conn.execute("SELECT * FROM findings WHERE project=?", (proj,)).fetchall()]
        same_subject = []
        for e in existing:
            if k and e["key"] == k:
                same_subject.append(e)
            elif not k and not e["key"] and _overlap(claim, e["claim"]) >= 0.6:
                same_subject.append(e)

        contradictions = []
        for e in same_subject:
            verdict_conflict = (verified in _TRUE_TAGS and e["verified"] == "refuted") or \
                               (verified == "refuted" and e["verified"] in _TRUE_TAGS)
            value_conflict = (val is not None and e["value"] is not None and not _close(val, e["value"]))
            if verdict_conflict or value_conflict:
                contradictions.append({
                    "prior_id": e["id"], "prior_claim": e["claim"], "prior_verified": e["verified"],
                    "prior_value": e["value"], "reason": "opposite verdict" if verdict_conflict else "different value",
                })

        cur = conn.execute(
            "INSERT INTO findings (project, key, claim, verified, value, evidence, source, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (proj, k, claim, verified, val, (evidence or "").strip(), (source or "").strip(),
             time.strftime("%Y-%m-%dT%H:%M:%S")),
        )
        conn.commit()
        rid = cur.lastrowid
    finally:
        conn.close()

    if contradictions:
        return _result(
            "refuted",
            f"⚠ CONTRADICTION: this result conflicts with {len(contradictions)} earlier VERIFIED finding(s) "
            f"in project '{proj}'. Reconcile before trusting it — one of them is wrong.",
            recorded_id=rid, key=k, project=proj, contradictions=contradictions,
        )
    return _result(
        "computed",
        f"recorded verified finding #{rid} in project '{proj}'"
        + (f" (key '{k}')" if k else "") + "; no conflict with prior findings.",
        recorded_id=rid, key=k, project=proj, contradictions=[],
    )


def kb_recall(query: str = "", key: str = "", limit: int = 5) -> str:
    """Retrieve prior verified findings (by subject key or keyword query) to build on/cite."""
    n = max(1, min(50, int(limit or 5)))
    proj = _project()
    conn = _conn()
    try:
        rows = [_row(r) for r in conn.execute(
            "SELECT * FROM findings WHERE project=? ORDER BY id DESC", (proj,)).fetchall()]
    finally:
        conn.close()

    k = _slug(key) if key else ""
    if k:
        hits = [r for r in rows if r["key"] == k]
    elif (query or "").strip():
        scored = [(r, _overlap(query, r["claim"] + " " + (r["evidence"] or ""))) for r in rows]
        hits = [r for r, s in sorted(scored, key=lambda x: x[1], reverse=True) if s > 0]
    else:
        hits = rows  # no filter -> most recent
    hits = hits[:n]
    if not hits:
        return _result("assumed", f"no prior verified findings in project '{proj}' for that query — derive it fresh (and record it).", findings=[])
    return _result("cited", f"{len(hits)} prior verified finding(s) in project '{proj}'", findings=hits)


# --- Registration (auto-imported by tools/registry.discover_builtin_tools) ---

KB_RECORD_SCHEMA = {
    "name": "kb_record",
    "description": (
        "Save a durable VERIFIED finding to this project's knowledge base so future work builds on it "
        "instead of re-deriving — and so a later result that CONTRADICTS it is flagged automatically. "
        "Record only results you actually verified (a [proved]/[computed]/[cited] tag). Give a short canonical "
        "'key' for the subject (e.g. 'gaussian_integral', 'water_boiling_point_1atm') so the same fact is "
        "tracked across sessions; include the numeric 'value' when there is one. Returns a contradiction "
        "warning (verified=refuted) if this conflicts with an earlier verified finding."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "claim": {"type": "string", "description": "The finding, stated precisely (e.g. '∫e^{-x²}dx over ℝ = √π')."},
            "verified": {"type": "string", "enum": ["proved", "computed", "cited", "refuted", "assumed"], "description": "How it was verified."},
            "key": {"type": "string", "description": "Short canonical subject slug to track this fact across sessions (recommended)."},
            "value": {"type": ["number", "string"], "description": "The numeric value, if the finding has one (enables value-contradiction checks)."},
            "evidence": {"type": "string", "description": "Brief evidence: the proof/computation/citation that verified it."},
            "source": {"type": "string", "description": "Citation/source identifier, if [cited]."},
        },
        "required": ["claim", "verified"],
    },
}

KB_RECALL_SCHEMA = {
    "name": "kb_recall",
    "description": (
        "Recall this project's prior VERIFIED findings before re-deriving — build on what you already proved, "
        "cite your own earlier results, and avoid redundant work. Search by 'key' (exact subject) or 'query' "
        "(keywords). Always check here first for a result that may already be established. Returns the stored "
        "claims with how each was verified and its evidence."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Keywords describing the result you're looking for."},
            "key": {"type": "string", "description": "Exact subject slug to look up (as used in kb_record)."},
            "limit": {"type": "integer", "description": "Max findings to return (default 5)."},
        },
        "required": [],
    },
}

from tools.registry import registry  # noqa: E402

registry.register(
    name="kb_record", toolset="science", schema=KB_RECORD_SCHEMA, emoji="🗄️",
    handler=lambda args, **kw: kb_record(
        args["claim"], args["verified"], args.get("key", ""), args.get("value"),
        args.get("evidence", ""), args.get("source", "")),
    description="Record a verified finding to the project knowledge base (flags contradictions).",
)
registry.register(
    name="kb_recall", toolset="science", schema=KB_RECALL_SCHEMA, emoji="🗂️",
    handler=lambda args, **kw: kb_recall(args.get("query", ""), args.get("key", ""), args.get("limit", 5)),
    description="Recall prior verified findings for this project to build on / cite.",
)
