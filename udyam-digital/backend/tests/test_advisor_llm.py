"""Gemini advisor path. A fake client mimics google-genai's `client.models.generate_content`, so the
tests pin down exactly what is sent (one call, with everything in the first message) and that the
server still re-validates whatever comes back."""
import json
from types import SimpleNamespace

import config
from advisor import agent
from rules.eligibility import Profile, eligible_products
from rules.quote import build_quote

SHOP = {"segment": "micro", "city_tier": 2, "employee_count": 2, "num_sites": 1, "has_active_gstin": False}
CLINIC = {"segment": "prof", "city_tier": 1, "employee_count": 12, "num_sites": 1, "has_active_gstin": True}
GOOD = '{"value":["P01","P07"],"lite":["P04","P07"],"rationale":"Tailored to you."}'


def ids(q):
    return [p["product_id"] for p in q["products"]]


def _resp(parts):
    return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=parts, role="model"))])


class OneShot:
    """Default single-call mode: the model answers straight away."""
    def __init__(self, answer, thought=None):
        self.answer, self.thought, self.seen = answer, thought, []
        self.models = SimpleNamespace(generate_content=self.generate_content)

    @property
    def calls(self):
        return len(self.seen)

    def generate_content(self, model, contents, config):
        self.seen.append((model, list(contents), config))
        parts = []
        if self.thought:
            parts.append(SimpleNamespace(function_call=None, text=self.thought, thought=True))
        parts.append(SimpleNamespace(function_call=None, text=self.answer, thought=False))
        return _resp(parts)

    def brief(self):
        return json.loads(self.seen[0][1][0].parts[0].text)


# ------------------------------------------------------------- single-call mode
def test_default_mode_resolves_in_a_single_model_call():
    fc = OneShot(GOOD)
    r = agent.recommend(SHOP, client=fc)
    assert fc.calls == 1 and r["source"] == "llm" and "Tailored to you." in r["rationale"]


def test_first_message_carries_catalogue_bundles_prices_and_priority(store):
    fc = OneShot(GOOD)
    agent.recommend(CLINIC, current_spend=3500, priority="customers", language="hi", client=fc)
    b = fc.brief()
    # the ELIGIBLE catalogue only, nothing else
    assert {c["product_id"] for c in b["eligible_catalogue"]} == set(eligible_products(Profile.from_dict(CLINIC)))
    # the owner's answers are in the prompt
    assert b["owner"]["top_priority"] == "customers" and b["owner"]["current_monthly_spend_inr"] == 3500
    assert b["owner"]["preferred_language"] == "Hindi"
    assert "Reaching customers" in b["owner"]["top_priority_meaning"]
    # starting bundles carry the server's own totals
    sv = b["starting_point"]["value"]
    assert sv["monthly_inr"] == build_quote("prof", 1, sv["product_ids"])["monthly_inr"]
    assert "P15" in sv["product_ids"] and sv["added_because"]["P15"] == "priority:customers"
    # per-product prices equal what the quote engine charges for that product
    by_id = {c["product_id"]: c for c in b["eligible_catalogue"]}
    for pid in ("P02", "P08", "P16"):
        assert by_id[pid]["monthly_inr_value_pricing"] == build_quote("prof", 1, [pid])["lines"][0]["monthly_inr"]
        assert by_id[pid]["monthly_inr_lite_pricing"] == \
            build_quote("prof", 1, [pid], price_mode="floor")["lines"][0]["monthly_inr"]


def test_priority_reaches_the_prompt_and_changes_the_starting_point():
    a, b = OneShot(GOOD), OneShot(GOOD)
    agent.recommend(CLINIC, priority="customers", client=a)
    agent.recommend(CLINIC, priority="security", client=b)
    assert a.brief()["owner"]["top_priority"] != b.brief()["owner"]["top_priority"]
    assert a.brief()["starting_point"]["value"]["product_ids"] != b.brief()["starting_point"]["value"]["product_ids"]
    assert "top_priority" in a.seen[0][2].system_instruction


def test_per_site_prices_in_the_prompt_scale_with_sites():
    multi = {"segment": "multi", "city_tier": 1, "employee_count": 30, "num_sites": 4, "has_active_gstin": True}
    fc = OneShot(GOOD)
    agent.recommend(multi, client=fc)
    p02 = next(c for c in fc.brief()["eligible_catalogue"] if c["product_id"] == "P02")
    assert p02["monthly_inr_value_pricing"] == 1650 * 4


def test_single_call_request_is_json_constrained_and_declares_no_tools():
    fc = OneShot(GOOD)
    agent.recommend(SHOP, client=fc)
    model, _, cfg = fc.seen[0]
    assert model.startswith("gemini") and cfg.response_mime_type == "application/json"
    assert not cfg.tools
    assert set(cfg.response_schema["required"]) == {"value", "lite", "rationale"}


def test_refused_requests_are_passed_so_the_model_does_not_re_add_them():
    fc = OneShot(GOOD)
    agent.recommend(SHOP, requested=["P10"], client=fc)
    assert fc.brief()["refused_requests"] == ["Managed SD-WAN"]


# --------------------------------------------------- the server backstop is kept
def test_llm_output_is_still_revalidated_server_side():
    ans = '{"value":["P01","P07","P10","P05","P99"],"lite":["P04","P07"],"rationale":"Good fit."}'
    r = agent.recommend(SHOP, client=OneShot(ans))
    got = set(ids(r["value"]))
    assert r["source"] == "llm" and not ({"P10", "P05", "P99"} & got) and {"P01", "P07"} <= got


def test_prices_come_from_the_server_not_the_model():
    ans = '{"value":["P01"],"lite":["P04"],"rationale":"Only Rs 1 per month!"}'
    r = agent.recommend(SHOP, client=OneShot(ans))
    assert r["value"]["monthly_inr"] == 999            # micro floor price of P01, from the quote engine


def test_llm_that_drops_the_internet_line_falls_back_to_the_rules_bundle():
    r = agent.recommend(SHOP, client=OneShot('{"value":["P07"],"lite":["P07"],"rationale":"x"}'))
    assert any(p in ids(r["value"]) for p in ("P01", "P02", "P04"))


def test_thought_parts_are_not_treated_as_the_answer():
    r = agent.recommend(SHOP, client=OneShot(GOOD, thought="internal reasoning, not JSON"))
    assert r["source"] == "llm" and "Tailored to you." in r["rationale"]


def test_llm_failure_and_garbage_fall_back_to_rules():
    class Boom:
        models = SimpleNamespace(generate_content=lambda **k: (_ for _ in ()).throw(RuntimeError("down")))
    r = agent.recommend(SHOP, client=Boom())
    assert r["source"] == "rules" and "down" in r["llm_error"] and r["value"]["products"]
    r = agent.recommend(SHOP, client=OneShot("sorry, I cannot help with that"))
    assert r["source"] == "rules" and r["value"]["products"]


def test_rules_only_fallback_when_no_key_is_set(monkeypatch):
    monkeypatch.setattr(config, "USE_LLM", False)

    def no_client():
        raise AssertionError("the LLM must not be used without a key")
    monkeypatch.setattr(agent.llm, "make_client", no_client)
    r = agent.recommend(CLINIC, current_spend=3500, priority="customers")
    assert r["source"] == "rules" and "llm_error" not in r
    assert r["value"]["products"] and r["lite"]["products"] and r["rationale"]


# ------------------- optional multi-round tool-calling mode (LLM_USE_TOOLS=1 / use_tools=True)
class ToolFake:
    """Round 1 the model asks for the catalogue; round 2 it answers (with ineligible products in it)."""
    def __init__(self, answer):
        self.answer, self.seen = answer, []
        self.models = SimpleNamespace(generate_content=self.generate_content)

    def generate_content(self, model, contents, config):
        self.seen.append((model, list(contents), config))
        if len(self.seen) == 1:
            fc = SimpleNamespace(name="get_catalogue", args={})
            return _resp([SimpleNamespace(function_call=fc, text=None, thought=False)])
        return _resp([SimpleNamespace(function_call=None, text=self.answer, thought=False)])


def test_tool_mode_still_works_and_only_offers_eligible_products(store):
    ans = '{"value":["P01","P07","P10","P05"],"lite":["P04","P07"],"rationale":"Good fit."}'
    fc = ToolFake(ans)
    r = agent.recommend(SHOP, client=fc, use_tools=True)
    assert len(fc.seen) == 2 and r["source"] == "llm"
    assert not ({"P10", "P05"} & set(ids(r["value"])))
    offered = {p["product_id"] for p in fc.seen[1][1][-1].parts[0].function_response.response["result"]}
    assert offered == set(eligible_products(Profile.from_dict(SHOP)))
    assert fc.seen[0][2].automatic_function_calling.disable is True


def test_chatty_model_is_forced_to_answer_on_the_last_round():
    class Chatty(ToolFake):
        def generate_content(self, model, contents, config):
            self.seen.append((model, list(contents), config))
            forced = getattr(getattr(config, "tool_config", None), "function_calling_config", None)
            if forced is not None and str(getattr(forced, "mode", "")).endswith("NONE"):
                return _resp([SimpleNamespace(function_call=None, thought=False,
                                              text='{"value":["P01"],"lite":["P04"],"rationale":"Done."}')])
            fc = SimpleNamespace(name="get_catalogue", args={})
            return _resp([SimpleNamespace(function_call=fc, text=None, thought=False)])
    fc = Chatty("")
    r = agent.recommend(SHOP, client=fc, use_tools=True)
    from advisor import llm
    assert r["source"] == "llm" and "Done." in r["rationale"] and len(fc.seen) == llm.MAX_TOOL_ROUNDS


def test_thinking_level_is_sent_to_the_model(monkeypatch):
    monkeypatch.setattr(config, "LLM_THINKING_LEVEL", "LOW")
    fc = OneShot(GOOD)
    agent.recommend(SHOP, client=fc)
    assert str(fc.seen[0][2].thinking_config.thinking_level).endswith("LOW")
    monkeypatch.setattr(config, "LLM_THINKING_LEVEL", "")
    fc2 = OneShot(GOOD)
    agent.recommend(SHOP, client=fc2)
    assert fc2.seen[0][2].thinking_config is None


def test_default_thinking_level_is_low():
    import importlib
    import os
    saved = os.environ.pop("LLM_THINKING_LEVEL", None)
    try:
        assert importlib.reload(config).LLM_THINKING_LEVEL == "LOW"
    finally:
        if saved is not None:
            os.environ["LLM_THINKING_LEVEL"] = saved
        importlib.reload(config)


def test_warm_up_is_a_noop_without_a_key_and_never_raises(monkeypatch):
    from advisor import llm
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    assert llm.warm_up() is None

    monkeypatch.setattr(config, "LLM_API_KEY", "fake-key")

    def boom():
        raise RuntimeError("network down")
    monkeypatch.setattr(llm, "make_client", boom)
    assert llm.warm_up() is None                       # swallowed: startup must never fail because of the LLM
