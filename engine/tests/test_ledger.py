"""What the ledger promises, stated as failures it must not allow."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from collect import GENESIS, Ledger, Record, scrub


def rec(prompt_id: str = "m1", repeat: int = 0, **over) -> Record:
    base = dict(
        snapshot_id="",
        seq=0,
        prompt_id=prompt_id,
        repeat=repeat,
        engine="chatgpt",
        surface="logged_out",
        model="gpt-5-2026-07-01",
        asked_at="2026-07-30T10:00:00Z",
        status="ok",
        latency_ms=1200,
        answer_text="Marx is a platform for trading agents.",
        brands=("marx",),
        citations=("https://marx.finance",),
        provider="fake",
    )
    base.update(over)
    return Record(**base)


@pytest.fixture
def led(tmp_path):
    return Ledger(tmp_path)


# -- asking twice must not destroy the first answer -------------------------


def test_second_round_is_a_new_snapshot_not_an_overwrite(led):
    now = datetime(2026, 7, 30, 10, tzinfo=timezone.utc)
    first = led.next_snapshot_id("marx", "chatgpt", "logged_out", now=now)
    led.append(first, rec())

    second = led.next_snapshot_id("marx", "chatgpt", "logged_out", now=now)

    assert first != second
    assert led.count(first) == 1
    assert led.count(second) == 0
    assert sorted(led.snapshots()) == [first]


def test_sequence_survives_two_rounds_inside_the_same_second(led):
    now = datetime(2026, 7, 30, 10, tzinfo=timezone.utc)
    ids = []
    for _ in range(3):
        sid = led.next_snapshot_id("marx", "chatgpt", "logged_out", now=now)
        led.append(sid, rec())
        ids.append(sid)

    assert len(set(ids)) == 3
    assert [led.count(i) for i in ids] == [1, 1, 1]


def test_appending_never_shortens_a_snapshot(led):
    sid = led.next_snapshot_id("marx", "chatgpt", "logged_out")
    for i in range(5):
        led.append(sid, rec(repeat=i))
    assert led.count(sid) == 5
    assert [r.seq for r in led.read(sid)] == [0, 1, 2, 3, 4]


# -- the chain must notice an edit -----------------------------------------


def test_intact_chain_verifies_clean(led):
    sid = led.next_snapshot_id("marx", "chatgpt", "logged_out")
    for i in range(4):
        led.append(sid, rec(repeat=i))
    assert led.verify(sid) == []


def test_first_record_links_to_genesis(led):
    sid = led.next_snapshot_id("marx", "chatgpt", "logged_out")
    written = led.append(sid, rec())
    assert written.prev_hash == GENESIS
    assert written.hash != ""


def test_editing_an_answer_after_the_fact_is_caught(led):
    sid = led.next_snapshot_id("marx", "chatgpt", "logged_out")
    for i in range(3):
        led.append(sid, rec(repeat=i))

    path = led.path_of(sid)
    lines = path.read_text(encoding="utf-8").splitlines()
    doctored = json.loads(lines[0])
    doctored["brands"] = ["marx", "planted-competitor"]
    lines[0] = json.dumps(doctored, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    problems = led.verify(sid)
    assert problems, "a rewritten answer must not verify clean"
    assert any("line 0" in p and "own hash" in p for p in problems)
    # An edit breaks exactly one link: the record that pointed at it. Claiming
    # every later line turns red would overstate the guarantee, and a claim we
    # cannot reproduce is the one thing this repo cannot afford. The real
    # guarantee is the cost of hiding the break, pinned in the test below.
    assert any("line 1" in p and "prev_hash" in p for p in problems)
    assert not any("line 2" in p for p in problems)


def _read(path):
    return path.read_text(encoding="utf-8").splitlines()


def _record_at(line: str) -> Record:
    d = json.loads(line)
    d["brands"] = tuple(d.get("brands", ()))
    d["citations"] = tuple(d.get("citations", ()))
    return Record(**d)


def _dump(record: Record) -> str:
    return json.dumps(
        {**record.payload(), "hash": record.hash},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def test_patching_the_break_only_moves_it_one_line_down(led):
    """Hiding an edit costs a rewrite of every record that follows it.

    This is the property the ledger is actually for. An attacker who rewrites an
    answer can make the next record point at the doctored one, and that link then
    resolves. It does not help: a record's own hash covers its `prev_hash`, so
    resealing it moves the break to the record after. Faking one old answer means
    reforging the entire tail, which is what makes a measured history expensive
    to fabricate after the fact.
    """
    sid = led.next_snapshot_id("marx", "chatgpt", "logged_out")
    for i in range(3):
        led.append(sid, rec(repeat=i))

    path = led.path_of(sid)
    lines = _read(path)

    doctored = json.loads(lines[0])
    doctored["brands"] = ["marx", "planted-competitor"]
    lines[0] = json.dumps(doctored, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    # the attacker's repair: repoint line 1 at the doctored line 0 and reseal it
    forged_prev = _record_at(lines[0]).digest()
    victim = _record_at(lines[1])
    relinked = Record(**{**victim.payload(), "prev_hash": forged_prev, "hash": ""})
    lines[1] = _dump(Record(**{**relinked.payload(), "hash": relinked.digest()}))

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    problems = led.verify(sid)
    # the repair worked, for exactly one line
    assert not any("line 1" in p and "prev_hash" in p for p in problems)
    # and immediately cost the next one
    assert any("line 2" in p and "prev_hash" in p for p in problems)
    # line 0 still fails on its own content, which no amount of relinking fixes
    assert any("line 0" in p and "own hash" in p for p in problems)


def test_deleting_a_record_is_caught(led):
    sid = led.next_snapshot_id("marx", "chatgpt", "logged_out")
    for i in range(4):
        led.append(sid, rec(repeat=i))

    path = led.path_of(sid)
    lines = path.read_text(encoding="utf-8").splitlines()
    del lines[1]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert led.verify(sid), "a removed run must not verify clean"


# -- failures are data ------------------------------------------------------


def test_a_failed_ask_is_written_not_dropped(led):
    sid = led.next_snapshot_id("marx", "chatgpt", "logged_out")
    led.append(sid, rec(repeat=0))
    led.append(
        sid,
        rec(
            repeat=1,
            status="error",
            answer_text="",
            brands=(),
            citations=(),
            error="timeout after 30s",
            model="unknown",
        ),
    )

    got = list(led.read(sid))
    assert len(got) == 2
    assert [r.status for r in got] == ["ok", "error"]
    assert got[1].error == "timeout after 30s"
    assert led.verify(sid) == []


# -- personal data never lands ---------------------------------------------


def test_contact_details_are_stripped_before_the_hash(led):
    sid = led.next_snapshot_id("marx", "chatgpt", "logged_out")
    written = led.append(sid, rec(answer_text="Reach them at hello@marx.finance or +90 532 111 22 33."))

    assert "hello@marx.finance" not in written.answer_text
    assert "[email]" in written.answer_text
    assert "532 111 22 33" not in written.answer_text

    raw = led.path_of(sid).read_text(encoding="utf-8")
    assert "hello@marx.finance" not in raw
    assert led.verify(sid) == []


def test_scrub_leaves_ordinary_text_alone():
    text = "Marx ranked 2nd in 2026 with 41% share of voice."
    assert scrub(text) == text
