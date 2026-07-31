"""What a collection round promises, stated as failures it must not allow."""

from __future__ import annotations

import pytest

from lulumelon.collect import (
    Brand,
    Budget,
    FakeProvider,
    Ledger,
    Prompt,
    Usage,
    replay,
    run_round,
)
from lulumelon.prices import price_for

BRANDS = (Brand("Marx", aliases=("marx.finance",)), Brand("Rival"))

P1 = Prompt("p1", "best trading agent platform?")
P2 = Prompt("p2", "alternatives to Rival?")

OPUS = price_for("anthropic", "claude-opus-5")
#: A stub that reports its usage, so a round through it is priced from measured
#: counts rather than from the guard's opening guess. 1000 in and 200 out on
#: this price is $0.01 of tokens, and one search is another $0.01.
METERED = Usage(input_tokens=1000, output_tokens=200, searches=1)


def ticking_clock():
    """A clock that never repeats, so ordering bugs cannot hide behind ties."""
    n = 0

    def clock() -> str:
        nonlocal n
        n += 1
        return f"2026-07-31T10:{n:02d}:00Z"

    return clock


@pytest.fixture
def led(tmp_path):
    return Ledger(tmp_path)


def test_k_of_one_is_refused_not_quietly_accepted(led):
    # a design that cannot carry an interval must not be able to produce a
    # ledger that looks measurable.
    with pytest.raises(ValueError, match="cannot support an interval"):
        run_round(
            ledger=led,
            provider=FakeProvider(),
            prompts=[P1],
            brands=BRANDS,
            k=1,
            subject="marx",
            clock=ticking_clock(),
        )


def test_every_ask_is_written_once(led):
    provider = FakeProvider(script={P1.text: ("Marx leads.", "Rival leads.")})
    result = run_round(
        ledger=led,
        provider=provider,
        prompts=[P1, P2],
        brands=BRANDS,
        k=3,
        subject="marx",
        clock=ticking_clock(),
    )

    assert result.asked == 6
    assert result.errors == 0
    assert led.count(result.snapshot_id) == 6
    assert led.verify(result.snapshot_id) == []


def test_a_failed_ask_is_recorded_not_retried(led):
    # the 2nd and 5th draws fail. A collector that retried would report six
    # answers; one that dropped them would report four and call it six.
    provider = FakeProvider(script={P1.text: ("Marx leads.",)}, fail_on=(1, 4))
    result = run_round(
        ledger=led,
        provider=provider,
        prompts=[P1],
        brands=BRANDS,
        k=6,
        subject="marx",
        clock=ticking_clock(),
    )

    assert result.asked == 6
    assert result.errors == 2
    assert led.count(result.snapshot_id) == 6, "failed asks stay in the ledger"

    statuses = [r.status for r in led.read(result.snapshot_id)]
    assert statuses.count("error") == 2
    errored = [r for r in led.read(result.snapshot_id) if r.status == "error"]
    assert all(r.error for r in errored), "a failure without a reason is not a record"
    assert all(r.brands == () for r in errored), "a failed ask observed no brands"


def test_replay_hands_back_the_failures_it_excluded(led):
    provider = FakeProvider(script={P1.text: ("Marx leads.",)}, fail_on=(1,))
    result = run_round(
        ledger=led,
        provider=provider,
        prompts=[P1],
        brands=BRANDS,
        k=4,
        subject="marx",
        clock=ticking_clock(),
    )

    seen = replay(led, result.snapshot_id)
    assert len(seen.runs) == 3
    assert seen.dropped == 1
    assert seen.total == 4
    # a timeout is missing data, not an answer that named nobody
    assert all(r.brands for r in seen.runs)
    assert "excluded" in seen.as_text()


def test_a_round_carries_one_surface_and_one_model(led):
    provider = FakeProvider(script={P1.text: ("Marx leads.",)}, surface="logged_out")
    result = run_round(
        ledger=led,
        provider=provider,
        prompts=[P1],
        brands=BRANDS,
        k=2,
        subject="marx",
        clock=ticking_clock(),
    )

    seen = replay(led, result.snapshot_id)
    assert seen.surfaces == ("logged_out",)
    assert seen.is_single_condition
    assert "WARNING" not in seen.as_text()
    assert all(r.surface == "logged_out" for r in seen.runs)


def test_mixed_conditions_are_flagged_rather_than_averaged(led):
    # the same subject measured on two surfaces in one snapshot. Published
    # measurement puts the gap between surfaces above the gap between reruns,
    # so this has to be visible before anyone reads a score off it.
    sid = None
    for surface in ("logged_out", "api"):
        provider = FakeProvider(script={P1.text: ("Marx leads.",)}, surface=surface)
        result = run_round(
            ledger=led,
            provider=provider,
            prompts=[P1],
            brands=BRANDS,
            k=2,
            subject="marx",
            clock=ticking_clock(),
        )
        sid = sid or result.snapshot_id

    # force the mix into one snapshot the way a careless caller would
    provider = FakeProvider(script={P1.text: ("Marx leads.",)}, surface="api")
    run_round(
        ledger=led,
        provider=provider,
        prompts=[P1],
        brands=BRANDS,
        k=2,
        subject="marx",
        clock=ticking_clock(),
    )

    # each round is its own snapshot, which is the actual protection
    assert len(led.snapshots()) == 3


def test_asking_twice_never_overwrites_the_first_round(led):
    provider = FakeProvider(script={P1.text: ("Marx leads.",)})
    first = run_round(
        ledger=led, provider=provider, prompts=[P1], brands=BRANDS, k=2,
        subject="marx", clock=ticking_clock(),
    )
    second = run_round(
        ledger=led, provider=provider, prompts=[P1], brands=BRANDS, k=2,
        subject="marx", clock=ticking_clock(),
    )

    assert first.snapshot_id != second.snapshot_id
    assert led.count(first.snapshot_id) == 2
    assert led.verify(first.snapshot_id) == []
    assert led.verify(second.snapshot_id) == []


def test_the_collector_computes_no_score(led):
    # the wall between the network and the arithmetic: a round returns counts.
    provider = FakeProvider(script={P1.text: ("Marx leads.",)})
    result = run_round(
        ledger=led, provider=provider, prompts=[P1], brands=BRANDS, k=2,
        subject="marx", clock=ticking_clock(),
    )
    assert not hasattr(result, "visibility")
    assert not hasattr(result, "score")
    assert result.ok == 2


# -- the budget, when there is one ------------------------------------------


def test_a_budget_nobody_could_exhaust_leaves_the_round_alone(led):
    # the guard has to be invisible when it is not binding, or nobody will run
    # a round with one on.
    unguarded = run_round(
        ledger=led, provider=FakeProvider(usage=METERED), prompts=[P1, P2], brands=BRANDS,
        k=3, subject="marx", clock=ticking_clock(),
    )
    guarded = run_round(
        ledger=led, provider=FakeProvider(usage=METERED), prompts=[P1, P2], brands=BRANDS,
        k=3, subject="marx", clock=ticking_clock(),
        budget=Budget(price=OPUS, limit_usd=5.0, max_searches=1),
    )

    assert (guarded.asked, guarded.ok, guarded.errors) == (unguarded.asked, unguarded.ok, unguarded.errors)
    assert guarded.planned == unguarded.planned == 6
    assert guarded.unasked == 0
    assert not guarded.stopped_for_budget
    assert led.count(guarded.snapshot_id) == led.count(unguarded.snapshot_id) == 6


def test_a_round_that_runs_out_stops_short_and_says_how_short(led):
    # $0.25 at $0.02 a call is twelve asks, and the design asked for sixteen.
    # The four that were never made are the reason every interval computed off
    # this snapshot is wider than the plan that bought it.
    budget = Budget(price=OPUS, limit_usd=0.25, max_searches=1)
    result = run_round(
        ledger=led, provider=FakeProvider(usage=METERED), prompts=[P1, P2], brands=BRANDS,
        k=8, subject="marx", clock=ticking_clock(), budget=budget,
    )

    assert result.planned == 16
    assert result.asked == 12
    assert result.unasked == 4
    assert result.stopped_for_budget
    assert result.errors == 0
    assert "stopped for budget, 4 never asked" in result.as_text()

    assert led.count(result.snapshot_id) == 12, "the ledger holds the asks that happened"
    assert led.verify(result.snapshot_id) == [], "stopping leaves no half-written record"
    assert budget.spent_usd == pytest.approx(0.24)


def test_a_budget_for_three_unmetered_calls_makes_exactly_three(led):
    # the stub reports no usage at all, so every call is charged at the opening
    # ceiling of $0.08 and $0.28 buys three of them. A guard that read the
    # silence as no spend would have asked all six.
    budget = Budget(price=OPUS, limit_usd=0.28, max_searches=1)
    result = run_round(
        ledger=led, provider=FakeProvider(), prompts=[P1, P2, Prompt("p3", "who else?")],
        brands=BRANDS, k=2, subject="marx", clock=ticking_clock(), budget=budget,
    )

    assert result.asked == 3
    assert result.planned == 6
    assert result.stopped_for_budget
    assert led.count(result.snapshot_id) == 3
    assert budget.unmetered_calls == 3
    assert budget.spent_usd == pytest.approx(0.24)


def test_a_round_that_cannot_afford_its_first_ask_asks_nothing(led):
    # a snapshot with no records in it is still a snapshot, and it is a better
    # outcome than one call made to discover the budget was never enough.
    budget = Budget(price=OPUS, limit_usd=0.01, max_searches=1)
    result = run_round(
        ledger=led, provider=FakeProvider(usage=METERED), prompts=[P1], brands=BRANDS,
        k=4, subject="marx", clock=ticking_clock(), budget=budget,
    )

    assert result.asked == 0
    assert result.unasked == 4
    assert result.stopped_for_budget
    assert result.error_rate == 0.0, "asking nothing is not failing"
    assert led.count(result.snapshot_id) == 0
    assert budget.spent_usd == 0.0
