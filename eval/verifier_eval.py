"""M5 — verifier eval: PROVE Emmy's verification catches wrong answers.

A battery of claims, each labelled with ground truth. We run each through the relevant
verified tool and check the tool's verdict matches reality: TRUE claims must come back
proved/computed/cited; FALSE claims must come back refuted. The whole point of the moat is
that a wrong answer is REJECTED, not rubber-stamped — this harness demonstrates exactly that.

Run:  python -m eval.verifier_eval        (prints a trust report; exit 1 if any case is mis-adjudicated)
Also wrapped by tests/test_verifier_eval.py for CI.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

import tools.science_tools as st

PASS_VERDICTS = {"proved", "computed", "cited"}  # the claim was upheld
FAIL_VERDICTS = {"refuted"}                       # the claim was caught as false


@dataclass
class Case:
    name: str
    run: Callable[[], str]   # returns the tool's JSON envelope
    truth: bool              # is the claim actually TRUE?


# Each lambda calls a real verified tool. `truth` is what SHOULD happen.
CASES: list[Case] = [
    # --- symbolic (sympy) ---
    Case("∫2x dx = x²  (true)",            lambda: st.symbolic_check("integrate(2*x, x)", "x**2", "x"), True),
    Case("∫2x dx = x²+x  (FALSE)",         lambda: st.symbolic_check("integrate(2*x, x)", "x**2 + x", "x"), False),
    Case("d/dx x³ = 3x²  (true)",          lambda: st.symbolic_check("diff(x**3, x)", "3*x**2", "x"), True),
    Case("d/dx x³ = 2x²  (FALSE)",         lambda: st.symbolic_check("diff(x**3, x)", "2*x**2", "x"), False),
    Case("sin²+cos² = 1  (true)",          lambda: st.symbolic_check("sin(x)**2 + cos(x)**2", "1", "x"), True),
    Case("(a+b)² = a²+b²  (FALSE)",        lambda: st.symbolic_check("(a+b)**2", "a**2 + b**2", "a b"), False),
    # --- numeric ---
    Case("π ≈ 3.14159  (true)",            lambda: st.numeric_verify(3.141592653589793, 3.14159, 1e-4, 1e-4), True),
    Case("π ≈ 3.0  (FALSE)",               lambda: st.numeric_verify(3.141592653589793, 3.0, 1e-3, 1e-3), False),
    Case("√2 ≈ 1.41421  (true)",           lambda: st.numeric_verify(2 ** 0.5, 1.41421356, 1e-5, 1e-8), True),
    Case("e ≈ 2.5  (FALSE)",               lambda: st.numeric_verify(2.718281828, 2.5, 1e-3, 1e-3), False),
    # --- units (pint) ---
    Case("g·t is a velocity  (true)",      lambda: st.units_check("9.81 meter/second**2 * 3 second", "meter/second"), True),
    Case("a length is a time  (FALSE)",    lambda: st.units_check("5 meter", "second"), False),
    Case("F=ma is a force  (true)",        lambda: st.units_check("2 kilogram * 3 meter/second**2", "newton"), True),
    Case("energy is a force  (FALSE)",     lambda: st.units_check("5 joule", "newton"), False),
    # --- qubo feasibility ---
    Case("knapsack stays under cap (true)", lambda: st.qubo_solve("knapsack", values=[3, 4, 5, 6], weights=[2, 3, 4, 5], capacity=7), True),
    Case("vertex cover covers edges (true)", lambda: st.qubo_solve("vertex_cover", num_nodes=4, edges=[[0, 1], [1, 2], [2, 3]]), True),
]


def _adjudicate(case: Case) -> tuple[bool, str]:
    """Return (correct, verdict). 'correct' = the tool's verdict matched ground truth."""
    try:
        verdict = json.loads(case.run()).get("verified", "assumed")
    except Exception as exc:  # tool/dep failure → can't adjudicate (counts as a miss)
        return False, f"error:{type(exc).__name__}"
    if case.truth:
        return verdict in PASS_VERDICTS, verdict
    return verdict in FAIL_VERDICTS, verdict


def run_eval() -> dict[str, Any]:
    rows = []
    for c in CASES:
        correct, verdict = _adjudicate(c)
        rows.append({"name": c.name, "truth": c.truth, "verdict": verdict, "correct": correct})
    total = len(rows)
    right = sum(r["correct"] for r in rows)
    caught = sum(1 for r in rows if not r["truth"] and r["correct"])  # false claims rejected
    false_total = sum(1 for r in rows if not r["truth"])
    return {
        "total": total,
        "correct": right,
        "trust_score": round(100 * right / total, 1) if total else 0.0,
        "false_claims_caught": f"{caught}/{false_total}",
        "rows": rows,
    }


def main() -> int:
    r = run_eval()
    print("Emmy verifier eval — does verification catch wrong answers?\n")
    for row in r["rows"]:
        mark = "✓" if row["correct"] else "✗ MISS"
        print(f"  {mark:7} [{row['verdict']:8}] {row['name']}")
    print(f"\nTrust score: {r['correct']}/{r['total']} adjudicated correctly ({r['trust_score']}%)")
    print(f"False claims caught (rejected): {r['false_claims_caught']}")
    return 0 if r["correct"] == r["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
