"""Files written by an older build, pinned so a schema change cannot move them.

The ledger's whole claim is that an old measurement is expensive to fake. That
claim dies quietly the day a schema change makes honest old files fail to
verify, because the failure looks exactly like tampering: "content does not
match its own hash", on an archive nobody touched.

Nothing in a normal test suite catches that. The tests are written against the
code that is being changed, so a change that moves the hash moves the test with
it and stays green. The only thing that catches it is a real file written by the
old build, committed before the change, and read back afterwards.

So each frozen schema version gets a golden snapshot under `fixtures/`, and each
one is pinned twice: the hashes it carries, and the exact set of field names its
version put inside those hashes. A version without a golden file is a version
whose archive is unprotected the moment the next one lands.

These files are evidence, not test data. They are never regenerated to make a
test pass. If one of them starts failing, the file is right and the code is
wrong.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from lulumelon.collect import Ledger

FIXTURES = Path(__file__).resolve().parent / "fixtures"

#: Written 2026-07-31 by the build at commit 028d407, before usage fields
#: existed. Four records: two ordinary answers, one recorded failure, and one
#: answer whose contact detail was scrubbed on the way in.
V1_SNAPSHOT = "marx__perplexity__api__20260731T120000Z__0001"

#: The sha256 of each line, as v1 computed it. These are the numbers a customer
#: would quote to say "this is the round I paid for".
V1_HASHES = (
    "271451e105a902158fc120b817b9af099d7e51dfd5eba23460c9a4e3f111b66e",
    "d400f43edf06b472779c1034011f64d8a1bd710a2cfd1ee5f1d5b7935614e733",
    "695360999d590e3d0563ba93305461cc2beaaf07d3e4ac832a4bf5ea375b6c41",
    "9adb964d3ab468aac85cdcba1ee8ef341f48ad2bee31f26b12b401fec81c6342",
)

#: Every key v1 wrote on a line, hash included. Spelled out rather than derived
#: from the code, because a test that asks the code what the code does cannot
#: fail. Adding a field to `Record` without versioning the hash changes this set
#: and breaks here, which is the entire point.
V1_KEYS = frozenset(
    {
        "answer_text",
        "asked_at",
        "brands",
        "citations",
        "engine",
        "error",
        "hash",
        "latency_ms",
        "model",
        "prev_hash",
        "prompt_id",
        "provider",
        "repeat",
        "seq",
        "snapshot_id",
        "status",
        "surface",
        "v",
    }
)


@pytest.fixture
def archive(tmp_path):
    """The golden file, copied somewhere a test is allowed to write."""
    shutil.copy(FIXTURES / f"{V1_SNAPSHOT}.jsonl", tmp_path / f"{V1_SNAPSHOT}.jsonl")
    return Ledger(tmp_path)


def _lines() -> list[dict]:
    text = (FIXTURES / f"{V1_SNAPSHOT}.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def test_a_snapshot_written_by_an_older_build_still_verifies(archive):
    """The one that matters. No migration, no rewrite, no exception."""
    assert archive.verify(V1_SNAPSHOT) == []


def test_the_golden_hashes_are_the_ones_the_older_build_produced():
    assert tuple(d["hash"] for d in _lines()) == V1_HASHES


def test_recomputing_the_golden_hashes_today_gives_the_same_answer(archive):
    """Reading is not enough: the digest has to come out the same too.

    `verify` already recomputes, but it reports a list. This asserts the value
    directly, so a failure says which line moved rather than that something did.
    """
    assert tuple(rec.digest() for rec in archive.read(V1_SNAPSHOT)) == V1_HASHES


def test_the_field_set_of_schema_one_is_frozen():
    for i, line in enumerate(_lines()):
        assert frozenset(line) == V1_KEYS, f"line {i} does not carry v1's key set"


def test_every_golden_line_declares_the_schema_version_it_was_written_under():
    assert [line["v"] for line in _lines()] == [1, 1, 1, 1]


def test_the_chain_in_the_golden_file_links_line_to_line(archive):
    records = list(archive.read(V1_SNAPSHOT))
    assert [r.seq for r in records] == [0, 1, 2, 3]
    assert records[0].prev_hash == "0" * 64
    for earlier, later in zip(records, records[1:]):
        assert later.prev_hash == earlier.hash


def test_the_recorded_failure_survived_as_a_failure(archive):
    """A round that half failed must still read as a round that half failed."""
    statuses = [r.status for r in archive.read(V1_SNAPSHOT)]
    assert statuses == ["ok", "ok", "error", "ok"]
    failed = [r for r in archive.read(V1_SNAPSHOT) if r.status == "error"]
    assert failed[0].error == "timeout after 45s"
    assert failed[0].brands == ()


def test_the_contact_detail_scrubbed_in_2026_is_still_absent(archive):
    raw = (FIXTURES / f"{V1_SNAPSHOT}.jsonl").read_text(encoding="utf-8")
    assert "hello@marx.finance" not in raw
    assert "[email]" in raw
