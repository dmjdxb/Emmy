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


# --- registration: all six tools land in the registry under the science toolset ---

def test_all_science_tools_registered():
    from tools.registry import registry

    for name in ["symbolic_check", "numeric_verify", "units_check", "qubo_solve",
                 "roofline_classify", "arxiv_search"]:
        entry = registry.get_entry(name)
        assert entry is not None, f"{name} not registered"
        assert entry.toolset == "science"


# --- export_notebook (M4 reproducibility) ---

def test_export_notebook_writes_valid_ipynb(tmp_path):
    import json as _json
    out = tmp_path / "deriv.ipynb"
    d = _v(st.export_notebook(
        "Steady-state derivation",
        [{"type": "markdown", "source": "# Derivation\nWe solve dy/dt=0."},
         {"type": "code", "source": "import sympy as sp\nx=sp.Symbol('x')\nprint(sp.integrate(2*x,x))"}],
        path=str(out),
    ))
    assert d["verified"] == "computed" and d["cells"] == 2
    nb = _json.loads(out.read_text())
    assert nb["nbformat"] == 4 and len(nb["cells"]) == 2
    assert nb["cells"][1]["cell_type"] == "code" and nb["cells"][1]["execution_count"] is None
