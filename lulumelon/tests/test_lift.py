"""The contrast the product is sold on, and every way it can be overstated.

The gate beside this decides whether a replica may stand in for a live surface.
This decides what one source inside that replica was worth, which is the number
a customer is actually paying to hear. So most of these tests are about the
ways a true number acquires a claim it did not earn: the word `lift` attaching
without a gate, an identical pair of arms reading as proof that a source does
not matter, and a fifth source quietly changing what the first one is allowed
to say.

`test_the_arms_are_identical_so_the_zero_is_refused_rather_than_published` is
the one that matters most. Two arms that never differed produce a difference of
zero with an interval of zero width, which is the single most confident-looking
output this module can compute and the least informative one in it.
"""

from __future__ import annotations

import pytest

from lulumelon.mirror.ablation import STANDS_IN, UNDECIDED as GATE_UNDECIDED, replica_gate
from lulumelon.mirror.lift import (
    ARM_DIFFERENCE,
    LIFT,
    MOVES,
    NEGLIGIBLE,
    NO_CONTRAST,
    UNDECIDED,
    ablation_series,
    source_effect,
)

SOURCE = "https://b.example/buyers-guide"

#: Held arm: four prompt shapes, so per-prompt differences vary and the
#: bootstrap has something to resample.
HELD = [[1, 1, 1, 0, 0], [1, 1, 0, 0, 0], [1, 1, 1, 1, 0], [1, 0, 0, 0, 0]]
#: Dropped arm, twenty points below on average.
DROPPED = [[1, 1, 0, 0, 0], [1, 0, 0, 0, 0], [1, 1, 0, 0, 0], [1, 0, 0, 0, 0]]
#: A pair asked ten times each, differing by two and a half points: real,
#: measurable, and smaller than the precision anything here is published at.
FINE_HELD = [
    [1] * 3 + [0] * 7,
    [1] * 5 + [0] * 5,
    [1] * 2 + [0] * 8,
    [1] * 6 + [0] * 4,
]
FINE_DROPPED = [
    [1] * 3 + [0] * 7,
    [1] * 4 + [0] * 6,
    [1] * 2 + [0] * 8,
    [1] * 6 + [0] * 4,
]


def rows(n: int, pattern):
    return {f"p{i}": list(pattern[i % len(pattern)]) for i in range(n)}


def arms(n: int = 40, dropped=DROPPED, held=HELD):
    return rows(n, held), rows(n, dropped)


def passing_gate(n: int = 30):
    """A replica that tracks its surface exactly, so the gate stands in."""
    return replica_gate(rows(n, HELD), rows(n, HELD), margin=0.05)


def failing_gate(n: int = 30):
    return replica_gate(rows(n, HELD), rows(n, [[0, 0, 0, 0, 0]]), margin=0.05)


def undecided_gate():
    return replica_gate(
        rows(6, [[1, 1, 0, 0]]), rows(6, [[1, 1, 1, 0], [1, 0, 0, 0]]), margin=0.05
    )


def effect(held=None, dropped=None, **kw):
    if held is None or dropped is None:
        held, dropped = arms()
    kw.setdefault("source", SOURCE)
    kw.setdefault("margin", 0.05)
    kw.setdefault("gate", None)
    return source_effect(held, dropped, **kw)


# -- the number itself ------------------------------------------------------


def test_a_source_worth_having_is_measured_as_both_levels_and_the_gap():
    e = effect()
    assert e.verdict == MOVES
    assert e.direction == "raises"
    assert e.held.point == pytest.approx(0.50)
    assert e.dropped.point == pytest.approx(0.30)
    assert e.difference.interval.point == pytest.approx(0.20)
    assert e.prompts_paired == 40


def test_the_three_numbers_on_screen_add_up():
    """A screen that prints 38, 61 and a gap has to have those agree.

    The levels are bootstrapped separately from the difference, so nothing
    forces them to reconcile except computing all three over the same set of
    paired prompts. Doing it over each arm's own prompts instead would print
    three true numbers that contradict each other.
    """
    e = effect()
    assert e.held.point - e.dropped.point == pytest.approx(
        e.difference.interval.point, abs=1e-12
    )


def test_a_source_the_model_did_better_without_keeps_its_sign():
    held, dropped = arms()
    e = effect(held=dropped, dropped=held)
    assert e.verdict == MOVES
    assert e.direction == "lowers"
    assert e.difference.interval.point < 0
    assert "lowers the rate" in e.reason


def test_only_prompts_asked_in_both_arms_are_paired_and_the_rest_are_counted():
    held, dropped = arms()
    held["extra-only-here"] = [1, 1, 1, 1, 1]
    dropped["other-side-only"] = [0, 0, 0, 0, 0]
    e = effect(held=held, dropped=dropped)
    assert e.prompts_paired == 40
    assert e.prompts_unpaired == 2
    assert "asked in only one arm" in e.as_text()


# -- the word is granted, not assumed ---------------------------------------


def test_without_a_gate_the_word_lift_never_reaches_the_screen():
    e = effect(gate=None)
    assert e.name == ARM_DIFFERENCE
    assert not e.is_lift
    text = e.as_text()
    assert "lift" not in text.lower()
    assert "no gate was supplied" in text


def test_a_passing_gate_grants_the_word_without_changing_a_digit():
    held, dropped = arms()
    ungated = effect(held=held, dropped=dropped, gate=None)
    gated = effect(held=held, dropped=dropped, gate=passing_gate())

    assert gated.name == LIFT and gated.is_lift
    assert "may be read as a lift" in gated.as_text()
    assert gated.difference.interval == ungated.difference.interval, (
        "the gate decides what the number may be called, not what it is"
    )
    assert gated.verdict == ungated.verdict


@pytest.mark.parametrize("gate_of", [failing_gate, undecided_gate])
def test_a_gate_that_did_not_pass_takes_the_word_and_names_itself(gate_of):
    gate = gate_of()
    assert not gate.passed
    e = effect(gate=gate)
    assert e.name == ARM_DIFFERENCE
    text = e.as_text()
    assert "lift" not in text.lower()
    assert f"the gate returned {gate.verdict.replace('_', ' ')}" in text
    assert "not a claim about what a customer sees" in text


def test_an_undecided_gate_is_not_a_pass_here_either():
    """The gate's third answer is the one most likely to be waved through."""
    gate = undecided_gate()
    assert gate.verdict == GATE_UNDECIDED
    assert not effect(gate=gate).is_lift


# -- transport, and what the gate did not buy -------------------------------


def test_a_transported_level_carries_the_gates_margin_on_top_of_its_own():
    gate = passing_gate()
    assert gate.verdict == STANDS_IN
    e = effect(gate=gate)

    live = e.transported(e.held)
    assert live is not None
    assert live.point == e.held.point
    assert live.low == pytest.approx(max(0.0, e.held.low - gate.margin))
    assert live.high == pytest.approx(min(1.0, e.held.high + gate.margin))
    assert live.half_width > e.held.half_width


def test_a_transported_rate_is_still_a_rate():
    """Widening must not push an appearance rate below zero or past one."""
    floor = rows(20, [[0, 0, 0, 0, 0], [0, 0, 0, 0, 1]])
    ceiling = rows(20, [[1, 1, 1, 1, 1], [1, 1, 1, 1, 0]])
    e = effect(held=ceiling, dropped=floor, gate=passing_gate())
    assert e.transported(e.dropped).low >= 0.0
    assert e.transported(e.held).high <= 1.0


def test_nothing_is_transported_without_a_gate():
    e = effect(gate=None)
    assert e.transported(e.held) is None


def test_the_screen_says_the_gate_does_not_cover_the_difference_of_differences():
    """A passing gate bounds levels. The transported quantity is a gap."""
    text = effect(gate=passing_gate()).as_text()
    assert "does not bound the difference of differences" in text
    assert "named assumption rather than on a proof" in text


# -- the four answers -------------------------------------------------------


def test_the_arms_are_identical_so_the_zero_is_refused_rather_than_published():
    """Two arms that never differed produce the most confident wrong answer.

    The difference is exactly zero and the interval has no width, so every
    threshold in this module would read it as proof that removing the source
    changed nothing. It is instead the signature of the same arm handed over
    twice, or of an outcome with no variation in it.
    """
    held, _ = arms()
    e = effect(held=held, dropped={k: list(v) for k, v in held.items()})

    assert e.verdict == NO_CONTRAST
    assert e.verdict != NEGLIGIBLE
    assert e.difference.interval.half_width == pytest.approx(0.0)
    assert "not a measured zero" in e.reason
    assert e.direction == "neither"


def test_an_effect_smaller_than_the_margin_is_a_finding_of_its_own():
    """Two and a half points, measured cleanly enough to exclude zero.

    A significance test would call this a result and put it on a slide. It is
    smaller than the precision the product quotes itself at, so it cannot move
    any claim the product is willing to make, and saying so is the useful
    answer rather than a weaker version of one.
    """
    e = effect(held=rows(40, FINE_HELD), dropped=rows(40, FINE_DROPPED), margin=0.05)
    assert e.verdict == NEGLIGIBLE
    assert e.difference.interval.excludes_zero
    assert abs(e.difference.interval.point) == pytest.approx(0.025)
    assert "cannot move a claim" in e.reason


def test_a_round_that_cannot_separate_the_source_says_what_would():
    """Six points against a five point margin, measured too loosely to tell."""
    e = effect(held=rows(30, HELD), dropped=rows(30, [[1, 1, 0, 0, 0]]), margin=0.05)
    assert e.verdict == UNDECIDED
    assert e.calls_needed is not None and e.calls_needed > e.calls_made
    assert e.shortfall == e.calls_needed - e.calls_made
    assert f"{e.calls_needed} calls an arm would decide it" in e.as_text()


def test_an_undecided_verdict_still_reports_a_direction_it_did_settle():
    e = effect(held=rows(30, HELD), dropped=rows(30, [[1, 1, 0, 0, 0]]), margin=0.05)
    assert e.verdict == UNDECIDED
    assert e.difference.significant, "this interval does exclude zero"
    assert "the direction is settled and the size is not" in e.reason


def test_a_prompt_set_too_small_to_ever_decide_quotes_no_call_count():
    cancelling = [[1, 0, 0, 0, 0], [1, 1, 0, 0, 0], [1, 1, 1, 0, 0], [0, 0, 0, 0, 0]]
    held = rows(8, [[1, 1, 0, 0, 0], [1, 0, 0, 0, 0], [1, 1, 1, 0, 0], [0, 0, 0, 0, 0]])
    e = effect(held=held, dropped=rows(8, cancelling), margin=0.05)
    assert e.verdict == UNDECIDED
    assert not e.reachable
    assert e.calls_needed is None
    assert "no number of repeats settles this" in e.as_text()


def test_looking_harder_turns_undecided_into_an_answer_on_the_same_behaviour():
    """The same generating process, decided at two hundred prompts."""
    cancelling = [[1, 0, 0, 0, 0], [1, 1, 0, 0, 0], [1, 1, 1, 0, 0], [0, 0, 0, 0, 0]]
    held = [[1, 1, 0, 0, 0], [1, 0, 0, 0, 0], [1, 1, 1, 0, 0], [0, 0, 0, 0, 0]]

    small = effect(held=rows(8, held), dropped=rows(8, cancelling), margin=0.05)
    large = effect(held=rows(200, held), dropped=rows(200, cancelling), margin=0.05)

    assert small.verdict == UNDECIDED
    assert large.verdict == NEGLIGIBLE
    assert large.difference.interval.point == pytest.approx(
        small.difference.interval.point, abs=0.01
    ), "the answer changed because the round did, not because the source did"


# -- several sources at once is several claims ------------------------------


def test_holding_five_sources_at_once_widens_every_interval():
    held, dropped = arms()
    alone = effect(held=held, dropped=dropped)
    family = ablation_series(
        held,
        {f"https://s{i}.example/page": dropped for i in range(5)},
        margin=0.05,
        gate=None,
    )
    assert len(family) == 5
    for e in family:
        assert e.family_size == 5
        assert e.difference.interval.half_width > alone.difference.interval.half_width
        assert "held at once" in e.as_text()


def test_the_eighth_source_changes_what_the_first_one_may_say():
    """The multiplicity charge, made visible on one source.

    Measured on its own the contrast clears a five point margin. Measured as
    one of eight it does not, and nothing about that source or its arm changed
    between the two readings. Publishing the first number after running the
    second comparison is the thing this correction exists to stop.
    """
    marginal = [[1, 1, 0, 0, 0], [1, 1, 0, 0, 0], [1, 1, 1, 0, 0], [1, 0, 0, 0, 0]]
    held, dropped = rows(24, HELD), rows(24, marginal)

    assert effect(held=held, dropped=dropped).verdict == MOVES
    family = ablation_series(
        held,
        {f"https://s{i}.example/page": dropped for i in range(8)},
        margin=0.05,
        gate=None,
    )
    assert family[0].verdict == UNDECIDED


def test_a_series_keeps_the_order_it_was_handed():
    """Sorting by effect size is how the least stable estimate gets the headline."""
    held, dropped = arms()
    urls = [f"https://s{i}.example/page" for i in range(4)]
    family = ablation_series(
        held, {u: dropped for u in urls}, margin=0.05, gate=None
    )
    assert [e.source for e in family] == urls


def test_each_arm_in_a_series_resamples_on_its_own_seed():
    held, dropped = arms()
    family = ablation_series(
        held,
        {f"https://s{i}.example/page": dropped for i in range(3)},
        margin=0.05,
        gate=None,
        seed=7,
    )
    seeds = [e.difference.interval.method for e in family]
    assert "seed=7)" in seeds[0] and "seed=8)" in seeds[1] and "seed=9)" in seeds[2]


def test_one_source_in_a_series_is_not_charged_for_a_family():
    held, dropped = arms()
    only = ablation_series(held, {SOURCE: dropped}, margin=0.05, gate=None)[0]
    alone = effect(held=held, dropped=dropped)
    assert only.difference.interval == alone.difference.interval


def test_a_series_with_nothing_removed_is_refused():
    held, _ = arms()
    with pytest.raises(ValueError, match="at least one source"):
        ablation_series(held, {}, margin=0.05, gate=None)


# -- what this refuses to be asked ------------------------------------------


def test_a_margin_of_zero_is_refused_by_name():
    with pytest.raises(ValueError, match="margin must be positive"):
        effect(margin=0.0)


def test_a_margin_that_covers_the_whole_range_is_refused():
    with pytest.raises(ValueError, match="decides nothing"):
        effect(margin=1.0)


def test_the_source_that_was_removed_has_to_be_named():
    with pytest.raises(ValueError, match="has to be named"):
        effect(source="   ")


def test_two_arms_with_no_prompt_in_common_cannot_be_paired():
    with pytest.raises(ValueError, match="nothing to pair"):
        effect(held={"p1": [1, 0]}, dropped={"p2": [1, 0]})


def test_a_confound_travels_onto_the_screen_with_the_number():
    text = effect(confounded_by=("sonar (model version)",)).as_text()
    assert "CONFOUNDED" in text
    assert "sonar (model version)" in text
    assert "did not differ only in the source that was removed" in text


def test_the_same_inputs_produce_the_same_screen():
    held, dropped = arms()
    first = effect(held=held, dropped=dropped, gate=passing_gate())
    second = effect(held=held, dropped=dropped, gate=passing_gate())
    assert first.as_text() == second.as_text()


# -- the command that puts the sentence on one screen -----------------------

import io  # noqa: E402
from pathlib import Path  # noqa: E402

from lulumelon.cli import Console, lift  # noqa: E402
from lulumelon.collect import (  # noqa: E402
    Brand,
    FakeProvider,
    Ledger,
    Prompt,
    ReplicaProvider,
    replica_prompt,
    replica_surface,
    run_round,
    without,
)

SRC = (
    "https://a.example/guide",
    "https://b.example/list",
    "https://c.example/review",
)
DROP = SRC[1]
ORNEK = (Brand(name="ornek", aliases=()),)

#: Four prompt shapes, each asked four times. Rates vary from prompt to prompt
#: on both sides, so the intervals the command prints come from a round with
#: something in it to resample rather than from four identical questions.
LIVE_ROWS = (
    ("ornek.", "ornek.", "ornek.", "nobody."),
    ("ornek.", "ornek.", "nobody.", "nobody."),
    ("ornek.", "ornek.", "ornek.", "ornek."),
    ("ornek.", "nobody.", "nobody.", "nobody."),
)
HELD_ROWS = LIVE_ROWS
DROPPED_ROWS = (
    ("ornek.", "ornek.", "nobody.", "nobody."),
    ("ornek.", "nobody.", "nobody.", "nobody."),
    ("ornek.", "ornek.", "nobody.", "nobody."),
    ("ornek.", "nobody.", "nobody.", "nobody."),
)
SILENT_ROWS = (("nobody.",) * 4,)


class Recorder:
    def __init__(self) -> None:
        self.out, self.err = io.StringIO(), io.StringIO()
        self.console = Console(out=self.out, err=self.err)

    @property
    def text(self) -> str:
        return self.out.getvalue() + self.err.getvalue()


def three_rounds(
    tmp_path,
    *,
    live_rows=LIVE_ROWS,
    held_rows=HELD_ROWS,
    dropped_rows=DROPPED_ROWS,
    n=30,
    k=4,
    dropped_model=None,
):
    """A live round and both replica arms, over the same prompts, in one ledger."""
    led = Ledger(tmp_path)
    prompts = [Prompt(id=f"p{i}", text=f"who should I use for job {i}?") for i in range(n)]

    def script(rows, wrap=lambda text: text):
        return {wrap(p.text): rows[i % len(rows)] for i, p in enumerate(prompts)}

    live = run_round(
        ledger=led,
        provider=FakeProvider(surface="api", script=script(live_rows)),
        prompts=prompts, brands=ORNEK, k=k, subject="ornek",
    )
    base = FakeProvider(surface="api")
    full = ReplicaProvider(base=base, sources=SRC)
    base.script = script(held_rows, lambda text: replica_prompt(text, SRC))
    held = run_round(
        ledger=led, provider=full, prompts=prompts, brands=ORNEK, k=k, subject="ornek"
    )

    other = FakeProvider(surface="api", model=dropped_model or "fake-1")
    arm = ReplicaProvider(base=other, sources=without(SRC, DROP))
    other.script = script(dropped_rows, lambda text: replica_prompt(text, arm.sources))
    dropped = run_round(
        ledger=led, provider=arm, prompts=prompts, brands=ORNEK, k=k, subject="ornek"
    )
    return led, live.snapshot_id, held.snapshot_id, dropped.snapshot_id


def run_lift(tmp_path, held_id, dropped_id, **kw):
    rec = Recorder()
    args = dict(
        ledger_dir=Path(tmp_path),
        held=held_id,
        dropped=dropped_id,
        brand="ornek",
        source=DROP,
        sources=SRC,
        margin=0.05,
    )
    args.update(kw)
    return lift(rec.console, **args), rec.text


def test_the_command_prints_both_levels_and_the_gap_and_exits_zero(tmp_path):
    _, live, held, dropped = three_rounds(tmp_path)
    code, text = run_lift(tmp_path, held, dropped, live=live)

    assert code == 0
    assert "REPLICA GATE: STANDS IN" in text
    assert "ABLATION: MOVES" in text
    assert "source held      62.5%" in text
    assert "source dropped   37.5%" in text
    assert "difference       +25.0 points" in text
    assert "NAMED: lift" in text
    assert "over 30 paired prompts" in text


def test_the_list_is_printed_in_order_with_the_removed_page_marked(tmp_path):
    _, live, held, dropped = three_rounds(tmp_path)
    _, text = run_lift(tmp_path, held, dropped, live=live)
    for i, url in enumerate(SRC, start=1):
        assert f"[{i}] {url}" in text
    assert f"[2] {DROP}   <- removed in the dropped arm" in text


def verdict_block(text: str) -> str:
    """Everything from the verdict onwards, so the command's own name is not read as one."""
    return text[text.index("ABLATION:"):]


def test_with_no_live_round_the_word_never_reaches_the_screen(tmp_path):
    """The arithmetic still runs. What it may be called does not."""
    _, _, held, dropped = three_rounds(tmp_path)
    code, text = run_lift(tmp_path, held, dropped)

    assert code == 6, "a laboratory result must not exit zero"
    assert "NAMED: arm difference" in text
    assert "lift" not in verdict_block(text).lower()
    assert "difference       +25.0 points" in text


def test_a_gate_that_does_not_pass_takes_the_word_from_the_command_too(tmp_path):
    _, live, held, dropped = three_rounds(tmp_path, live_rows=SILENT_ROWS)
    code, text = run_lift(tmp_path, held, dropped, live=live)
    assert code == 6
    assert "REPLICA GATE: DIFFERS" in text
    assert "NAMED: arm difference" in text
    assert "lift" not in verdict_block(text).lower()


@pytest.mark.parametrize("margin,expected", [(0.40, 1), (0.25, 4)])
def test_the_margin_decides_which_answer_the_command_gives(tmp_path, margin, expected):
    """Twenty-five points is worth chasing at five and not at forty.

    At a margin of exactly twenty-five the interval straddles it, and the
    command says it cannot tell rather than picking the side it is nearer.
    """
    _, live, held, dropped = three_rounds(tmp_path)
    code, _ = run_lift(tmp_path, held, dropped, live=live, margin=margin, gate_margin=0.05)
    assert code == expected


def test_two_arms_that_never_differed_do_not_exit_as_a_finding(tmp_path):
    _, live, held, dropped = three_rounds(tmp_path, dropped_rows=HELD_ROWS)
    code, text = run_lift(tmp_path, held, dropped, live=live)
    assert code == 5
    assert "ABLATION: NO CONTRAST" in text
    assert "not a measured zero" in text


# -- the treatment is checked against the evidence --------------------------


def test_swapping_the_two_arms_is_refused_by_the_ledger(tmp_path):
    _, _, held, dropped = three_rounds(tmp_path)
    with pytest.raises(ValueError, match="the two arms have been swapped"):
        run_lift(tmp_path, dropped, held)


def test_a_source_list_that_is_not_the_one_asked_is_refused(tmp_path):
    _, _, held, dropped = three_rounds(tmp_path)
    with pytest.raises(ValueError, match="was collected under"):
        run_lift(tmp_path, held, dropped, sources=SRC + ("https://d.example/extra",))


def test_reordering_the_list_is_a_different_arm(tmp_path):
    """Position in a supplied list is a treatment, and the ledger knows it."""
    _, _, held, dropped = three_rounds(tmp_path)
    reordered = (SRC[1], SRC[0], SRC[2])
    with pytest.raises(ValueError, match="was collected under"):
        run_lift(tmp_path, held, dropped, sources=reordered)


def test_a_round_written_before_digests_is_read_and_not_verified(tmp_path):
    """An old evidence file stays readable, and stops short of proving itself."""
    led = Ledger(tmp_path)
    prompts = [Prompt(id=f"p{i}", text=f"q{i}") for i in range(4)]
    legacy = run_round(
        ledger=led,
        provider=FakeProvider(surface="replica", script={p.text: LIVE_ROWS[0] for p in prompts}),
        prompts=prompts, brands=ORNEK, k=4, subject="ornek",
    )
    _, _, _, dropped = three_rounds(tmp_path)
    with pytest.raises(ValueError, match="it cannot be verified"):
        run_lift(tmp_path, legacy.snapshot_id, dropped)


def test_a_live_round_cannot_be_handed_in_as_the_live_side_twice(tmp_path):
    _, _, held, dropped = three_rounds(tmp_path)
    with pytest.raises(ValueError, match="itself a replica round"):
        run_lift(tmp_path, held, dropped, live=held)


def test_a_broken_chain_produces_no_number_at_all(tmp_path):
    led, live, held, dropped = three_rounds(tmp_path)
    path = led.path_of(held)
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[0] = lines[0].replace("ornek.", "ornek!")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    code, text = run_lift(tmp_path, held, dropped, live=live)
    assert code == 3
    assert "CHAIN BROKEN" in text
    assert "ABLATION" not in text


def test_a_second_model_version_between_the_arms_travels_onto_the_screen(tmp_path):
    """The two arms may differ in one source. They may not differ in the model."""
    _, live, held, dropped = three_rounds(tmp_path, dropped_model="fake-2")
    _, text = run_lift(tmp_path, held, dropped, live=live)
    assert "CONFOUNDED" in text
    assert "did not differ only in the source that was removed" in text


def test_the_sentence_the_readme_quotes_is_the_one_the_command_prints(tmp_path):
    """The README quotes this command's output, so it is read back off a run."""
    import re

    _, live, held, dropped = three_rounds(tmp_path)
    _, text = run_lift(tmp_path, held, dropped, live=live)

    low = re.search(r"source dropped\s+([\d.]+)%", text).group(1)
    high = re.search(r"source held\s+([\d.]+)%", text).group(1)
    gap = re.search(r"difference\s+([+-][\d.]+) points", text).group(1)

    readme = (Path(__file__).resolve().parents[2] / "README.md").read_text(encoding="utf-8")
    assert f"`{low}% without it, {high}%\nwith it, {gap} points`" in readme


def test_an_arm_carrying_two_engines_is_refused_by_name(tmp_path, two_engine_round):
    """Both commands read their rounds through one door, so both refuse here.

    The mixed round is given the held arm's own surface, so the only thing left
    for the refusal to be about is the engine.
    """
    _, live, _, dropped = three_rounds(tmp_path)
    _, mixed = two_engine_round(
        tmp_path,
        {"perplexity": ("ornek.",), "anthropic": ("nobody.",)},
        brands=ORNEK,
        surface=replica_surface(SRC),
    )
    with pytest.raises(ValueError, match="more than one engine") as refused:
        run_lift(tmp_path, mixed, dropped, live=live)
    assert "perplexity, anthropic" in str(refused.value)
