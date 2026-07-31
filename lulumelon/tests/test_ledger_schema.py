"""Adding a column to a hashed record, stated as the failures it must not allow.

The existing guarantees live in `test_ledger.py` and are not touched here. If
any of them needs editing to accommodate a schema change, the change altered a
promise rather than extending a format, and that is the thing to notice.

What this file covers is the new failure surface: a version's field set, the
refusal to read a line as a version it does not claim to be, and the four
numbers a cost claim will rest on.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from lulumelon.collect import (
    HASHED_FIELDS,
    SCHEMA_VERSION,
    Ledger,
    LedgerFormatError,
    Record,
    UnknownSchemaVersion,
    Usage,
    decode,
)
from lulumelon.collect.ask import FakeProvider
from lulumelon.collect.detect import Brand
from lulumelon.collect.session import Prompt, run_round

FIXTURES = Path(__file__).resolve().parent / "fixtures"
V1_SNAPSHOT = "marx__perplexity__api__20260731T120000Z__0001"


def rec(**over) -> Record:
    base = dict(
        snapshot_id="",
        seq=0,
        prompt_id="m1",
        repeat=0,
        engine="perplexity",
        surface="api",
        model="sonar",
        asked_at="2026-07-31T10:00:00Z",
        status="ok",
        latency_ms=1200,
        answer_text="Marx is a platform for trading agents.",
        brands=("marx",),
        citations=("https://marx.finance",),
        provider="perplexity",
    )
    base.update(over)
    return Record(**base)


@pytest.fixture
def led(tmp_path):
    return Ledger(tmp_path)


@pytest.fixture
def archive(tmp_path):
    """The real v1 file, in a directory a test may write to."""
    shutil.copy(FIXTURES / f"{V1_SNAPSHOT}.jsonl", tmp_path / f"{V1_SNAPSHOT}.jsonl")
    return Ledger(tmp_path)


# -- the field table is a promise about bytes already written ---------------


def test_the_field_set_of_every_frozen_version_is_a_literal():
    """Written out here, not derived from the code.

    A test that asks the code what the code does cannot fail. These are the
    key names that are already inside sha256 digests on customers' disks.
    """
    assert HASHED_FIELDS[1] == frozenset(
        {
            "snapshot_id", "seq", "prompt_id", "repeat", "engine", "surface",
            "model", "asked_at", "status", "latency_ms", "answer_text",
            "brands", "citations", "provider", "error", "prev_hash", "v",
        }
    )
    assert HASHED_FIELDS[2] == frozenset(
        {
            "snapshot_id", "seq", "prompt_id", "repeat", "engine", "surface",
            "model", "asked_at", "status", "latency_ms", "answer_text",
            "brands", "citations", "provider", "error",
            "input_tokens", "output_tokens", "search_context", "reported_cost_usd",
            "prev_hash", "v",
        }
    )


def test_a_version_only_ever_adds_fields():
    """Renaming or dropping one makes every older snapshot unreadable."""
    for older, newer in zip(sorted(HASHED_FIELDS), sorted(HASHED_FIELDS)[1:]):
        assert HASHED_FIELDS[older] < HASHED_FIELDS[newer]


def test_the_current_schema_is_the_highest_row_in_the_table():
    assert SCHEMA_VERSION == max(HASHED_FIELDS)


def test_a_record_hashes_exactly_the_keys_its_version_declares():
    assert set(rec(v=1).payload()) == HASHED_FIELDS[1]
    assert set(rec().payload()) == HASHED_FIELDS[2]


def test_relabelling_a_records_version_changes_its_hash():
    """`v` is inside the digest, so a line cannot be re-badged in place."""
    assert rec(v=1).digest() != rec(v=2).digest()


# -- an old archive keeps working, with no migration ------------------------


def test_a_snapshot_from_before_these_fields_still_verifies(archive):
    assert archive.verify(V1_SNAPSHOT) == []


def test_a_new_record_appends_onto_an_old_snapshot(archive):
    archive.append(V1_SNAPSHOT, rec(prompt_id="p3", input_tokens=101, output_tokens=42))
    assert archive.verify(V1_SNAPSHOT) == []
    assert [r.v for r in archive.read(V1_SNAPSHOT)] == [1, 1, 1, 1, 2]


def test_an_old_record_reports_its_usage_as_never_recorded_not_as_zero(archive):
    """The distinction the whole `| None` decision exists for."""
    assert all(r.usage() is None for r in archive.read(V1_SNAPSHOT))


def test_a_silent_provider_is_not_a_measured_zero(led):
    written = led.append("s__e__api__x__0001", rec())
    assert written.usage() is not None, "the field exists at this version"
    assert written.usage().known is False, "and the provider said nothing through it"
    assert written.input_tokens is None


# -- a version cannot carry what it cannot store ----------------------------


def test_an_old_version_cannot_be_built_with_token_counts():
    with pytest.raises(ValueError, match="cannot carry input_tokens"):
        rec(v=1, input_tokens=5)


def test_sealing_cannot_launder_an_illegal_record():
    """`replace` runs __post_init__, so downgrading a populated record raises."""
    from dataclasses import replace

    populated = rec(input_tokens=5)
    with pytest.raises(ValueError, match="cannot carry"):
        replace(populated, v=1)


def test_the_ledger_refuses_to_write_an_old_schema_version(led):
    with pytest.raises(ValueError, match="never written"):
        led.append("s__e__api__x__0001", rec(v=1))


def test_a_non_finite_cost_is_refused_at_construction():
    for bad in (float("nan"), float("inf")):
        with pytest.raises(ValueError, match="finite"):
            rec(reported_cost_usd=bad)


def test_an_unknown_version_cannot_be_constructed():
    with pytest.raises(ValueError, match="not one this build knows"):
        rec(v=99)


def test_a_boolean_version_is_not_schema_one():
    """`isinstance(True, int)` is True, so this would otherwise alias v1."""
    with pytest.raises(ValueError, match="not one this build knows"):
        rec(v=True)


# -- decode refuses, it does not guess --------------------------------------


def test_a_key_the_version_never_hashed_is_refused_not_dropped():
    line = json.loads(rec(v=1).as_line())
    line["input_tokens"] = 5
    with pytest.raises(LedgerFormatError, match="never hashed"):
        decode(line)


def test_a_key_the_version_required_is_missing_is_reported():
    line = json.loads(rec().as_line())
    del line["latency_ms"]
    with pytest.raises(LedgerFormatError, match="is missing"):
        decode(line)


def test_a_line_with_no_version_marker_is_refused():
    line = json.loads(rec().as_line())
    del line["v"]
    with pytest.raises(LedgerFormatError, match="integer schema version"):
        decode(line)


def test_a_line_from_a_newer_build_says_so(led):
    line = json.loads(rec().as_line())
    line["v"] = SCHEMA_VERSION + 1
    with pytest.raises(UnknownSchemaVersion, match="newer build"):
        decode(line)


def test_a_line_that_is_not_an_object_is_reported_not_raised_at_random():
    with pytest.raises(LedgerFormatError, match="must be a JSON object"):
        decode([1, 2, 3])


# -- the file is what is signed, not a reparse of it ------------------------


def _tamper(led: Ledger, snapshot_id: str, index: int, fn) -> None:
    path = led.path_of(snapshot_id)
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[index] = fn(lines[index])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_a_duplicated_key_is_reported_rather_than_last_wins(archive):
    _tamper(
        archive,
        V1_SNAPSHOT,
        0,
        lambda line: line.replace('"brands":["marx"]', '"brands":["marx"],"brands":["marx","planted"]'),
    )
    assert any("twice" in p for p in archive.verify(V1_SNAPSHOT))


def test_a_reformatted_line_with_the_same_values_is_reported(archive):
    _tamper(archive, V1_SNAPSHOT, 0, lambda line: json.dumps(json.loads(line), sort_keys=False))
    assert any("canonical" in p for p in archive.verify(V1_SNAPSHOT))


def test_a_snapshot_file_renamed_onto_another_id_is_reported(archive, tmp_path):
    stolen = "other__perplexity__api__20260731T130000Z__0002"
    archive.path_of(V1_SNAPSHOT).rename(archive.path_of(stolen))
    assert any("belongs to snapshot" in p for p in archive.verify(stolen))


def test_a_missing_snapshot_is_not_reported_as_intact(archive):
    assert archive.verify("never__written__api__x__0001") != []


def test_an_empty_snapshot_file_is_reported(led, tmp_path):
    (tmp_path / "empty__e__api__x__0001.jsonl").write_text("", encoding="utf-8")
    assert any("no records" in p for p in led.verify("empty__e__api__x__0001"))


def test_an_unreadable_line_does_not_hide_a_forgery_after_it(archive):
    """The fatal one. A planted byte must not decide where the audit ends."""
    _tamper(archive, V1_SNAPSHOT, 1, lambda _: "{not json at all")
    _tamper(
        archive,
        V1_SNAPSHOT,
        3,
        lambda line: json.dumps(
            {**json.loads(line), "status": "forged"},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ),
    )
    problems = archive.verify(V1_SNAPSHOT)
    assert any("line 1" in p and "unreadable" in p for p in problems)
    assert any("line 3" in p and "own hash" in p for p in problems), "the walk stopped early"


def test_a_flipped_byte_inside_an_answer_is_reported_not_raised(archive):
    path = archive.path_of(V1_SNAPSHOT)
    blob = bytearray(path.read_bytes())
    blob[blob.index(b"platform")] = 0xFF
    path.write_bytes(bytes(blob))
    assert archive.verify(V1_SNAPSHOT) != []


def test_verify_never_raises_on_a_damaged_file(archive):
    path = archive.path_of(V1_SNAPSHOT)
    path.write_bytes(b'{"v":1}\nnot json\n\xff\xfe\n[]\n')
    assert isinstance(archive.verify(V1_SNAPSHOT), list)


def test_read_raises_where_verify_reports(archive):
    _tamper(archive, V1_SNAPSHOT, 1, lambda _: "{not json at all")
    assert archive.verify(V1_SNAPSHOT) != []
    with pytest.raises(LedgerFormatError, match="line 1"):
        list(archive.read(V1_SNAPSHOT))


# -- usage travels from the answer into the file ----------------------------


def test_usage_travels_from_the_answer_into_the_written_record(led):
    """End to end, because session.py is where the four fields enter a file.

    Without a stub that reports usage, the lines doing this could be deleted
    with the whole suite still green, and the loss would be indistinguishable
    on disk from a provider that said nothing.
    """
    provider = FakeProvider(
        name="perplexity",
        script={"who trades agents?": ("Marx does.",)},
        usage=Usage(input_tokens=118, output_tokens=64, search_context="low", cost_usd=0.0061),
    )
    result = run_round(
        ledger=led,
        provider=provider,
        prompts=[Prompt(id="p1", text="who trades agents?")],
        brands=[Brand(name="marx", aliases=())],
        k=2,
        subject="marx",
        clock=lambda: "2026-07-31T12:00:00Z",
    )
    written = list(led.read(result.snapshot_id))
    assert [r.input_tokens for r in written] == [118, 118]
    assert [r.output_tokens for r in written] == [64, 64]
    assert [r.search_context for r in written] == ["low", "low"]
    assert [r.reported_cost_usd for r in written] == [0.0061, 0.0061]
    assert led.verify(result.snapshot_id) == []


def test_a_round_from_a_silent_provider_writes_unknown_not_zero(led):
    result = run_round(
        ledger=led,
        provider=FakeProvider(name="perplexity", script={"q": ("Marx does.",)}),
        prompts=[Prompt(id="p1", text="q")],
        brands=[Brand(name="marx", aliases=())],
        k=2,
        subject="marx",
        clock=lambda: "2026-07-31T12:00:00Z",
    )
    raw = led.path_of(result.snapshot_id).read_text(encoding="utf-8")
    assert '"input_tokens":null' in raw
    assert '"input_tokens":0' not in raw


def test_an_answer_with_a_broken_character_does_not_abort_the_round(led):
    """A malformed reply is an observation, not a reason to stop collecting.

    An unpaired surrogate arrives from a provider now and again. Refusing to
    encode it would kill the round at that ask and leave a short file that is
    indistinguishable from a complete one, which is the truncation hole with
    extra steps.
    """
    broken = "Marx \ud83d is first."
    result = run_round(
        ledger=led,
        provider=FakeProvider(name="perplexity", script={"q": (broken,)}),
        prompts=[Prompt(id="p1", text="q")],
        brands=[Brand(name="marx", aliases=())],
        k=3,
        subject="marx",
        clock=lambda: "2026-07-31T12:00:00Z",
    )
    assert result.asked == 3 and led.count(result.snapshot_id) == 3
    assert led.verify(result.snapshot_id) == []


def test_a_reported_cost_survives_the_round_trip(led):
    awkward = 0.006100000000000001
    written = led.append("s__e__api__x__0001", rec(reported_cost_usd=awkward))
    assert next(iter(led.read("s__e__api__x__0001"))).reported_cost_usd == awkward
    assert led.verify("s__e__api__x__0001") == []


def test_an_error_record_carries_no_invented_usage(led):
    written = led.append("s__e__api__x__0001", rec(status="error", answer_text="", brands=(), citations=(), error="timeout after 45s"))
    assert written.usage().known is False


def test_contact_details_are_stripped_from_the_error_field_too(led):
    """The provider's own words reach disk, and they have quoted an address."""
    written = led.append(
        "s__e__api__x__0001",
        rec(status="error", answer_text="", brands=(), citations=(), error="http 400: contact ops@marx.finance"),
    )
    assert "ops@marx.finance" not in written.error
    assert "[email]" in written.error
    assert "ops@marx.finance" not in led.path_of("s__e__api__x__0001").read_text(encoding="utf-8")


# -- the hole that is still open -------------------------------------------


@pytest.mark.xfail(reason="no record states how long a round was, so a cut tail leaves no trace", strict=True)
def test_truncating_a_snapshot_is_reported(archive):
    """Known open. Kept as a failing test rather than a comment.

    Deleting lines from the end of a file returns a clean verify, and the next
    honest append seals onto the new tail, so the loss becomes permanently
    undetectable. It closes when a round seals its own length.
    """
    path = archive.path_of(V1_SNAPSHOT)
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(lines[:2]) + "\n", encoding="utf-8")
    assert archive.verify(V1_SNAPSHOT) != []
