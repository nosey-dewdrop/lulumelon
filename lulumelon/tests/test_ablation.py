"""The gate that can retire this whole line of work, stated as what it must refuse.

The replica is the only instrument that can turn a co-occurrence into a claim
about cause, and it is worthless unless it behaves like the surface it replaces.
So the tests here are mostly about the ways a gate can open when it should not,
because a gate that opens on thin evidence is worse than no gate: it launders
a laboratory artefact into a sentence a customer pays for.

The one that matters most is `test_the_same_truth_is_undecided_until_enough_calls_are_made`.
Two sides that are genuinely alike come back `undecided` at four prompts and
`stands_in` at two hundred, on identical underlying behaviour. Nothing about
the replica changed between those runs. Only how hard we looked did, and a gate
that cannot tell those apart rewards not looking.
"""

from __future__ import annotations

import pytest

from lulumelon.mirror.ablation import DIFFERS, STANDS_IN, UNDECIDED, replica_gate


def sides(n_prompts: int, live_row: list[int], replica_rows: list[list[int]]):
    """`n_prompts` prompts, each with the same live pattern and a cycled replica."""
    live = {f"p{i}": list(live_row) for i in range(n_prompts)}
    replica = {f"p{i}": list(replica_rows[i % len(replica_rows)]) for i in range(n_prompts)}
    return live, replica


def flat(n_prompts: int, live_row: list[int], replica_row: list[int]):
    return sides(n_prompts, live_row, [replica_row])


# -- the three answers ------------------------------------------------------


def test_a_replica_that_behaves_identically_stands_in():
    live, replica = flat(12, [1, 1, 0, 0, 1], [1, 1, 0, 0, 1])
    gate = replica_gate(live, replica, margin=0.05)
    assert gate.verdict == STANDS_IN
    assert gate.passed
    assert "inside the margin" in gate.reason


def test_a_replica_that_behaves_nothing_like_the_surface_is_refused():
    live, replica = flat(12, [1, 1, 1, 1, 0], [0, 0, 0, 0, 0])
    gate = replica_gate(live, replica, margin=0.05)
    assert gate.verdict == DIFFERS
    assert not gate.passed
    assert "nothing causal should be read off it" in gate.reason
    assert "-80.0 points" in gate.as_text()


def test_the_same_truth_is_undecided_until_enough_calls_are_made():
    """The whole reason this is an equivalence test and not an overlap test.

    Both sides average the same rate, prompt by prompt, and differ only in
    which repeats land where. At four prompts the interval is 25 points wide
    and the honest answer is that this design cannot tell. At two hundred it
    narrows inside a five point margin and the replica stands in. The data
    generating process is identical in both runs.
    """
    rows = [[1, 1, 1, 0], [1, 0, 0, 0]]

    small = replica_gate(*sides(4, [1, 1, 0, 0], rows), margin=0.05)
    assert small.verdict == UNDECIDED
    assert not small.passed, "an underpowered comparison must never open the gate"

    large = replica_gate(*sides(200, [1, 1, 0, 0], rows), margin=0.05)
    assert large.verdict == STANDS_IN
    assert large.difference.interval.point == pytest.approx(
        small.difference.interval.point, abs=0.01
    ), "the answer changed because the design did, not because the replica did"


def test_looking_less_hard_never_turns_a_refusal_into_a_pass():
    """Cutting the round down can lose a verdict; it cannot invent one."""
    live, replica = flat(40, [1, 1, 1, 1, 0], [0, 0, 0, 0, 0])
    assert replica_gate(live, replica, margin=0.05).verdict == DIFFERS

    thin_live = {k: live[k][:1] for k in list(live)[:3]}
    thin_replica = {k: replica[k][:1] for k in list(replica)[:3]}
    assert replica_gate(thin_live, thin_replica, margin=0.05).verdict in (DIFFERS, UNDECIDED)


# -- equivalence is not the same question as significance -------------------


def test_a_real_but_irrelevant_difference_still_stands_in():
    """Two points apart, measured cleanly, with a five point margin.

    The difference excludes zero, so a significance test would call it a
    finding. It is smaller than the precision anything here is published at, so
    it cannot move a claim, and the gate says so.
    """
    live_row = [1] * 5 + [0] * 45
    replica_row = [1] * 6 + [0] * 44
    gate = replica_gate(*flat(30, live_row, replica_row), margin=0.05)

    assert gate.difference.interval.excludes_zero
    assert gate.verdict == STANDS_IN


def test_a_difference_larger_than_the_margin_is_refused_even_when_it_is_small():
    """Eight points is a finding at a five point margin, however tidy it looks."""
    live_row = [1] * 5 + [0] * 45
    replica_row = [1] * 9 + [0] * 41
    gate = replica_gate(*flat(30, live_row, replica_row), margin=0.05)
    assert gate.verdict == DIFFERS


def test_a_wider_margin_accepts_what_a_narrower_one_refuses():
    """The margin is the claim being made, so it has to be visible on screen."""
    live_row = [1] * 5 + [0] * 45
    replica_row = [1] * 9 + [0] * 41
    args = flat(30, live_row, replica_row)
    assert replica_gate(*args, margin=0.05).verdict == DIFFERS
    assert replica_gate(*args, margin=0.10).verdict == STANDS_IN
    assert "+/-10.0 points" in replica_gate(*args, margin=0.10).as_text()


# -- an undecided verdict arrives with the round that would settle it -------


def test_an_undecided_gate_says_how_many_calls_would_decide_it():
    live, replica = sides(40, [1, 1, 0, 0], [[1, 1, 1, 0], [1, 0, 0, 0]])
    gate = replica_gate(live, replica, margin=0.05)
    assert gate.verdict == UNDECIDED
    assert gate.calls_needed is not None and gate.calls_needed > gate.calls_made
    assert gate.shortfall == gate.calls_needed - gate.calls_made
    assert f"{gate.calls_needed} calls a side would decide it" in gate.as_text()


def test_the_call_count_it_asks_for_is_the_count_that_changes_the_verdict():
    """The number is a prediction, and here it is checked against the outcome.

    At forty prompts the gate is undecided and names a figure. Run a round of
    about that size and the verdict resolves. A planner that asked for a number
    the evidence then ignored would be decoration.
    """
    rows = [[1, 1, 1, 0], [1, 0, 0, 0]]
    undecided = replica_gate(*sides(40, [1, 1, 0, 0], rows), margin=0.05)
    assert undecided.verdict == UNDECIDED

    asked_for = undecided.calls_needed
    enough = replica_gate(*sides(asked_for // 4, [1, 1, 0, 0], rows), margin=0.05)
    assert enough.calls_made >= asked_for * 0.9
    assert enough.verdict == STANDS_IN


def test_a_shortfall_shrinks_as_the_round_grows():
    rows = [[1, 1, 1, 0], [1, 0, 0, 0]]
    shortfalls = [
        replica_gate(*sides(n, [1, 1, 0, 0], rows), margin=0.05).shortfall
        for n in (10, 40, 80)
    ]
    assert shortfalls == sorted(shortfalls, reverse=True)


def test_a_prompt_set_too_small_to_ever_decide_says_so_rather_than_quoting_calls():
    """Past the ceiling repeats buy nothing, and a call count would be a lie."""
    live, replica = sides(4, [1, 1, 1, 1], [[1, 1, 1, 1], [0, 0, 0, 0]])
    gate = replica_gate(live, replica, margin=0.02)
    assert gate.verdict == UNDECIDED
    assert not gate.reachable
    assert "no number of repeats settles this at this prompt count" in gate.as_text()


# -- what the gate refuses to be asked --------------------------------------


def test_a_margin_of_zero_is_refused_by_name():
    live, replica = flat(8, [1, 0], [1, 0])
    with pytest.raises(ValueError, match="margin must be positive"):
        replica_gate(live, replica, margin=0.0)


def test_a_margin_that_covers_the_whole_range_is_refused():
    """Every replica passes at a margin of one, so the gate would decide nothing."""
    live, replica = flat(8, [1, 0], [0, 1])
    with pytest.raises(ValueError, match="decides nothing"):
        replica_gate(live, replica, margin=1.0)


def test_two_rounds_with_no_prompt_in_common_cannot_be_paired():
    live = {"p1": [1, 0]}
    replica = {"p2": [1, 0]}
    with pytest.raises(ValueError, match="no prompt appears in both"):
        replica_gate(live, replica, margin=0.05)


def test_a_confounded_comparison_carries_the_confound_onto_the_screen():
    """A replica on another model version is a verdict about two things at once."""
    live, replica = flat(12, [1, 1, 0, 0, 1], [1, 1, 0, 0, 1])
    gate = replica_gate(
        live, replica, margin=0.05, confounded_by=("model moved: sonar -> sonar-2",)
    )
    text = gate.as_text()
    assert "CONFOUNDED" in text
    assert "sonar -> sonar-2" in text
    assert "not about the replica" in text


def test_the_verdict_is_reproducible_for_the_same_inputs():
    """A gate whose answer moves between runs cannot be quoted in a report."""
    args = sides(40, [1, 1, 0, 0], [[1, 1, 1, 0], [1, 0, 0, 0]])
    first = replica_gate(*args, margin=0.05)
    second = replica_gate(*args, margin=0.05)
    assert first.as_text() == second.as_text()
