"""The one place that talks to the network: what it records, and what it hides."""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request

from collect.ask import UNKNOWN_MODEL, PerplexityProvider
from keys import REDACTED

KEY = "pplx-" + "a1b2c3d4e5" * 4


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


def raising(exc):
    def urlopen(req, timeout=None):
        raise exc

    return urlopen


def reply(content: str, **extra) -> dict:
    return {"choices": [{"message": {"content": content}}], **extra}


def test_the_model_recorded_is_the_one_the_response_names(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", answering(reply("nike leads.", model="sonar-2026-07")))
    got = PerplexityProvider(api_key=KEY, model="sonar").ask("best running shoe?")
    assert got.ok
    assert got.text == "nike leads."
    assert got.model == "sonar-2026-07"


def test_a_response_that_names_no_model_is_recorded_as_unknown(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", answering(reply("nike leads.")))
    assert PerplexityProvider(api_key=KEY).ask("q").model == UNKNOWN_MODEL


def test_sources_are_read_from_either_field_the_api_has_used(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", answering(reply("x", citations=["https://a.example"])))
    assert PerplexityProvider(api_key=KEY).ask("q").citations == ("https://a.example",)

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        answering(reply("x", search_results=[{"url": "https://b.example", "title": "b"}])),
    )
    assert PerplexityProvider(api_key=KEY).ask("q").citations == ("https://b.example",)


def test_the_key_is_sent_as_a_bearer_header(monkeypatch):
    seen: list = []
    monkeypatch.setattr(urllib.request, "urlopen", answering(reply("x"), capture=seen))
    PerplexityProvider(api_key=KEY).ask("q")
    assert seen[0].get_header("Authorization") == f"Bearer {KEY}"


def test_the_surface_is_recorded_as_the_api_not_as_a_person(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", answering(reply("x")))
    assert PerplexityProvider(api_key=KEY).ask("q").surface == "api"


# -- failures are observations ----------------------------------------------


def test_a_rejected_key_comes_back_as_a_recorded_error_not_an_exception(monkeypatch):
    body = json.dumps({"error": {"message": "Invalid API key provided.", "code": 401}}).encode()
    err = urllib.error.HTTPError("https://api.perplexity.ai", 401, "Unauthorized", {}, io.BytesIO(body))
    monkeypatch.setattr(urllib.request, "urlopen", raising(err))
    got = PerplexityProvider(api_key=KEY).ask("q")
    assert not got.ok
    assert got.status == "error"
    assert "http 401" in got.error
    assert "Invalid API key provided." in got.error


def test_a_network_failure_keeps_the_reason(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", raising(TimeoutError("timed out")))
    got = PerplexityProvider(api_key=KEY).ask("q")
    assert not got.ok
    assert "TimeoutError" in got.error


def test_a_response_of_an_unexpected_shape_is_an_error_not_a_crash(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", answering({"unexpected": True}))
    got = PerplexityProvider(api_key=KEY).ask("q")
    assert not got.ok
    assert "unexpected response shape" in got.error


# -- the key stays out of everything ----------------------------------------


def test_the_provider_does_not_print_its_key():
    provider = PerplexityProvider(api_key=KEY)
    assert KEY not in repr(provider)
    assert "perplexity" in repr(provider)


def test_a_provider_that_echoes_the_key_back_does_not_get_it_into_the_record(monkeypatch):
    body = f"bad request for key {KEY}".encode()
    err = urllib.error.HTTPError("https://api.perplexity.ai", 400, "Bad Request", {}, io.BytesIO(body))
    monkeypatch.setattr(urllib.request, "urlopen", raising(err))
    got = PerplexityProvider(api_key=KEY).ask("q")
    assert KEY not in got.error
    assert REDACTED in got.error
