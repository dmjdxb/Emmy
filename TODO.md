# Emmy — Build Roadmap

Phased TODO derived from [docs/PRODUCT_BRIEF.md](docs/PRODUCT_BRIEF.md). Each phase
has a **Goal**, **Tasks** (checkboxes), and a **Done when** gate. Ship a phase only
when its gate passes. Check items off as they land.

## Invariants (apply to every phase — non-negotiable)

- [ ] **Prove every claim.** No performance/correctness statement ships unverified
      (measured CI, combinatorial/ε-equivalence, or formal). On failure, say so —
      never fake a result.
- [ ] **Frontier model only where math demands it**; cheap models for the bulk;
      verified engines for exact computation.
- [ ] **Grounded + cited.** Doc-derived answers cite the source at the correct version.
- [ ] **Self-measuring.** Every model call is metered through the gateway; the bill
      is always inspectable.
- [ ] **Niche discipline.** Serve scientific/numerical/ML work — do not drift into
      general-purpose coding.

---

## Phase 0 — Frame (fork Robin → rebrand → wire to the gateway)

**Goal:** an installable Emmy desktop app, rebranded, that completes a chat call
through the AI Models gateway.

- [x] Import the Robin/Hermes frame as the fork basis (clean import, full divergence).
- [x] Rebrand identity (manifests): app name, bundle id, window/title strings,
      installer + desktop `package.json`, config header → Emmy.
- [x] Rebrand the user-facing UI/display strings ("Robin" → "Emmy") — guarded pass,
      leaving provider/auth keys, `dmjdxb/Robin` URLs, `Robin*` types, and internal
      `robin/` paths for the build-verified pass.
- [ ] Build-verified pass: flip `Robin*` type names, `X-Robin-Session-*` header,
      and `dmjdxb/Robin` → Emmy URLs (under typecheck + the `brand-gate` CI).
- [ ] Inventory what to keep (tools + chat + memory + zero-tooling install) vs
      replace; remove Robin-specific fidelity copy.
- [x] **Decision:** models = DeepSeek **V4 Pro** (Lead/frontier) + DeepSeek **V4
      Flash** (cheap cascade workers); upstream provider = **DeepInfra** (cheaper
      than TogetherAI). Confirm exact slugs at deepinfra.com/dash/models.
- [ ] Wire **DeepInfra** as a first-class provider **server-side only** (in the
      EnergyIR gateway): endpoint `https://api.deepinfra.com/v1/openai`, auth
      `DEEPINFRA_TOKEN`, slugs `org/model`. The Emmy client must NEVER see DeepInfra,
      its token, or its endpoint — it talks only to `api.energyir.io`.
- [x] **Server-side, confidential DeepInfra price table** added to the cost optimizer
      (EnergyIR repo `cache_check/providers/deepinfra.py`, beside Together's; commit
      75eadd7). Rates (USD/1M tok, snapshot 2026-06-23): V4 Pro 1.30/2.60/0.10 cached;
      V4 Flash 0.10/0.20/0.02 cached (Flash ~13× cheaper). Internal-only — never shipped
      to the client / shown. **Confirm rates against the DeepInfra dash** (account rates differ).
- [ ] Extend `brand-gate` CI to forbid the string **"DeepInfra"** (and any provider
      host) in the shipped UI — confidentiality can't regress.
- [ ] Subscription model: tiers ≈ **$50 / $100 / $200**/mo (flat; users never pay
      per token). Wire billing in the portal (Stripe) — separate from this repo.
- [ ] Route LLM calls through the **AI Models gateway** (V4 Pro Lead + V4 Flash
      workers via the cascade); provision Emmy's gateway tenant/key (DeepInfra upstream).
- [ ] Metering via the gateway; surface **savings** (energy/tokens/usage) to the
      user — never provider prices.
- [ ] Preserve the zero-tooling install pipeline (CI-built backend bundle + signed app).
- [ ] Smoke test: app launches rebranded, one chat round-trip through the gateway,
      metering recorded.

**Done when:** Emmy installs clean, launches as Emmy (not Robin), and completes a
chat call through the gateway with the cost recorded.

---

## Phase 1 — Engine + cast (verified engines as tools, visible debate, rungs 1–3)

**Goal:** given a numerical task, Emmy writes code, runs a verified engine, and
returns a measured win with a CI — shown in a live agent debate.

> **Server-side spine built + TDD-verified headlessly** (EnergyIR repo, 202 tests
> green): the cost cascade (lead→V4 Pro / worker→V4 Flash), the DeepInfra runtime
> provider (`DeepInfraTokenProvider`, mock-tested), the verified tool surface
> (`energy.agent_tools`), the savings engine/ledger, and the
> **`EmmyOrchestrator`** end-to-end (task → routing → verified tool → metered
> savings → proof). Remaining items below need the desktop/GPU/live-key envs.

- [~] Agent graph: a deterministic **`EmmyOrchestrator`** (lead/worker + verified
      tools + metering) is built & tested; the LangGraph `build_agent_graph` wiring +
      live LLM remain (needs the agent runtime).
- [~] Tool adapters — uniform `ToolResult` surface built; GPU-free engines wired + tested:
  - [ ] The 7 `*-doctor` profilers (array / jit / compile / train / graph / frame / agent) — need torch/jax/GPU.
  - [ ] Verified kernel synthesis (ε-equivalent, signed) — needs GPU.
  - [x] QUBO/Ising solver (knapsack / vertex_cover / set_cover) — verified, tested.
  - [x] Roofline classifier (compute/memory-bound + proxy error) — tested. (`schedule_doctor` next.)
- [ ] Code-execution sandbox (reuse the synthesis isolation boundary) for running
      user workloads safely.
- [ ] **Workspace understanding via graphify:** build a KG of the user's project +
      installed env; agents query/path/explain it instead of re-reading files
      (comprehension + token efficiency). Wire graphify's MCP server as a tool.
- [ ] **Verification rungs 1–3 wired:** empirical (doctor CI), combinatorial (QUBO
      verifier), ε-equivalence (synthesis signature).
- [ ] **Visible-debate UI:** render Lead + workers debating live; surface each
      claim's verification evidence inline (the audit trail).

**Done when:** for a real numerical/ML task, Emmy produces working code plus a
measured speed/energy win with a CI (or an honest "no confident win"), with the
debate + evidence visible.

---

## Phase 2 — Skills (version-pinned, cited, on-demand pre-learning)

**Goal:** the agent loads the right version-correct skill on demand, cites it, and
warns on breaking version changes.

- [ ] Skill format spec (SKILL.md-style: name, one-line index, body, version tag,
      citations, applicability).
- [ ] Retrieval mechanism: always-loaded index + on-demand body fetch
      (progressive disclosure). **graphify KG is the retrieval substrate** — skills
      + docs become a queryable graph (query/path/explain), not a flat dump.
- [ ] Package-doc ingestion pipeline → skill cards:
  - [ ] Compute: NumPy, SciPy, JAX, PyTorch, TensorFlow.
  - [ ] Orchestration: LangChain, LangGraph.
  - [ ] Delivery / viz: **Streamlit**, Gradio, Plotly, Matplotlib, pandas/polars.
- [ ] **Version-pinning** wired to EnergyIR's API-change DB (`upgrade-check` /
      `cve-check`): read installed versions, load the matching skill, warn on breaks.
- [ ] Domain-expertise skills (the harder, higher-value asset): optimization,
      numerical methods, linear algebra, ODE/PDE, stochastic methods, LLM
      training/inference, precision/stability.
- [ ] Citation surfacing in answers (grounded + checkable).
- [ ] Signed, updatable skill packs (reuse `db_snapshot` / federated updates).
- [ ] Prefix-cache the static skill index across agents/queries.
- [ ] **Decision:** which packages + domain skills ship in v1; maintenance cadence.

**Done when:** Emmy answers a package question by loading the correct *versioned*
skill on demand, cites the source, and flags a breaking-change risk for the user's
installed version.

---

## Phase 3 — Orchestration efficiency (the cost-bounded controller)

**Goal:** tasks complete within a measured budget; early-stop and routing
demonstrably cut cost; the bill is shown.

- [ ] Wire the cascade router + categorizer (`energy/tokens`) per agent step;
      cheapest-competent first, escalate on verified failure.
- [ ] Enforce the cost split: frontier on reasoning kernels, cheap on bulk.
- [ ] **QUBO-assigned spawn count + task→model assignment** under a hard budget
      (manager emits objective/affinities; solver allocates; verifier checks).
- [ ] **Cost-geodesic debate depth** (`schedule_doctor`) + **early-stop gate**
      (stop spawning/escalating when the quality CI stops improving).
- [ ] **Semantic-cache rung** (embed → nearest-neighbor → reuse within a verified
      threshold) before the cheapest model.
- [ ] **Structured context projection** — pass 200–500-token slices to workers,
      not the full transcript.
- [ ] Bayesian routing + calibration (`energy/intelligence`): learn the best
      (model, #agents, depth) per task category; `earned_silence` autonomy threshold.
- [ ] Gateway metering + `SpendGuard` + per-session budget cap; show the bill +
      savings receipt.

**Done when:** a benchmark task runs under budget with metered cost, early-stop is
shown to save vs. always-on, and the user sees a per-task bill + savings.

---

## Phase 4 — Formal tier (opt-in Lean "Prover" rung)

**Goal:** a provable mathematical claim earns a machine-checked proof badge;
unprovable claims fall back honestly.

- [ ] Lean 4 + mathlib integration; evaluate DeepSeek-Prover / autoformalization path.
- [ ] "Prover" specialist agent — **opt-in, off the hot path.**
- [ ] Gate: attempt formalization within a budget; on success show the
      Lean-verified badge + proof; on failure fall back to the empirical/numerical
      check and **say so** ("not formally verified; empirically checked to tol X").
- [ ] Keep formal-math scope contained — do not let it pull the product off the
      numerical-computing niche.

**Done when:** a discrete provable proposition is machine-checked and badged, and a
non-formalizable one degrades gracefully with an honest label.

---

## Cross-cutting / ongoing

- [ ] Honest telemetry + metering throughout (promise enforcement).
- [ ] Eval harness: scientific-task benchmark for quality + cost regression.
- [ ] Docs/onboarding for scientists.

## Open decisions (resolve as phases reach them)

- [ ] Frontier model for the Lead + cheap worker set (blocks Phase 0 wiring).
- [ ] Pricing / packaging — standalone vs. a tier alongside AI Models.
- [ ] "Emmy" domain / handle / trademark availability + visual identity.
- [ ] v1 Skills coverage + maintenance cadence (blocks Phase 2 scope).
