"""The command that prints what a round measured, and the two it refuses to.

`lulu collect` sealed rounds for a week before anything printed one, so every
figure this repo quoted about its own first round came out of calling `mirror`
by hand. This is that half, and the tests here are about the three ways the
screen can be wrong: a number derived from a file that does not re-derive, a
number inflated by a question carrying the brand's own name, and a round where
every question does that and there is no number at all.

The output flags are here too, and the property they are held to is that they
add a file and change nothing else. A `.tex` is written on a machine with no
TeX on it at all; a PDF is not, and the difference is said out loud and carried
in an exit code that no script can confuse with a round that would not score.
No test in this file runs a typesetter. The one that exercises a successful
compile is handed a stand-in, for the reason the collector is handed one.

Everything runs against the deterministic stub with the network closed, and the
round is built by the collector rather than assembled by hand, so what is
reported here came down the same path a real round comes down.
"""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

import pytest

from lulumelon.cli import (
    CHAIN_BROKEN,
    NOTHING_TO_SCORE,
    NO_TEX_ENGINE,
    TEX_ENGINE,
    TEX_ENGINE_FAILED,
    Console,
    main,
    report,
)
from lulumelon.collect import FakeProvider, Ledger, load_subject, replay, run_round
from lulumelon.mirror.report import brand_report
from lulumelon.mirror.types import Snapshot, group_runs

HAIKU = "claude-haiku-4-5"

#: One question that carries the brand's own domain, and two that do not. m1 is
#: the shape that produced this rule: the name is inside the question, so the
#: answer below names the brand while saying it has never heard of it.
SUBJECT = {
    "subject": {"id": "ornek", "name": "Ornek", "aliases": ["Ornek Finance", "ornek.com"]},
    "prompts": [
        {"id": "m1", "text": "What is ornek.com?", "intent": "entity"},
        {"id": "m2", "text": "Agentic finance platforms in 2026", "intent": "category"},
        {"id": "m3", "text": "Reputation systems for AI trading agents", "intent": "solution"},
    ],
}

#: What the stub answers each question with, cycled over the repeats.
SCRIPT = {
    "What is ornek.com?": (
        "I don't have specific information about ornek.com in my training data.",
    ),
    "Agentic finance platforms in 2026": ("Ornek Finance is one.", "nobody."),
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
    path = tmp_path / "ornek.json"
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


def run(rec: Recorder, ledger: Ledger, snapshot: str, subject: Path, brand="Ornek") -> int:
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
    assert "excluded from the rate and its interval: 1 prompt whose own text names Ornek (m1)" in text
    assert "2 prompts" in text, "the design is the scored prompts, not every prompt asked"


def test_the_rate_on_screen_is_the_one_mirror_computes(tmp_path):
    """The printed percentage, recomputed from the same round rather than typed."""
    rec = Recorder()
    ledger, snapshot, subject = collected(tmp_path)
    assert run(rec, ledger, snapshot, subject) == 0

    played = replay(ledger, snapshot)
    scored = brand_report(
        Snapshot(label=snapshot, samples=group_runs(played.runs)),
        "Ornek",
        self_naming=load_subject(subject).self_naming("Ornek"),
    )
    point = scored.detection_by_prompt.point

    assert point == pytest.approx(0.25), "m2 named it once in two asks, m3 never"
    assert f"Ornek is named in {point * 100:.1f}% of answers" in rec.text


def test_the_question_that_names_the_brand_is_what_moves_the_rate(tmp_path):
    """m1's answer says it has never heard of the brand, and detection reads it as a mention."""
    ledger, snapshot, subject = collected(tmp_path)
    played = replay(ledger, snapshot)
    snap = Snapshot(label=snapshot, samples=group_runs(played.runs))

    kept = brand_report(snap, "Ornek", self_naming=())
    dropped = brand_report(snap, "Ornek", self_naming=("m1",))

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


def test_a_subject_file_that_has_moved_since_the_round_is_refused(tmp_path):
    """The questions and the exclusions are read off the file, so it has to be the file.

    Renaming a prompt id after collection leaves a file that loads cleanly and
    describes a different round: the renamed question would print with nothing
    against it, the one that was asked would not print at all, and the rule that
    leaves out a question naming the brand would be applied to whatever survived.
    """
    rec = Recorder()
    ledger, snapshot, subject = collected(tmp_path)
    doc = json.loads(subject.read_text(encoding="utf-8"))
    doc["prompts"][1]["id"] = "renamed"
    subject.write_text(json.dumps(doc), encoding="utf-8")

    with pytest.raises(ValueError, match="does not state m2"):
        run(rec, ledger, snapshot, subject)


# -- the questions, and the parameters they were asked under -----------------


def test_the_questions_are_printed_with_what_each_one_produced(tmp_path):
    """The prompt list, from the file the command already opens."""
    rec = Recorder()
    ledger, snapshot, subject = collected(tmp_path)

    assert run(rec, ledger, snapshot, subject) == 0
    text = rec.text

    assert "QUESTIONS" in text
    for prompt in SUBJECT["prompts"]:
        assert prompt["text"] in text
    assert "2 usable of 2 asked, excluded from the rate and its interval" in text


def test_a_question_whose_asks_failed_says_so_on_its_own_line(tmp_path):
    """The round is unbalanced, and the design line averages that away."""
    rec = Recorder()
    path = tmp_path / "ornek.json"
    path.write_text(json.dumps(SUBJECT), encoding="utf-8")
    subject_file = load_subject(path)
    ledger = Ledger(tmp_path / "ledger")
    result = run_round(
        ledger=ledger,
        provider=FakeProvider(name="anthropic", model=HAIKU, script=SCRIPT, fail_on=(2, 3)),
        prompts=subject_file.prompts,
        brands=subject_file.brands,
        k=2,
        subject=subject_file.id,
        clock=lambda: "2026-08-01T03:30:00Z",
    )

    assert run(rec, ledger, result.snapshot_id, path) == 0
    assert "0 usable of 2 asked" in rec.text
    assert "2 usable of 2 asked" in rec.text


def test_the_parameters_the_round_was_collected_under_are_printed(tmp_path):
    """Where it asked from, and what it may not say about the search cap."""
    rec = Recorder()
    ledger, snapshot, subject = collected(tmp_path)

    assert run(rec, ledger, snapshot, subject) == 0
    assert "no location was requested" in rec.text
    assert "not recoverable from this round" in rec.text


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
            "Ornek",
        ],
        console=rec.console,
    )

    assert code == 0
    assert "APPEARANCE" in rec.text


# -- the two output flags ----------------------------------------------------

#: A machine with nothing installed on it. Every test below that is about the
#: `.tex` uses this, so "writing the document needs no TeX" is a property the
#: suite holds rather than a sentence in a docstring.
NO_ENGINE = lambda _: None  # noqa: E731 - one expression, named for what it is


def unusable(_cmd, **_kwargs):
    """A typesetter that must never be reached, so reaching one is a failure."""
    raise AssertionError("the suite ran a typesetter")


def stand_in(returncode: int = 0, stderr: str = "", *, seen: list | None = None):
    """A typesetter, as far as this command can tell.

    Writes the file the engine would write, where the engine would write it,
    which is what the code after the call has to find. Named after the engine's
    contract rather than after tectonic: what is being tested is that a PDF
    produced in a build directory arrives at the path that was asked for.
    """

    def run(cmd, **_kwargs):
        if seen is not None:
            seen.append(cmd)
        if returncode == 0:
            build = Path(cmd[cmd.index("--outdir") + 1])
            (build / f"{Path(cmd[-1]).stem}.pdf").write_bytes(b"%PDF-1.7\n")
        return subprocess.CompletedProcess(cmd, returncode, "", stderr)

    return run


def test_the_tex_is_written_on_a_machine_with_no_tex_on_it(tmp_path):
    rec = Recorder()
    ledger, snapshot, subject = collected(tmp_path)
    tex = tmp_path / "round.tex"

    code = report(
        rec.console,
        ledger_dir=ledger.root,
        snapshot=snapshot,
        subject_path=subject,
        brand="Ornek",
        tex_path=tex,
        which=NO_ENGINE,
        run=unusable,
    )

    assert code == 0
    assert tex.read_text(encoding="utf-8").startswith("\\documentclass")
    assert snapshot.replace("_", "\\_") in tex.read_text(encoding="utf-8")
    assert f"wrote {tex}" in rec.text


def test_the_screen_is_the_same_screen_with_the_flag_and_without_it(tmp_path):
    """A report somebody has been reading for weeks does not move for a file."""
    ledger, snapshot, subject = collected(tmp_path)

    plain = Recorder()
    report(
        plain.console,
        ledger_dir=ledger.root,
        snapshot=snapshot,
        subject_path=subject,
        brand="Ornek",
    )
    with_file = Recorder()
    report(
        with_file.console,
        ledger_dir=ledger.root,
        snapshot=snapshot,
        subject_path=subject,
        brand="Ornek",
        tex_path=tmp_path / "round.tex",
        which=NO_ENGINE,
        run=unusable,
    )

    added = with_file.text[len(plain.text) :]
    assert with_file.text.startswith(plain.text)
    assert added.strip() == f"wrote {tmp_path / 'round.tex'}"


def test_no_engine_still_writes_the_document_and_says_which_binary_was_looked_for(tmp_path):
    rec = Recorder()
    ledger, snapshot, subject = collected(tmp_path)
    pdf = tmp_path / "round.pdf"

    code = report(
        rec.console,
        ledger_dir=ledger.root,
        snapshot=snapshot,
        subject_path=subject,
        brand="Ornek",
        pdf_path=pdf,
        which=NO_ENGINE,
        run=unusable,
    )

    assert code == NO_TEX_ENGINE
    assert not pdf.exists()
    assert pdf.with_suffix(".tex").is_file()
    assert TEX_ENGINE in rec.text
    assert str(pdf.with_suffix(".tex")) in rec.text


def test_a_missing_engine_is_not_a_measurement_refusal():
    """4, 5 and 6 all mean a number would not stand up. This means neither did.

    Pinned as a set rather than one at a time, so a refusal added later that
    reaches for the next free number collides here instead of colliding in
    somebody's build script.
    """
    assert NO_TEX_ENGINE not in {0, NOTHING_TO_SCORE, CHAIN_BROKEN, 5, 6}
    assert TEX_ENGINE_FAILED not in {0, NOTHING_TO_SCORE, CHAIN_BROKEN, 5, 6, NO_TEX_ENGINE}


def test_the_pdf_lands_on_the_path_that_was_asked_for(tmp_path):
    rec = Recorder()
    ledger, snapshot, subject = collected(tmp_path)
    pdf = tmp_path / "somewhere" / "named-by-the-caller.pdf"
    pdf.parent.mkdir()
    seen: list = []

    code = report(
        rec.console,
        ledger_dir=ledger.root,
        snapshot=snapshot,
        subject_path=subject,
        brand="Ornek",
        pdf_path=pdf,
        which=lambda name: f"/usr/local/bin/{name}",
        run=stand_in(seen=seen),
    )

    assert code == 0
    assert pdf.read_bytes().startswith(b"%PDF")
    assert pdf.with_suffix(".tex").is_file()
    assert seen[0][-1] == str(pdf.with_suffix(".tex"))
    assert f"wrote {pdf}" in rec.text


def test_an_engine_that_fails_leaves_the_document_and_says_what_it_said(tmp_path):
    rec = Recorder()
    ledger, snapshot, subject = collected(tmp_path)
    pdf = tmp_path / "round.pdf"

    code = report(
        rec.console,
        ledger_dir=ledger.root,
        snapshot=snapshot,
        subject_path=subject,
        brand="Ornek",
        pdf_path=pdf,
        which=lambda name: f"/usr/local/bin/{name}",
        run=stand_in(returncode=1, stderr="error: Undefined control sequence"),
    )

    assert code == TEX_ENGINE_FAILED
    assert not pdf.exists()
    assert pdf.with_suffix(".tex").is_file()
    assert "Undefined control sequence" in rec.text


def test_a_directory_that_does_not_exist_is_refused_rather_than_made(tmp_path):
    """The one command line mistake here, reported as one."""
    rec = Recorder()
    ledger, snapshot, subject = collected(tmp_path)

    with pytest.raises(ValueError, match="is not a directory"):
        report(
            rec.console,
            ledger_dir=ledger.root,
            snapshot=snapshot,
            subject_path=subject,
            brand="Ornek",
            tex_path=tmp_path / "nowhere" / "round.tex",
            which=NO_ENGINE,
            run=unusable,
        )


def test_both_flags_reach_the_command(tmp_path, monkeypatch):
    """Through `main`, which is where the defaults for the two callables live."""
    rec = Recorder()
    ledger, snapshot, subject = collected(tmp_path)
    monkeypatch.setattr("lulumelon.cli.shutil.which", NO_ENGINE)
    tex = tmp_path / "elsewhere.tex"
    pdf = tmp_path / "round.pdf"

    code = main(
        [
            "report",
            "--ledger", str(ledger.root),
            "--snapshot", snapshot,
            "--subject", str(subject),
            "--brand", "Ornek",
            "--tex", str(tex),
            "--pdf", str(pdf),
        ],
        console=rec.console,
    )

    assert code == NO_TEX_ENGINE
    assert tex.is_file(), "the named path is used rather than one derived from the pdf"
    assert not pdf.with_suffix(".tex").exists()
