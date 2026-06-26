"""Emmy's verified scientific tools — the "prove every claim" surface.

Each tool returns a JSON result carrying a ``verified`` tag — one of:
  - "proved"    : established symbolically / by exhaustive feasibility check
  - "computed"  : produced by a numerical routine (deterministic, reproducible)
  - "cited"     : sourced from a named external reference
  - "refuted"   : the claim was checked and is FALSE
  - "assumed"   : could not verify; treat as an unproven premise

The agent (and the UI claim-badges) use this tag so a result is never presented as
"proved" when it was only "assumed". Verification logic mirrors the EnergyIR engines
(numeric ε-gate, QUBO feasibility verifier, roofline classifier) — reimplemented here
self-contained so Emmy has no cross-repo dependency.

Optional deps are gated per-tool via check_fn (graceful "unavailable" when missing):
sympy (symbolic_check), pint (units_check), dimod+openjij (qubo_solve). numpy ships in
the [science] bundle; roofline_classify and arxiv_search need no extra deps.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any


def _result(verified: str, summary: str, **data: Any) -> str:
    """Uniform JSON envelope. `verified` ∈ proved|computed|cited|refuted|assumed."""
    return json.dumps({"verified": verified, "summary": summary, **data}, default=str)


def _err(msg: str) -> str:
    return json.dumps({"verified": "assumed", "error": msg, "summary": f"could not verify: {msg}"})


def _have(mod: str) -> bool:
    import importlib.util

    return importlib.util.find_spec(mod) is not None


# ---------------------------------------------------------------------------
# symbolic_check — prove (or refute) an algebraic/calculus equality with sympy
# ---------------------------------------------------------------------------

SYMBOLIC_CHECK_SCHEMA = {
    "name": "symbolic_check",
    "description": (
        "Independently verify a mathematical claim by symbolic computation (sympy). "
        "Give two expressions; the tool proves whether they are mathematically equal "
        "(simplifies lhs - rhs to zero), so you can confirm a derivation, integral, "
        "derivative, or algebraic simplification rather than asserting it. Use standard "
        "math syntax: 'sin(x)**2 + cos(x)**2', 'integrate(2*x, x)', 'diff(x**3, x)', "
        "'Sum(k, (k, 1, n)).doit()'. Returns verified=proved if equal, refuted if not."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "lhs": {"type": "string", "description": "Left expression (your result/derivation)."},
            "rhs": {"type": "string", "description": "Right expression (what it should equal)."},
            "symbols": {
                "type": "string",
                "description": "Optional space-separated variable names to declare (e.g. 'x y n'). Defaults to auto.",
            },
        },
        "required": ["lhs", "rhs"],
    },
}


def symbolic_check(lhs: str, rhs: str, symbols: str = "") -> str:
    try:
        import sympy as sp
        from sympy.parsing.sympy_parser import parse_expr
    except Exception:
        return _err("sympy not available")
    local: dict[str, Any] = {}
    try:
        if symbols.strip():
            for name in symbols.split():
                local[name] = sp.Symbol(name)
        a = parse_expr(lhs, local_dict=local, evaluate=True)
        b = parse_expr(rhs, local_dict=local, evaluate=True)
    except Exception as exc:
        return _err(f"parse error: {type(exc).__name__}: {exc}")
    try:
        diff = sp.simplify(a - b)
        equal = diff == 0 or sp.simplify(diff) == 0
    except Exception as exc:
        return _err(f"simplify error: {type(exc).__name__}: {exc}")
    if equal:
        return _result("proved", f"{lhs} = {rhs} (symbolically verified)", lhs=str(a), rhs=str(b), equal=True)
    return _result(
        "refuted",
        f"{lhs} ≠ {rhs}; difference simplifies to {diff} (NOT zero)",
        lhs=str(a), rhs=str(b), difference=str(diff), equal=False,
    )


# ---------------------------------------------------------------------------
# numeric_verify — ε-equivalence of two numeric results (mirrors NumericGate)
# ---------------------------------------------------------------------------

NUMERIC_VERIFY_SCHEMA = {
    "name": "numeric_verify",
    "description": (
        "Verify that a numeric result matches a reference within tolerance "
        "(|a - b| <= atol + rtol*|b|, elementwise) — the standard way to confirm a "
        "computation against an analytical value, a known case, or a second method. "
        "Accepts scalars or equal-length lists. Returns verified=computed if within "
        "tolerance, refuted otherwise, with the worst deviation."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "actual": {"type": ["number", "array"], "items": {"type": "number"}, "description": "Your computed value(s)."},
            "expected": {"type": ["number", "array"], "items": {"type": "number"}, "description": "Reference value(s)."},
            "rtol": {"type": "number", "description": "Relative tolerance (default 1e-6)."},
            "atol": {"type": "number", "description": "Absolute tolerance (default 1e-9)."},
        },
        "required": ["actual", "expected"],
    },
}


def numeric_verify(actual: Any, expected: Any, rtol: float = 1e-6, atol: float = 1e-9) -> str:
    try:
        import numpy as np
    except Exception:
        return _err("numpy not available")
    try:
        a = np.asarray(actual, dtype=float)
        b = np.asarray(expected, dtype=float)
        if a.shape != b.shape:
            return _err(f"shape mismatch: {a.shape} vs {b.shape}")
        absdiff = np.abs(a - b)
        thresh = atol + rtol * np.abs(b)
        ok = bool(np.all(absdiff <= thresh))
        worst = float(np.max(absdiff)) if absdiff.size else 0.0
    except Exception as exc:
        return _err(f"{type(exc).__name__}: {exc}")
    if ok:
        return _result("computed", f"match within tol (max |Δ|={worst:.3e}, rtol={rtol}, atol={atol})",
                       max_abs_diff=worst, passed=True)
    return _result("refuted", f"MISMATCH beyond tol (max |Δ|={worst:.3e} > rtol={rtol}/atol={atol})",
                   max_abs_diff=worst, passed=False)


# ---------------------------------------------------------------------------
# units_check — dimensional analysis with pint
# ---------------------------------------------------------------------------

UNITS_CHECK_SCHEMA = {
    "name": "units_check",
    "description": (
        "Check the dimensional consistency of a physical expression and (optionally) that "
        "it reduces to an expected unit — catches unit/dimension errors before they reach a "
        "result. Example: expression='9.81 meter/second**2 * 3 second', expected_unit='meter/second'. "
        "Returns the evaluated quantity + base dimensions; verified=proved if it parses and "
        "(if given) matches expected_unit's dimensionality, refuted on a dimensional mismatch."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "expression": {"type": "string", "description": "Physical expression with pint units (use full unit names or symbols)."},
            "expected_unit": {"type": "string", "description": "Optional unit the result should reduce to (dimensionality is compared)."},
        },
        "required": ["expression"],
    },
}


def units_check(expression: str, expected_unit: str = "") -> str:
    try:
        import pint
    except Exception:
        return _err("pint not available")
    ureg = pint.UnitRegistry()
    try:
        q = ureg.parse_expression(expression)
    except Exception as exc:
        return _err(f"parse error: {type(exc).__name__}: {exc}")
    try:
        base = q.to_base_units()
        dim = str(getattr(q, "dimensionality", ""))
    except Exception as exc:
        return _err(f"dimensional error: {type(exc).__name__}: {exc}")
    if expected_unit.strip():
        try:
            exp_q = ureg.parse_expression(expected_unit)
            if q.dimensionality != exp_q.dimensionality:
                return _result(
                    "refuted",
                    f"dimension mismatch: expression is [{q.dimensionality}], expected [{exp_q.dimensionality}]",
                    value=str(q), dimensionality=dim, expected=expected_unit, passed=False,
                )
            converted = q.to(exp_q.units)
            return _result("proved", f"{expression} = {converted} (dimensionally consistent with {expected_unit})",
                           value=str(converted), dimensionality=dim, passed=True)
        except Exception as exc:
            return _err(f"{type(exc).__name__}: {exc}")
    return _result("proved", f"{expression} = {q} (parsed; dimensions [{dim}])",
                   value=str(q), base_units=str(base), dimensionality=dim, passed=True)


# ---------------------------------------------------------------------------
# qubo_solve — build a QUBO for a discrete optimization problem, solve, and
# VERIFY feasibility against the original constraints (mirrors EnergyIR's verify gate)
# ---------------------------------------------------------------------------

QUBO_SOLVE_SCHEMA = {
    "name": "qubo_solve",
    "description": (
        "Solve a small discrete optimization problem by formulating it as a QUBO and "
        "checking the solution is feasible against the original constraints (not just "
        "low-energy). Supported problem types: 'knapsack' (maximize value s.t. weight<=capacity), "
        "'vertex_cover' (min nodes covering all edges), 'set_cover' (min subsets covering the universe). "
        "Returns the objective + assignment with verified=proved when the solution is confirmed feasible."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "problem": {"type": "string", "enum": ["knapsack", "vertex_cover", "set_cover"]},
            "values": {"type": "array", "items": {"type": "number"}, "description": "knapsack: item values."},
            "weights": {"type": "array", "items": {"type": "number"}, "description": "knapsack: item weights."},
            "capacity": {"type": "number", "description": "knapsack: weight capacity."},
            "num_nodes": {"type": "integer", "description": "vertex_cover: node count."},
            "edges": {"type": "array", "items": {"type": "array", "items": {"type": "integer"}}, "description": "vertex_cover: list of [u,v] edges."},
            "universe_size": {"type": "integer", "description": "set_cover: size of the universe (elements 0..N-1)."},
            "subsets": {"type": "array", "items": {"type": "array", "items": {"type": "integer"}}, "description": "set_cover: list of subsets (each a list of element indices)."},
        },
        "required": ["problem"],
    },
}


def _solve_bqm(bqm, n_vars: int):
    """ExactSolver for small problems (provably optimal); openjij SA for larger."""
    import dimod

    if n_vars <= 18:
        ss = dimod.ExactSolver().sample(bqm)
        return ss.first.sample, "exact"
    try:
        import openjij as oj

        ss = oj.SASampler().sample(bqm, num_reads=200)
        return ss.first.sample, "annealing"
    except Exception:
        ss = dimod.SimulatedAnnealingSampler().sample(bqm, num_reads=200)
        return ss.first.sample, "annealing"


def qubo_solve(problem: str, **kw: Any) -> str:
    if not _have("dimod"):
        return _err("dimod/openjij not available (QUBO backend)")
    import dimod

    try:
        if problem == "knapsack":
            values = list(kw.get("values") or [])
            weights = list(kw.get("weights") or [])
            capacity = float(kw.get("capacity", 0))
            n = len(values)
            if n == 0 or len(weights) != n:
                return _err("knapsack needs equal-length values and weights")
            # maximize Σ v_i x_i  s.t. Σ w_i x_i <= capacity. Penalty on overflow.
            P = (max(values) + 1) * 10.0
            bqm = dimod.BinaryQuadraticModel("BINARY")
            for i in range(n):
                bqm.add_variable(i, -values[i])
            # soft penalty: P * max(0, Σ w_i x_i - capacity) approximated quadratically
            for i in range(n):
                bqm.add_linear(i, P * weights[i] * (weights[i] - 2 * capacity) / max(capacity, 1))
                for j in range(i + 1, n):
                    bqm.add_quadratic(i, j, 2 * P * weights[i] * weights[j] / max(capacity, 1))
            sample, method = _solve_bqm(bqm, n)
            chosen = [i for i in range(n) if sample.get(i, 0) == 1]
            tot_w = sum(weights[i] for i in chosen)
            tot_v = sum(values[i] for i in chosen)
            feasible = tot_w <= capacity + 1e-9
            verdict = "proved" if feasible else "refuted"
            return _result(verdict, f"knapsack ({method}): value={tot_v}, weight={tot_w}/{capacity}, feasible={feasible}",
                           objective=tot_v, selection=chosen, weight=tot_w, capacity=capacity, feasible=feasible)

        if problem == "vertex_cover":
            n = int(kw.get("num_nodes", 0))
            edges = [tuple(e) for e in (kw.get("edges") or [])]
            if n == 0:
                return _err("vertex_cover needs num_nodes")
            P = float(n + 1)
            bqm = dimod.BinaryQuadraticModel("BINARY")
            for i in range(n):
                bqm.add_variable(i, 1.0)  # minimize count
            for (u, v) in edges:  # penalty unless x_u + x_v >= 1: P*(1 - x_u - x_v + x_u x_v)
                bqm.add_linear(u, -P); bqm.add_linear(v, -P); bqm.add_quadratic(u, v, P); bqm.offset += P
            sample, method = _solve_bqm(bqm, n)
            cover = [i for i in range(n) if sample.get(i, 0) == 1]
            uncovered = [(u, v) for (u, v) in edges if u not in cover and v not in cover]
            feasible = not uncovered
            verdict = "proved" if feasible else "refuted"
            return _result(verdict, f"vertex_cover ({method}): |cover|={len(cover)}, uncovered_edges={len(uncovered)}",
                           objective=len(cover), cover=cover, feasible=feasible, uncovered=uncovered)

        if problem == "set_cover":
            usize = int(kw.get("universe_size", 0))
            subsets = [list(s) for s in (kw.get("subsets") or [])]
            m = len(subsets)
            if usize == 0 or m == 0:
                return _err("set_cover needs universe_size and subsets")
            P = float(m + 1)
            bqm = dimod.BinaryQuadraticModel("BINARY")
            for j in range(m):
                bqm.add_variable(j, 1.0)  # minimize chosen subsets
            for e in range(usize):  # each element must be covered: penalty if Σ_{j∋e} x_j < 1
                covering = [j for j in range(m) if e in subsets[j]]
                if not covering:
                    return _err(f"element {e} is in no subset — infeasible")
                for j in covering:
                    bqm.add_linear(j, -P)
                for a in range(len(covering)):
                    for b in range(a + 1, len(covering)):
                        bqm.add_quadratic(covering[a], covering[b], P)
                bqm.offset += P
            sample, method = _solve_bqm(bqm, m)
            chosen = [j for j in range(m) if sample.get(j, 0) == 1]
            covered = set().union(*[set(subsets[j]) for j in chosen]) if chosen else set()
            feasible = covered >= set(range(usize))
            verdict = "proved" if feasible else "refuted"
            return _result(verdict, f"set_cover ({method}): |chosen|={len(chosen)}, covers_universe={feasible}",
                           objective=len(chosen), chosen=chosen, feasible=feasible)

        return _err(f"unknown problem '{problem}'")
    except Exception as exc:
        return _err(f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# roofline_classify — compute-vs-memory bound + energy estimate (EnergyIR model)
# ---------------------------------------------------------------------------

ROOFLINE_SCHEMA = {
    "name": "roofline_classify",
    "description": (
        "Classify a workload as compute-bound or memory-bound from its FLOPs and bytes moved, "
        "and estimate energy from a measured roofline model. Useful for reasoning about whether "
        "an algorithm is limited by arithmetic or by data movement. Returns arithmetic intensity, "
        "the bound, and an energy estimate (verified=computed)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "flops": {"type": "number", "description": "Floating-point operations."},
            "nbytes": {"type": "number", "description": "Bytes moved to/from memory."},
            "device": {"type": "string", "enum": ["cpu", "gpu"], "description": "Energy model (default cpu)."},
        },
        "required": ["flops", "nbytes"],
    },
}

# Measured reference constants (EnergyIR roofline model).
_ROOFLINE = {
    "cpu": {"e_flop": 2.54e-10, "e_byte": 5.91e-11},
    "gpu": {"e_flop": 3.526e-12, "e_byte": 1.0e-12},
}


def roofline_classify(flops: float, nbytes: float, device: str = "cpu") -> str:
    m = _ROOFLINE.get(device, _ROOFLINE["cpu"])
    if nbytes <= 0:
        return _err("nbytes must be > 0")
    intensity = flops / nbytes
    crossover = m["e_byte"] / m["e_flop"]  # intensity where flop/byte energy balance
    e_flop = m["e_flop"] * flops
    e_byte = m["e_byte"] * nbytes
    energy = e_flop + e_byte
    bound = "compute-bound" if intensity > crossover else "memory-bound"
    return _result(
        "computed",
        f"{bound} on {device}: intensity {intensity:.3g} (crossover {crossover:.3g}); est. energy {energy:.3e} J",
        intensity=intensity, crossover=crossover, bound=bound, energy_j=energy,
        e_flop_j=e_flop, e_byte_j=e_byte, device=device,
    )


# ---------------------------------------------------------------------------
# arxiv_search — real literature citations (arXiv API, no key)
# ---------------------------------------------------------------------------

ARXIV_SCHEMA = {
    "name": "arxiv_search",
    "description": (
        "Search arXiv for papers to cite (real sources, no fabrication). Returns titles, authors, "
        "arXiv IDs, links, and abstracts for the top matches. Use when a claim needs a citation or "
        "the user wants relevant literature. Results are verified=cited (real published references)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query (keywords, title, or author)."},
            "max_results": {"type": "integer", "description": "How many papers (default 5, max 20)."},
        },
        "required": ["query"],
    },
}

_ATOM = "{http://www.w3.org/2005/Atom}"


def arxiv_search(query: str, max_results: int = 5) -> str:
    n = max(1, min(20, int(max_results or 5)))
    url = "http://export.arxiv.org/api/query?" + urllib.parse.urlencode(
        {"search_query": f"all:{query}", "start": 0, "max_results": n}
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Emmy/arxiv-search"})
        with urllib.request.urlopen(req, timeout=20) as r:
            root = ET.fromstring(r.read())
    except Exception as exc:
        return _err(f"arxiv fetch failed: {type(exc).__name__}: {exc}")
    papers = []
    for entry in root.findall(f"{_ATOM}entry"):
        title = (entry.findtext(f"{_ATOM}title") or "").strip().replace("\n", " ")
        link = (entry.findtext(f"{_ATOM}id") or "").strip()
        summary = (entry.findtext(f"{_ATOM}summary") or "").strip().replace("\n", " ")
        authors = [a.findtext(f"{_ATOM}name") for a in entry.findall(f"{_ATOM}author")]
        papers.append({
            "title": title,
            "authors": [a for a in authors if a][:8],
            "arxiv_id": link.rsplit("/", 1)[-1],
            "link": link,
            "abstract": summary[:500],
        })
    if not papers:
        return _result("cited", f"no arXiv results for '{query}'", papers=[])
    return _result("cited", f"{len(papers)} arXiv papers for '{query}'", papers=papers)


# ---------------------------------------------------------------------------
# export_notebook — reproducible research artifact (a rerunnable Jupyter .ipynb)
# ---------------------------------------------------------------------------

EXPORT_NOTEBOOK_SCHEMA = {
    "name": "export_notebook",
    "description": (
        "Export the work as a Jupyter notebook (.ipynb) AND execute it — runs every code cell in your "
        "OWN bundled environment (numpy/scipy/pandas/matplotlib are already installed) and embeds the "
        "outputs (printed text, results, and matplotlib figures as inline images) directly in the "
        "notebook, so it opens already-run and reproduces anywhere. This is the ONE step for delivering a "
        "notebook — do NOT use jupyter / nbconvert / ipykernel / kernel registration (they point at a "
        "different Python that lacks the scientific stack). Provide ordered cells (markdown for "
        "explanation, code for computation). Returns the saved file path (it appears in the artifacts "
        "panel) plus any cell errors so you can fix and re-export."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Notebook title (also the default filename)."},
            "cells": {
                "type": "array",
                "description": "Ordered cells. Code cells share one namespace top-to-bottom (like a real notebook).",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["markdown", "code"]},
                        "source": {"type": "string", "description": "Cell content."},
                    },
                    "required": ["type", "source"],
                },
            },
            "path": {"type": "string", "description": "Optional output path; defaults to <title>.ipynb in the cwd."},
            "execute": {
                "type": "boolean",
                "description": "Run the code cells in Emmy's environment and embed outputs/figures (default true). "
                               "Set false only to write code-only cells without running them.",
            },
        },
        "required": ["title", "cells"],
    },
}


def _execute_notebook_cells(nb_cells: list) -> list:
    """Run code cells in-process (Emmy's venv HAS numpy/scipy/pandas/matplotlib) and embed
    their outputs — stdout as a stream, matplotlib figures as inline PNGs, exceptions as error
    outputs. Cells share one namespace top-to-bottom, like a real notebook. Returns the list of
    per-cell error strings (empty when everything ran clean). No Jupyter/nbconvert involved."""
    import base64
    import contextlib
    import io
    import traceback as _tb

    try:
        import matplotlib

        matplotlib.use("Agg")  # headless: figures captured, never displayed
        import matplotlib.pyplot as plt

        have_mpl = True
    except Exception:
        have_mpl = False

    ns: dict = {"__name__": "__main__"}
    errors: list = []
    n = 0
    for cell in nb_cells:
        if cell.get("cell_type") != "code":
            continue
        n += 1
        cell["execution_count"] = n
        src = "".join(cell.get("source", []))
        outputs: list = []
        buf = io.StringIO()
        if have_mpl:
            plt.close("all")
        try:
            with contextlib.redirect_stdout(buf):
                exec(compile(src, f"<cell {n}>", "exec"), ns)  # noqa: S102 — agent's own analysis code
        except Exception as exc:
            outputs.append({
                "output_type": "error",
                "ename": type(exc).__name__,
                "evalue": str(exc),
                "traceback": _tb.format_exc().splitlines(),
            })
            errors.append(f"cell {n}: {type(exc).__name__}: {exc}")
        text = buf.getvalue()
        if text:
            outputs.append({"output_type": "stream", "name": "stdout", "text": text.splitlines(keepends=True)})
        if have_mpl:
            for fignum in plt.get_fignums():
                try:
                    imgbuf = io.BytesIO()
                    plt.figure(fignum).savefig(imgbuf, format="png", bbox_inches="tight", dpi=110)
                    outputs.append({
                        "output_type": "display_data",
                        "data": {"image/png": base64.b64encode(imgbuf.getvalue()).decode("ascii")},
                        "metadata": {},
                    })
                except Exception:
                    pass
            plt.close("all")
        cell["outputs"] = outputs
    return errors


def export_notebook(title: str, cells: list, path: str = "", execute: bool = True) -> str:
    import os
    import re

    def _nb_cell(c):
        ctype = "code" if c.get("type") == "code" else "markdown"
        src = str(c.get("source", ""))
        cell = {"cell_type": ctype, "metadata": {}, "source": src.splitlines(keepends=True)}
        if ctype == "code":
            cell["outputs"] = []
            cell["execution_count"] = None
        return cell

    nb_cells = [_nb_cell(c) for c in (cells or [])]
    errors: list = []
    if execute:
        try:
            errors = _execute_notebook_cells(nb_cells)
        except Exception as exc:
            errors = [f"execution harness error: {type(exc).__name__}: {exc}"]

    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
            "title": title,
            "generated_by": "Emmy (EnergyIR)",
        },
        "cells": nb_cells,
    }
    if not path.strip():
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", title).strip("_") or "emmy_notebook"
        path = f"{safe}.ipynb"
    try:
        path = os.path.abspath(os.path.expanduser(path))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(nb, f, indent=1)
    except Exception as exc:
        return _err(f"write failed: {type(exc).__name__}: {exc}")

    code_cells = sum(1 for c in nb_cells if c["cell_type"] == "code")
    if errors:
        return _result(
            "computed",
            f"wrote notebook to {path} ({code_cells} code cells run; {len(errors)} had errors — fix and re-export)",
            path=path, cells=len(nb_cells), executed=execute, errors=errors,
        )
    ran = "executed, outputs + figures embedded" if execute else "code-only (not executed)"
    return _result("computed", f"wrote reproducible notebook ({len(nb_cells)} cells, {ran}) to {path}",
                   path=path, cells=len(nb_cells), executed=execute, errors=[])


# ---------------------------------------------------------------------------
# interval_verify — RIGOROUS numerics: a guaranteed enclosure (not an ε-hope)
# ---------------------------------------------------------------------------
# numeric_verify compares float64 results within a tolerance the caller picks —
# fine for a sanity check, but the bound is asserted, not proven. interval_verify
# evaluates the expression in INTERVAL ARITHMETIC (mpmath.iv): every constant and
# operation is replaced by a rigorous enclosure, so the returned [lo, hi] is a
# mathematical GUARANTEE that the true value lies inside. A claimed value is then
# "computed" only if it falls within that proven interval, else "refuted". This is
# what lets the [computed] tag carry a real error bound.

INTERVAL_VERIFY_SCHEMA = {
    "name": "interval_verify",
    "description": (
        "Rigorously evaluate a numeric expression with a GUARANTEED error bound using "
        "interval arithmetic (mpmath), and optionally verify a claimed value lies inside "
        "that proven enclosure. Unlike a float computation, the returned [low, high] "
        "interval is a mathematical guarantee the true value is contained. Use it to back "
        "a [computed] claim with a real bound, or to check a constant/integral/sum to many "
        "digits. Write plain math: 'sqrt(2)', 'pi/4', 'exp(1)', '4*atan(1)', '22/7'. "
        "Available: + - * / **, sqrt, exp, log, sin, cos, tan, atan, asin, acos, sinh, "
        "cosh, tanh, pi, e. Returns verified=computed with the enclosure (and passed=true/"
        "false if a claim was given); refuted if the claim is provably outside the interval."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "expression": {"type": "string", "description": "Math expression to enclose, e.g. 'pi/4' or 'sqrt(2)'."},
            "claim": {
                "type": ["number", "string"],
                "description": "Optional asserted value; verified if it agrees with the proven true value within tolerance.",
            },
            "dps": {"type": "integer", "description": "Decimal digits of working precision (default 30, max 200)."},
            "rtol": {"type": "number", "description": "Relative tolerance for checking a claim (default 1e-9)."},
        },
        "required": ["expression"],
    },
}

# Names exposed to the sandboxed expression, bound to interval-aware ops at call time.
_IV_FUNCS = ("sqrt", "exp", "log", "sin", "cos", "tan", "atan", "asin", "acos", "sinh", "cosh", "tanh")
_IV_CONSTS = ("pi", "e")


def _iv_namespace(iv):
    ns: dict[str, Any] = {f: getattr(iv, f) for f in _IV_FUNCS if hasattr(iv, f)}
    ns["pi"] = iv.pi
    ns["e"] = iv.exp(1)
    return ns


def interval_verify(expression: str, claim: Any = None, dps: int = 30, rtol: float = 1e-9) -> str:
    try:
        from mpmath import iv
    except Exception:
        return _err("mpmath not available")
    import ast

    iv.dps = max(5, min(200, int(dps or 30)))

    # Wrap every numeric literal as an exact interval (iv.mpf("<text>")) so decimals
    # like 0.1 — not representable in binary — become a rigorous bracket, not a lossy
    # float. This is what keeps the whole evaluation a guaranteed enclosure.
    class _WrapNums(ast.NodeTransformer):
        def visit_Constant(self, node):  # py3.8+
            if isinstance(node.value, bool):
                return node
            if isinstance(node.value, (int, float)):
                return ast.copy_location(
                    ast.Call(
                        func=ast.Name(id="__mpf", ctx=ast.Load()),
                        args=[ast.Constant(value=str(node.value))],
                        keywords=[],
                    ),
                    node,
                )
            return node

    try:
        tree = ast.parse(expression, mode="eval")
        tree = ast.fix_missing_locations(_WrapNums().visit(tree))
        code = compile(tree, "<interval_verify>", "eval")
    except Exception as exc:
        return _err(f"parse error: {type(exc).__name__}: {exc}")

    ns = _iv_namespace(iv)
    ns["__mpf"] = iv.mpf
    try:
        enc = eval(code, {"__builtins__": {}}, ns)  # noqa: S307 — sandboxed: no builtins, curated names
        lo, hi = float(enc.a), float(enc.b)
        try:
            width = float(enc.delta)  # the true enclosure width (may be far below float64 resolution)
        except Exception:
            width = hi - lo
    except Exception as exc:
        return _err(f"evaluation error: {type(exc).__name__}: {exc}")

    if claim is None:
        return _result(
            "computed",
            f"{expression} ∈ [{lo:.16g}, {hi:.16g}] (rigorous enclosure, width {width:.3e})",
            low=lo, high=hi, width=width, dps=iv.dps,
        )
    try:
        c = float(claim)
    except Exception:
        return _err(f"claim is not a number: {claim!r}")
    # The enclosure [lo, hi] is a PROVEN bracket on the true value (often far tighter
    # than float64). A finite-precision claim is verified if it agrees with that true
    # value to within `tol` — i.e. it lies within tol of the proven enclosure. This
    # keeps the rigor (true value is bracketed) while not refusing a correct float64
    # input just because it can't match 30 exact digits.
    tol = abs(rtol) * max(1.0, abs(c)) + 1e-12
    inside = (lo - tol) <= c <= (hi + tol)
    if inside:
        return _result(
            "computed",
            f"{claim} verified: agrees with proven value {expression} ∈ [{lo:.16g}, {hi:.16g}] within {tol:.2e}",
            claim=c, low=lo, high=hi, width=width, tol=tol, passed=True, dps=iv.dps,
        )
    return _result(
        "refuted",
        f"{claim} disagrees with proven value {expression} ∈ [{lo:.16g}, {hi:.16g}] (beyond tol {tol:.2e}) — claim is wrong",
        claim=c, low=lo, high=hi, width=width, tol=tol, passed=False, dps=iv.dps,
    )


# ---------------------------------------------------------------------------
# stats_test — assumption-aware statistics: effect sizes + CIs, anti-p-hacking
# ---------------------------------------------------------------------------
# A bare p-value is the most abused number in science. stats_test runs the test
# AND checks its assumptions (normality, equal variance), ALWAYS reports an effect
# size + confidence interval (not just significance), and supports multiple-
# comparison correction. It refuses to let "p<0.05" stand alone: a tiny effect, a
# violated assumption, or an uncorrected family of tests is surfaced as a warning.

STATS_TEST_SCHEMA = {
    "name": "stats_test",
    "description": (
        "Run a statistical test the RIGOROUS way: it checks the test's assumptions "
        "(normality, equal variance), always reports an effect size and 95% confidence "
        "interval (never a bare p-value), and warns about misuse so you cannot p-hack. "
        "Tests: 'ttest' (two independent samples a,b — uses Welch by default), "
        "'paired_ttest' (a,b same length), 'anova' (groups: list of arrays), "
        "'correlation' (x,y — Pearson+Spearman), 'normality' (data — Shapiro-Wilk), "
        "'correct' (pvalues: list, method 'bh'|'bonferroni' — multiple-comparison "
        "correction). Returns verified=computed with stats, effect size, CI, and a "
        "warnings list; assumption violations and trivial effects are flagged, not hidden."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "test": {
                "type": "string",
                "enum": ["ttest", "paired_ttest", "anova", "correlation", "normality", "correct"],
                "description": "Which analysis to run.",
            },
            "a": {"type": "array", "items": {"type": "number"}, "description": "First sample (ttest/paired_ttest)."},
            "b": {"type": "array", "items": {"type": "number"}, "description": "Second sample (ttest/paired_ttest)."},
            "x": {"type": "array", "items": {"type": "number"}, "description": "First variable (correlation)."},
            "y": {"type": "array", "items": {"type": "number"}, "description": "Second variable (correlation)."},
            "data": {"type": "array", "items": {"type": "number"}, "description": "Sample (normality)."},
            "groups": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}, "description": "List of arrays (anova)."},
            "pvalues": {"type": "array", "items": {"type": "number"}, "description": "p-values to correct (correct)."},
            "method": {"type": "string", "description": "Correction method: 'bh' (default) or 'bonferroni'."},
            "alpha": {"type": "number", "description": "Significance threshold (default 0.05)."},
        },
        "required": ["test"],
    },
}


def _shapiro_note(stats, sample, label, warnings):
    """Append a normality warning when Shapiro-Wilk rejects (n in [3,5000])."""
    if 3 <= len(sample) <= 5000:
        p = float(stats.shapiro(sample).pvalue)
        if p < 0.05:
            warnings.append(f"{label} fails normality (Shapiro p={p:.3g}); prefer a non-parametric test.")
        return p
    return None


def stats_test(test: str, **kw: Any) -> str:
    try:
        import numpy as np
        from scipy import stats
    except Exception:
        return _err("numpy/scipy not available")

    alpha = float(kw.get("alpha", 0.05) or 0.05)
    warnings: list[str] = []

    def _eff_label(name, val, small, medium, large):
        a = abs(val)
        tier = "negligible" if a < small else "small" if a < medium else "medium" if a < large else "large"
        return f"{name}={val:.3g} ({tier})"

    try:
        if test in ("ttest", "paired_ttest"):
            a = np.asarray(kw.get("a", []), float)
            b = np.asarray(kw.get("b", []), float)
            if a.size < 2 or b.size < 2:
                return _err("ttest needs at least 2 observations per sample")
            paired = test == "paired_ttest"
            if paired and a.size != b.size:
                return _err("paired_ttest needs equal-length samples")
            _shapiro_note(stats, a, "sample a", warnings)
            _shapiro_note(stats, b, "sample b", warnings)
            if not paired:
                lev = float(stats.levene(a, b).pvalue)
                if lev < 0.05:
                    warnings.append(f"unequal variances (Levene p={lev:.3g}); Welch's t used (correct for this).")
            if paired:
                t, p = stats.ttest_rel(a, b)
                diff = a - b
                d = float(np.mean(diff) / np.std(diff, ddof=1)) if np.std(diff, ddof=1) else 0.0
                n = a.size
                se = float(np.std(diff, ddof=1) / np.sqrt(n))
                tcrit = float(stats.t.ppf(1 - alpha / 2, n - 1))
                mean_d = float(np.mean(diff))
                method = "paired t-test"
                dfree = n - 1
            else:
                t, p = stats.ttest_ind(a, b, equal_var=False)
                # pooled SD for Cohen's d
                sp = np.sqrt(((a.size - 1) * np.var(a, ddof=1) + (b.size - 1) * np.var(b, ddof=1)) / (a.size + b.size - 2))
                d = float((np.mean(a) - np.mean(b)) / sp) if sp else 0.0
                se = float(np.sqrt(np.var(a, ddof=1) / a.size + np.var(b, ddof=1) / b.size))
                # Welch–Satterthwaite df
                va, vb, na, nb = np.var(a, ddof=1), np.var(b, ddof=1), a.size, b.size
                dfree = float((va / na + vb / nb) ** 2 / ((va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1)))
                tcrit = float(stats.t.ppf(1 - alpha / 2, dfree))
                mean_d = float(np.mean(a) - np.mean(b))
                method = "Welch's t-test"
            ci = [mean_d - tcrit * se, mean_d + tcrit * se]
            p = float(p)
            sig = p < alpha
            if sig and abs(d) < 0.2:
                warnings.append("statistically significant but effect size is negligible (|d|<0.2) — likely not meaningful.")
            if not sig and ci[0] <= 0 <= ci[1]:
                warnings.append("not significant; the 95% CI includes zero — do not claim an effect.")
            return _result(
                "computed",
                f"{method}: mean diff={mean_d:.4g}, 95% CI [{ci[0]:.4g}, {ci[1]:.4g}], "
                f"t={float(t):.3g}, df={dfree:.3g}, p={p:.4g}; {_eff_label('Cohen d', d, 0.2, 0.5, 0.8)}",
                test=method, mean_difference=mean_d, ci95=ci, t=float(t), df=float(dfree),
                p_value=p, cohens_d=d, significant=sig, alpha=alpha, warnings=warnings,
            )

        if test == "anova":
            groups = [np.asarray(g, float) for g in kw.get("groups", [])]
            if len(groups) < 2 or any(g.size < 2 for g in groups):
                return _err("anova needs ≥2 groups with ≥2 observations each")
            for i, g in enumerate(groups):
                _shapiro_note(stats, g, f"group {i+1}", warnings)
            lev = float(stats.levene(*groups).pvalue)
            if lev < 0.05:
                warnings.append(f"unequal variances (Levene p={lev:.3g}); consider Welch ANOVA / Kruskal–Wallis.")
            f, p = stats.f_oneway(*groups)
            grand = np.concatenate(groups)
            ss_between = sum(g.size * (g.mean() - grand.mean()) ** 2 for g in groups)
            ss_total = float(np.sum((grand - grand.mean()) ** 2))
            eta2 = float(ss_between / ss_total) if ss_total else 0.0
            p = float(p)
            if p < alpha:
                warnings.append("significant omnibus test — run a post-hoc (e.g. Tukey HSD) with correction to locate differences.")
            return _result(
                "computed",
                f"one-way ANOVA: F={float(f):.3g}, p={p:.4g}; {_eff_label('eta^2', eta2, 0.01, 0.06, 0.14)}",
                test="one-way ANOVA", F=float(f), p_value=p, eta_squared=eta2,
                k_groups=len(groups), significant=p < alpha, alpha=alpha, warnings=warnings,
            )

        if test == "correlation":
            x = np.asarray(kw.get("x", []), float)
            y = np.asarray(kw.get("y", []), float)
            if x.size < 3 or x.size != y.size:
                return _err("correlation needs equal-length x,y with ≥3 points")
            r, pr = stats.pearsonr(x, y)
            rho, ps = stats.spearmanr(x, y)
            r = float(r)
            # Fisher z 95% CI for Pearson r
            n = x.size
            z = np.arctanh(r)
            se = 1 / np.sqrt(n - 3)
            zc = float(stats.norm.ppf(1 - alpha / 2))
            ci = [float(np.tanh(z - zc * se)), float(np.tanh(z + zc * se))]
            if abs(float(rho) - r) > 0.3:
                warnings.append("Pearson and Spearman disagree markedly — relationship may be non-linear or outlier-driven.")
            return _result(
                "computed",
                f"Pearson r={r:.3g} (95% CI [{ci[0]:.3g}, {ci[1]:.3g}], p={float(pr):.4g}); "
                f"Spearman ρ={float(rho):.3g} (p={float(ps):.4g})",
                pearson_r=r, pearson_ci95=ci, pearson_p=float(pr),
                spearman_rho=float(rho), spearman_p=float(ps), n=int(n), warnings=warnings,
            )

        if test == "normality":
            data = np.asarray(kw.get("data", []), float)
            if not (3 <= data.size <= 5000):
                return _err("normality (Shapiro-Wilk) needs 3 ≤ n ≤ 5000")
            w, p = stats.shapiro(data)
            p = float(p)
            normal = p >= alpha
            return _result(
                "computed",
                f"Shapiro-Wilk W={float(w):.3g}, p={p:.4g} — {'consistent with normal' if normal else 'NOT normal'}",
                W=float(w), p_value=p, normal=normal, n=int(data.size), alpha=alpha,
            )

        if test == "correct":
            pvals = [float(v) for v in kw.get("pvalues", [])]
            if not pvals:
                return _err("correct needs a non-empty 'pvalues' list")
            method = str(kw.get("method", "bh")).lower()
            m = len(pvals)
            order = sorted(range(m), key=lambda i: pvals[i])
            adj = [0.0] * m
            if method in ("bonferroni", "bonf"):
                for i in range(m):
                    adj[i] = min(1.0, pvals[i] * m)
                method_name = "Bonferroni"
            else:  # Benjamini–Hochberg (FDR)
                prev = 1.0
                for rank in range(m - 1, -1, -1):
                    i = order[rank]
                    val = min(prev, pvals[i] * m / (rank + 1))
                    adj[i] = val
                    prev = val
                method_name = "Benjamini–Hochberg (FDR)"
            rejected = [bool(a < alpha) for a in adj]
            n_sig = sum(rejected)
            naive_sig = sum(1 for v in pvals if v < alpha)
            if naive_sig > n_sig:
                warnings.append(f"{naive_sig - n_sig} result(s) lose significance after correction — the uncorrected count was inflated.")
            return _result(
                "computed",
                f"{method_name}: {n_sig}/{m} significant at α={alpha} after correcting {m} tests (uncorrected: {naive_sig})",
                method=method_name, adjusted_p=adj, rejected=rejected,
                n_significant=n_sig, n_tests=m, alpha=alpha, warnings=warnings,
            )

        return _err(f"unknown test '{test}'")
    except Exception as exc:
        return _err(f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Registration — a "science" toolset, auto-discovered by tools/registry.py
# ---------------------------------------------------------------------------

from tools.registry import registry  # noqa: E402

registry.register(
    name="symbolic_check", toolset="science", schema=SYMBOLIC_CHECK_SCHEMA, emoji="🧮",
    handler=lambda args, **kw: symbolic_check(args["lhs"], args["rhs"], args.get("symbols", "")),
    check_fn=lambda: _have("sympy"),
    description="Symbolically prove/refute a math equality (sympy).",
)
registry.register(
    name="numeric_verify", toolset="science", schema=NUMERIC_VERIFY_SCHEMA, emoji="📐",
    handler=lambda args, **kw: numeric_verify(args["actual"], args["expected"], args.get("rtol", 1e-6), args.get("atol", 1e-9)),
    check_fn=lambda: _have("numpy"),
    description="ε-equivalence check of a numeric result vs a reference.",
)
registry.register(
    name="interval_verify", toolset="science", schema=INTERVAL_VERIFY_SCHEMA, emoji="🎯",
    handler=lambda args, **kw: interval_verify(args["expression"], args.get("claim"), args.get("dps", 30), args.get("rtol", 1e-9)),
    check_fn=lambda: _have("mpmath"),
    description="Rigorous numeric enclosure with a guaranteed error bound (mpmath interval arithmetic).",
)
registry.register(
    name="stats_test", toolset="science", schema=STATS_TEST_SCHEMA, emoji="📈",
    handler=lambda args, **kw: stats_test(args["test"], **{k: v for k, v in args.items() if k != "test"}),
    check_fn=lambda: _have("scipy"),
    description="Assumption-aware statistical test with effect size, CI, and multiple-comparison correction.",
)
registry.register(
    name="units_check", toolset="science", schema=UNITS_CHECK_SCHEMA, emoji="📏",
    handler=lambda args, **kw: units_check(args["expression"], args.get("expected_unit", "")),
    check_fn=lambda: _have("pint"),
    description="Dimensional-consistency check (pint).",
)
registry.register(
    name="qubo_solve", toolset="science", schema=QUBO_SOLVE_SCHEMA, emoji="🧩",
    handler=lambda args, **kw: qubo_solve(args["problem"], **{k: v for k, v in args.items() if k != "problem"}),
    check_fn=lambda: _have("dimod"),
    description="Solve + verify-feasible a small QUBO (knapsack/vertex_cover/set_cover).",
)
registry.register(
    name="roofline_classify", toolset="science", schema=ROOFLINE_SCHEMA, emoji="📊",
    handler=lambda args, **kw: roofline_classify(args["flops"], args["nbytes"], args.get("device", "cpu")),
    description="Compute/memory-bound classification + energy estimate.",
)
registry.register(
    name="arxiv_search", toolset="science", schema=ARXIV_SCHEMA, emoji="📚",
    handler=lambda args, **kw: arxiv_search(args["query"], args.get("max_results", 5)),
    description="Search arXiv for real citable papers.",
)
registry.register(
    name="export_notebook", toolset="science", schema=EXPORT_NOTEBOOK_SCHEMA, emoji="📓",
    handler=lambda args, **kw: export_notebook(
        args["title"], args.get("cells", []), args.get("path", ""), args.get("execute", True)
    ),
    description="Write + execute a reproducible Jupyter notebook (outputs/figures embedded).",
)
