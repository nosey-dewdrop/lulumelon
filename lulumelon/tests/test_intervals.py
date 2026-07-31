"""Interval estimators, including the one test that justifies the library.

`test_cluster_bootstrap_covers_and_naive_does_not` is the load-bearing one. It
builds data whose true mean is known, runs both estimators many times, and
counts how often each interval actually contains the truth. A 95% interval that
covers 60% of the time is not a conservative interval, it is a wrong one, and
that is what pooling correlated repeats produces.
"""

from __future__ import annotations

import numpy as np
import pytest

from lulumelon.mirror.intervals import (
    cluster_bootstrap_ci,
    naive_bootstrap_ci,
    wilson_interval,
    z_for,
)


def test_z_for_known_values() -> None:
    assert z_for(0.95) == pytest.approx(1.959963985, abs=1e-6)
    assert z_for(0.99) == pytest.approx(2.575829304, abs=1e-6)


@pytest.mark.parametrize("bad", [0.0, 1.0, -0.1, 1.5])
def test_z_for_rejects_impossible_confidence(bad: float) -> None:
    with pytest.raises(ValueError):
        z_for(bad)


def test_wilson_stays_inside_zero_one_at_the_extremes() -> None:
    """The reason Wilson is here instead of the normal approximation.

    At zero successes the algebra puts the lower bound exactly at zero, so the
    tolerance here is for floating point residue, not for slack in the claim.
    """
    zero = wilson_interval(0, 12)
    assert zero.low == pytest.approx(0.0, abs=1e-12)
    assert 0.0 < zero.high < 0.30

    everything = wilson_interval(12, 12)
    assert everything.high == pytest.approx(1.0, abs=1e-12)
    assert 0.70 < everything.low < 1.0


def test_wilson_interval_narrows_with_more_runs() -> None:
    small = wilson_interval(5, 10)
    large = wilson_interval(500, 1000)
    assert large.half_width < small.half_width / 5


def test_wilson_rejects_impossible_counts() -> None:
    with pytest.raises(ValueError):
        wilson_interval(5, 3)
    with pytest.raises(ValueError):
        wilson_interval(-1, 3)
    with pytest.raises(ValueError):
        wilson_interval(1, 0)


def test_cluster_bootstrap_is_reproducible_from_its_seed() -> None:
    """Same seed, same digits. Different seed, different draw.

    Enough distinct clusters that two seeds cannot land on the same percentile
    by coincidence, which is what happens with three near-identical prompts.
    """
    rng = np.random.default_rng(0)
    clusters = [list(rng.normal(0.4 + 0.05 * i, 0.2, size=6)) for i in range(12)]
    a = cluster_bootstrap_ci(clusters, seed=7, resamples=500)
    b = cluster_bootstrap_ci(clusters, seed=7, resamples=500)
    c = cluster_bootstrap_ci(clusters, seed=8, resamples=500)
    assert (a.low, a.high) == (b.low, b.high)
    assert (a.low, a.high) != (c.low, c.high)
    assert a.point == c.point  # the estimate itself does not depend on the seed


def test_cluster_bootstrap_weights_each_prompt_once() -> None:
    """A prompt asked 100 times must not outvote a prompt asked twice."""
    clusters = [[1.0] * 100, [0.0, 0.0]]
    ci = cluster_bootstrap_ci(clusters, seed=1, resamples=400)
    assert ci.point == pytest.approx(0.5)


def _beta_binomial_snapshot(
    rng: np.random.Generator, n_prompts: int, k: int, mean: float, concentration: float
) -> list[list[float]]:
    """Prompts differ genuinely; each run is a coin flip at that prompt's rate.

    This is the structure real measurement has: some prompts simply mention the
    brand more, and on top of that the model rerolls every time.
    """
    a = mean * concentration
    b = (1.0 - mean) * concentration
    rates = rng.beta(a, b, size=n_prompts)
    return [list(rng.binomial(1, r, size=k).astype(float)) for r in rates]


@pytest.mark.slow
def test_cluster_bootstrap_covers_and_naive_does_not() -> None:
    """Monte Carlo coverage check against a known truth.

    True prompt-weighted mean is `mean` by construction. A correct 95% interval
    should contain it about 95% of the time. The naive interval, which treats
    the k repeats of a prompt as k independent observations, should fall well
    short because it believes it has n*k independent points when it has n.
    """
    rng = np.random.default_rng(20260730)
    trials = 150
    n_prompts, k, mean, concentration = 25, 8, 0.35, 4.0

    clustered_hits = 0
    naive_hits = 0
    for t in range(trials):
        clusters = _beta_binomial_snapshot(rng, n_prompts, k, mean, concentration)
        c = cluster_bootstrap_ci(clusters, resamples=250, seed=t)
        n = naive_bootstrap_ci(clusters, resamples=250, seed=t)
        clustered_hits += int(c.contains(mean))
        naive_hits += int(n.contains(mean))

    clustered_coverage = clustered_hits / trials
    naive_coverage = naive_hits / trials

    assert clustered_coverage >= 0.88, (
        f"clustered interval only covered {clustered_coverage:.2%} of the time"
    )
    assert naive_coverage < clustered_coverage - 0.10, (
        f"naive {naive_coverage:.2%} vs clustered {clustered_coverage:.2%}: "
        "the naive interval was supposed to be visibly too narrow"
    )


def test_naive_interval_is_narrower_than_clustered_on_correlated_data() -> None:
    """The mechanism behind the coverage gap, checked directly."""
    rng = np.random.default_rng(11)
    clusters = _beta_binomial_snapshot(rng, 20, 10, 0.4, 3.0)
    clustered = cluster_bootstrap_ci(clusters, resamples=600, seed=3)
    naive = naive_bootstrap_ci(clusters, resamples=600, seed=3)
    assert naive.half_width < clustered.half_width


def test_published_competitor_margin_matches_its_stated_constant() -> None:
    """Reproduce the vendor's own published number before criticising it.

    Their claim: ~800 conversations gives +/-5 percentage points at 95%.
    """
    from lulumelon.mirror.intervals import published_binomial_moe

    assert published_binomial_moe(800) == pytest.approx(0.0347, abs=0.001)
    # The 0.98/sqrt(n) form they quote, checked directly.
    assert published_binomial_moe(800) == pytest.approx(0.98 / (800**0.5), abs=1e-4)


@pytest.mark.slow
def test_published_competitor_margin_undercovers_on_clustered_data() -> None:
    """The correction that matters: their formula is applied to correlated data.

    Same simulated world as the coverage test above. The published margin is
    computed from the observation count, as the vendor describes, and checked
    for how often it actually contains the truth. A 95% claim that lands well
    under 95% is not conservative, it is wrong, and this measures by how much.
    """
    from lulumelon.mirror.intervals import published_binomial_moe

    rng = np.random.default_rng(20260731)
    trials = 150
    n_prompts, k, mean, concentration = 25, 8, 0.35, 4.0

    published_hits = 0
    clustered_hits = 0
    for t in range(trials):
        clusters = _beta_binomial_snapshot(rng, n_prompts, k, mean, concentration)
        observed = float(np.mean([np.mean(c) for c in clusters]))
        moe = published_binomial_moe(n_prompts * k)
        published_hits += int(observed - moe <= mean <= observed + moe)
        clustered_hits += int(cluster_bootstrap_ci(clusters, resamples=250, seed=t).contains(mean))

    published_coverage = published_hits / trials
    clustered_coverage = clustered_hits / trials

    assert published_coverage < 0.90, (
        f"the published margin covered {published_coverage:.2%}, which would "
        "have meant the criticism does not hold on this data"
    )
    assert clustered_coverage > published_coverage


@pytest.mark.slow
def test_two_designs_the_vendor_calls_equivalent_are_not() -> None:
    """The published claim, tested on its own terms.

    A vendor states, verbatim: "Ten related prompts run 39 times each, or
    fifty prompts run 8 times each, both get you to +/-5 pp". Under their
    formula the two are interchangeable because both land near 400
    observations. Under clustering they are not: repeats of one prompt carry
    much less information than a fresh prompt, so the design with fewer
    prompts is far wider even though it has the same observation count.

    This test simulates both designs in the same world and asserts the gap.
    """
    rng = np.random.default_rng(7)
    mean, concentration, trials = 0.35, 4.0, 120

    def mean_half_width(n_prompts: int, k: int) -> float:
        widths = []
        for t in range(trials):
            clusters = _beta_binomial_snapshot(rng, n_prompts, k, mean, concentration)
            widths.append(cluster_bootstrap_ci(clusters, resamples=250, seed=t).half_width)
        return float(np.mean(widths))

    few_prompts_many_repeats = mean_half_width(10, 39)
    many_prompts_few_repeats = mean_half_width(50, 8)

    # Same observation count, materially different precision.
    assert few_prompts_many_repeats > many_prompts_few_repeats * 1.5

    # And both are wider than the published margin claims.
    from lulumelon.mirror.intervals import published_binomial_moe

    assert few_prompts_many_repeats > published_binomial_moe(390) * 2
    assert many_prompts_few_repeats > published_binomial_moe(400)


def test_interval_text_is_readable() -> None:
    ci = cluster_bootstrap_ci([[0.3, 0.4], [0.5, 0.6]], seed=2, resamples=200)
    text = ci.as_text(digits=1, scale=100, unit="%")
    assert "95% CI" in text
    assert "+/-" in text


def test_empty_input_is_an_error_not_a_zero() -> None:
    with pytest.raises(ValueError):
        cluster_bootstrap_ci([])
    with pytest.raises(ValueError):
        cluster_bootstrap_ci([[], []])
