# Emmy — Product Brief (founding)

Status: design captured, no application code yet. This is the seed document for a
**separate product and repo** in the EnergyIR family.

---

## 1. One-liner & positioning

**Emmy: the scientific-computing agent that proves its work.**

A specialised agentic coding coworker for scientists and ML/numerical engineers.
It deep-reasons the mathematics, grounds claims in version-correct docs, computes
hard results with verified engines (not guesses), shows its agents debating, and
**proves the performance it claims**.

Positioning discipline: **not** "a better general coding agent" (unwinnable vs
Cursor / Claude Code / Devin). We win on a triangle only we can occupy:
**scientific niche + verified-optimization tools + visible proof.** Every product
decision serves that triangle.

## 2. The EnergyIR promise, embodied

Cardinal rule inherited from EnergyIR: **never report a result we have not
verified.** In Emmy this shows up twice, both auditable:
1. **The agent proves its optimizations** — measured, signed, CI-gated output.
2. **The fleet runs cheaply** — cost-bounded orchestration, with the bill shown.

This is the trust mechanism. A pure-LLM "math reasoner" gets caught hallucinating;
Emmy computes with verified tools and **shows the work + the measurement + the CI.**

## 3. Relationship to the other products (three SKUs)

| Product | Role | Philosophy | LLM path |
|---|---|---|---|
| **EnergyIR / AI Models** | Verified LLM-inference cost optimizer (gateway) | Optimize & meter | n/a (is the gateway) |
| **Robin** | General fidelity desktop coworker | Fidelity, never optimized | Together direct |
| **Emmy** | Specialised scientific coding agent | Optimization-first, verified | **Through the AI Models gateway** |

Emmy is a **remake of Robin** — it reuses Robin's desktop frame (Hermes/Electron
shell, tools + chat + memory, zero-tooling install) but flips the philosophy to
optimization-first. Emmy **routes its LLM calls through the AI Models gateway** —
frontier (DeepSeek V4 Pro) for the Lead, cheap workers via the cascade — so it
stays cheap, keeps the promise (every call metered), and dogfoods our own gateway.
(A user's-own-key privacy mode can be a later toggle, not v1.)

## 4. The mathematical reasoning engine (concrete)

The "deep math engine" = a math-literate model + EnergyIR's verify-first engines
as **callable agent tools**:

- **The 7 `*-doctor` tools** — profile the user's *actual* workload and
  measurement-verify fixes (NumPy / SciPy / JAX / PyTorch / TensorFlow).
- **Verified kernel synthesis** — propose ε-equivalent faster CPU/GPU kernels with
  signed proofs.
- **QUBO/Ising solver** — solve real combinatorial subproblems (scheduling,
  assignment, hyperparameter, factorization) with an *independent* verifier.
- **Roofline + cost-geodesic `schedule_doctor`** — reason compute- vs memory-bound;
  pick the cheaper path; escalate precision only when residual stalls.
- **Intelligence engine** — learn which optimizations win for which patterns.
- **graphify (knowledge-graph backbone)** — turn the user's project *and* the
  Skills corpus into a navigable KG with query / path / explain (GraphRAG). Agents
  query the graph instead of re-reading files — this is both how Emmy *understands*
  a codebase and how it *retrieves* skills on demand, and it's a token-efficiency
  lever (cited, not dumped). Exposed to agents via graphify's MCP server.

Key principle: **never make the LLM hallucinate a hard answer it can't reliably
produce** (an optimization, a kernel speedup, a numerical equivalence, a proof) —
call the verified engine. Cheaper *and* correct.

## 5. The verification ladder

Claims are verified at the strongest rung that applies:

1. **Empirical** — measured speed/energy with a CI (the doctors). *Core, v1.*
2. **Combinatorial** — feasibility/optimality via the QUBO verifier. *Core, v1.*
3. **ε-equivalence** — kernel synthesis signed proofs. *Core, v1.*
4. **Formal proof** — **Lean** (machine-checked). *Opt-in "Prover" specialist,
   phase 2+, premium.*

**Lean note:** philosophically perfect (verify-don't-assert for *math itself*),
and synergistic with DeepSeek-Prover. But it serves a smaller, adjacent segment
(formal math) and autoformalization is still brittle. So: **top opt-in rung, off
the hot path, with honest fallback** ("not formally verified; empirically checked
to tolerance X"). Do not let the formal-math tail wag the numerical-computing dog;
keep it out of v1's critical path.

## 6. Cost model — deep reasoning *and* affordable

The economic make-or-break. Work splits three ways:
1. **Frontier model (e.g. DeepSeek V4 Pro) only on the reasoning kernels** —
   deriving approach, planning numerics, judging correctness. Small token share,
   non-negotiable quality.
2. **Cheap models on the bulk** — reading docs, boilerplate, running tools,
   retrieval, formatting, routine edits. Most tokens; cascade escalates only on
   verified failure.
3. **Verified engines do the actual computation** — exact, signed results instead
   of expensive/hallucinated LLM "reasoning".

Reference points from SOTA: budget-workers + frontier-orchestrator ≈ 97.7% of
full-frontier accuracy at ~61% cost; prompt/prefix caching ≈ 90% input-cost cut;
delta-only shared context measured at 0.316× baseline energy (EnergyIR
`energyir_context`). Multi-agent debate ≈ 1.5–2.5× a single call (not N×) when
early-stopped.

## 7. The agent cast (visible, Grok-style)

Maps to EnergyIR's `build_agent_graph` (manager / worker / critic) with a
scientific cast:
- **Lead** (frontier) — plans, decomposes, synthesizes.
- **Numerics** (cheap + package skills) — writes the math/array code.
- **Performance** — runs the doctors / kernel synthesis; brings *measured* wins.
- **Verifier / contrarian** — reproduces, checks equivalence, tries to refute;
  invokes the **Prover (Lean)** rung when warranted.

The visible debate is the **measurement audit trail rendered live** — the brand,
not UX flash. Spawn count + which model + when to stop are decided by the
cost-bounded orchestration controller (QUBO-assigned, cost-geodesic-scheduled,
calibration-gated), not by a token-burning manager loop.

## 8. The Skills system (pre-learning)

A curated, retrievable expertise library — the moat content asset.

- **Two kinds of skills:**
  - **Package skills** built from official docs: NumPy, SciPy, JAX, PyTorch,
    TensorFlow, LangChain, LangGraph, **Streamlit**, plus delivery/viz (Gradio,
    Plotly, Matplotlib, pandas/polars).
  - **Domain-expertise skills** (the harder, more valuable asset): optimization,
    numerical methods, linear algebra, ODE/PDE, stochastic methods, LLM
    training/inference, precision/stability.
- **Retrieval, not context-stuffing** — always-loaded one-line index + full body
  fetched on demand (SKILL.md / progressive-disclosure pattern). **graphify is the
  retrieval substrate**: skills + docs become a KG the agents query/path/explain,
  rather than a flat dump. Small context = cheap calls = a cost lever, not just an
  organization choice.
- **Version-pinned** — tied to EnergyIR's API-change DB (`upgrade-check` /
  `cve-check`): read the user's installed versions, load the right skill, warn on
  breaking changes. Unique tie-in.
- **Citation-backed** — every skill cites its source; answers are grounded and
  checkable (anti-hallucination).
- **Maintained + cache-friendly** — signed, updatable skill packs (reuse
  `db_snapshot` / federated signed updates); static shared prefix → prefix-caches
  perfectly across agents and queries.

## 9. Reuse map (what already exists in EnergyIR / Robin)

- Desktop frame, tools+chat+memory, zero-tooling install → **Robin**.
- Manager/worker/critic graph → `energyir_agent` (`build_agent_graph`).
- Delta-only shared context → `energyir_context` (measured 0.316×).
- Cascade router + categorizer + quality gate + gateway + SpendGuard → `energy/tokens`.
- Bayesian routing + calibration → `energy/intelligence`.
- Verified engines (doctors, synthesis, QUBO, roofline, schedule_doctor) → `energy/*`, `src/energyir`.
- Cross-fleet learning + signed skill/dispatch updates → `energy/federated`, `db_snapshot`.
- Knowledge-graph understanding + retrieval (codebase + Skills) → **graphify** (KG + query/path/explain + MCP server).

New build: the Skills pipeline (on a graphify KG), tool-wiring, the scientific
agent cast + visible UI, the cost-bounded orchestration controller, and the rebrand.

## 10. Phased build (proposed)

- **Phase 0 — Frame:** fork Robin's shell, rebrand to Emmy, route LLM calls
  through the AI Models gateway (frontier Lead + cheap workers via the cascade).
- **Phase 1 — Engine + cast:** expose the verified engines as tools; **graphify
  the user's workspace into a KG agents query** (comprehension); manager +
  numerics/performance/verifier cast; visible-debate UI; empirical/combinatorial/
  ε-equivalence verification rungs.
- **Phase 2 — Skills:** package-doc skill pipeline (version-pinned, cited,
  on-demand) **on a graphify KG** + first domain-expertise skills; wire to the
  API-change DB.
- **Phase 3 — Orchestration efficiency:** QUBO-assigned spawn count,
  cost-geodesic debate depth, early-stop gate, semantic-cache rung, structured
  context projection.
- **Phase 4 — Formal tier:** opt-in Lean "Prover" rung with honest fallback.

## 11. Open decisions

- Frontier model choice for the Lead (DeepSeek V4 Pro candidate) + the cheap
  worker set.
- Pricing/packaging (standalone vs. tier alongside AI Models).
- Domain (name/handle/trademark) availability for "Emmy" + visual identity.
- Skills maintenance cadence + which packages ship in v1.
