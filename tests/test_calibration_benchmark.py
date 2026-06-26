"""CI wrapper for the calibration benchmark (eval/calibration_benchmark.py).

Asserts the calibration guarantees hold: the verified layer NEVER asserts a false claim
as true (overclaim = 0), catches every false claim, is correct whenever it commits, and is
far better calibrated (Brier) than asserting without a checker. Portable — Lean cases are
included only when Lean is installed; the offline set still proves every guarantee.
"""
from eval.calibration_benchmark import run_benchmark


def test_calibration_guarantees():
    r = run_benchmark()

    # The cardinal guarantee: a verified tag ([proved]/[computed]/[cited]) is NEVER attached
    # to a false claim. This is the whole moat — confidence must not be misplaced.
    assert r["overclaim_count"] == 0, [row for row in r["rows"] if row["tag"] in {"proved", "computed", "cited"} and not row["truth"]]

    # Every false claim is caught (refuted), not rubber-stamped.
    assert r["caught_rate"] == 1.0, r["rows"]

    # When the system COMMITS (doesn't abstain), it is right.
    assert r["confident_accuracy"] == 1.0

    # It actually abstains on things it cannot check (honest "don't know"), not guesses.
    assert r["abstained"] >= 1

    # Calibration: far better than the no-checker baseline, and well-calibrated in absolute terms.
    assert r["verified_brier"] < r["naive_brier"]
    assert r["verified_brier"] < 0.1
    assert r["naive_caught"] == 0  # the contrast: assertion-without-verification catches nothing


def test_benchmark_has_balanced_battery():
    r = run_benchmark()
    assert r["n_claims"] >= 15
    assert r["n_false"] >= 5 and r["n_true"] >= 5  # a meaningful mix of true and false claims
