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
    # The protocol must tell the manager to run parallel solvers on the cheap model.
    assert "delegate_task" in HEAVY_GUIDANCE
    assert "deepseek-ai/DeepSeek-V4-Flash" in HEAVY_GUIDANCE
    assert "verify" in HEAVY_GUIDANCE.lower() and "synthe" in HEAVY_GUIDANCE.lower()
