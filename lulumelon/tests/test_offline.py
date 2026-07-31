"""The guarantee that the suite cannot spend money, checked rather than assumed.

`conftest.py` closes the network for every test. A guard nobody exercises is a
guard that can stop working without anybody noticing, and the failure mode here
is a test suite that quietly starts billing a customer's key.
"""

from __future__ import annotations

import socket
import urllib.request

import pytest

from lulumelon.collect.ask import AnthropicProvider, PerplexityProvider

# Matched by behaviour rather than by class. pytest loads `conftest` under its
# own module name, so importing the exception here would produce a second class
# object and a `pytest.raises` that never matches the one actually thrown.


def test_the_guard_refuses_a_connection_and_names_the_test():
    with pytest.raises(RuntimeError, match="tried to open a socket"):
        socket.create_connection(("example.com", 443))


def test_a_provider_that_reaches_the_network_fails_instead_of_billing():
    """The two classes that cost money, driven with the guard in place.

    Each returns a recorded failure rather than raising, which is the same
    behaviour a real outage produces, so this also shows that a blocked call
    lands in the ledger as an error rather than as a brand nobody mentioned.
    """
    for provider in (
        PerplexityProvider(api_key="pplx-" + "x" * 40),
        AnthropicProvider(api_key="sk-ant-" + "x" * 40),
    ):
        answer = provider.ask("who should I use?")
        assert not answer.ok
        assert answer.text == ""


def test_the_guard_covers_the_call_the_providers_actually_make():
    with pytest.raises(RuntimeError, match="tried to open a socket"):
        urllib.request.urlopen("https://example.com", timeout=1)
