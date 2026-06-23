# Plan: Effort Selector + Cost-Tiered Model Routing

**Status:** Draft for review (no code written yet)
**Date:** 2026-06-23
**Goal:** Cut per-user inference cost by defaulting conversations to a cheaper-but-excellent model and giving users a Claude-style **effort selector** in the chat input bar to step up to deep reasoning when they want it. Tool calls / auxiliary tasks stay on the cheapest model regardless.

---

## 1. Decisions (locked)

| Decision | Choice |
|---|---|
| New-conversation default | **Balanced** → `deepseek-ai/DeepSeek-V3.1` |
| Tiers | **3** — Quick / Balanced / Max |
| Persistence | **Per-conversation**, changeable mid-chat (live `switch_model`) |
| Rollout | Full plan doc first (this file), then implement |

### The effort ladder

The `nous`/EnergyIR endpoint uses **OpenRouter-style slugs** (`vendor/model`), confirmed by the existing aux config which uses `openai/gpt-oss-120b`. All three tier slugs below are present in EnergyIR's curated catalog (`robin/models.py` `_PROVIDER_MODELS["nous"]`, lines 153-189):

| UI label | Model (nous slug) | Catalog | Role |
|---|---|---|---|
| ⚡ **Quick** | `openai/gpt-oss-120b` | proven via `auxiliary.*` | Fast, low cost; already vetted for tool calls |
| ◐ **Balanced** ★default | `deepseek/deepseek-v4-flash` | `models.py:170` | Cheaper DeepSeek — great for docs & writing |
| ✦ **Max effort** | `deepseek/deepseek-v4-pro` | `models.py:169` | Deep reasoning (today's default) |

Cost order holds (Quick ≪ Flash < Pro). Exact per-token prices are EnergyIR's (their proxy, not Together's public list); the slugs are catalog-confirmed so no live `/v1/models` check is required to ship. Tier slugs live in config and are trivially retunable.

**Invariant:** the effort tier sets the **primary/chat model only**. The `auxiliary.*` tasks (web_extract, mcp, title_generation, skills_hub, triage_specifier, kanban_decomposer, profile_describer) remain pinned to `openai/gpt-oss-120b` and are NOT affected — that routing already exists (`robin/config.py:1227-1340`) and is independent of the primary model.

---

## 2. Architecture overview

```
┌────────────────────────── Frontend (apps/desktop, React/TS) ──────────────────────────┐
│ Composer controls bar ──[new ⚙ effort button]── opens popover (3 tiers + small print)  │
│   selection → ChatBarState.effort → sent on prompt.submit as { effort: "balanced" }    │
└───────────────────────────────────────────────────────────────────────────────────────┘
                                   │ JSON-RPC  prompt.submit { session_id, text, effort }
                                   ▼
┌────────────────────────── Backend (tui_gateway + robin) ──────────────────────────────┐
│ _run_prompt_submit  → reads effort, stores on session dict                             │
│   if effort changed vs agent's current model → agent.switch_model(tier_model)          │
│   else _make_agent builds AIAgent(model = effort_to_model(effort))                     │
│                                                                                         │
│ effort_to_model(effort)  ── new resolver in robin/models.py, reads config effort_tiers │
│ auxiliary.* tasks            ── unchanged, stay on gpt-oss-120b                         │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

Why this is low-risk: the override seam already exists. `resolve_runtime_provider(target_model=…)` overrides config (`robin/runtime_provider.py:305`), `AIAgent(model=…)` overrides config (`agent/agent_init.py:254`), and `agent.switch_model()` (`run_agent.py:678`) already does live mid-session switching. We are wiring an existing capability to a new UI control, not inventing model-swapping.

---

## 3. Config schema (new block)

Add an `effort_tiers` block to `DEFAULT_CONFIG` in `robin/config.py` (mirrors the `auxiliary.*` shape so EnergyIR can retune fleet-wide via Portal/config without a binary ship). Insert near the `auxiliary` block (after `robin/config.py:1340`).

```python
# Primary-model effort ladder shown in the chat composer's effort selector.
# Each tier maps a user-facing effort level to a concrete primary model.
# Auxiliary/tool-call tasks are NOT affected (see "auxiliary" above).
"effort_tiers": {
    "default": "balanced",          # tier for new conversations
    "tiers": [
        {
            "id": "quick",
            "label": "Quick",
            "model": "openai/gpt-oss-120b",
            "provider": "auto",
            "blurb": "Fast, low cost — everyday questions",
            "cost_hint": 1,           # relative cost weight for UI dots/warning
        },
        {
            "id": "balanced",
            "label": "Balanced",
            "model": "deepseek/deepseek-v4-flash",
            "provider": "auto",
            "blurb": "Great for docs & writing",
            "cost_hint": 2,
        },
        {
            "id": "max",
            "label": "Max effort",
            "model": "deepseek/deepseek-v4-pro",
            "provider": "auto",
            "blurb": "Deep reasoning — uses your limits faster",
            "cost_hint": 3,
        },
    ],
},
```

Notes:
- Keep `model` strings as the **only** place tier→model is defined → single source of truth.
- `provider: "auto"` lets the existing resolver pick the nous/EnergyIR endpoint.
- Backwards compatible: absent block → code falls back to defaults baked into `robin/models.py`.

---

## 4. Backend changes (file-by-file)

### 4a. `robin/models.py` — tier resolver + bug fix
- **New:** `EFFORT_TIERS_FALLBACK` constant (the 3 tiers above) and helpers:
  - `get_effort_tiers() -> list[dict]` — read `config.effort_tiers.tiers`, fall back to constant.
  - `get_default_effort() -> str` — read `config.effort_tiers.default` (→ `"balanced"`).
  - `effort_to_model(effort_id: str) -> tuple[str, str]` — return `(model, provider)`; unknown id → default tier; validate against live `/v1/models` where available, else trust config.
- **Fix `:1170`** `_PROVIDER_SILENT_DEFAULT_OVERRIDES["nous"]` → change `deepseek/deepseek-v4-flash` (not served by TogetherAI; likely 404) to a confirmed-served cheap model, recommend `openai/gpt-oss-120b`. Independent of this feature but found during investigation — ship it.

### 4b. `tui_gateway/server.py` — plumb effort per conversation
- **`prompt.submit` handler** (`_run_prompt_submit`, ~`:4478`): accept optional `effort` in the RPC payload. Resolve `effort → (model, provider)` via `effort_to_model`.
- **Session dict** (`_init_session`, `:2583`): add `"effort": get_default_effort()`.
- **On submit:** if `effort` present and differs from session's current → update `session["effort"]` and call `session["agent"].switch_model(model, provider)` **before** `run_conversation` (`:4623`). This is the mid-chat switch path; no session rebuild.
- **`_make_agent`** (`:2510`): accept an optional `effort` arg; when building a fresh agent, resolve `model, requested_provider` from the effort tier instead of `_resolve_startup_runtime()` (which currently reads config default). Keep `_resolve_startup_runtime` as the fallback when no effort is supplied.
- **`model.options` RPC** (existing): extend its response to include the `effort_tiers` list (label, blurb, id, cost_hint, current selection) so the UI renders the ladder. Source from `get_effort_tiers()`.

### 4c. `robin/web_server.py` — global (no active session) options
- The UI calls `getGlobalModelOptions()` (→ `/api/model/options`) when there is no active session (`apps/desktop/.../chat/index.tsx:205-224`). Add the same `effort_tiers` payload there so the selector renders on the empty "Start with a goal" screen (Image #2/#3).

### 4d. Auxiliary tasks — **no change**
Confirm (spot-check, no edit) that `auxiliary.*` resolution in `agent/auxiliary_client.py` does not read the primary effort/model — it doesn't (it reads `auxiliary.<task>.*`). Tool calls stay cheap automatically.

---

## 5. Frontend changes (apps/desktop, React/TS)

### 5a. State — `chat/composer/types.ts`
Extend `ChatBarState.model` (already has `canSwitch`, `quickModels`) or add a sibling:
```ts
effort: {
  current: string            // tier id, e.g. "balanced"
  tiers: EffortTier[]        // from model.options
  canSwitch: boolean
}
interface EffortTier { id: string; label: string; blurb: string; costHint: number }
```

### 5b. New selector button — `chat/composer/controls.tsx`
- Add a `GHOST_ICON_BTN` button **between the document icon (`:74-90`) and the `DictationButton` (`:91`)**, matching the composer's existing icon row (Image #3).
- Icon: a small gauge/spark (reuse `lib/icons`); label shows current tier short name (like Claude's "High ›" chip in Image #1).

### 5c. Popover — reuse Radix `DropdownMenuRadioGroup` (`components/ui/dropdown-menu.tsx`)
Same primitive the "+" context menu already uses. Opens **above** the input. Layout mirrors Claude (Image #1):

```
┌─────────────────────────────────────────────┐
│  Effort                                       │
│                                               │
│  ⚡ Quick                                      │
│     Fast, low cost — everyday questions       │
│                                               │
│  ◐ Balanced                          ✓        │   ← default / selected
│     Great for docs & writing                  │
│                                               │
│  ✦ Max effort                                 │
│     Deep reasoning — uses your limits faster  │
│  ─────────────────────────────────────────── │
│  Higher effort means more thorough answers,   │   ← small print (token warning)
│  but takes longer and uses more of your usage.│
└─────────────────────────────────────────────┘
```

### 5d. Submit payload — `session/hooks/use-prompt-actions.ts:337`
Add `effort: currentEffort` to the `requestGateway('prompt.submit', { … })` payload. Read current tier from the composer store.

### 5e. Options query — `chat/index.tsx:205-224`
The `model.options` / `/api/model/options` response now carries `effort_tiers`; map it into the `effort` state. No new endpoint needed.

### 5f. i18n — `i18n/en.ts`
Strings: `effort.title`, tier labels/blurbs, the small-print warning. (Locales dir exists for other languages.)

---

## 6. UX / product reconciliation

The existing product lock (`robin/default_soul.py:20`) forbids the assistant from offering **model** choice ("there is nothing to choose"). The effort selector is consistent with that promise **because it exposes effort, not models** — users never see "DeepSeek V4 Pro", they see "Max effort". The model mapping stays hidden.
- **Action:** lightly update `default_soul.py` wording so the assistant may acknowledge the *effort* control if asked, while still never naming/offering models. (One-line tweak, reviewed with you.)
- Keep the selector's small print honest about cost/limits (matches Claude's pattern and the "keep things reversible / per-action consent" ethos in the hero copy).

---

## 7. ~~Bug fix bundled in~~ — DROPPED (false alarm)

Investigated: `robin/models.py:1170` silent fallback `deepseek/deepseek-v4-flash` is judged against EnergyIR's catalog, not Together's public list — and it **is** in `_PROVIDER_MODELS["nous"]` (`:170`). `get_default_model_for_provider` only returns the override when it's in that curated list; repointing to `gpt-oss-120b` (not in the list) would fall through to `models[0]` = `anthropic/claude-opus-4.8` — re-introducing the exact billing footgun the override exists to prevent. **Left unchanged.**

---

## 8. Edge cases & guards

- **Free-tier users:** `partition_nous_models_by_tier` / `is_nous_free_tier` (`robin/models.py:516-569`) — if a tier's model isn't entitled, gray it out in the selector ("Currently unavailable", like Fable 5 in Image #1) and clamp the effective model to the best entitled tier. Never silently bill a blocked model.
- **Unknown/again-removed model id:** `effort_to_model` validates against the live model list when available; unknown → fall back to default tier, log once.
- **Mid-chat switch cost:** switching effort changes the model for the *next* turn; in-flight turns finish on their current model. Surface the active tier in the composer chip so it's never ambiguous.
- **Misrouting risk:** a hard task on Quick may loop/retry and cost more. The selector is user-driven so this is their call; optionally add a future "Auto" tier (the heuristic+triage router from the earlier investigation) as a 4th option — out of scope for this round, noted in §10.
- **Cache economics:** V4 Pro input drops ~10.5× when prompt prefix is cached. Existing Anthropic-style prompt-cache policy (`run_agent.py:1184`) — verify nous/DeepSeek path benefits; if so, Max effort is cheaper than headline price for long sessions. (Investigate during impl.)

---

## 9. Testing

- **Unit:** `effort_to_model` (each tier, unknown id, missing config block → fallback); `get_default_effort`.
- **Backend integration:** `prompt.submit` with each effort builds/switches to the right model; omitting effort uses Balanced default; aux tasks still resolve to gpt-oss-120b (assert unaffected).
- **Live switch:** change effort mid-conversation → `switch_model` invoked, next turn uses new model, history preserved.
- **Frontend:** selector renders 3 tiers from `model.options`, selection persists per conversation, payload includes `effort`, disabled/grayed tier for free users.
- **Regression:** the v4-flash fallback fix — `get_default_model_for_provider("nous")` returns the served model.
- **Manual:** run the desktop app (`/run`), verify the popover matches Image #1 layout and sits at the input bar (Image #3).

---

## 10. Out of scope (future)
- **Auto tier:** automatic per-turn routing (heuristics + cheap triage call, escalate on signal) from the earlier cost investigation — would slot in as a 4th "Auto" effort.
- **Per-message (vs per-conversation) effort** — current plan is per-conversation; per-message is a small delta if wanted later.
- **Thinking toggle** (Image #1 has one) — DeepSeek reasoning on/off as a sub-control; defer until tier behavior is validated.

---

## 11. Implementation order (when approved)
1. Bug fix §7 (standalone, safe).
2. Config schema §3 + resolver §4a (+ unit tests §9).
3. Gateway plumbing §4b + global options §4c.
4. Frontend selector §5.
5. UX wording §6.
6. Tests §9 + manual verify.

Estimated surface: ~2 new helpers + 1 config block (backend), ~1 new component + state/payload wiring (frontend), 1 bug fix. No schema migrations (session dict is unstructured).
