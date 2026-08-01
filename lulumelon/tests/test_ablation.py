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

from lulumelon.cli import Console, ablate
from lulumelon.collect import (
    Brand,
    FakeProvider,
    Ledger,
    Prompt,
    ReplicaProvider,
    replica_prompt,
    run_round,
)
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


# -- the command that puts one verdict on one screen ------------------------

import io  # noqa: E402
from pathlib import Path  # noqa: E402

SRC = ("https://a.example/guide", "https://b.example/list")
MARX = (Brand(name="marx", aliases=()),)


class Recorder:
    def __init__(self) -> None:
        self.out, self.err = io.StringIO(), io.StringIO()
        self.console = Console(out=self.out, err=self.err)

    @property
    def text(self) -> str:
        return self.out.getvalue() + self.err.getvalue()


def two_rounds(tmp_path, live_replies, replica_replies, *, n=30, k=4, replica_model=None):
    """A live round and a replica round over the same prompts, in one ledger."""
    led = Ledger(tmp_path)
    prompts = [Prompt(id=f"p{i}", text=f"who should I use for {i}?") for i in range(n)]

    live = run_round(
        ledger=led,
        provider=FakeProvider(surface="api", script={p.text: live_replies for p in prompts}),
        prompts=prompts, brands=MARX, k=k, subject="marx",
    )
    base = FakeProvider(surface="api", model=replica_model or "fake-1")
    lab = ReplicaProvider(base=base, sources=SRC)
    base.script = {replica_prompt(p.text, SRC): replica_replies for p in prompts}
    replica = run_round(
        ledger=led, provider=lab, prompts=prompts, brands=MARX, k=k, subject="marx"
    )
    return led, live.snapshot_id, replica.snapshot_id


def run_ablate(tmp_path, live_id, replica_id, **kw):
    rec = Recorder()
    args = dict(ledger_dir=Path(tmp_path), live=live_id, replica=replica_id,
                brand="marx", margin=0.05)
    args.update(kw)
    return ablate(rec.console, **args), rec.text


SOME = ("marx is one pick.", "marx again.", "nobody.", "nobody.")
NONE = ("nobody.", "nobody.", "nobody.", "nobody.")


def test_a_replica_that_tracks_the_surface_passes_with_a_zero_exit(tmp_path):
    _, live, replica = two_rounds(tmp_path, SOME, SOME)
    code, text = run_ablate(tmp_path, live, replica)
    assert code == 0
    assert "REPLICA GATE: STANDS IN" in text
    assert "may be read as a lift" in text


def test_a_replica_that_does_not_track_the_surface_fails_with_a_nonzero_exit(tmp_path):
    _, live, replica = two_rounds(tmp_path, SOME, NONE)
    code, text = run_ablate(tmp_path, live, replica)
    assert code == 1
    assert "REPLICA GATE: DIFFERS" in text
    assert "nothing causal is read off this replica" in text


def test_a_round_too_small_to_decide_does_not_exit_zero(tmp_path):
    """The whole point of the third verdict: cannot tell is not fine.

    The two sides average the same rate. They disagree prompt by prompt, by
    half in each direction, so six prompts cannot resolve a five point margin
    and the honest answer is that this round settles nothing.
    """
    _, live, replica = two_rounds(
        tmp_path,
        ("marx.", "marx.", "nobody.", "nobody."),
        ("marx.", "nobody."),
        n=6, k=2,
    )
    code, text = run_ablate(tmp_path, live, replica)
    assert code == 4, "an undecided gate must not report success"
    assert "REPLICA GATE: UNDECIDED" in text
    assert "nothing causal is read off this replica" in text


def test_a_broken_chain_produces_no_verdict_at_all(tmp_path):
    led, live, replica = two_rounds(tmp_path, SOME, SOME)
    path = led.path_of(live)
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[0] = lines[0].replace("marx is one pick.", "marx is one pick!")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    code, text = run_ablate(tmp_path, live, replica)
    assert code == 3
    assert "CHAIN BROKEN" in text
    assert "REPLICA GATE" not in text


def test_two_live_rounds_are_not_what_this_gate_asks(tmp_path):
    _, live, _ = two_rounds(tmp_path, SOME, SOME)
    with pytest.raises(ValueError, match="not on the replica surface"):
        run_ablate(tmp_path, live, live)


def test_a_replica_cannot_be_used_as_the_live_side(tmp_path):
    """Passing then proves only that the instrument repeats itself."""
    _, _, replica = two_rounds(tmp_path, SOME, SOME)
    with pytest.raises(ValueError, match="itself a replica round"):
        run_ablate(tmp_path, replica, replica)


def test_a_replica_on_another_model_version_says_so_on_screen(tmp_path):
    """Surfaces differ by construction here; model versions must not."""
    _, live, replica = two_rounds(tmp_path, SOME, SOME, replica_model="fake-2")
    _, text = run_ablate(tmp_path, live, replica)
    assert "CONFOUNDED" in text
    assert "model version" in text


def test_the_screen_names_both_rounds_and_what_was_usable_in_them(tmp_path):
    _, live, replica = two_rounds(tmp_path, SOME, SOME)
    _, text = run_ablate(tmp_path, live, replica)
    assert live in text and replica in text
    assert "120 usable of 120 asked" in text


# -- a round that carries two engines ---------------------------------------

from lulumelon.cli import _detections  # noqa: E402
from lulumelon.collect import replay, replica_surface  # noqa: E402
from lulumelon.mirror.types import group_runs  # noqa: E402

#: One engine names the brand every time, the other never does. Keyed by the
#: prompt alone the two collapse onto one entry, so whichever engine was
#: written second decides whether the round reads as 100% or as 0%.
MIXED = {"perplexity": ("marx.",), "anthropic": ("nobody.",)}


def test_two_engines_answering_one_prompt_stay_two_samples(tmp_path, two_engine_round):
    """The keying collision, on the smallest round that can show it.

    `group_runs` buckets by (prompt, engine), and this mapping is built out of
    those buckets, so keying it by the prompt alone is narrower than the thing
    it is built from: the two samples for `p0` land on one key and the second
    overwrites the first. Nothing raises, nothing is printed, and one engine's
    answers to every prompt leave the sample.
    """
    ledger, snapshot = two_engine_round(tmp_path, MIXED, brands=MARX)
    played = replay(ledger, snapshot)

    kept = _detections(played, "marx")
    assert set(kept) == {(s.prompt_id, s.engine) for s in group_runs(played.runs)}
    assert sum(len(runs) for runs in kept.values()) == len(played.runs)


def test_a_live_round_carrying_two_engines_is_refused_by_name(tmp_path, two_engine_round):
    """A round is one engine, so two of them is not a round to key around."""
    _, _, replica = two_rounds(tmp_path, SOME, SOME)
    _, mixed = two_engine_round(tmp_path, MIXED, brands=MARX)

    rec = Recorder()
    with pytest.raises(ValueError, match="more than one engine") as refused:
        ablate(
            rec.console,
            ledger_dir=Path(tmp_path),
            live=mixed,
            replica=replica,
            brand="marx",
            margin=0.05,
        )
    assert "perplexity, anthropic" in str(refused.value)
    assert mixed in str(refused.value)
    assert "engines: perplexity, anthropic" in rec.text


def test_the_replica_side_is_refused_for_the_same_reason(tmp_path, two_engine_round):
    _, live, _ = two_rounds(tmp_path, SOME, SOME)
    _, mixed = two_engine_round(
        tmp_path, MIXED, brands=MARX, surface=replica_surface(SRC)
    )
    with pytest.raises(ValueError, match="more than one engine"):
        run_ablate(tmp_path, live, mixed)
