"""Integration tests for effort plumbing in tui_gateway.server.

Covers the live same-endpoint model swap (_apply_effort_to_agent) — the piece
that handles a mid-conversation effort change. The first-build override path is
exercised indirectly via _make_agent's branch (guarded on provider == 'nous').
"""

from unittest.mock import MagicMock


class _FakeAgent:
    def __init__(self, model, provider, base_url="https://ep/v1", api_key="k", api_mode="chat_completions"):
        self.model = model
        self.provider = provider
        self.base_url = base_url
        self.api_key = api_key
        self.api_mode = api_mode
        self.switch_calls = []

    def switch_model(self, new_model, new_provider, api_key="", base_url="", api_mode=""):
        self.switch_calls.append((new_model, new_provider, api_key, base_url, api_mode))
        self.model = new_model
        self.provider = new_provider


def test_apply_effort_swaps_model_on_nous():
    import tui_gateway.server as s
    agent = _FakeAgent(model="deepseek/deepseek-v4-pro", provider="nous")
    session = {"agent": agent, "effort": "balanced"}
    s._apply_effort_to_agent(session)
    assert agent.model == "deepseek/deepseek-v4-flash"
    # reused the same endpoint creds (same-provider swap)
    assert agent.switch_calls == [
        ("deepseek/deepseek-v4-flash", "nous", "k", "https://ep/v1", "chat_completions")
    ]


def test_apply_effort_noop_when_model_already_matches():
    import tui_gateway.server as s
    agent = _FakeAgent(model="deepseek/deepseek-v4-flash", provider="nous")
    session = {"agent": agent, "effort": "balanced"}
    s._apply_effort_to_agent(session)
    assert agent.switch_calls == []


def test_apply_effort_noop_on_non_nous_provider():
    """Tier slugs are nous-specific; never swap on another backend."""
    import tui_gateway.server as s
    agent = _FakeAgent(model="gpt-5.4", provider="openai")
    session = {"agent": agent, "effort": "max"}
    s._apply_effort_to_agent(session)
    assert agent.switch_calls == []
    assert agent.model == "gpt-5.4"


def test_apply_effort_noop_when_no_effort_or_agent():
    import tui_gateway.server as s
    s._apply_effort_to_agent({"agent": None, "effort": "max"})  # no agent
    agent = _FakeAgent(model="x", provider="nous")
    s._apply_effort_to_agent({"agent": agent, "effort": None})  # no effort
    assert agent.switch_calls == []


def test_apply_effort_swallows_switch_failure():
    """A failed swap must not raise — the turn proceeds on the old model."""
    import tui_gateway.server as s
    agent = _FakeAgent(model="deepseek/deepseek-v4-pro", provider="nous")
    agent.switch_model = MagicMock(side_effect=RuntimeError("boom"))
    session = {"agent": agent, "effort": "quick"}
    s._apply_effort_to_agent(session)  # must not raise
    assert agent.model == "deepseek/deepseek-v4-pro"  # unchanged


def test_apply_effort_to_max_tier():
    import tui_gateway.server as s
    agent = _FakeAgent(model="deepseek/deepseek-v4-flash", provider="nous")
    session = {"agent": agent, "effort": "max"}
    s._apply_effort_to_agent(session)
    assert agent.model == "deepseek/deepseek-v4-pro"
