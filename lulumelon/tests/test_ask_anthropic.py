"""The second engine, stated as the ways it could quietly measure the wrong thing.

Adding an engine to a visibility product is not plumbing. A number here is
about one door, and the published gap between doors is larger than the noise
this library exists to quantify, so a second provider is a second condition and
every way it can differ silently from the first is a defect.

Two failures matter most and neither of them is a crash.
`test_a_failed_search_is_not_a_question_with_no_sources` covers a search that
errored inside a successful response, which read carelessly becomes a measured
absence. `test_a_paused_turn_is_not_a_short_answer` covers a reply the API
stopped halfway, which read carelessly becomes an answer where the brand
happened not to come up.
"""

from __future__ import annotations

import io
import json
import urllib.request

import pytest

from lulumelon.collect.ask import (
    DEFAULT_MAX_SEARCHES,
    UNKNOWN_MODEL,
    WEB_SEARCH_TOOL,
    AnthropicProvider,
    PerplexityProvider,
    provider_for,
)
from lulumelon.keys import REDACTED

KEY = "sk-ant-" + "a1b2c3d4e5" * 4


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def answering(payload: dict, capture: list | None = None):
    def urlopen(req, timeout=None):
        if capture is not None:
            capture.append(req)
        return FakeResponse(json.dumps(payload).encode("utf-8"))

    return urlopen


def searched(*urls: str) -> dict:
    return {
        "type": "web_search_tool_result",
        "tool_use_id": "srvtoolu_1",
        "content": [
            {"type": "web_search_result", "url": u, "title": "t", "page_age": "x"} for u in urls
        ],
    }


def message(content: list, **extra) -> dict:
    base = {"content": content, "model": "claude-haiku-4-5", "stop_reason": "end_turn"}
    base.update(extra)
    return base


# -- the request the provider actually posts --------------------------------


def test_the_search_tool_is_asked_for_with_a_cap_on_its_own_fee(monkeypatch):
    """The cap is the price and the condition, so it travels on every call."""
    seen: list = []
    monkeypatch.setattr(
        urllib.request, "urlopen", answering(message([{"type": "text", "text": "ok"}]), seen)
    )
    AnthropicProvider(api_key=KEY, max_searches=4).ask("who should I use?")

    body = json.loads(seen[0].data.decode("utf-8"))
    assert body["tools"] == [
        {"type": WEB_SEARCH_TOOL, "name": "web_search", "max_uses": 4}
    ]
    assert body["messages"] == [{"role": "user", "content": "who should I use?"}]


def test_the_tool_version_is_pinned_rather_than_tracking_the_newest():
    """Later versions filter results with code written afresh per call.

    That changes what the model was shown, which is the condition being
    measured, so the version is a constant in this module rather than whatever
    the provider most recently shipped.
    """
    assert WEB_SEARCH_TOOL == "web_search_20250305"


def test_the_key_goes_in_the_header_the_api_documents(monkeypatch):
    seen: list = []
    monkeypatch.setattr(
        urllib.request, "urlopen", answering(message([{"type": "text", "text": "ok"}]), seen)
    )
    AnthropicProvider(api_key=KEY).ask("q")
    headers = {k.lower(): v for k, v in seen[0].header_items()}
    assert headers["X-api-key".lower()] == KEY
    assert headers["Anthropic-version".lower()] == "2023-06-01"


def test_a_round_with_no_search_at_all_is_refused_by_name():
    with pytest.raises(ValueError, match="ungrounded model"):
        AnthropicProvider(api_key=KEY, max_searches=0)


# -- what comes back --------------------------------------------------------


def test_the_answer_is_every_text_block_joined(monkeypatch):
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        answering(
            message(
                [
                    {"type": "text", "text": "I'll look. "},
                    {"type": "server_tool_use", "id": "srvtoolu_1", "name": "web_search"},
                    searched("https://a.example/guide"),
                    {"type": "text", "text": "marx is the usual pick."},
                ]
            )
        ),
    )
    got = AnthropicProvider(api_key=KEY).ask("q")
    assert got.ok
    assert got.text == "I'll look. marx is the usual pick."


def test_the_model_recorded_is_the_one_the_response_names(monkeypatch):
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        answering(message([{"type": "text", "text": "x"}], model="claude-haiku-4-5-20251001")),
    )
    assert AnthropicProvider(api_key=KEY).ask("q").model == "claude-haiku-4-5-20251001"


def test_a_response_that_names_no_model_is_recorded_as_unknown(monkeypatch):
    payload = message([{"type": "text", "text": "x"}])
    payload.pop("model")
    monkeypatch.setattr(urllib.request, "urlopen", answering(payload))
    assert AnthropicProvider(api_key=KEY).ask("q").model == UNKNOWN_MODEL


def test_the_pages_recorded_are_the_ones_retrieved_not_the_ones_quoted(monkeypatch):
    """Two observations arrive and only one travels.

    The response reports both the results a search returned and the subset the
    answer quoted. The other engine here reports only the first, so the first is
    what is recorded; pooling one engine's retrievals with another's citations
    would give the source graph two meanings and no label.
    """
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        answering(
            message(
                [
                    searched("https://a.example/guide", "https://b.example/list"),
                    {
                        "type": "text",
                        "text": "marx.",
                        "citations": [
                            {
                                "type": "web_search_result_location",
                                "url": "https://a.example/guide",
                                "title": "t",
                                "cited_text": "marx is",
                            }
                        ],
                    },
                ]
            )
        ),
    )
    got = AnthropicProvider(api_key=KEY).ask("q")
    assert got.citations == ("https://a.example/guide", "https://b.example/list")


def test_the_searches_it_ran_are_recorded_because_the_fee_multiplies_them(monkeypatch):
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        answering(
            message(
                [{"type": "text", "text": "x"}],
                usage={
                    "input_tokens": 6039,
                    "output_tokens": 931,
                    "server_tool_use": {"web_search_requests": 3},
                },
            )
        ),
    )
    usage = AnthropicProvider(api_key=KEY).ask("q").usage
    assert (usage.input_tokens, usage.output_tokens, usage.searches) == (6039, 931, 3)
    assert usage.known


def test_a_response_that_counts_no_searches_says_unknown_not_zero(monkeypatch):
    """Zero searches is a claim that a grounded call was not grounded."""
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        answering(message([{"type": "text", "text": "x"}], usage={"input_tokens": 10})),
    )
    usage = AnthropicProvider(api_key=KEY).ask("q").usage
    assert usage.searches is None
    assert usage.output_tokens is None


def test_no_cost_is_invented_from_our_own_table(monkeypatch):
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        answering(message([{"type": "text", "text": "x"}], usage={"input_tokens": 10, "output_tokens": 2})),
    )
    assert AnthropicProvider(api_key=KEY).ask("q").usage.cost_usd is None


# -- the two failures that arrive looking like successes --------------------


def test_a_failed_search_is_not_a_question_with_no_sources(monkeypatch):
    """The API answers 200 and puts the failure inside the body.

    Read as an empty result list it becomes "this question had no sources",
    which is a measurement claim nobody made and which pushes every visibility
    number down by however often the search happened to be rate limited.
    """
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        answering(
            message(
                [
                    {
                        "type": "web_search_tool_result",
                        "tool_use_id": "srvtoolu_1",
                        "content": {
                            "type": "web_search_tool_result_error",
                            "error_code": "too_many_requests",
                        },
                    },
                    {"type": "text", "text": "I could not look it up."},
                ]
            )
        ),
    )
    got = AnthropicProvider(api_key=KEY).ask("q")
    assert not got.ok
    assert "too_many_requests" in got.error
    assert got.citations == ()


def test_a_paused_turn_is_not_a_short_answer(monkeypatch):
    """A fragment recorded as a reply is a draw where the brand had less room."""
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        answering(message([{"type": "text", "text": "Let me search"}], stop_reason="pause_turn")),
    )
    got = AnthropicProvider(api_key=KEY).ask("q")
    assert not got.ok
    assert "fragment" in got.error


def test_a_shape_nobody_recognises_is_an_error_not_an_empty_answer(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", answering({"nothing": "familiar"}))
    got = AnthropicProvider(api_key=KEY).ask("q")
    assert not got.ok
    assert "unexpected response shape" in got.error


def test_the_key_never_travels_in_an_error(monkeypatch):
    def urlopen(req, timeout=None):
        raise RuntimeError(f"connection refused while sending {KEY}")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    got = AnthropicProvider(api_key=KEY).ask("q")
    assert KEY not in got.error
    assert REDACTED in got.error


# -- one place where an engine name becomes a class -------------------------


def test_the_factory_returns_the_engine_that_was_named():
    assert isinstance(provider_for("anthropic", KEY), AnthropicProvider)
    assert isinstance(provider_for("perplexity", "pplx-x"), PerplexityProvider)
    assert provider_for("anthropic", KEY, model="claude-opus-5").model == "claude-opus-5"


def test_an_engine_this_build_cannot_call_is_refused_with_the_list():
    with pytest.raises(ValueError, match="anthropic, perplexity"):
        provider_for("gemini", KEY)


def test_the_default_cap_is_low_enough_to_price_and_high_enough_to_search():
    assert 1 <= DEFAULT_MAX_SEARCHES <= 5
