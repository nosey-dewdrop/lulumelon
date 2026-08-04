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

The other thing here is a round that no collector can produce, for a failure
that no collectable round would have shown.
"""

from __future__ import annotations

import socket

import pytest

from lulumelon.collect import Ledger, Record, detect


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


@pytest.fixture
def two_engine_round():
    """Build one snapshot holding answers from two engines, record by record.

    Nothing in `collect` produces such a file. `run_round` asks through a single
    provider and stamps its name on every record, and the engine is part of the
    snapshot's own name, so a round carrying two of them is a name claimed by
    one collector and appended to by another, or a ledger somebody assembled by
    hand. It is built here rather than collected because until this round could
    exist there was one engine, the keying it breaks agreed with itself by
    accident, and no round that a collector *can* write would have shown it.

    `replies` maps each engine to the answers it cycles through, so the two
    engines can be given different behaviour and the loss of one of them is
    visible in the arithmetic rather than only in a count.
    """

    def build(directory, replies, *, brands, n=6, k=4, surface="api", subject="ornek"):
        ledger = Ledger(directory)
        engines = list(replies)
        # Claimed under the first engine's name, which is how one of these
        # arrives: the file says one engine and the records say two.
        snapshot = ledger.next_snapshot_id(subject, engines[0], surface)
        asked = 0
        for engine in engines:
            rows = replies[engine]
            for prompt in range(n):
                for repeat in range(k):
                    text = rows[repeat % len(rows)]
                    ledger.append(
                        snapshot,
                        Record(
                            snapshot_id=snapshot,
                            seq=0,
                            prompt_id=f"p{prompt}",
                            repeat=repeat,
                            engine=engine,
                            surface=surface,
                            model="fake-1",
                            asked_at="2026-08-01T00:00:00Z",
                            status="ok",
                            latency_ms=1,
                            answer_text=text,
                            brands=detect(text, brands),
                            citations=(),
                            provider=engine,
                        ),
                    )
                    asked += 1
        ledger.seal(snapshot, asked=asked, ok=asked, errors=0, at="2026-08-01T00:00:00Z")
        return ledger, snapshot

    return build
