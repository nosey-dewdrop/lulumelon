"""What the ledger promises, stated as failures it must not allow."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from lulumelon.collect import GENESIS, Ledger, Record, scrub


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


def round_of(led: Ledger, snapshot_id: str, records: list[Record]) -> str:
    """Write these asks and close the round the way a collector does.

    A round is only complete once it has stated how many calls it made, so a
    test that fabricates one has to fabricate a finished one. Assembling the
    asks and leaving the file open would be building the exact object `verify`
    now reports: a round that stopped mid-flight or lost its tail.
    """
    for record in records:
        led.append(snapshot_id, record)
    ok = sum(1 for record in records if record.status == "ok")
    led.seal(snapshot_id, asked=len(records), ok=ok, errors=len(records) - ok)
    return snapshot_id


# -- asking twice must not destroy the first answer -------------------------


def test_second_round_is_a_new_snapshot_not_an_overwrite(led):
    now = datetime(2026, 7, 30, 10, tzinfo=timezone.utc)
    first = led.next_snapshot_id("marx", "chatgpt", "logged_out", now=now)
    round_of(led, first, [rec()])

    second = led.next_snapshot_id("marx", "chatgpt", "logged_out", now=now)

    assert first != second
    assert led.calls(first) == 1
    assert led.count(second) == 0
    # Both names are taken the moment they are handed out, so the second one is
    # listed with nothing in it rather than being free for somebody else.
    assert sorted(led.snapshots()) == [first, second]
    assert led.verify(first) == []
    assert any("has no records" in p for p in led.verify(second))


def test_a_name_is_taken_by_creating_the_file_not_by_returning_a_string(led):
    """The race this format cannot otherwise report.

    Two collectors that scan the same directory in the same second are both
    told they own the next number, and two rounds interleaved into one file
    verify clean: every link really was written in the order it landed. So the
    name is claimed on disk, and asking again cannot hand back a name that is
    already spoken for.
    """
    now = datetime(2026, 7, 30, 10, tzinfo=timezone.utc)
    handed_out = [
        led.next_snapshot_id("marx", "chatgpt", "logged_out", now=now) for _ in range(5)
    ]
    assert len(set(handed_out)) == 5
    for snapshot_id in handed_out:
        assert led.path_of(snapshot_id).exists(), "a name nobody reserved is a name two can take"


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
    round_of(led, sid, [rec(repeat=i) for i in range(4)])
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
    round_of(
        led,
        sid,
        [
            rec(repeat=0),
            rec(
                repeat=1,
                status="error",
                answer_text="",
                brands=(),
                citations=(),
                error="timeout after 30s",
                model="unknown",
            ),
        ],
    )

    got = [r for r in led.read(sid) if not r.is_seal]
    assert len(got) == 2
    assert [r.status for r in got] == ["ok", "error"]
    assert got[1].error == "timeout after 30s"
    assert led.verify(sid) == []
    # The failure is in the round's own account of itself, not only in the
    # records: a seal that reported two answers would be a round claiming a
    # call came back that did not.
    assert (led.seal_of(sid).round_ok, led.seal_of(sid).round_errors) == (1, 1)


# -- personal data never lands ---------------------------------------------


def test_contact_details_are_stripped_before_the_hash(led):
    sid = led.next_snapshot_id("marx", "chatgpt", "logged_out")
    written = led.append(sid, rec(answer_text="Reach them at hello@marx.finance or +90 532 111 22 33."))
    led.seal(sid, asked=1, ok=1, errors=0)

    assert "hello@marx.finance" not in written.answer_text
    assert "[email]" in written.answer_text
    assert "532 111 22 33" not in written.answer_text

    raw = led.path_of(sid).read_text(encoding="utf-8")
    assert "hello@marx.finance" not in raw
    assert led.verify(sid) == []


def test_scrub_leaves_ordinary_text_alone():
    text = "Marx ranked 2nd in 2026 with 41% share of voice."
    assert scrub(text) == text


#: Formats a contact page plausibly carries. The first one is why this list
#: exists: the rule this replaced matched a shape three groups long, so a
#: four-group number came out of it as `[phone] 33`, and half a phone number on
#: disk is a phone number on disk.
REACHABLE = [
    "Reach them at +90 532 111 22 33.",
    "call 0532 111 22 33 today",
    "+1 (555) 123-4567",
    "555-123-4567",
    "(0212) 555 12 34",
    "05321112233",
    "+44 20 7946 0958",
    "tel: +90-532-111-22-33",
]

#: Figures this product prints about itself, which a redactor counting shapes
#: rather than digits would eat. A scrub that damages an answer damages the
#: evidence the whole repo exists to keep, so it is held to both directions.
FIGURES = [
    "per call $0.005182 across 4 records",
    "1.2 +/- 0.45 and 56.6% - 100.0%",
    "sonar is $1 in / $1 out per 1M tokens, plus $5 to $12 per 1000 requests",
    "snapshot marx__fake__api__20260731T205245Z__0001",
    "https://a.example/guide/1234567",
    "https://a.example/p?id=12345678901",
    "icc 0.0603, 1360/2720 calls",
    "the round asked 120 of 120 and dropped 0",
    "0 of 5 is not 0%, it is compatible with 43.4%",
]


@pytest.mark.parametrize("text", REACHABLE)
def test_a_phone_number_is_removed_whole_or_not_at_all(text: str):
    scrubbed = scrub(text)
    assert "[phone]" in scrubbed
    left_behind = scrubbed.replace("[phone]", "")
    assert not any(ch.isdigit() for ch in left_behind), (
        f"{left_behind!r} still carries part of the number"
    )


@pytest.mark.parametrize("text", FIGURES)
def test_the_figures_this_product_prints_survive_the_scrub(text: str):
    assert scrub(text) == text


# -- what the first paid round taught the scrubber ---------------------------

#: Verbatim from the round collected on 1 August 2026. The phone rule fired
#: eleven times across 404 records and was wrong on all eleven, and because
#: redaction happens before the hash none of it can be recovered. These are the
#: shapes it destroyed, kept here so it cannot destroy them again.
FIGURES_A_ROUND_NEEDS = (
    'from_="2024-01-01", to="2024-12-31"',
    "client.stock_candle('AAPL','D',1704067200,1735689600)",
    "Agents trained on 2020-2023 data underperform in regime shifts",
    "Paid feeds ($2000-10000/month) for serious strategies",
    "## What to Watch in 2026-2027",
)


@pytest.mark.parametrize("text", FIGURES_A_ROUND_NEEDS)
def test_a_figure_a_reader_needs_survives_the_scrubber(text: str) -> None:
    """None of these is a phone number and every one of them was taken.

    An ISO date, a pair of unix timestamps, two year ranges and a price band.
    A tool that sells a file as evidence cannot quietly rewrite the evidence.
    """
    assert scrub(text) == text


#: Test numbers published by the card schemes for exactly this purpose. None is
#: issued to anybody, and each clears the checksum.
PUBLISHED_TEST_CARDS = (
    "4111 1111 1111 1111",
    "4111-1111-1111-1111",
    "4111111111111111",
    "5500 0055 5555 5559",
    "378282246310005",
)


@pytest.mark.parametrize("number", PUBLISHED_TEST_CARDS)
def test_a_card_number_is_removed_whichever_way_it_is_written(number: str) -> None:
    """Sixteen digits used to walk straight through.

    The phone rule stopped at fifteen, so an Amex was redacted and a Visa was
    not, which is the wrong way round from how often each is written down. A
    card is now decided by its checksum rather than by its length.
    """
    assert scrub(number) == "[card]"
    assert number not in scrub(number)


def test_a_run_of_digits_that_is_not_a_card_is_left_alone() -> None:
    """The checksum is the point: it fires on cards and almost nothing else."""
    assert scrub("4111 1111 1111 1112") == "4111 1111 1111 1112"


def test_a_card_is_never_reported_as_a_phone_number() -> None:
    """The two patterns overlap, so the one that can be checked goes first."""
    assert "[phone]" not in scrub("4111 1111 1111 1111")


@pytest.mark.parametrize(
    "text",
    ("555-123-4567", "+90 532 111 22 33", "0532 111 22 33", "(555) 123 4567"),
)
def test_the_numbers_a_person_is_reached_on_are_still_taken(text: str) -> None:
    """Fixing the false positives was not allowed to cost the true ones."""
    assert "[phone]" in scrub(text)
