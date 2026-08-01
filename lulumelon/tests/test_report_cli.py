"""The command that prints what a round measured, and the two it refuses to.

`lulu collect` sealed rounds for a week before anything printed one, so every
figure this repo quoted about its own first round came out of calling `mirror`
by hand. This is that half, and the tests here are about the three ways the
screen can be wrong: a number derived from a file that does not re-derive, a
number inflated by a question carrying the brand's own name, and a round where
every question does that and there is no number at all.

Everything runs against the deterministic stub with the network closed, and the
round is built by the collector rather than assembled by hand, so what is
reported here came down the same path a real round comes down.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from lulumelon.cli import CHAIN_BROKEN, NOTHING_TO_SCORE, Console, main, report
from lulumelon.collect import FakeProvider, Ledger, load_subject, replay, run_round
from lulumelon.mirror.report import brand_report
from lulumelon.mirror.types import Snapshot, group_runs

HAIKU = "claude-haiku-4-5"

#: One question that carries the brand's own domain, and two that do not. m1 is
#: the shape that produced this rule: the name is inside the question, so the
#: answer below names the brand while saying it has never heard of it.
SUBJECT = {
    "subject": {"id": "marx", "name": "Marx", "aliases": ["Marx Finance", "marx.finance"]},
    "prompts": [
        {"id": "m1", "text": "What is marx.finance?", "intent": "entity"},
        {"id": "m2", "text": "Agentic finance platforms in 2026", "intent": "category"},
        {"id": "m3", "text": "Reputation systems for AI trading agents", "intent": "solution"},
    ],
}

#: What the stub answers each question with, cycled over the repeats.
SCRIPT = {
    "What is marx.finance?": (
        "I don't have specific information about marx.finance in my training data.",
    ),
    "Agentic finance platforms in 2026": ("Marx Finance is one.", "nobody."),
    "Reputation systems for AI trading agents": ("nobody.",),
}


class Recorder:
    """A console whose whole output is one searchable string."""

    def __init__(self) -> None:
        self.out, self.err = io.StringIO(), io.StringIO()
        self.console = Console(out=self.out, err=self.err)

    @property
    def text(self) -> str:
        return self.out.getvalue() + self.err.getvalue()


def collected(tmp_path: Path, doc: dict | None = None) -> tuple[Ledger, str, Path]:
    """One sealed round over the questions in `doc`, each asked twice."""
    path = tmp_path / "marx.json"
    path.write_text(json.dumps(doc or SUBJECT), encoding="utf-8")
    subject = load_subject(path)
    ledger = Ledger(tmp_path / "ledger")
    result = run_round(
        ledger=ledger,
        provider=FakeProvider(name="anthropic", model=HAIKU, script=SCRIPT),
        prompts=subject.prompts,
        brands=subject.brands,
        k=2,
        subject=subject.id,
        clock=lambda: "2026-08-01T03:30:00Z",
    )
    return ledger, result.snapshot_id, path


def run(rec: Recorder, ledger: Ledger, snapshot: str, subject: Path, brand="Marx") -> int:
    return report(
        rec.console,
        ledger_dir=ledger.root,
        snapshot=snapshot,
        subject_path=subject,
        brand=brand,
    )


# -- one round, printed ------------------------------------------------------


def test_the_round_is_reported_with_the_self_naming_question_named(tmp_path):
    rec = Recorder()
    ledger, snapshot, subject = collected(tmp_path)

    assert run(rec, ledger, snapshot, subject) == 0
    text = rec.text

    assert snapshot in text
    assert "excluded from the rate and its interval: 1 prompt whose own text names Marx (m1)" in text
    assert "2 prompts" in text, "the design is the scored prompts, not every prompt asked"


def test_the_rate_on_screen_is_the_one_mirror_computes(tmp_path):
    """The printed percentage, recomputed from the same round rather than typed."""
    rec = Recorder()
    ledger, snapshot, subject = collected(tmp_path)
    assert run(rec, ledger, snapshot, subject) == 0

    played = replay(ledger, snapshot)
    scored = brand_report(
        Snapshot(label=snapshot, samples=group_runs(played.runs)),
        "Marx",
        self_naming=load_subject(subject).self_naming("Marx"),
    )
    point = scored.detection_by_prompt.point

    assert point == pytest.approx(0.25), "m2 named it once in two asks, m3 never"
    assert f"Marx is named in {point * 100:.1f}% of answers" in rec.text


def test_the_question_that_names_the_brand_is_what_moves_the_rate(tmp_path):
    """m1's answer says it has never heard of the brand, and detection reads it as a mention."""
    ledger, snapshot, subject = collected(tmp_path)
    played = replay(ledger, snapshot)
    snap = Snapshot(label=snapshot, samples=group_runs(played.runs))

    kept = brand_report(snap, "Marx", self_naming=())
    dropped = brand_report(snap, "Marx", self_naming=("m1",))

    assert kept.detection_by_prompt.point == pytest.approx(0.5)
    assert dropped.detection_by_prompt.point == pytest.approx(0.25)
    assert all(
        "don't have specific information" in r.answer_text
        for r in ledger.read(snapshot)
        if r.prompt_id == "m1"
    )


# -- the two refusals --------------------------------------------------------


def test_a_round_that_does_not_re_derive_is_refused_before_any_number(tmp_path):
    """A number from a file that does not verify is not a cheaper number."""
    rec = Recorder()
    ledger, snapshot, subject = collected(tmp_path)
    path = ledger.path_of(snapshot)
    lines = path.read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[0])
    row["answer_text"] = "something else entirely"
    lines[0] = json.dumps(row, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    assert run(rec, ledger, snapshot, subject) == CHAIN_BROKEN
    assert "CHAIN BROKEN" in rec.text
    assert "APPEARANCE" not in rec.text


def test_a_round_where_every_question_names_the_brand_has_no_rate(tmp_path):
    """Reported with the prompts named, rather than divided by zero."""
    rec = Recorder()
    doc = json.loads(json.dumps(SUBJECT))
    doc["prompts"] = [doc["prompts"][0]]
    ledger, snapshot, subject = collected(tmp_path, doc)

    assert run(rec, ledger, snapshot, subject) == NOTHING_TO_SCORE
    assert "nothing left to score" in rec.text
    assert "(m1)" in rec.text
    assert "APPEARANCE" not in rec.text


def test_a_brand_the_subject_does_not_track_is_refused(tmp_path):
    """Nothing in the file says what would count as naming it, so nothing is scored."""
    rec = Recorder()
    ledger, snapshot, subject = collected(tmp_path)

    with pytest.raises(ValueError, match="not 'Numerai'"):
        run(rec, ledger, snapshot, subject, brand="Numerai")


# -- the flags reach the command ---------------------------------------------


def test_the_command_line_carries_all_four_of_them(tmp_path):
    rec = Recorder()
    ledger, snapshot, subject = collected(tmp_path)

    code = main(
        [
            "report",
            "--ledger",
            str(ledger.root),
            "--snapshot",
            snapshot,
            "--subject",
            str(subject),
            "--brand",
            "Marx",
        ],
        console=rec.console,
    )

    assert code == 0
    assert "APPEARANCE" in rec.text
