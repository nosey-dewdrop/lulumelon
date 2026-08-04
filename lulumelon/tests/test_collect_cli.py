"""The command that spends real money, driven end to end without spending any.

`lulu collect` is the only command that bills a whole round, so the tests here
are about what has to be true before the first call and what has to be on
screen after the last one. Three of them are about money that cannot be
recovered: a round with no ceiling, a round priced from a table that has no row
for the model, and a round that stopped early and did not say so.

Everything runs against the deterministic stub, so the whole path from a
subject file to a sealed snapshot is exercised with the network closed. The key
is still resolved on that path, because never printing it is a promise this
command keeps whether or not it calls anything.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from lulumelon import cli
from lulumelon.cli import Console, collect
from lulumelon.collect import (
    UNSEARCHED_SURFACE,
    FakeProvider,
    Ledger,
    Usage,
    replay,
)
from lulumelon.collect.budget import UNMEASURED_INPUT_TOKENS
from lulumelon.prices import price_for

KEY = "sk-ant-" + "a1b2c3d4e5" * 4
OPUS = price_for("anthropic", "claude-opus-5")

#: What the stub says every call consumed. The input count is the one the first
#: real billed call in this repo reported, so the arithmetic on screen is
#: checked against the shape of a real response rather than a round number.
METERED = Usage(input_tokens=10046, output_tokens=210, searches=1)

SUBJECT = {
    "subject": {
        "id": "marx",
        "name": "Marx",
        "domain": "marx.finance",
        "aliases": ["Marx Finance", "marx.finance"],
        "ambiguousName": True,
    },
    "competitors": [{"name": "Numerai", "aliases": ["numer.ai"]}],
    "prompts": [
        {"id": "m1", "text": "What is marx.finance?"},
        {"id": "m2", "text": "Agentic finance platforms in 2026"},
    ],
}


class Recorder:
    """A console whose whole output is one searchable string."""

    def __init__(self) -> None:
        self.out = io.StringIO()
        self.err = io.StringIO()
        self.console = Console(out=self.out, err=self.err)

    @property
    def text(self) -> str:
        return self.out.getvalue() + self.err.getvalue()


def subject_file(tmp_path: Path, doc: dict | None = None) -> Path:
    path = tmp_path / "marx.json"
    path.write_text(json.dumps(doc or SUBJECT), encoding="utf-8")
    return path


def stub(**over) -> FakeProvider:
    """A provider that answers as the engine being priced.

    The name and the model are the ones the ledger will record and `lulu usage`
    will price from, so a round collected through this is priced by the same
    path a real one is.
    """
    kw = dict(
        name="anthropic",
        model="claude-opus-5",
        script={"What is marx.finance?": ("Marx Finance is an agent platform.",)},
        usage=METERED,
    )
    kw.update(over)
    return FakeProvider(**kw)


def run(rec: Recorder, tmp_path: Path, *, engine=None, **over) -> int:
    """One round, with the machine's own key store pinned out of the way."""
    kw = dict(
        subject_path=subject_file(tmp_path),
        ledger_dir=tmp_path / "ledger",
        k=3,
        budget_usd=5.0,
        cwd=tmp_path,
        home=tmp_path / "home",
        provider="anthropic",
        model="claude-opus-5",
        env={"ANTHROPIC_API_KEY": KEY},
        keychain=lambda service, account: None,
        build_provider=lambda: engine or stub(),
        clock=lambda: "2026-08-01T03:30:00Z",
    )
    kw.update(over)
    return collect(rec.console, **kw)


# -- one round, end to end ---------------------------------------------------


def test_a_round_is_collected_sealed_and_readable(tmp_path):
    rec = Recorder()
    assert run(rec, tmp_path) == 0

    ledger = Ledger(tmp_path / "ledger")
    (snapshot,) = ledger.snapshots()

    assert snapshot.startswith("marx__anthropic__api__")
    assert ledger.calls(snapshot) == 6, "two prompts asked three times each"
    assert ledger.verify(snapshot) == [], "the round it wrote re-derives from its own contents"
    assert ledger.seal_of(snapshot).round_asked == 6

    played = replay(ledger, snapshot)
    assert played.surfaces == ("api",)
    assert {run.prompt_id for run in played.runs} == {"m1", "m2"}
    assert any("Marx" in run.brands for run in played.runs), "the subject's brands were detected"


def test_the_round_says_what_it_asked_and_what_it_spent(tmp_path):
    """Every figure printed, recomputed from the same tables the code uses."""
    rec = Recorder()
    run(rec, tmp_path)
    text = rec.text

    per_call = (10046 * OPUS.input_per_mtok_usd + 210 * OPUS.output_per_mtok_usd) / 1_000_000 + 0.01
    assert "asked 6 of 6, 6 answered, 0 failed" in text
    assert f"spent ${6 * per_call:.4f} of $5.00" in text
    assert "6 calls the provider metered" in text
    assert "measured 10046 in / 210 out tokens per call" in text
    assert (tmp_path / "ledger").name in text


def test_the_worst_case_is_printed_before_anything_is_spent(tmp_path):
    """The first screen is the one that costs the most, at the guess.

    A person running this sees the ceiling before the round rather than the
    total afterwards, and the two numbers below are the ones a round can be
    stopped by, so they are recomputed here rather than transcribed.
    """
    rec = Recorder()
    run(rec, tmp_path, k=4)

    # The output half is the cap the stub carries, not a guess about it: the
    # request states how much the model may write and the guard prices that
    # number, so the two cannot disagree the way they did when one said 400 and
    # the other allowed 1,024.
    ceiling = (
        UNMEASURED_INPUT_TOKENS * OPUS.input_per_mtok_usd
        + stub().max_output_tokens * OPUS.output_per_mtok_usd
    ) / 1_000_000 + 3 * 0.01
    text = rec.text
    before, after = text.split("ASKING")

    assert f"${ceiling:.4f} is the most one of them can cost" in before
    assert f"${8 * ceiling:.4f} is the most the whole round can cost" in before
    assert "8 calls planned: 2 prompts, 4 times each" in before
    assert "plus up to 3 searches at $10 per thousand searches" in before
    assert "read 2026-08-01" in before, "a price with no date is a price nobody can check"
    assert "spent $" in after and "spent $" not in before


def test_the_tracked_names_and_their_forms_are_on_screen_before_the_spend(tmp_path):
    rec = Recorder()
    run(rec, tmp_path)
    before = rec.text.split("ASKING")[0]

    assert "Marx (also Marx Finance, marx.finance)" in before
    assert "Numerai (also numer.ai)" in before
    assert "ambiguous name" in before, "the file says the name is ambiguous, so the screen does"


# -- the key ------------------------------------------------------------------


def test_the_key_is_never_printed_and_never_written_down(tmp_path):
    """The same promise `init` and `doctor` keep, on the command that runs longest."""
    rec = Recorder()
    run(rec, tmp_path)

    assert KEY not in rec.text
    assert "sha256:" in rec.text
    assert "ANTHROPIC_API_KEY" in rec.text, "where it came from is not the key itself"

    ledger_dir = tmp_path / "ledger"
    written = "".join(p.read_text(encoding="utf-8") for p in ledger_dir.glob("*.jsonl"))
    assert KEY not in written
    assert "sk-ant-" not in written


def test_a_round_with_no_key_asks_nothing_and_says_where_it_looked(tmp_path):
    rec = Recorder()
    assert run(rec, tmp_path, env={}) == 1

    assert "ANTHROPIC_API_KEY" in rec.text
    assert "lulu init" in rec.text
    assert not (tmp_path / "ledger").exists(), "a round that never ran writes no snapshot"


# -- the ceiling --------------------------------------------------------------


def test_a_ceiling_of_nothing_is_refused_before_the_first_call(tmp_path):
    rec = Recorder()
    with pytest.raises(ValueError, match="buys nothing"):
        run(rec, tmp_path, budget_usd=0.0)

    assert not (tmp_path / "ledger").exists()


def test_an_engine_with_no_unsearched_arm_is_refused_before_it_is_priced(tmp_path):
    """The refusal that would otherwise arrive after a screen full of figures."""
    rec = Recorder()
    with pytest.raises(ValueError, match="no unsearched arm"):
        run(
            rec,
            tmp_path,
            provider="perplexity",
            model="sonar",
            can_search=False,
            build_provider=None,
            env={"PERPLEXITY_API_KEY": "pplx-" + "a1b2c3d4e5" * 4},
        )

    assert "BEFORE ANYTHING IS SPENT" not in rec.text
    assert not (tmp_path / "ledger").exists()


def test_a_model_with_no_published_price_is_refused_rather_than_run(tmp_path):
    """Unpriced means the guard cannot count, which is the same as no guard."""
    rec = Recorder()
    with pytest.raises(ValueError, match="no published price on file"):
        run(rec, tmp_path, model="claude-opus-9")

    assert not (tmp_path / "ledger").exists()


def test_a_round_the_ceiling_cuts_short_says_so_and_does_not_call_it_a_failure(tmp_path):
    """$0.25 buys three of these calls, and the design asked for eight.

    The first is checked against the opening guess of $0.10 and the rest
    against this round's own measured rate, which is why three fit inside a
    ceiling that the guess alone would have stopped at two.

    The round on disk is real and shorter. What the screen has to carry is the
    count that was never asked, because nothing else on disk distinguishes this
    from a round that was designed small.
    """
    rec = Recorder()
    assert run(rec, tmp_path, k=4, budget_usd=0.25) == cli.ROUND_CUT_SHORT

    text = rec.text
    assert "asked 3 of 8" in text
    assert "5 of 8 asks were never made" in text
    assert "shorter round rather than a failed one" in text

    ledger = Ledger(tmp_path / "ledger")
    (snapshot,) = ledger.snapshots()
    assert ledger.calls(snapshot) == 3
    assert ledger.seal_of(snapshot).round_asked == 3
    assert ledger.verify(snapshot) == []


def test_a_failed_ask_is_reported_and_left_in_the_file(tmp_path):
    rec = Recorder()
    assert run(rec, tmp_path, engine=stub(fail_on=(0, 3))) == 0

    assert "6 answered" not in rec.text
    assert "4 answered, 2 failed" in rec.text
    assert "none was retried" in rec.text

    ledger = Ledger(tmp_path / "ledger")
    (snapshot,) = ledger.snapshots()
    errored = [r for r in ledger.read(snapshot) if r.status == "error"]
    assert len(errored) == 2
    assert all(r.error for r in errored)


# -- the arm that does not search ---------------------------------------------


def test_the_unsearched_arm_is_filed_apart_and_charged_no_search_fee(tmp_path):
    rec = Recorder()
    assert (
        run(
            rec,
            tmp_path,
            can_search=False,
            engine=stub(surface=UNSEARCHED_SURFACE, usage=Usage(input_tokens=900, output_tokens=210)),
        )
        == 0
    )

    ledger = Ledger(tmp_path / "ledger")
    (snapshot,) = ledger.snapshots()
    assert f"__{UNSEARCHED_SURFACE}__" in snapshot
    assert replay(ledger, snapshot).surfaces == (UNSEARCHED_SURFACE,)

    tokens = (900 * OPUS.input_per_mtok_usd + 210 * OPUS.output_per_mtok_usd) / 1_000_000
    text = rec.text
    assert "no tool to run one with" in text
    assert f"spent ${6 * tokens:.4f} of $5.00" in text, "no fee for a search nothing could run"
    assert UNSEARCHED_SURFACE in text


# -- the parser ---------------------------------------------------------------


def test_the_command_line_carries_every_choice_the_round_needs():
    args = cli.build_parser().parse_args(
        [
            "collect",
            "--subject", "data/subjects/marx.json",
            "--k", "5",
            "--ledger", "./ledger",
            "--provider", "anthropic",
            "--model", "claude-opus-5",
            "--budget", "12.50",
            "--max-searches", "2",
            "--no-search",
        ]
    )

    assert (args.subject, args.k, args.budget) == ("data/subjects/marx.json", 5, 12.5)
    assert (args.model, args.max_searches, args.no_search) == ("claude-opus-5", 2, True)


def test_a_round_cannot_be_asked_for_without_a_ceiling_or_a_k():
    """Neither is defaulted: one decides what the round can carry, one what it costs."""
    parser = cli.build_parser()
    for missing in (
        ["collect", "--subject", "s.json", "--k", "5"],
        ["collect", "--subject", "s.json", "--budget", "5"],
        ["collect", "--k", "5", "--budget", "5"],
    ):
        with pytest.raises(SystemExit):
            parser.parse_args(missing)
