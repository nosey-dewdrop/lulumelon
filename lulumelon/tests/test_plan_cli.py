"""The screen `lulu plan` prints, driven end to end.

The arithmetic beside this file is covered by `test_plan.py`. What was not
covered by anything is the command itself, which is the only version of that
arithmetic a customer ever sees, and the one the README tells a reader to run.
Every figure quoted on that screen is asserted here, so a number in the docs
that stops matching the code fails the suite instead of a demo.

Three things get particular attention.

**Both ends of the range carry their assumption.** With no pilot the command
cannot honestly quote one price, because the split it depends on has not been
measured. Quoting only the cheapest end, unlabelled, next to a section that
does label its own assumption is how the most optimistic number on the page
gets read as the price.

**A ceiling is a fact about the design, not about the budget.** Past it, more
money buys nothing, and a price list that stops without saying so implies the
opposite.

**The inputs a person actually mistypes.** Zero prompts, a rate of zero or one,
a confidence of one. Each has a defined answer here rather than a traceback.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest

from lulumelon.cli import Console, main, plan
from lulumelon.collect import Ledger, Record

SID = "ornek__perplexity__api__20260731T120000Z__0001"


class Recorder:
    def __init__(self) -> None:
        self.out, self.err = io.StringIO(), io.StringIO()
        self.console = Console(out=self.out, err=self.err)

    @property
    def text(self) -> str:
        return self.out.getvalue() + self.err.getvalue()


def run(**kwargs) -> str:
    """The command, with the README's defaults unless a test says otherwise."""
    rec = Recorder()
    args = dict(prompts=40, half_width=0.05, brands=5)
    args.update(kwargs)
    assert plan(rec.console, **args) == 0
    return rec.text


def price_rows(text: str) -> list[str]:
    body = text.split("PRICE", 1)[1]
    return [line.strip() for line in body.splitlines() if "calls   " in line]


# -- the command the README tells a reader to run ---------------------------


def test_the_readme_command_runs_and_prints_the_ceiling_the_readme_quotes():
    text = run()
    assert "above icc 0.0603" in text, "the docs quote this ceiling; the code must produce it"
    assert "40 prompts, 5 brands tracked" in text
    assert "target +/-5.0 points at 95% confidence" in text


def test_the_pair_figures_on_the_readme_screen_are_the_ones_the_code_computes():
    text = run()
    assert "1360 calls per round, 2720 for the pair." in text


def test_more_brands_are_paid_for_in_calls_rather_than_in_confidence():
    """A leaderboard is one claim about every brand, so the z widens."""
    one = run(brands=1)
    five = run(brands=5)
    assert "(one brand at a time)" in one
    assert "(held across all 5 brands at once)" in five
    assert "does not cost more calls" in five

    def cheapest(text: str) -> int:
        return int(re.search(r"one interval, icc 0\.00\s+(\d+) calls", text).group(1))

    assert cheapest(five) > cheapest(one)


# -- the price section quotes a range, not its cheapest end -----------------


def test_both_ends_of_the_reachable_range_are_priced_and_labelled():
    rows = price_rows(run())
    intervals = [r for r in rows if r.startswith("one interval")]
    assert len(intervals) == 2, "one end is not a range"
    for row in intervals:
        assert re.match(r"one interval, icc \d\.\d\d\s+\d+ calls", row), row


def test_no_interval_price_is_printed_without_the_icc_it_assumes():
    """The failure this replaces: the icc 0 end, unlabelled, read as the price."""
    for row in price_rows(run()):
        if row.startswith("one interval"):
            assert "icc" in row, f"an unlabelled interval price: {row}"


def test_the_cheapest_end_is_the_one_the_daily_comparison_is_made_against():
    text = run()
    designed = int(re.search(r"one interval, icc 0\.00\s+(\d+) calls", text).group(1))
    assert f"spend {designed} calls and return a stated interval" in text


def test_the_price_list_says_where_it_stops_being_a_price_list():
    """Past the ceiling no budget reaches the target, and a list must say so."""
    text = run()
    tail = text.split("PRICE", 1)[1]
    assert "has no price at any budget" in tail
    assert "no amount of money buys it" in tail


def test_an_unmetered_plan_is_labelled_a_floor_rather_than_a_total():
    text = run()
    assert "these are" in text and "floors, not totals" in text
    assert "request fees only" in text


# -- a pilot replaces every assumption on the screen ------------------------


def pilot_ledger(tmp_path: Path, detections: list[list[int]], *, failures: int = 0, **over) -> Ledger:
    """A recorded round where `ornek` appears exactly where `detections` says.

    Written through `Ledger.append` rather than as raw lines, and closed with a
    seal, so the round the planner reads is chained and verifies the same way a
    collected one does. `failures` appends that many recorded timeouts before
    the round closes, which is the only way to put one in: a round states its
    length, so nothing can be added to it afterwards.
    """
    led = Ledger(tmp_path)
    asked = 0
    for i, repeats in enumerate(detections):
        for k, hit in enumerate(repeats):
            led.append(
                SID,
                Record(
                    snapshot_id=SID,
                    seq=0,
                    prompt_id=f"p{i}",
                    repeat=k,
                    engine="perplexity",
                    surface="api",
                    model="sonar",
                    asked_at="2026-07-31T12:00:00Z",
                    status="ok",
                    latency_ms=900,
                    answer_text="Ornek is one option." if hit else "Nobody in particular.",
                    brands=("ornek",) if hit else (),
                    citations=(),
                    provider="perplexity",
                    **over,
                ),
            )
            asked += 1
    for _ in range(failures):
        led.append(
            SID,
            Record(
                snapshot_id=SID, seq=0, prompt_id="p9", repeat=0, engine="perplexity",
                surface="api", model="sonar", asked_at="2026-07-31T12:00:00Z", status="error",
                latency_ms=45000, answer_text="", brands=(), citations=(),
                provider="perplexity", error="timeout after 45s",
            ),
        )
    led.seal(SID, asked=asked + failures, ok=asked, errors=failures)
    return led


def test_a_pilot_replaces_the_assumed_bracket_with_one_measured_line(tmp_path):
    pilot_ledger(tmp_path, [[1, 0, 1, 0], [0, 1, 0, 1], [1, 0, 0, 1]])
    text = run(pilot=SID, brand="ornek", ledger_dir=tmp_path)

    assert "VARIANCE, measured from the pilot" in text
    assert "VARIANCE, assumed" not in text
    assert "across the range the split could take" not in text
    assert len([r for r in price_rows(text) if r.startswith("one interval")]) == 1


def test_a_pilot_that_reported_tokens_prices_the_plan_from_them(tmp_path):
    pilot_ledger(tmp_path, [[1, 0], [0, 1]], input_tokens=1200, output_tokens=800)
    text = run(pilot=SID, brand="ornek", ledger_dir=tmp_path)
    assert "priced from a measured 1200 in / 800 out tokens per call." in text
    assert "floors, not totals" not in text


def test_a_pilot_that_metered_no_tokens_leaves_the_plan_a_floor(tmp_path):
    pilot_ledger(tmp_path, [[1, 0], [0, 1]])
    text = run(pilot=SID, brand="ornek", ledger_dir=tmp_path)
    assert "floors, not totals" in text
    assert "priced from a measured" not in text


def test_a_failed_pilot_ask_is_excluded_and_said_out_loud(tmp_path):
    pilot_ledger(tmp_path, [[1, 0], [0, 1]], failures=1)
    text = run(pilot=SID, brand="ornek", ledger_dir=tmp_path)
    assert "1 of 5 pilot asks failed and are excluded" in text
    assert "a failed ask is missing data, not an observed absence" in text


def test_a_pilot_that_does_not_verify_plans_nothing(tmp_path):
    """A design sized from a doctored round is a doctored design."""
    led = pilot_ledger(tmp_path, [[1, 0], [0, 1]])
    path = led.path_of(SID)
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace("Nobody in particular.", "Nobody in particular!")
    assert lines[1] != path.read_text(encoding="utf-8").splitlines()[1]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="does not verify"):
        run(pilot=SID, brand="ornek", ledger_dir=tmp_path)


def test_a_pilot_without_a_brand_cannot_be_scored(tmp_path):
    pilot_ledger(tmp_path, [[1, 0]])
    with pytest.raises(ValueError, match="needs --brand"):
        run(pilot=SID, ledger_dir=tmp_path)


def test_a_single_prompt_pilot_still_produces_a_screen(tmp_path):
    """One prompt cannot separate the two variances, and must not crash."""
    pilot_ledger(tmp_path, [[1, 1, 0, 1]])
    text = run(prompts=1, pilot=SID, brand="ornek", ledger_dir=tmp_path)
    assert "VARIANCE, measured from the pilot" in text
    assert "PRICE" in text


# -- the inputs a person mistypes -------------------------------------------


def test_zero_prompts_is_refused_by_name_rather_than_by_traceback():
    rec = Recorder()
    assert main(["plan", "--prompts", "0"], console=rec.console) == 2
    assert "at least one prompt" in rec.text


def test_a_confidence_of_one_is_refused_by_name():
    rec = Recorder()
    assert main(["plan", "--prompts", "40", "--confidence", "1.0"], console=rec.console) == 2
    assert "confidence must be in (0, 1)" in rec.text


def test_a_rate_outside_the_unit_interval_is_refused_by_name():
    rec = Recorder()
    assert main(["plan", "--prompts", "40", "--rate", "1.5"], console=rec.console) == 2
    assert "appearance rate must be in [0, 1]" in rec.text


@pytest.mark.parametrize("rate", [0.0, 1.0])
def test_a_certain_outcome_has_no_ceiling_and_says_so_by_omission(rate):
    """At p=0 or p=1 there is nothing to be uncertain about, so nothing to buy.

    The ceiling line is dropped rather than printed as `inf`, which would read
    as a very large but finite icc a design could still fall under.
    """
    text = run(rate=rate)
    assert "0.0000" in text
    assert "above icc" not in text
    assert "inf" not in text.lower().replace("information", "")


def test_a_measured_split_the_prompt_set_cannot_beat_is_not_given_a_price(tmp_path):
    """Precision the prompt set cannot carry is not a cheaper plan.

    Every prompt here is either always or never named, so the whole variance
    sits between prompts and repeats buy nothing. Past that ceiling there is no
    design, so there must be no figure beside one.
    """
    pilot_ledger(tmp_path, [[1, 1, 1, 1], [0, 0, 0, 0], [1, 1, 1, 1]])
    text = run(prompts=3, pilot=SID, brand="ornek", ledger_dir=tmp_path)

    assert "unreachable" in text
    assert "prompts would reach it even if repeats bought nothing" in text
    rows = [r for r in price_rows(text) if r.startswith("one interval")]
    assert rows == [], "an unreachable design must not be given a price"
    assert "one interval             not reachable at this prompt count" in text


def test_the_daily_schedule_is_still_priced_when_the_design_is_not(tmp_path):
    """The comparison is the argument, and it survives an impossible target."""
    pilot_ledger(tmp_path, [[1, 1, 1, 1], [0, 0, 0, 0], [1, 1, 1, 1]])
    text = run(prompts=3, pilot=SID, brand="ornek", ledger_dir=tmp_path)
    assert "a daily schedule" in text
    assert "90 calls" in text


# -- a diagnostic round prices a plan, and sizes nothing ---------------------


DIAGNOSTIC = "diagnostic__anthropic__api__20260801T014500Z__0001"


def test_a_diagnostic_pilot_prices_the_plan_without_being_treated_as_a_sample(tmp_path):
    """The check call is the only call this repo has actually billed.

    Figures are the ones that call came back with: 10046 input tokens for an
    eleven word question, because the search results arrive as input, and 91
    out. That is what makes the price real. It is one draw with no brand list,
    which is why the split above it stays labelled assumed instead of being
    computed from a single answer.
    """
    led = Ledger(tmp_path)
    led.append(
        DIAGNOSTIC,
        Record(
            snapshot_id=DIAGNOSTIC,
            seq=0,
            prompt_id="diagnostic",
            repeat=0,
            engine="anthropic",
            surface="api",
            model="claude-haiku-4-5-20251001",
            asked_at="2026-08-01T01:45:00Z",
            status="ok",
            latency_ms=2961,
            answer_text="1 August 2026.",
            brands=(),
            citations=("https://www.rapidtables.com/tools/todays-date.html",),
            provider="anthropic",
            input_tokens=10046,
            output_tokens=91,
            searches=1,
        ),
    )
    led.seal(DIAGNOSTIC, asked=1, ok=1, errors=0)

    text = run(pilot=DIAGNOSTIC, ledger_dir=tmp_path, provider="anthropic")

    assert "priced from a measured 10046 in / 91 out tokens per call." in text
    assert "floors, not totals" not in text
    assert "VARIANCE, assumed" in text
    assert "VARIANCE, measured from the pilot" not in text
    assert "is a diagnostic round" in text


def test_a_diagnostic_pilot_that_does_not_verify_plans_nothing(tmp_path):
    """The chain is checked before the price is read off it, as for any round."""
    led = Ledger(tmp_path)
    led.append(
        DIAGNOSTIC,
        Record(
            snapshot_id=DIAGNOSTIC, seq=0, prompt_id="diagnostic", repeat=0,
            engine="anthropic", surface="api", model="claude-haiku-4-5-20251001",
            asked_at="2026-08-01T01:45:00Z", status="ok", latency_ms=2961,
            answer_text="1 August 2026.", brands=(), citations=(), provider="anthropic",
            input_tokens=10046, output_tokens=91, searches=1,
        ),
    )
    led.seal(DIAGNOSTIC, asked=1, ok=1, errors=0)
    path = led.path_of(DIAGNOSTIC)
    path.write_text(
        path.read_text(encoding="utf-8").replace('"input_tokens":10046', '"input_tokens":10'),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="does not verify"):
        run(pilot=DIAGNOSTIC, ledger_dir=tmp_path, provider="anthropic")
