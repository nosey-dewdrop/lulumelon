"""The suite cannot spend money, and that is enforced rather than promised.

Every provider in this package is billed per call, and one of them is billed
per search the model chooses to run inside a call. A test suite that reaches a
real endpoint by accident does not fail loudly, it succeeds and sends an
invoice, and the person who finds out is the customer whose key was in the
environment at the time.

So the guarantee is not a convention about writing tests carefully. Sockets are
closed for the whole run. A test that tries to open one fails on the spot and
names itself, which is the only version of this promise that survives somebody
adding a test in a hurry.
"""

from __future__ import annotations

import socket

import pytest


class NetworkUsedInTests(RuntimeError):
    """A test tried to open a connection, which would have cost real money."""


@pytest.fixture(autouse=True)
def no_network(monkeypatch, request):
    """Refuse every outbound connection for the duration of one test."""

    def refuse(*args, **kwargs):
        raise NetworkUsedInTests(
            f"{request.node.nodeid} tried to open a socket. Every provider here bills per "
            "call, so the suite runs with the network closed and the collector is exercised "
            "through the deterministic stub instead."
        )

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
