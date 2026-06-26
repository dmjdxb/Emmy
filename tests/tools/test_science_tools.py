"""Tests for Emmy's verified scientific tools (the moat).

Each test asserts the `verified` tag is correct — the whole point is that the tools
never label an unproven/false claim as proved. Optional-dep tools skip cleanly when
their backend isn't installed (CI installs the [science]+[qubo] extras).
"""
import json

import pytest

import tools.science_tools as st


def _v(out):
    return json.loads(out)


# --- roofline + numeric: no optional deps beyond numpy (always in [science]) ---

def test_roofline_compute_bound():
    d = _v(st.roofline_classify(2e12, 5e8, "cpu"))
    assert d["verified"] == "computed"
    assert d["bound"] == "compute-bound"
    assert d["energy_j"] > 0


def test_roofline_memory_bound():
    d = _v(st.roofline_classify(1e6, 1e9, "cpu"))
    assert d["bound"] == "memory-bound"


def test_numeric_verify_pass_and_fail():
    np = pytest.importorskip("numpy")  # noqa: F841
    assert _v(st.numeric_verify([1.0, 2.0], [1.0000001, 2.0], 1e-5, 1e-8))["verified"] == "computed"
    bad = _v(st.numeric_verify(3.14, 3.20, 1e-3, 1e-3))
    assert bad["verified"] == "refuted" and bad["passed"] is False


# --- symbolic_check (sympy) ---

def test_symbolic_check_true_and_false():
    pytest.importorskip("sympy")
    assert _v(st.symbolic_check("integrate(2*x, x)", "x**2", "x"))["verified"] == "proved"
    refuted = _v(st.symbolic_check("diff(x**3, x)", "2*x**2", "x"))
    assert refuted["verified"] == "refuted"  # the tool must CATCH the wrong claim


def test_symbolic_check_identity():
    pytest.importorskip("sympy")
    assert _v(st.symbolic_check("sin(x)**2 + cos(x)**2", "1", "x"))["verified"] == "proved"


# --- units_check (pint) ---

def test_units_check_consistent_and_mismatch():
    pytest.importorskip("pint")
    ok = _v(st.units_check("9.81 meter/second**2 * 3 second", "meter/second"))
    assert ok["verified"] == "proved"
    bad = _v(st.units_check("5 meter", "second"))
    assert bad["verified"] == "refuted"


# --- qubo_solve (dimod) — verify FEASIBILITY, not just low energy ---

def test_qubo_knapsack_feasible():
    pytest.importorskip("dimod")
    d = _v(st.qubo_solve("knapsack", values=[3, 4, 5, 6], weights=[2, 3, 4, 5], capacity=7))
    assert d["verified"] == "proved"
    assert d["feasible"] is True
    assert d["weight"] <= 7 + 1e-9


def test_qubo_vertex_cover_covers_all_edges():
    pytest.importorskip("dimod")
    d = _v(st.qubo_solve("vertex_cover", num_nodes=4, edges=[[0, 1], [1, 2], [2, 3]]))
    assert d["verified"] == "proved"
    assert d["uncovered"] == []


def test_qubo_set_cover():
    pytest.importorskip("dimod")
    d = _v(st.qubo_solve("set_cover", universe_size=4, subsets=[[0, 1], [1, 2], [2, 3], [3, 0]]))
    assert d["verified"] == "proved" and d["feasible"] is True


# --- interval_verify (mpmath) — RIGOROUS numerics with a guaranteed bound ---

def test_interval_verify_encloses_constant():
    pytest.importorskip("mpmath")
    d = _v(st.interval_verify("pi/4"))
    assert d["verified"] == "computed"
    assert d["low"] <= 0.7853981633974483 <= d["high"]  # true pi/4 inside the proven bracket


def test_interval_verify_accepts_correct_float64_claim():
    # A correctly-computed float64 value must pass (not be refused for lacking 30 digits).
    pytest.importorskip("mpmath")
    assert _v(st.interval_verify("sqrt(2)", claim=1.4142135623730951))["verified"] == "computed"
    assert _v(st.interval_verify("sqrt(pi)", claim=1.7724538509055159))["passed"] is True


def test_interval_verify_refutes_wrong_claim():
    # The headline guarantee: a provably-wrong value is REFUTED, not waved through.
    pytest.importorskip("mpmath")
    bad = _v(st.interval_verify("sqrt(2)", claim=1.41))
    assert bad["verified"] == "refuted" and bad["passed"] is False
    # ∫₀¹ x² = 1/3, not 0.5 — the classic wrong answer must be caught.
    assert _v(st.interval_verify("1/3", claim=0.5))["verified"] == "refuted"


def test_interval_verify_width_below_float64():
    pytest.importorskip("mpmath")
    d = _v(st.interval_verify("exp(1)", dps=40))
    assert d["verified"] == "computed" and 0 <= d["width"] < 1e-25  # honest sub-float64 enclosure


# --- stats_test (scipy) — assumption-aware, effect sizes, anti-p-hacking ---

def test_stats_ttest_reports_effect_and_ci():
    pytest.importorskip("scipy")
    d = _v(st.stats_test("ttest", a=[5.1, 4.9, 5.0, 5.2, 4.8], b=[6.0, 6.1, 5.9, 6.2, 5.8]))
    assert d["verified"] == "computed"
    assert d["significant"] is True
    assert "cohens_d" in d and abs(d["cohens_d"]) > 0.8  # large effect
    assert len(d["ci95"]) == 2 and d["ci95"][0] < d["ci95"][1]


def test_stats_ttest_flags_trivial_effect_at_significance():
    # Significant p but negligible effect (huge n) must be warned about — anti-p-hacking.
    pytest.importorskip("scipy")
    import numpy as np  # noqa: F401
    a = [0.0] * 200 + [1.0] * 200
    b = [0.0] * 195 + [1.0] * 205
    d = _v(st.stats_test("ttest", a=a, b=b))
    assert d["verified"] == "computed"
    assert any("CI includes zero" in w or "negligible" in w for w in d["warnings"])


def test_stats_anova_reports_eta_squared():
    pytest.importorskip("scipy")
    d = _v(st.stats_test("anova", groups=[[1, 2, 3, 2], [4, 5, 6, 5], [7, 8, 9, 8]]))
    assert d["verified"] == "computed" and d["eta_squared"] > 0.1


def test_stats_multiple_comparison_correction():
    # Four "significant" p-values, but after FDR correction the inflated count must drop.
    pytest.importorskip("scipy")
    d = _v(st.stats_test("correct", pvalues=[0.01, 0.04, 0.03, 0.045, 0.2], method="bh"))
    assert d["verified"] == "computed"
    assert d["n_significant"] < 4  # uncorrected naive count was inflated
    assert d["warnings"]


def test_stats_normality():
    pytest.importorskip("scipy")
    d = _v(st.stats_test("normality", data=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]))
    assert d["verified"] == "computed" and "normal" in d


# --- verifiable citations: source detection + passage matching (no network) ---

def test_cite_source_detection():
    assert st._detect_source("1706.03762") == ("arxiv", "1706.03762")
    assert st._detect_source("arXiv:1706.03762") == ("arxiv", "1706.03762")
    assert st._detect_source("10.1038/nature14539") == ("doi", "10.1038/nature14539")
    assert st._detect_source("doi:10.1038/nature14539") == ("doi", "10.1038/nature14539")
    assert st._detect_source("33495535") == ("pmid", "33495535")
    assert st._detect_source("transformer attention models") == ("query", "transformer attention models")


def test_cite_best_passage_ranks_supporting_sentence():
    passage, score = st._best_passage(
        "transformers use self-attention for sequence modeling",
        "Intro sentence about widgets. The Transformer uses self-attention to relate sequence positions.",
    )
    assert score >= 0.5 and "self-attention" in passage


def test_cite_best_passage_zero_for_unrelated():
    _, score = st._best_passage("photosynthesis in plants", "Quantum chromodynamics and gluon fields.")
    assert score == 0.0


def test_cite_check_requires_both_args():
    assert _v(st.cite_check("", "1706.03762"))["verified"] == "assumed"  # _err envelope


# --- live citation checks (network) — skip cleanly when offline/rate-limited ---

def _online(fn):
    try:
        return fn()
    except Exception:
        pytest.skip("network unavailable")


def test_cite_check_verifies_real_source_live():
    out = _online(lambda: st.cite_check("The Transformer relies entirely on attention mechanisms", "1706.03762"))
    d = _v(out)
    if not d.get("found"):
        pytest.skip("arXiv unreachable")
    assert d["verified"] == "cited" and d["support_score"] >= 0.34
    assert "arXiv" in (d["citation"] or "") or "1706.03762" in (d["citation"] or "")


def test_cite_check_refutes_fabricated_source_live():
    d = _v(_online(lambda: st.cite_check("Cats photosynthesize", "2999.99999")))
    assert d["verified"] == "refuted" and d["found"] is False


# --- registration: all tools land in the registry under the science toolset ---

def test_all_science_tools_registered():
    from tools.registry import registry

    for name in ["symbolic_check", "numeric_verify", "interval_verify", "stats_test",
                 "units_check", "qubo_solve", "roofline_classify", "arxiv_search",
                 "literature_search", "cite_check"]:
        entry = registry.get_entry(name)
        assert entry is not None, f"{name} not registered"
        assert entry.toolset == "science"


# --- export_notebook (M4 reproducibility) ---

def test_export_notebook_executes_and_embeds_output(tmp_path):
    pytest.importorskip("sympy")
    import json as _json
    out = tmp_path / "deriv.ipynb"
    d = _v(st.export_notebook(
        "Steady-state derivation",
        [{"type": "markdown", "source": "# Derivation"},
         {"type": "code", "source": "import sympy as sp\nx=sp.Symbol('x')\nprint(sp.integrate(2*x,x))"}],
        path=str(out),
    ))
    assert d["verified"] == "computed" and d["executed"] is True and d["errors"] == []
    nb = _json.loads(out.read_text())
    assert nb["nbformat"] == 4 and len(nb["cells"]) == 2
    code = nb["cells"][1]
    assert code["cell_type"] == "code" and code["execution_count"] == 1  # executed in-process
    streams = [o for o in code["outputs"] if o["output_type"] == "stream"]
    assert streams and "x**2" in "".join(streams[0]["text"])  # print output embedded


def test_export_notebook_embeds_matplotlib_figure(tmp_path):
    pytest.importorskip("matplotlib")
    import json as _json
    out = tmp_path / "plot.ipynb"
    st.export_notebook(
        "Plot",
        [{"type": "code", "source": "import matplotlib.pyplot as plt\nplt.plot([0,1,2],[0,1,4])"}],
        path=str(out),
    )
    nb = _json.loads(out.read_text())
    outs = nb["cells"][0]["outputs"]
    assert any(o["output_type"] == "display_data" and "image/png" in o.get("data", {}) for o in outs)


def test_export_notebook_surfaces_cell_errors(tmp_path):
    out = tmp_path / "bad.ipynb"
    d = _v(st.export_notebook("Bad", [{"type": "code", "source": "1/0"}], path=str(out)))
    assert d["errors"] and "ZeroDivisionError" in d["errors"][0]


def test_export_notebook_code_only_when_execute_false(tmp_path):
    import json as _json
    out = tmp_path / "raw.ipynb"
    d = _v(st.export_notebook("Raw", [{"type": "code", "source": "print(1)"}], path=str(out), execute=False))
    nb = _json.loads(out.read_text())
    assert nb["cells"][0]["execution_count"] is None and d["executed"] is False
