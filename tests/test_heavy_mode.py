"""M3: Max-effort 'Heavy mode' trigger.

_apply_effort_to_agent appends HEAVY_GUIDANCE to the agent's ephemeral system prompt when
the session effort is 'max', and removes it otherwise — idempotently, without clobbering an
existing personality prompt already in the slot.
"""
from agent.prompt_builder import HEAVY_GUIDANCE
from tui_gateway.server import _apply_effort_to_agent


class _FakeAgent:
    provider = "together"
    model = "deepseek-ai/DeepSeek-V4-Pro"
    api_key = ""
    base_url = ""
    api_mode = ""

    def __init__(self, ephemeral=None):
        self.ephemeral_system_prompt = ephemeral

    def switch_model(self, *a, **kw):  # no-op; model already matches in these tests
        pass


def _heavy_present(agent):
    return bool(agent.ephemeral_system_prompt) and HEAVY_GUIDANCE in agent.ephemeral_system_prompt


def test_max_effort_injects_heavy():
    agent = _FakeAgent()
    _apply_effort_to_agent({"agent": agent, "effort": "max"})
    assert _heavy_present(agent)


def test_non_max_effort_has_no_heavy():
    agent = _FakeAgent()
    _apply_effort_to_agent({"agent": agent, "effort": "balanced"})
    assert not _heavy_present(agent)
    assert agent.ephemeral_system_prompt is None


def test_toggle_is_idempotent_and_preserves_personality():
    persona = "You speak like a terse senior researcher."
    agent = _FakeAgent(ephemeral=persona)
    # Max ON: persona preserved + heavy appended
    _apply_effort_to_agent({"agent": agent, "effort": "max"})
    assert persona in agent.ephemeral_system_prompt and _heavy_present(agent)
    # Max again: no duplication
    _apply_effort_to_agent({"agent": agent, "effort": "max"})
    assert agent.ephemeral_system_prompt.count(HEAVY_GUIDANCE) == 1
    # Back to Balanced: heavy removed, persona intact
    _apply_effort_to_agent({"agent": agent, "effort": "balanced"})
    assert agent.ephemeral_system_prompt == persona


def test_heavy_guidance_routes_solvers_to_cheap_model():
    # The protocol tells the manager to delegate to cheap parallel workers, escalate
    # to the strong tier only on hard pieces / verification failure, and synthesize.
    # It must use the SEMANTIC tiers ('fast'/'deep') — never leak a raw model slug.
    g = HEAVY_GUIDANCE.lower()
    assert "delegate_task" in HEAVY_GUIDANCE
    assert "'fast'" in HEAVY_GUIDANCE and "'deep'" in HEAVY_GUIDANCE
    assert "deepseek" not in g  # model identity must not appear in the prompt
    assert "decompose" in g and "escalat" in g
    assert "verif" in g and "synthe" in g


def test_max_installs_cheap_default_and_tier_resolver():
    from robin.models import effort_to_model

    fast, _ = effort_to_model("balanced")
    deep, _ = effort_to_model("max")
    agent = _FakeAgent()
    _apply_effort_to_agent({"agent": agent, "effort": "max"})
    # Cost guardrail: un-tagged delegated workers default to the CHEAP model.
    assert agent._delegate_default_model == fast
    # Semantic escalation: 'fast'->cheap, 'deep'->strong; unknown -> None (raw passthrough).
    assert agent._delegate_model_resolver("fast") == fast
    assert agent._delegate_model_resolver("deep") == deep
    assert agent._delegate_model_resolver("nonsense") is None


def test_non_max_clears_delegate_routing():
    agent = _FakeAgent()
    _apply_effort_to_agent({"agent": agent, "effort": "max"})
    _apply_effort_to_agent({"agent": agent, "effort": "balanced"})
    assert agent._delegate_default_model is None
    assert agent._delegate_model_resolver is None


def test_resolve_delegate_model_precedence():
    from tools.delegate_tool import _resolve_delegate_model

    class A:
        _delegate_model_resolver = staticmethod(
            lambda alias: {"fast": "cheap-x", "deep": "strong-x"}.get(alias)
        )
        _delegate_default_model = "cheap-x"

    a = A()
    # explicit alias -> mapped through resolver
    assert _resolve_delegate_model(a, "deep", None) == "strong-x"
    # explicit unknown -> passed through verbatim (raw slug)
    assert _resolve_delegate_model(a, "some/raw-slug", None) == "some/raw-slug"
    # no request in heavy mode -> cheap default guardrail
    assert _resolve_delegate_model(a, None, "creds-model") == "cheap-x"
    # no request, no heavy default -> falls back to delegation creds (prior behavior)
    class B:
        pass
    assert _resolve_delegate_model(B(), None, "creds-model") == "creds-model"
    assert _resolve_delegate_model(B(), None, None) is None
