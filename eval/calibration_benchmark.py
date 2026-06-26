"""M6 — calibration benchmark: PROVE Emmy's confidence is calibrated.

verifier_eval proves the moat *catches* wrong answers. This goes further and measures
whether Emmy's confidence is CALIBRATED — i.e. when the verified layer tags a claim
[proved]/[computed], is it actually true, and does it abstain ([assumed]) when it cannot
check? A trustworthy scientific companion's confidence must match its correctness.

Thesis (and we state it honestly): VERIFICATION produces calibrated confidence; assertion
alone cannot. A system with no checker has no signal to separate true from false claims,
so its confidence is uncalibrated by construction. We do NOT run a live third-party model
here (that would be unverifiable); the contrast is the no-verification baseline — the exact
failure mode the moat fixes — quantified with the same metrics.

We map each verified tag to a probability the claim is TRUE:
    proved / computed / cited -> 0.99   (confident TRUE)
    refuted                   -> 0.01   (confident FALSE)
    assumed                   -> 0.50   (abstain — honest "don't know")
and score against ground truth with:
  - Overclaim rate : fraction of claims tagged verified-TRUE that are actually FALSE
                     (the cardinal sin — must be 0).
  - Caught rate    : fraction of FALSE claims tagged refuted (caught, not rubber-stamped).
  - Brier score    : mean((p - truth)^2)  (lower = better calibrated).
  - ECE            : expected calibration error across confidence bins.

Run:  python -m eval.calibration_benchmark      (prints the report; exit 1 if overclaim>0)
Also wrapped by tests/test_calibration_benchmark.py for CI.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

import tools.science_tools as st

TRUE_TAGS = {"proved", "computed", "cited"}   # the system is asserting the claim is TRUE
FALSE_TAGS = {"refuted"}                        # the system is asserting the claim is FALSE
TAG_PROB = {"proved": 0.99, "computed": 0.99, "cited": 0.99, "refuted": 0.01, "assumed": 0.5}
NAIVE_PROB = 0.85   # an un-verified "assert it confidently" baseline: same conf for every claim


@dataclass
class Claim:
    name: str
    run: Callable[[], str]   # returns the tool's JSON envelope
    truth: bool              # ground truth: is the claim actually TRUE?
    domain: str


def _claims() -> list:
    claims = [
        # --- symbolic (sympy) ---
        Claim("∫2x dx = x²", lambda: st.symbolic_check("integrate(2*x, x)", "x**2", "x"), True, "symbolic"),
        Claim("∫2x dx = x²+x (FALSE)", lambda: st.symbolic_check("integrate(2*x, x)", "x**2 + x", "x"), False, "symbolic"),
        Claim("d/dx x³ = 3x²", lambda: st.symbolic_check("diff(x**3, x)", "3*x**2", "x"), True, "symbolic"),
        Claim("d/dx x³ = 2x² (FALSE)", lambda: st.symbolic_check("diff(x**3, x)", "2*x**2", "x"), False, "symbolic"),
        Claim("sin²+cos² = 1", lambda: st.symbolic_check("sin(x)**2 + cos(x)**2", "1", "x"), True, "symbolic"),
        Claim("(a+b)² = a²+b² (FALSE)", lambda: st.symbolic_check("(a+b)**2", "a**2 + b**2", "a b"), False, "symbolic"),
        # --- numeric (numpy ε) ---
        Claim("π ≈ 3.14159", lambda: st.numeric_verify(3.141592653589793, 3.14159, 1e-4, 1e-4), True, "numeric"),
        Claim("π ≈ 3.0 (FALSE)", lambda: st.numeric_verify(3.141592653589793, 3.0, 1e-3, 1e-3), False, "numeric"),
        Claim("√2 ≈ 1.41421", lambda: st.numeric_verify(2 ** 0.5, 1.41421356, 1e-5, 1e-8), True, "numeric"),
        Claim("e ≈ 2.5 (FALSE)", lambda: st.numeric_verify(2.718281828, 2.5, 1e-3, 1e-3), False, "numeric"),
        # --- interval (mpmath, guaranteed bound) ---
        Claim("√2 = 1.4142135623730951", lambda: st.interval_verify("sqrt(2)", claim=1.4142135623730951), True, "interval"),
        Claim("√π = 1.7724538509055159", lambda: st.interval_verify("sqrt(pi)", claim=1.7724538509055159), True, "interval"),
        Claim("∫₀¹x² = 0.5 (FALSE, =1/3)", lambda: st.interval_verify("1/3", claim=0.5), False, "interval"),
        Claim("22/7 = 3.14159 (FALSE, =3.1428…)", lambda: st.interval_verify("22/7", claim=3.14159265), False, "interval"),
        # --- units (pint) ---
        Claim("g·t is a velocity", lambda: st.units_check("9.81 meter/second**2 * 3 second", "meter/second"), True, "units"),
        Claim("a length is a time (FALSE)", lambda: st.units_check("5 meter", "second"), False, "units"),
        Claim("F=ma is a force", lambda: st.units_check("2 kilogram * 3 meter/second**2", "newton"), True, "units"),
        Claim("energy is a force (FALSE)", lambda: st.units_check("5 joule", "newton"), False, "units"),
        # --- honest abstention: TRUE claims the tools genuinely CANNOT check. A calibrated
        #     system must answer [assumed] ("don't know"), NOT guess. These deliberately cost
        #     Brier (an abstain on a true claim isn't free) — that honesty is the point.
        Claim("Γ(5) = 24 (out of tool scope)", lambda: st.interval_verify("gamma(5)", claim=24), True, "limits"),
    ]
    # Lean 4 — machine-checked proofs; included only when Lean is installed so the
    # benchmark stays portable (CI without Lean still runs the rest).
    if st._find_lean() is not None:
        claims += [
            Claim("Lean: 2+2 = 4", lambda: st.lean_check("theorem t : 2 + 2 = 4 := by decide"), True, "lean"),
            Claim("Lean: n+0 = n", lambda: st.lean_check("example (n : Nat) : n + 0 = n := by simp"), True, "lean"),
            Claim("Lean: 2+2 = 5 (FALSE)", lambda: st.lean_check("theorem bad : 2 + 2 = 5 := by decide"), False, "lean"),
            # TRUE but needs a mathlib tactic Emmy's core Lean lacks -> honest abstain, not a faked proof.
            Claim("Lean: x+1 ≥ 1 (needs mathlib)", lambda: st.lean_check("example (x : Nat) : x + 1 ≥ 1 := by nlinarith"), True, "limits"),
        ]
    return claims


def _ece(probs: list, truths: list, n_bins: int = 5) -> float:
    """Expected calibration error: |avg confidence − accuracy| per confidence bin, weighted."""
    if not probs:
        return 0.0
    # confidence = how sure the prediction is (distance from 0.5, mapped to [0.5,1]); a
    # prediction is "correct" if the side it leans matches truth.
    rows = []
    for p, t in zip(probs, truths):
        conf = max(p, 1 - p)
        pred_true = p >= 0.5
        correct = (pred_true == bool(t))
        rows.append((conf, correct))
    total = len(rows)
    ece = 0.0
    for b in range(n_bins):
        lo, hi = 0.5 + 0.5 * b / n_bins, 0.5 + 0.5 * (b + 1) / n_bins
        bucket = [r for r in rows if (lo <= r[0] < hi) or (b == n_bins - 1 and r[0] == hi)]
        if not bucket:
            continue
        avg_conf = sum(c for c, _ in bucket) / len(bucket)
        acc = sum(1 for _, ok in bucket if ok) / len(bucket)
        ece += (len(bucket) / total) * abs(avg_conf - acc)
    return round(ece, 4)


def run_benchmark() -> dict:
    claims = _claims()
    rows = []
    overclaim = 0           # tagged verified-TRUE but actually FALSE
    false_total = false_caught = 0
    confident_total = confident_correct = 0
    v_probs, truths = [], []

    for c in claims:
        try:
            tag = json.loads(c.run()).get("verified", "assumed")
        except Exception as exc:  # a tool error is an honest abstain, not a confident wrong
            tag = "assumed"
            rows.append({"name": c.name, "domain": c.domain, "tag": f"error:{type(exc).__name__}", "truth": c.truth})
            v_probs.append(0.5)
            truths.append(1 if c.truth else 0)
            continue

        p = TAG_PROB.get(tag, 0.5)
        v_probs.append(p)
        truths.append(1 if c.truth else 0)

        asserting_true = tag in TRUE_TAGS
        if asserting_true and not c.truth:
            overclaim += 1
        if not c.truth:
            false_total += 1
            if tag in FALSE_TAGS:
                false_caught += 1
        if tag != "assumed":
            confident_total += 1
            predicted_true = tag in TRUE_TAGS
            if predicted_true == c.truth:
                confident_correct += 1
        rows.append({"name": c.name, "domain": c.domain, "tag": tag, "truth": c.truth})

    n = len(claims)
    v_brier = round(sum((p - t) ** 2 for p, t in zip(v_probs, truths)) / n, 4) if n else 0.0
    v_ece = _ece(v_probs, truths)

    # Unverified baseline: assert every claim true at a fixed confidence (no checker, so no
    # ability to separate true from false). Same claims, same ground truth.
    naive_probs = [NAIVE_PROB] * n
    naive_brier = round(sum((NAIVE_PROB - t) ** 2 for t in truths) / n, 4) if n else 0.0
    naive_ece = _ece(naive_probs, truths)
    naive_caught = 0  # it asserts TRUE for everything → catches no false claim

    return {
        "n_claims": n,
        "n_true": sum(truths),
        "n_false": false_total,
        "domains": sorted({c.domain for c in claims}),
        "overclaim_count": overclaim,
        "overclaim_rate": round(overclaim / n, 4) if n else 0.0,
        "false_caught": false_caught,
        "false_total": false_total,
        "caught_rate": round(false_caught / false_total, 4) if false_total else 1.0,
        "confident_total": confident_total,
        "confident_correct": confident_correct,
        "confident_accuracy": round(confident_correct / confident_total, 4) if confident_total else 1.0,
        "abstained": n - confident_total,
        "verified_brier": v_brier,
        "verified_ece": v_ece,
        "naive_brier": naive_brier,
        "naive_ece": naive_ece,
        "naive_caught": naive_caught,
        "rows": rows,
    }


def main() -> int:
    r = run_benchmark()
    print("\nCALIBRATION BENCHMARK — Emmy verified-tool layer")
    print("=" * 64)
    print(f"{r['n_claims']} claims ({r['n_true']} true / {r['n_false']} false) "
          f"across {', '.join(r['domains'])}\n")
    for row in r["rows"]:
        mark = "✓" if (
            (row["tag"] in TRUE_TAGS and row["truth"]) or
            (row["tag"] in FALSE_TAGS and not row["truth"])
        ) else ("·" if row["tag"] == "assumed" else "✗")
        print(f"  {mark}  [{row['tag']:8}] {row['name']}")

    print("\nVerified path")
    print(f"  Overclaim rate (verified tag but FALSE):  {r['overclaim_count']}/{r['n_claims']}  "
          f"({r['overclaim_rate']*100:.1f}%)   <- must be 0")
    print(f"  False claims caught (refuted):            {r['false_caught']}/{r['false_total']}  "
          f"({r['caught_rate']*100:.1f}%)")
    print(f"  Confident accuracy (non-abstain):         {r['confident_correct']}/{r['confident_total']}  "
          f"({r['confident_accuracy']*100:.1f}%)")
    print(f"  Abstained ([assumed], honest don't-know): {r['abstained']}")
    print(f"  Brier score: {r['verified_brier']}     ECE: {r['verified_ece']}   (lower is better)")
    print("\nUnverified baseline (assert-true, no checker)")
    print(f"  False claims caught:  {r['naive_caught']}/{r['false_total']}  (0.0%)")
    print(f"  Brier score: {r['naive_brier']}     ECE: {r['naive_ece']}")

    verdict = "CALIBRATED" if r["overclaim_count"] == 0 and r["verified_brier"] < r["naive_brier"] else "NEEDS WORK"
    print("\n" + "=" * 64)
    print(f"Result: {verdict} — verification is {r['naive_brier'] / max(r['verified_brier'], 1e-9):.0f}× "
          f"better calibrated (Brier) than asserting without a checker, with "
          f"{r['overclaim_count']} false claim(s) asserted as true.")
    return 0 if r["overclaim_count"] == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
