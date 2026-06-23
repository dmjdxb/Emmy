# Emmy

**The scientific-computing agent that proves its work.**

Emmy is a specialised, agentic coding coworker for scientists and ML/numerical
engineers. It doesn't just write numerical and ML code — it **deep-reasons the
mathematics, grounds every claim in version-correct documentation, computes hard
results with verified engines instead of guessing, shows its agents debating the
problem, and proves the performance it claims.**

> The name carries the science: **Emmy Noether**, whose theorem proves that every
> symmetry corresponds to a conservation law — including conservation of *energy*.
> It threads our origin (EnergyIR) through deep mathematics and our cardinal rule:
> **never assert what we have not verified.**

Emmy is a member of the EnergyIR family — and a **separate product** from:
- **EnergyIR / AI Models** — the verified LLM-inference cost optimizer (gateway).
- **Robin** — the fidelity desktop coworker (never optimized, general purpose).

Emmy reuses Robin's desktop frame but inverts its philosophy: it is
**optimization-first**, routes its model calls **through the AI Models gateway**,
and is **specialised for deep scientific work**.

---

## Who it's for

Scientists and engineers doing real numerical / ML / scientific-computing work:
LLM builds & inference, JAX, PyTorch, TensorFlow, NumPy, SciPy, optimization,
numerical methods, and the delivery layer they ship with (Streamlit, Gradio,
Plotly, pandas/polars). The niche **is** the strategy — we win where general
coding agents are weakest and where verified correctness + performance actually
matter.

## What makes it different (the moat)

1. **A real mathematical reasoning engine** — not a vague "math brain", but
   EnergyIR's verify-first engines exposed as native agent tools:
   the 7 `*-doctor` profilers, verified kernel synthesis, the QUBO/Ising solver
   with an independent verifier, roofline + cost-geodesic scheduling, and the
   learning/routing intelligence engine.
2. **Proves every claim** — performance is measured (CI excludes zero), math is
   verified. The promise of EnergyIR, applied to an agent's output.
3. **Grounded in real, version-pinned docs** — a curated Skills library with
   citations, wired to EnergyIR's API-change DB so the agent knows your installed
   versions and warns on breaking changes.
4. **Visible agents** — a manager + specialist workers debate in the open. The
   debate *is* the verification audit trail, rendered live.
5. **Affordable** — a deep-reasoning frontier model only where math demands it;
   cheap models for the bulk; verified engines for exact computation. The
   cost-bounded orchestration is what makes it a product people use daily.

See **[docs/PRODUCT_BRIEF.md](docs/PRODUCT_BRIEF.md)** for the full architecture,
agent cast, Skills taxonomy, verification ladder, and phased build plan.

## Status

Founding scaffold. Vision and architecture captured; **no application code yet.**
