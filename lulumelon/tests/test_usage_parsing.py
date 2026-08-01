"""Reading what a call consumed, stated as the ways it must not be misread.

The four numbers this file is about become permanent the moment they enter the
ledger, and they are the ones a dollar figure is computed from. Every test here
exists because the same fact, "the provider did not say", has more than one
plausible wrong encoding, and each wrong encoding turns into a confident number
somewhere downstream.
"""

from __future__ import annotations

import json
import urllib.request

import pytest

from lulumelon.collect.ask import PerplexityProvider, _usage
from lulumelon.prices import estimate, fees, price_for, reported
from lulumelon.tests.test_ask import KEY, answering, reply


def usage_of(**raw) -> object:
    return _usage({"usage": raw})


# -- absent is not zero -----------------------------------------------------


def test_a_response_with_no_usage_block_reports_nothing_known():
    got = _usage({"choices": []})
    assert got.known is False
    assert got.input_tokens is None and got.output_tokens is None
    assert got.cost_usd is None


def test_a_measured_zero_is_kept_as_a_measured_zero():
    """Zero tokens is a claim. It must survive as one, distinct from silence."""
    got = usage_of(prompt_tokens=0, completion_tokens=0)
    assert got.known is True
    assert got.input_tokens == 0 and got.output_tokens == 0


def test_a_renamed_token_field_reads_as_unknown_not_as_zero():
    got = usage_of(inputTokens=12, outputTokens=3)
    assert got.input_tokens is None and got.output_tokens is None
    assert got.known is False


def test_the_agent_api_names_are_read_too():
    """The successor API renames both counts; one provider class covers both."""
    got = usage_of(input_tokens=101, output_tokens=42)
    assert (got.input_tokens, got.output_tokens) == (101, 42)


def test_a_boolean_is_not_one_token():
    """`isinstance(True, int)` is True in Python, so this needs saying."""
    got = usage_of(prompt_tokens=True, completion_tokens=False)
    assert got.input_tokens is None and got.output_tokens is None


def test_a_token_count_sent_as_text_is_not_silently_accepted():
    assert usage_of(prompt_tokens="512").input_tokens is None


def test_a_missing_search_context_is_unknown_not_empty():
    """It decides which request-fee band applies, so "" and None differ."""
    assert usage_of(prompt_tokens=1).search_context is None
    assert usage_of(prompt_tokens=1, search_context_size="low").search_context == "low"


# -- the provider's own cost figure -----------------------------------------


def test_the_documented_cost_path_is_read():
    assert usage_of(prompt_tokens=1, cost={"total_cost": 0.0061}).cost_usd == 0.0061


def test_an_undocumented_cost_path_is_not_invented():
    """Only `usage.cost.total_cost` is specified, so only it is looked for.

    Probing for names nobody publishes costs nothing right up until one of them
    matches something that is not a total.
    """
    assert usage_of(prompt_tokens=1, total_cost=9.99).cost_usd is None
    assert usage_of(prompt_tokens=1, cost={"total_cost_usd": 9.99}).cost_usd is None


def test_a_non_finite_cost_is_refused():
    assert usage_of(prompt_tokens=1, cost={"total_cost": float("inf")}).cost_usd is None


def test_a_boolean_cost_is_not_one_dollar():
    assert usage_of(prompt_tokens=1, cost={"total_cost": True}).cost_usd is None


# -- the wire, end to end ---------------------------------------------------


def test_usage_survives_the_round_trip_from_a_response(monkeypatch):
    payload = reply(
        "Marx does.",
        model="sonar",
        usage={
            "prompt_tokens": 118,
            "completion_tokens": 64,
            "total_tokens": 182,
            "search_context_size": "low",
            "cost": {"input_tokens_cost": 0.000118, "output_tokens_cost": 0.000064,
                     "request_cost": 0.005, "total_cost": 0.005182},
        },
    )
    monkeypatch.setattr(urllib.request, "urlopen", answering(payload))
    got = PerplexityProvider(api_key=KEY).ask("who trades agents?")
    assert got.usage.input_tokens == 118
    assert got.usage.output_tokens == 64
    assert got.usage.search_context == "low"
    assert got.usage.cost_usd == 0.005182


def test_a_failed_call_claims_no_usage(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", answering(reply("")))
    got = PerplexityProvider(api_key=KEY).ask("q")
    assert got.usage.known is False


def test_the_documented_endpoint_is_the_one_called(monkeypatch):
    """An undocumented route gets no deprecation notice when it goes."""
    captured: list = []
    monkeypatch.setattr(urllib.request, "urlopen", answering(reply("x"), capture=captured))
    PerplexityProvider(api_key=KEY).ask("q")
    assert captured[0].full_url == "https://api.perplexity.ai/v1/sonar"


# -- pricing refuses to invent the missing term -----------------------------


def test_pricing_refuses_an_unmeasured_call():
    price = price_for("perplexity", "sonar")
    with pytest.raises(ValueError, match="use fees"):
        estimate(price, input_tokens=None, output_tokens=12)


def test_fees_say_they_are_a_floor():
    price = price_for("perplexity", "sonar")
    floor = fees(price, fee_units=200)
    assert floor.low_usd == pytest.approx(1.00)
    assert floor.high_usd == pytest.approx(2.40)
    assert floor.measured is False
    assert "no call metered yet" in floor.basis


def test_a_metered_amount_carries_no_band_and_says_who_said_it():
    exact = reported(0.005182)
    assert exact.exact and exact.measured
    assert "provider" in exact.basis


def test_a_fee_is_described_in_words_a_reader_recognises():
    """The first real run of setup printed "$10 per thousand searchs"."""
    from lulumelon.prices import price_for

    assert "per thousand searches" in price_for("anthropic", "claude-haiku-4-5").fee_text
    assert "per thousand requests" in price_for("perplexity", "sonar").fee_text
