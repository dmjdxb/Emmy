"""Together AI provider profile.

Together AI is an OpenAI-compatible cloud inference API (base URL
``https://api.together.xyz/v1``, namespaced model IDs such as
``deepseek-ai/DeepSeek-V4-Pro``). It implements chat completions with function
calling and structured output, but NOT the OpenAI Responses/Assistants APIs —
so the agent loop is driven by Robin's own function-calling harness, which is
exactly the supported pattern.

This is the configured default provider for Robin (by EnergyIR): the model is
hosted by Together AI (US) — it is not run locally on the user's device.

DeepSeek V4 served through Together uses the same thinking-mode wire contract as
DeepSeek's own endpoint (``extra_body.thinking`` + top-level
``reasoning_effort``). The only difference is the model ID is namespaced
(``deepseek-ai/DeepSeek-V4-Pro`` rather than ``deepseek-v4-pro``), so the
capability check strips the ``<vendor>/`` prefix before matching.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

from providers import register_provider
from providers.base import ProviderProfile

# Robin's managed-inference endpoint = the EnergyIR gateway (api.energyir.io). Customers authenticate with
# their eir-robin- key (stored in TOGETHER_API_KEY); the gateway proxies to DeepSeek V4 Pro via the hidden
# platform key, preserving full agentic fidelity (tools, history, streaming). Customers never see Together.
# Dev override: set ENERGYIR_BASE_URL (e.g. https://api.together.xyz/v1) to talk to Together directly with
# a Together key — useful for development without an eir-robin- key.
_DEFAULT_BASE_URL = "https://api.energyir.io/v1"
_BASE_URL = (os.environ.get("ENERGYIR_BASE_URL", "").strip() or _DEFAULT_BASE_URL).rstrip("/")
_HOSTNAME = urlparse(_BASE_URL).hostname or "api.energyir.io"


def _bare_model(model: str | None) -> str:
    """Strip the Together ``<vendor>/`` namespace and lowercase.

    ``deepseek-ai/DeepSeek-V4-Pro`` -> ``deepseek-v4-pro``.
    """
    m = (model or "").strip().lower()
    if "/" in m:
        m = m.rsplit("/", 1)[-1]
    return m


def _model_supports_thinking(model: str | None) -> bool:
    """DeepSeek V4+ family served via Together exposes thinking mode."""
    m = _bare_model(model)
    if not m:
        return False
    # deepseek-v4-*, deepseek-v5-*, etc. — every V4+ generation has thinking.
    if m.startswith("deepseek-v") and not m.startswith("deepseek-v3"):
        return True
    return False


class TogetherProfile(ProviderProfile):
    """Together AI — OpenAI-compatible; DeepSeek V4 thinking-mode passthrough."""

    def build_api_kwargs_extras(
        self, *, reasoning_config: dict | None = None, model: str | None = None, **context
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        extra_body: dict[str, Any] = {}
        top_level: dict[str, Any] = {}

        if not _model_supports_thinking(model):
            # Non-DeepSeek-V4 Together models (Llama, Qwen, …) — leave the wire
            # format untouched.
            return extra_body, top_level

        # DeepSeek V4 on Together mirrors the native DeepSeek contract: the
        # thinking type must be set explicitly to avoid the reasoning_content
        # echo trap on subsequent turns after a tool call.
        enabled = True
        if isinstance(reasoning_config, dict) and reasoning_config.get("enabled") is False:
            enabled = False

        extra_body["thinking"] = {"type": "enabled" if enabled else "disabled"}

        if not enabled:
            return extra_body, top_level

        # Effort mapping: pass low/medium/high through; xhigh/max → max.
        if isinstance(reasoning_config, dict):
            effort = (reasoning_config.get("effort") or "").strip().lower()
            if effort in {"xhigh", "max"}:
                top_level["reasoning_effort"] = "max"
            elif effort in {"low", "medium", "high"}:
                top_level["reasoning_effort"] = effort

        return extra_body, top_level


together = TogetherProfile(
    name="together",
    aliases=("togetherai", "together-ai"),
    env_vars=("TOGETHER_API_KEY",),
    display_name="EnergyIR",
    description="EnergyIR — managed inference for Robin",
    signup_url="https://energyir.io",
    base_url=_BASE_URL,
    models_url=f"{_BASE_URL}/models",
    hostname=_HOSTNAME,
    supports_vision=True,
    # Curated agentic, tool-calling models shown in the picker when live fetch
    # fails. DeepSeek V4 Pro is Robin's configured default; Flash is the
    # cheaper/faster option for simple, high-volume turns.
    fallback_models=(
        "deepseek-ai/DeepSeek-V4-Pro",
        "deepseek-ai/DeepSeek-V4-Flash",
        "Qwen/Qwen3-235B-A22B-Instruct",
        "meta-llama/Llama-4-Maverick-Instruct",
    ),
    # Cheap model for auxiliary work (context compression, vision aux, etc.).
    default_aux_model="deepseek-ai/DeepSeek-V4-Flash",
)

register_provider(together)
