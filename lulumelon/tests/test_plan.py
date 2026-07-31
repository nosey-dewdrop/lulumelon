"""Sizing a round before it is bought.

The recovery tests are the important ones. A planner that returns a confident
number nobody checked is the thing this library sells against, so each claim it
makes is either solved and then verified against the variance model it came
from, or measured against simulated data with a known answer.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from lulumelon.mirror.intervals import z_for
from lulumelon.mirror.variance import decompose
from lulumelon.plan import (
    MIN_DRAWS,
    Comparison,
    critical_value,
    draws_needed,
    price_of,
    prompts_for_worst_case,
    reachable_icc,
    total_variance,
    variance_of,
)
from lulumelon.prices import price_for

SONAR = price_for("perplexity", "sonar")


def _binary_clusters(rng, n: int, k: int, rate: float, icc: float) -> list[list[float]]:
    """Prompts whose own rates vary around `rate` with the given correlation."""
    a = rate * (1 - icc) / icc
    b = (1 - rate) * (1 - icc) / icc
    out = []
    for _ in range(n):
        p = rng.beta(a, b)
        out.append([float(rng.random() < p) for _ in range(k)])
    return out


# -- the bound that makes a no-pilot answer legitimate ----------------------


def test_the_total_variance_of_a_yes_or_no_draw_is_p_times_one_minus_p():
    """Not an assumption. Measured against the repo's own decomposition.

    This identity is what lets `plan` size a round with no pilot at all: the
    total is known exactly from the appearance rate, and only its split is
    unknown. If this ever fails, every no-pilot number the planner prints is
    resting on nothing.
    """
    rng = np.random.default_rng(2026)
    for rate, icc in ((0.35, 0.25), (0.5, 0.10), (0.12, 0.40)):
        clusters = _binary_clusters(rng, n=3000, k=6, rate=rate, icc=icc)
        split = decompose(clusters)
        observed = split.grand_mean
        assert variance_of(split) == pytest.approx(observed * (1 - observed), rel=0.02)


def test_the_worst_case_variance_is_a_quarter():
    assert total_variance(0.5) == 0.25
    assert total_variance(0.1) < 0.25
    assert total_variance(0.9) == pytest.approx(total_variance(0.1))


def test_an_impossible_rate_is_refused():
    with pytest.raises(ValueError, match="in \\[0, 1\\]"):
        total_variance(1.4)


# -- the design solves the model it claims to solve -------------------------


def test_the_recommended_design_actually_reaches_the_target():
    """Solve for k, then put k back into se and check the half-width."""
    z, variance, n, target = z_for(0.95), 0.25, 200, 0.03
    for icc in (0.0, 0.01, 0.05):
        design = draws_needed(n, target, z, variance, icc)
        assert design.reachable
        se = math.sqrt(variance / n * (icc + (1 - icc) / design.k_runs))
        assert z * se <= target + 1e-12


def test_a_design_is_refused_when_no_number_of_repeats_can_reach_it():
    """The regime the incumbent argument is right about, named as such."""
    z, variance, n, target = z_for(0.95), 0.25, 40, 0.05
    ceiling = reachable_icc(n, target, z, variance)
    assert draws_needed(n, target, z, variance, ceiling * 0.9).reachable
    beyond = draws_needed(n, target, z, variance, ceiling + 0.01)
    assert not beyond.reachable
    assert beyond.calls is None
    assert "no number of repeats closes it" in beyond.reason


def test_the_reachable_ceiling_is_where_infinite_repeats_land():
    """At the ceiling, se converges to exactly the target as k grows."""
    z, variance, n, target = z_for(0.95), 0.25, 40, 0.05
    ceiling = reachable_icc(n, target, z, variance)
    se_at_infinity = math.sqrt(variance / n * ceiling)
    assert z * se_at_infinity == pytest.approx(target)


def test_a_design_never_recommends_a_round_that_cannot_be_decomposed():
    """k=1 is cheap and produces a round with no interval, ever."""
    huge_n = draws_needed(100_000, 0.05, z_for(0.95), 0.25, 0.0)
    assert huge_n.k_runs >= MIN_DRAWS


def test_more_prompts_never_need_more_repeats():
    z, variance, target = z_for(0.95), 0.25, 0.04
    smaller = draws_needed(200, target, z, variance, 0.0)
    larger = draws_needed(400, target, z, variance, 0.0)
    assert larger.k_runs <= smaller.k_runs


def test_a_tighter_target_costs_more():
    z, variance, n = z_for(0.95), 0.25, 400
    assert draws_needed(n, 0.02, z, variance, 0.0).calls > draws_needed(n, 0.05, z, variance, 0.0).calls


def test_the_worst_case_prompt_count_reaches_the_target_at_any_split():
    """At icc=1 repeats buy nothing, so this is the count that always works."""
    z, variance, target = z_for(0.95), 0.25, 0.05
    n = prompts_for_worst_case(target, z, variance)
    assert z * math.sqrt(variance / n) <= target + 1e-12
    # and one fewer prompt is not enough, so the number is not padded
    assert z * math.sqrt(variance / (n - 1)) > target


# -- brands cost a critical value, not calls --------------------------------


def test_tracking_more_brands_does_not_multiply_calls():
    """Every brand is read out of the same answers."""
    z_one = critical_value(0.95, 1, family=True)
    z_five = critical_value(0.95, 5, family=True)
    one = draws_needed(400, 0.02, z_one, 0.25, 0.0)
    five = draws_needed(400, 0.02, z_five, 0.25, 0.0)
    assert one.n_prompts == five.n_prompts
    assert five.k_runs > one.k_runs, "the wider interval is what more brands cost"


def test_a_family_wide_claim_is_wider_than_a_single_one():
    assert critical_value(0.95, 5, family=True) > critical_value(0.95, 5, family=False)
    assert critical_value(0.95, 1, family=True) == pytest.approx(z_for(0.95))


def test_the_bonferroni_values_are_the_published_ones():
    assert critical_value(0.95, 5, family=True) == pytest.approx(2.5758, abs=1e-4)
    assert critical_value(0.95, 10, family=True) == pytest.approx(2.8070, abs=1e-4)


def test_a_plan_with_no_brands_is_refused():
    with pytest.raises(ValueError, match="at least one brand"):
        critical_value(0.95, 0, family=True)


# -- the comparison targets a method, and never overclaims ------------------


def test_the_daily_comparison_names_what_that_shape_cannot_do():
    text = Comparison(
        designed_calls=680, daily_calls=1200, days=30, scans_per_day=1, n_prompts=40
    ).as_text()
    assert "cannot be decomposed" in text
    assert "refresh rate is not sample size" in text


def test_the_comparison_never_claims_to_be_cheaper():
    """It is not always cheaper, so the sentence is not available to be wrong.

    A designed round that has to detect a movement can cost more calls than a
    daily schedule spends in the same window. Both counts are printed and
    neither is described as the saving.
    """
    text = Comparison(
        designed_calls=3720, daily_calls=1200, days=30, scans_per_day=1, n_prompts=40
    ).as_text()
    assert "cheaper" not in text
    assert "3720" in text and "1200" in text


def test_the_comparison_says_nothing_about_a_design_that_does_not_exist():
    text = Comparison(
        designed_calls=None, daily_calls=1200, days=30, scans_per_day=1, n_prompts=40
    ).as_text()
    assert "1200 calls" in text
    assert "stated interval" not in text


# -- pricing carries its basis ----------------------------------------------


def test_an_unmeasured_plan_is_priced_as_a_floor():
    cost = price_of(SONAR, 680, None)
    assert cost.low_usd == pytest.approx(3.40)
    assert "no call metered yet" in cost.basis


def test_a_measured_token_rate_is_used_when_there_is_one():
    cost = price_of(SONAR, 680, (118, 64))
    floor = price_of(SONAR, 680, None)
    assert cost.low_usd > floor.low_usd, "tokens add to the fee, they do not replace it"
    assert cost.low_usd == pytest.approx(3.40 + 680 * (118 + 64) / 1_000_000)


def test_a_model_with_no_price_is_not_priced_from_a_relative():
    assert price_of(None, 680, (118, 64)) is None
