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
        "Export the work as a runnable Jupyter notebook (.ipynb) so the result is reproducible — "
        "the researcher can open it and re-run every step. Provide ordered cells (markdown for "
        "explanation/derivation, code for the computation). Use this to hand back a hard analysis as a "
        "self-contained artifact. Returns the saved file path (it appears in the artifacts panel)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Notebook title (also the default filename)."},
            "cells": {
                "type": "array",
                "description": "Ordered cells.",
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
        },
        "required": ["title", "cells"],
    },
}


def export_notebook(title: str, cells: list, path: str = "") -> str:
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

    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
            "title": title,
            "generated_by": "Emmy (EnergyIR)",
        },
        "cells": [_nb_cell(c) for c in (cells or [])],
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
    return _result("computed", f"wrote reproducible notebook ({len(nb['cells'])} cells) to {path}",
                   path=path, cells=len(nb["cells"]))


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
    handler=lambda args, **kw: export_notebook(args["title"], args.get("cells", []), args.get("path", "")),
    description="Export the work as a reproducible Jupyter notebook.",
)
