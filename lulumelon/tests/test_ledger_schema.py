"""Adding a column to a hashed record, stated as the failures it must not allow.

The existing guarantees live in `test_ledger.py` and are not touched here. If
any of them needs editing to accommodate a schema change, the change altered a
promise rather than extending a format, and that is the thing to notice.

What this file covers is the new failure surface: a version's field set, the
refusal to read a line as a version it does not claim to be, the numbers a cost
claim rests on, and the record a round closes with, which is how a file that
has lost lines off the end says so.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from lulumelon.collect import (
    GENESIS,
    HASHED_FIELDS,
    ROUND_END,
    SCHEMA_VERSION,
    Ledger,
    LedgerFormatError,
    Record,
    UnknownSchemaVersion,
    Usage,
    decode,
    replay,
)
from lulumelon.collect.ask import FakeProvider
from lulumelon.collect.detect import Brand
from lulumelon.collect.session import Prompt, run_round

FIXTURES = Path(__file__).resolve().parent / "fixtures"
V1_SNAPSHOT = "marx__perplexity__api__20260731T120000Z__0001"

#: The round the previous build wrote, kept as evidence in
#: `test_ledger_golden.py`. Read here for the one question this file asks of
#: it: what a checker that knows about seals says about a file that has none.
V2_SNAPSHOT = "marx__perplexity__api__20260801T020000Z__0002"


def _reforge(path: Path) -> None:
    """Rewrite a whole file as a clean chain, the way a determined forger must.

    Nothing here is secret, so the digests can always be recomputed. This does
    exactly that, renumbering and relinking every record from genesis, and it
    is what the hash chain really costs somebody: not impossibility, a rewrite
    of the entire tail. The tests that use it are about what survives it.
    """
    prev = GENESIS
    out = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        record = replace(decode(json.loads(line)), seq=i, prev_hash=prev, hash="")
        linked = record.linked(prev)
        out.append(linked.as_line())
        prev = linked.hash
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


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
    assert HASHED_FIELDS[3] == frozenset(
        {
            "snapshot_id", "seq", "prompt_id", "repeat", "engine", "surface",
            "model", "asked_at", "status", "latency_ms", "answer_text",
            "brands", "citations", "provider", "error",
            "input_tokens", "output_tokens", "search_context", "reported_cost_usd",
            "searches", "round_asked", "round_ok", "round_errors",
            "prev_hash", "v",
        }
    )


def test_the_figure_no_response_has_ever_carried_is_not_a_column():
    """`request_cost` is documented by a provider and has never arrived here.

    A column for it would sit at `None` on every row, and `None` in this file
    means the provider was asked and said nothing. Nobody has asked: the
    endpoint that documents the field has never answered this build. The rule
    is that a real response settles which schema a figure lands in, and the
    response that settled `searches` into v3 is one that carried it.
    """
    assert not any("request_cost" in row for row in HASHED_FIELDS.values())
    assert "searches" in HASHED_FIELDS[3]


def test_a_version_only_ever_adds_fields():
    """Renaming or dropping one makes every older snapshot unreadable."""
    for older, newer in zip(sorted(HASHED_FIELDS), sorted(HASHED_FIELDS)[1:]):
        assert HASHED_FIELDS[older] < HASHED_FIELDS[newer]


def test_the_current_schema_is_the_highest_row_in_the_table():
    assert SCHEMA_VERSION == max(HASHED_FIELDS)


def test_a_record_hashes_exactly_the_keys_its_version_declares():
    assert set(rec(v=1).payload()) == HASHED_FIELDS[1]
    assert set(rec(v=2).payload()) == HASHED_FIELDS[2]
    assert set(rec().payload()) == HASHED_FIELDS[3]


def test_relabelling_a_records_version_changes_its_hash():
    """`v` is inside the digest, so a line cannot be re-badged in place."""
    assert rec(v=1).digest() != rec(v=2).digest()


# -- an old archive keeps working, with no migration ------------------------


def test_a_snapshot_from_before_these_fields_still_verifies(archive):
    assert archive.verify(V1_SNAPSHOT) == []


def test_a_new_record_appends_onto_an_old_snapshot(archive):
    """One file, two schemas, one chain, and it still re-derives.

    The old records were never rewritten to look like the new ones, which is
    what keeps their hashes the ones the customer was given. The seal at the
    end is a v3 record closing a round whose first four calls are v1, and the
    count it states is a count of all of them.
    """
    archive.append(V1_SNAPSHOT, rec(prompt_id="p3", input_tokens=101, output_tokens=42))
    archive.seal(V1_SNAPSHOT, asked=5, ok=4, errors=1)
    assert archive.verify(V1_SNAPSHOT) == []
    assert [r.v for r in archive.read(V1_SNAPSHOT)] == [1, 1, 1, 1, 3, 3]
    assert archive.calls(V1_SNAPSHOT) == 5


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
    written = [r for r in led.read(result.snapshot_id) if not r.is_seal]
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
    assert result.asked == 3 and led.calls(result.snapshot_id) == 3
    assert led.verify(result.snapshot_id) == []


def test_a_reported_cost_survives_the_round_trip(led):
    awkward = 0.006100000000000001
    led.append("s__e__api__x__0001", rec(reported_cost_usd=awkward))
    led.seal("s__e__api__x__0001", asked=1, ok=1, errors=0)
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


# -- the check a customer can actually run ----------------------------------


def _console():
    import io

    from lulumelon.cli import Console

    out, err = io.StringIO(), io.StringIO()
    return Console(out=out, err=err), out


def test_verify_command_passes_an_untouched_archive(archive, tmp_path):
    from lulumelon.cli import verify as run_verify

    console, out = _console()
    assert run_verify(console, ledger_dir=tmp_path) == 0
    assert "intact" in out.getvalue()


def test_verify_command_names_what_moved(archive, tmp_path):
    from lulumelon.cli import verify as run_verify

    _tamper(archive, V1_SNAPSHOT, 0, lambda line: line.replace('"marx"', '"planted"'))
    console, out = _console()
    assert run_verify(console, ledger_dir=tmp_path) == 1
    assert "BROKEN" in out.getvalue()
    assert "own hash" in out.getvalue()


def test_verify_command_states_the_limit_of_the_check(archive, tmp_path):
    """It must not read as a completeness claim, because it is not one."""
    from lulumelon.cli import verify as run_verify

    console, out = _console()
    run_verify(console, ledger_dir=tmp_path)
    text = out.getvalue()
    assert "does not cover" in text
    assert "cut tail leaves no trace" in text


# -- the hole that was open: a round now states its own length --------------


def a_round(led: Ledger, k: int = 2, **over) -> str:
    """Two prompts asked `k` times through the stub, and closed the way a
    collected round is closed. The provider never leaves this process."""
    result = run_round(
        ledger=led,
        provider=FakeProvider(name="perplexity", script={"q1": ("Marx does.",)}, **over),
        prompts=[Prompt(id="p1", text="q1"), Prompt(id="p2", text="q2")],
        brands=[Brand(name="marx", aliases=())],
        k=k,
        subject="marx",
        clock=lambda: "2026-08-01T02:00:00Z",
    )
    return result.snapshot_id


def _cut_to(path, lines: int) -> None:
    text = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(text[:lines]) + "\n", encoding="utf-8")


def test_truncating_a_snapshot_is_reported(led):
    """The hole this ledger shipped with, closed for every round it writes.

    Deleting lines from the end used to return a clean verify, and the next
    honest append linked onto the new tail, so the loss became permanent and
    invisible in one move. A round now ends with a record stating how many
    calls it made, and that record is the first thing a cut tail removes.

    It stands on a round this build collected rather than on the v1 fixture it
    used to stand on, and that is not a softer test, it is the only true one:
    a file whose records never stated their own length cannot be shown to be
    short, and the alternative reading of "report every snapshot that has no
    seal" reports every round anybody collected before today as tampered with.
    That limit is the test below this one, stated rather than glossed.
    """
    snapshot_id = a_round(led)
    assert led.calls(snapshot_id) == 4
    _cut_to(led.path_of(snapshot_id), 2)

    problems = led.verify(snapshot_id)
    assert problems != []
    assert any("not sealed" in p for p in problems)


def test_a_round_written_before_seals_existed_cannot_be_shown_to_be_short(archive, tmp_path):
    """The exact limit of the check, kept in front of us instead of implied.

    The same cut on a snapshot from an older build reads clean, because
    nothing in it ever said how long it was. Reporting it would mean reporting
    every honest archive collected before this change as damaged, so the
    command says which rounds the length check does not reach and the number
    of them, and the caveat prints for those rounds only.
    """
    from lulumelon.cli import verify as run_verify

    path = archive.path_of(V1_SNAPSHOT)
    _cut_to(path, 2)
    assert archive.verify(V1_SNAPSHOT) == []

    console, out = _console()
    assert run_verify(console, ledger_dir=tmp_path) == 0
    text = out.getvalue()
    assert "length never sealed" in text
    assert "does not cover" in text
    assert "cut tail leaves no trace" in text


def test_a_round_from_the_build_before_this_one_is_not_reported_as_forged(tmp_path):
    """A v2 file, written by v2, read by v3: unsealed and undamaged.

    This is the failure mode a length check invites. Every round in every
    customer's archive predates the seal, and a checker that called them all
    short would be wrong about all of them on the day it shipped.
    """
    from lulumelon.cli import verify as run_verify

    shutil.copy(FIXTURES / f"{V2_SNAPSHOT}.jsonl", tmp_path / f"{V2_SNAPSHOT}.jsonl")
    led = Ledger(tmp_path)

    assert led.verify(V2_SNAPSHOT) == []
    assert led.seal_of(V2_SNAPSHOT) is None

    console, out = _console()
    assert run_verify(console, ledger_dir=tmp_path) == 0, "an old round is not a broken round"
    text = out.getvalue()
    assert "BROKEN" not in text
    assert f"intact   {V2_SNAPSHOT}   3 records, length never sealed" in text


def test_removing_only_the_seal_is_reported(led):
    """The cheapest attack on a sealed round: take one line off the end.

    Every call is still there and every link still resolves. What is gone is
    the sentence saying how many there should be, and a round from this build
    without that sentence is reported rather than read as complete.
    """
    snapshot_id = a_round(led)
    _cut_to(led.path_of(snapshot_id), 4)

    problems = led.verify(snapshot_id)
    assert any("not sealed" in p for p in problems)
    assert not any("prev_hash" in p for p in problems), "the chain itself is untouched"


def test_removing_a_call_and_reforging_the_chain_is_caught_by_the_count(led):
    """The whole-tail rewrite, which is what the hash chain costs an attacker.

    Anyone can recompute these digests, so a forger who is willing to rewrite
    every record after the one they removed gets a chain that re-derives. The
    seal is what they cannot fix by relinking: it states four calls, the file
    holds three, and the two are compared rather than assumed to agree.
    """
    snapshot_id = a_round(led)
    path = led.path_of(snapshot_id)
    lines = path.read_text(encoding="utf-8").splitlines()
    del lines[1]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _reforge(path)

    problems = led.verify(snapshot_id)
    assert not any("prev_hash" in p or "own hash" in p for p in problems), (
        "the forger did the expensive part; the count is what stops them"
    )
    assert any("says the round made 4 calls and 3 are on the file" in p for p in problems)


def test_a_second_seal_is_refused_by_the_ledger_and_reported_on_disk(led):
    """A round states its length once.

    Through the library the second one cannot be written at all, which is the
    protection that matters: nothing in this repo can quietly reopen a closed
    round. Written past the library, straight onto the file and correctly
    linked, it is reported, because a file with two statements of its own
    length has none.
    """
    snapshot_id = a_round(led)
    with pytest.raises(ValueError, match="is sealed"):
        led.seal(snapshot_id, asked=4, ok=4, errors=0)

    path = led.path_of(snapshot_id)
    tail = list(led.read(snapshot_id))[-1]
    second = replace(
        Record(
            snapshot_id=snapshot_id, seq=5, prompt_id="", repeat=0, engine="", surface="",
            model="", asked_at="2026-08-01T02:00:00Z", status=ROUND_END, latency_ms=0,
            answer_text="", brands=(), citations=(), provider="",
            round_asked=4, round_ok=4, round_errors=0,
        ),
        prev_hash=tail.hash,
    ).linked(tail.hash)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(second.as_line() + "\n")

    assert any("a second seal" in p for p in led.verify(snapshot_id))


def test_a_record_written_after_the_round_closed_is_reported(led):
    """A file that says it is over and then goes on is two rounds in one name.

    The library will not do this, since `append` refuses a sealed round, so the
    record is written straight onto the file, correctly linked, which is what
    somebody splicing one round's answers into another would have to do.
    """
    snapshot_id = a_round(led)
    path = led.path_of(snapshot_id)
    tail = list(led.read(snapshot_id))[-1]
    smuggled = replace(
        rec(snapshot_id=snapshot_id, seq=5, prompt_id="p9"), prev_hash=tail.hash
    ).linked(tail.hash)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(smuggled.as_line() + "\n")

    problems = led.verify(snapshot_id)
    assert any("1 record were written after the round said it was over" in p for p in problems)
    assert any("says the round made 4 calls and 5 are on the file" in p for p in problems)


def test_a_length_that_cannot_be_checked_says_so_instead_of_accusing(led):
    """One unreadable line, and the count on the file is not the count.

    Reporting "the seal says four and three are here" would be an accusation
    built on a line nobody could read: the record may be sitting there intact
    under a flipped byte. The unreadable line is the finding, and the length
    check says out loud that it could not run.
    """
    snapshot_id = a_round(led)
    path = led.path_of(snapshot_id)
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1] = "{not json at all"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    problems = led.verify(snapshot_id)
    assert any("line 1" in p and "unreadable" in p for p in problems)
    assert any("that cannot be checked here" in p for p in problems)
    assert not any("are on the file" in p for p in problems)


def test_a_seal_whose_parts_do_not_add_up_is_refused():
    """A seal is one statement, and its own arithmetic is part of it."""
    with pytest.raises(ValueError, match="do not add up"):
        Record(
            snapshot_id="s__e__api__x__0001", seq=0, prompt_id="", repeat=0, engine="",
            surface="", model="", asked_at="", status=ROUND_END, latency_ms=0,
            answer_text="", brands=(), citations=(), provider="",
            round_asked=4, round_ok=4, round_errors=1,
        )


def test_a_seal_cannot_carry_an_answer():
    """Everything downstream skips it, so an answer in one is unmeasurable."""
    with pytest.raises(ValueError, match="not an answer"):
        Record(
            snapshot_id="s__e__api__x__0001", seq=0, prompt_id="", repeat=0, engine="",
            surface="", model="", asked_at="", status=ROUND_END, latency_ms=0,
            answer_text="", brands=("marx",), citations=(), provider="",
            round_asked=1, round_ok=1, round_errors=0,
        )


def test_an_ask_cannot_state_what_the_whole_round_did():
    with pytest.raises(ValueError, match="only the record that closes a round"):
        rec(round_asked=4, round_ok=4, round_errors=0)


def test_a_schema_with_nowhere_to_put_the_counts_cannot_seal():
    with pytest.raises(ValueError, match="cannot close a round"):
        rec(v=2, status=ROUND_END, answer_text="", brands=(), citations=())


def test_a_seal_with_a_forged_count_is_reported_by_the_line_it_sits_on(led):
    """The counts are inside the digest, so they cannot be edited in place."""
    snapshot_id = a_round(led)
    path = led.path_of(snapshot_id)
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[-1] = lines[-1].replace('"round_asked":4', '"round_asked":9').replace(
        '"round_ok":4', '"round_ok":9'
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    problems = led.verify(snapshot_id)
    assert any("own hash" in p for p in problems)
    assert any("says the round made 9 calls and 4 are on the file" in p for p in problems)


def test_replay_ignores_the_seal_and_the_run_count_is_unchanged(led):
    """`mirror` counts asks. A seal counted as one would be a call nobody made."""
    snapshot_id = a_round(led, k=3)
    played = replay(led, snapshot_id)

    assert len(played.runs) == 6
    assert played.dropped == 0
    assert played.total == 6 == led.calls(snapshot_id)
    assert "6 usable of 6 asked" in played.as_text()


def test_lulu_usage_does_not_count_the_seal_as_an_answered_call(led):
    """The seal was never billed, and it is in no divisor on that screen."""
    from lulumelon.usage import spend_of

    snapshot_id = a_round(led, usage=Usage(input_tokens=118, output_tokens=64))
    spend = spend_of(led.read(snapshot_id))

    assert (spend.calls, spend.answered, spend.failed) == (4, 4, 0)
    assert spend.priced == 4
    assert "4 calls recorded: 4 answered, 0 failed" in spend.as_text()
