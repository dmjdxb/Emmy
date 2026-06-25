"""CI wrapper for the M5 verifier eval — the verification must catch every wrong answer."""
import pytest

# All cases need at least one optional dep (sympy/pint/dimod); skip cleanly if absent.
pytest.importorskip("sympy")
pytest.importorskip("pint")
pytest.importorskip("dimod")

from eval.verifier_eval import run_eval


def test_verifier_adjudicates_every_case_correctly():
    r = run_eval()
    misses = [row["name"] for row in r["rows"] if not row["correct"]]
    assert not misses, f"verifier mis-adjudicated: {misses}"
    assert r["trust_score"] == 100.0


def test_every_false_claim_is_refuted():
    r = run_eval()
    false_rows = [row for row in r["rows"] if not row["truth"]]
    assert false_rows, "eval must include false claims to be meaningful"
    for row in false_rows:
        assert row["correct"], f"FALSE claim not caught: {row['name']} (verdict={row['verdict']})"
