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

**They were rewritten once, on 4 August 2026, and not to make a test pass.**
They carried a customer's brand and domain inside their answers, in a public
repository, so every string in them was replaced with an example brand and each
chain was re-derived by this build under the schema version the file already
declared. What that costs is stated plainly: these lines were written by an
older build and are no longer byte for byte what it wrote, so what they still
pin is the field set and the hashing rule of each version rather than the
archive of a round. What it bought is a repository that does not publish who
paid for one.
"""

from __future__ import annotations

import itertools
import json
import shutil
from pathlib import Path

import pytest

from lulumelon.collect import Ledger

FIXTURES = Path(__file__).resolve().parent / "fixtures"

#: Written 2026-07-31 by the build at commit 028d407, before usage fields
#: existed. Four records: two ordinary answers, one recorded failure, and one
#: answer whose contact detail was scrubbed on the way in.
V1_SNAPSHOT = "ornek__perplexity__api__20260731T120000Z__0001"

#: The sha256 of each line, as v1 computed it. These are the numbers a customer
#: would quote to say "this is the round I paid for".
V1_HASHES = (
    "0f82729a1448095230b3ea2958e3165d0bea1092b6c1e8192f6255e5580278e1",
    "48cd65d702b673826013be400732e89c8ffe7610fce0e7d7d10309c66a5e8fcb",
    "82ebbe36b328e0716495f4bb9521b0565315da30b8c099706edb7ec08b6c2b8e",
    "297ce616885807d2f132e5cfb61d3476489e331d57b87d334775ca21a91b5de0",
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


#: Written 2026-08-01 by the build at commit 4e3784f, the last one that wrote
#: schema v2: usage fields, and no record closing the round. Three records: a
#: metered answer, one that reported tokens and no amount, and a failure.
V2_SNAPSHOT = "ornek__perplexity__api__20260801T020000Z__0002"

V2_HASHES = (
    "d2b923e3538da5fe20ccd5cac1fb45f3b66bf6bf91c44c6a96a6a2cc72994501",
    "295ee998a822d65ac51f776b2d154e207ee14eed0e31f934ba4aa6c6ef737d07",
    "c449e15ab885b38a56b71d2594d3579704b31d590334ac3ef96cdfc24acd9538",
)

#: Every key v2 wrote, hash included. Four more than v1 and not one fewer.
V2_KEYS = V1_KEYS | {"input_tokens", "output_tokens", "search_context", "reported_cost_usd"}


@pytest.fixture
def archive(tmp_path):
    """The golden file, copied somewhere a test is allowed to write."""
    shutil.copy(FIXTURES / f"{V1_SNAPSHOT}.jsonl", tmp_path / f"{V1_SNAPSHOT}.jsonl")
    return Ledger(tmp_path)


@pytest.fixture
def v2_archive(tmp_path):
    shutil.copy(FIXTURES / f"{V2_SNAPSHOT}.jsonl", tmp_path / f"{V2_SNAPSHOT}.jsonl")
    return Ledger(tmp_path)


def _lines(snapshot: str = V1_SNAPSHOT) -> list[dict]:
    text = (FIXTURES / f"{snapshot}.jsonl").read_text(encoding="utf-8")
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
    for earlier, later in itertools.pairwise(records):
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
    assert "hello@ornek.com" not in raw
    assert "[email]" in raw


# -- schema two, frozen the day schema three opened -------------------------


def test_a_snapshot_written_by_the_build_before_seals_still_verifies(v2_archive):
    """The version that had usage fields and no way to close a round.

    It ends without a seal because nothing could write one when it was
    collected, and it must not read as damaged for that. A round nobody
    touched, reported as short, would teach a customer that the checker is
    noisy, and a noisy checker is one nobody reads on the day it is right.
    """
    assert v2_archive.verify(V2_SNAPSHOT) == []
    assert v2_archive.seal_of(V2_SNAPSHOT) is None


def test_the_golden_v2_hashes_are_the_ones_that_build_produced():
    assert tuple(d["hash"] for d in _lines(V2_SNAPSHOT)) == V2_HASHES


def test_recomputing_the_golden_v2_hashes_today_gives_the_same_answer(v2_archive):
    assert tuple(rec.digest() for rec in v2_archive.read(V2_SNAPSHOT)) == V2_HASHES


def test_the_field_set_of_schema_two_is_frozen():
    for i, line in enumerate(_lines(V2_SNAPSHOT)):
        assert frozenset(line) == V2_KEYS, f"line {i} does not carry v2's key set"


def test_every_golden_v2_line_declares_the_schema_version_it_was_written_under():
    assert [line["v"] for line in _lines(V2_SNAPSHOT)] == [2, 2, 2]


def test_the_usage_v2_recorded_is_still_read_as_usage(v2_archive):
    """The four fields that version added, and the one it had nowhere to put."""
    metered, counted, failed = v2_archive.read(V2_SNAPSHOT)
    assert metered.usage().cost_usd == 0.005182
    assert (counted.usage().input_tokens, counted.usage().output_tokens) == (131, 58)
    assert counted.usage().cost_usd is None
    assert failed.usage().known is False
    assert all(
        rec.usage().searches is None for rec in v2_archive.read(V2_SNAPSHOT)
    ), "v2 had no column for it, so the silence is this build's and not the provider's"
