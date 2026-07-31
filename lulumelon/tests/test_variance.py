"""Variance decomposition and measurement design.

The recovery test is the important one: generate data with a known split
between prompt-to-prompt variance and rerun variance, then check the estimator
finds it. If it cannot, every design recommendation built on top is guesswork.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from lulumelon.mirror.intervals import z_for
from lulumelon.mirror.variance import decompose, prompts_needed, runs_needed


def _synthetic(
    rng: np.random.Generator, n: int, k: int, sd_between: float, sd_within: float, mean: float
) -> list[list[float]]:
    prompt_effects = rng.normal(0.0, sd_between, size=n)
    return [list(rng.normal(mean + a, sd_within, size=k)) for a in prompt_effects]


def test_decompose_recovers_a_known_split() -> None:
    rng = np.random.default_rng(4242)
    clusters = _synthetic(rng, n=400, k=6, sd_between=0.20, sd_within=0.50, mean=0.35)
    split = decompose(clusters)

    assert split.within == pytest.approx(0.25, rel=0.10)
    assert split.between == pytest.approx(0.04, rel=0.35)
    assert split.grand_mean == pytest.approx(0.35, abs=0.02)
    assert split.k_effective == pytest.approx(6.0, abs=1e-9)


def test_decompose_flags_when_rerun_noise_dominates() -> None:
    rng = np.random.default_rng(7)
    noisy_model = _synthetic(rng, n=120, k=6, sd_between=0.05, sd_within=0.60, mean=0.4)
    assert decompose(noisy_model).within_dominates

    varied_prompts = _synthetic(rng, n=120, k=6, sd_between=0.60, sd_within=0.05, mean=0.4)
    assert not decompose(varied_prompts).within_dominates


def test_icc_moves_the_right_way() -> None:
    rng = np.random.default_rng(99)
    mostly_prompt = decompose(_synthetic(rng, 200, 5, 0.5, 0.1, 0.5))
    mostly_model = decompose(_synthetic(rng, 200, 5, 0.1, 0.5, 0.5))
    assert mostly_prompt.icc > 0.8
    assert mostly_model.icc < 0.2


def test_single_run_designs_are_refused() -> None:
    """k=1 is the industry default and it cannot support an interval."""
    with pytest.raises(ValueError, match="asked once"):
        decompose([[0.0], [1.0], [1.0], [0.0]])


def test_between_variance_is_clamped_at_zero_not_reported_negative() -> None:
    rng = np.random.default_rng(3)
    # No real prompt differences at all: the moment estimator can go negative.
    clusters = _synthetic(rng, n=30, k=4, sd_between=0.0, sd_within=0.4, mean=0.5)
    split = decompose(clusters)
    assert split.between >= 0.0


def test_unbalanced_designs_use_an_effective_group_size() -> None:
    clusters = [[0.1] * 2, [0.5] * 10, [0.9] * 6]
    split = decompose(clusters)
    assert 1.0 <= split.k_effective <= 10.0
    assert split.n_prompts == 3


def test_noise_floor_shrinks_as_the_design_grows() -> None:
    rng = np.random.default_rng(15)
    small = decompose(_synthetic(rng, 10, 3, 0.2, 0.5, 0.4))
    large = decompose(_synthetic(rng, 200, 12, 0.2, 0.5, 0.4))
    assert large.noise_floor < small.noise_floor


def test_runs_needed_actually_reaches_the_target() -> None:
    """Solve for k, then verify the resulting design meets the precision.

    n is large here on purpose. At n=60 with this much rerun noise, the
    between-prompt estimate itself carries enough sampling error to swamp a
    small true value, which is a real property of the estimator and the reason
    a design recommendation from a tiny prompt set is not trustworthy.
    """
    rng = np.random.default_rng(21)
    split = decompose(_synthetic(rng, n=400, k=4, sd_between=0.05, sd_within=0.45, mean=0.4))
    target = 0.02
    req = runs_needed(split, target)
    assert req.reachable and req.k_runs is not None

    achieved = z_for(split.confidence) * math.sqrt(
        split.between / split.n_prompts + split.within / (split.n_prompts * req.k_runs)
    )
    assert achieved <= target + 1e-9


def test_runs_needed_admits_when_repeats_cannot_help() -> None:
    """The regime where the incumbent's counter-argument is correct.

    When prompt-set variance alone already exceeds the precision budget, no
    number of repeats closes the gap. The honest output is a refusal plus a
    pointer at prompts, not an inflated k.
    """
    rng = np.random.default_rng(33)
    split = decompose(_synthetic(rng, n=8, k=5, sd_between=0.60, sd_within=0.05, mean=0.4))
    req = runs_needed(split, 0.01)
    assert not req.reachable
    assert "prompts" in req.reason

    wider = prompts_needed(split, 0.01, k_runs=3)
    assert wider.reachable and wider.n_prompts is not None
    assert wider.n_prompts > split.n_prompts


def test_prompts_needed_reaches_the_target() -> None:
    rng = np.random.default_rng(45)
    split = decompose(_synthetic(rng, n=40, k=5, sd_between=0.25, sd_within=0.30, mean=0.5))
    target = 0.03
    req = prompts_needed(split, target, k_runs=5)
    assert req.reachable and req.n_prompts is not None

    achieved = z_for(split.confidence) * math.sqrt(
        (split.between + split.within / 5) / req.n_prompts
    )
    assert achieved <= target + 1e-9


def test_tighter_targets_demand_bigger_designs() -> None:
    rng = np.random.default_rng(51)
    split = decompose(_synthetic(rng, n=100, k=5, sd_between=0.10, sd_within=0.40, mean=0.5))
    loose = runs_needed(split, 0.05)
    tight = runs_needed(split, 0.025)
    assert loose.reachable and tight.reachable
    assert tight.k_runs >= loose.k_runs

    n_loose = prompts_needed(split, 0.05, k_runs=3)
    n_tight = prompts_needed(split, 0.025, k_runs=3)
    assert n_tight.n_prompts > n_loose.n_prompts


def test_impossible_targets_are_rejected_not_rounded() -> None:
    rng = np.random.default_rng(63)
    split = decompose(_synthetic(rng, n=20, k=4, sd_between=0.01, sd_within=0.90, mean=0.5))
    req = runs_needed(split, 1e-6, max_k=50)
    assert not req.reachable
    with pytest.raises(ValueError):
        runs_needed(split, 0.0)
