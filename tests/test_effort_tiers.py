"""Tests for the effort ladder — robin.models effort tier resolver.

The effort tier sets the PRIMARY chat model only; auxiliary tasks are
independent and not covered here.
"""

from unittest.mock import patch


class TestEffortTiers:
    """Unit tests for get_effort_tiers / get_default_effort / effort_to_model."""

    def test_default_tiers_present_and_ordered(self):
        from robin.models import get_effort_tiers
        tiers = get_effort_tiers()
        ids = [t["id"] for t in tiers]
        assert ids == ["quick", "balanced", "max"]
        # cheapest-first ordering via cost_hint
        hints = [t["cost_hint"] for t in tiers]
        assert hints == sorted(hints)

    def test_each_tier_has_required_fields(self):
        from robin.models import get_effort_tiers
        for t in get_effort_tiers():
            assert t.get("id") and t.get("model")
            assert "label" in t and "blurb" in t

    def test_default_effort_is_balanced(self):
        from robin.models import get_default_effort
        assert get_default_effort() == "balanced"

    def test_effort_to_model_each_tier(self):
        from robin.models import effort_to_model
        assert effort_to_model("quick") == ("openai/gpt-oss-120b", "auto")
        assert effort_to_model("balanced") == ("deepseek/deepseek-v4-flash", "auto")
        assert effort_to_model("max") == ("deepseek/deepseek-v4-pro", "auto")

    def test_unknown_effort_falls_back_to_default(self):
        from robin.models import effort_to_model, get_default_effort, get_effort_tier
        model, provider = effort_to_model("does-not-exist")
        default_tier = get_effort_tier(get_default_effort())
        assert (model, provider) == (default_tier["model"], "auto")

    def test_none_effort_falls_back_to_default(self):
        from robin.models import effort_to_model, get_default_effort, get_effort_tier
        assert effort_to_model(None)[0] == get_effort_tier(get_default_effort())["model"]

    def test_balanced_is_cheaper_than_max(self):
        """Sanity: the default tier must cost less than Max effort."""
        from robin.models import get_effort_tier
        assert get_effort_tier("balanced")["cost_hint"] < get_effort_tier("max")["cost_hint"]

    def test_aux_invariant_quick_matches_aux_model(self):
        """Quick tier reuses the same cheap model the aux tasks already use,
        confirming it is a served slug in the nous catalog."""
        from robin.models import effort_to_model
        assert effort_to_model("quick")[0] == "openai/gpt-oss-120b"


class TestEffortTiersConfigOverride:
    """The config block is the source of truth; helpers fall back when absent."""

    def test_config_tiers_override_fallback(self):
        custom = {
            "default": "eco",
            "tiers": [
                {"id": "eco", "label": "Eco", "model": "vendor/cheap", "provider": "auto", "cost_hint": 1},
                {"id": "turbo", "label": "Turbo", "model": "vendor/big", "provider": "auto", "cost_hint": 2},
            ],
        }
        with patch("robin.config.load_config", return_value={"effort_tiers": custom}):
            from robin.models import get_effort_tiers, get_default_effort, effort_to_model
            assert [t["id"] for t in get_effort_tiers()] == ["eco", "turbo"]
            assert get_default_effort() == "eco"
            assert effort_to_model("turbo") == ("vendor/big", "auto")

    def test_malformed_config_falls_back_to_constant(self):
        from robin.models import EFFORT_TIERS_FALLBACK
        for bad in ({"effort_tiers": {"tiers": "nope"}}, {"effort_tiers": {}}, {}, None):
            with patch("robin.config.load_config", return_value=bad):
                from robin.models import get_effort_tiers
                assert get_effort_tiers() == list(EFFORT_TIERS_FALLBACK)

    def test_invalid_default_falls_back_to_balanced(self):
        custom = {"default": "ghost", "tiers": None}
        with patch("robin.config.load_config", return_value={"effort_tiers": custom}):
            from robin.models import get_default_effort
            assert get_default_effort() == "balanced"

    def test_load_config_exception_is_swallowed(self):
        with patch("robin.config.load_config", side_effect=RuntimeError("boom")):
            from robin.models import get_effort_tiers, EFFORT_TIERS_FALLBACK
            assert get_effort_tiers() == list(EFFORT_TIERS_FALLBACK)
