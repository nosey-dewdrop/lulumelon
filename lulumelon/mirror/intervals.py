"""Interval estimates.

Two estimators live here and they answer different questions.

`wilson_interval` is for a single proportion out of n independent trials. It is
exact enough at small n, where the textbook normal approximation produces
intervals that run past 0 or 1 and quietly lie.

`cluster_bootstrap_ci` is for a mean computed over repeated measurements of the
same prompts. Resampling individual runs would be wrong: runs of the same
prompt are correlated, and treating them as independent shrinks the interval
until it stops covering the truth. So the prompt is the resampling unit and all
of its repeats travel together. This is the cluster bootstrap.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np
from scipy import stats

# Sequence of per-run values for one prompt. Length is that prompt's k.
Cluster = Sequence[float]


def z_for(confidence: float) -> float:
    """Two-sided normal critical value for a confidence level."""
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")
    return float(stats.norm.ppf(0.5 + confidence / 2.0))


#: Draws a tail must contain before a percentile read off it means anything.
#: A hundred is the usual working figure for a stable endpoint; below about
#: twenty the endpoint is mostly which draw happened to land furthest out.
TAIL_DRAWS = 100


def resamples_for(confidence: float, *, floor: int = 2000, tail_draws: int = TAIL_DRAWS) -> int:
    """Bootstrap draws needed for the endpoints of `confidence` to be populated.

    A percentile interval does not compute its endpoints, it reads them off the
    bootstrap distribution, so each tail has to contain enough draws to place
    one. At 95% with 2000 resamples a tail holds about fifty draws, which is
    thin but workable. Hold five intervals at once and the family-wide level
    moves to 99%, where those same 2000 draws leave five draws per tail and the
    endpoint is mostly luck. The resample count therefore follows the confidence
    level instead of sitting at a constant, because the constant is only ever
    right for the one confidence level it was chosen at.
    """
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")
    if floor < 1 or tail_draws < 1:
        raise ValueError("floor and tail_draws must both be positive")
    half = (1.0 - confidence) / 2.0
    return max(floor, math.ceil(tail_draws / half))


@dataclass(frozen=True, slots=True)
class Interval:
    """A point estimate that refuses to travel without its uncertainty."""

    point: float
    low: float
    high: float
    confidence: float
    n_units: int
    method: str

    @property
    def half_width(self) -> float:
        return (self.high - self.low) / 2.0

    @property
    def excludes_zero(self) -> bool:
        return self.low > 0.0 or self.high < 0.0

    def contains(self, value: float) -> bool:
        return self.low <= value <= self.high

    def as_text(self, digits: int = 3, scale: float = 1.0, unit: str = "") -> str:
        """Human-readable form, e.g. "34.0 +/- 6.2 (95% CI 27.8..40.2)%"."""
        p, lo, hi = self.point * scale, self.low * scale, self.high * scale
        pct = int(round(self.confidence * 100))
        return (
            f"{p:.{digits}f} +/- {(hi - lo) / 2:.{digits}f} "
            f"({pct}% CI {lo:.{digits}f}..{hi:.{digits}f}){unit}"
        )


def wilson_interval(successes: int, n: int, confidence: float = 0.95) -> Interval:
    """Wilson score interval for a proportion.

    Args:
        successes: number of runs where the event happened.
        n: total runs.
        confidence: two-sided confidence level.

    Used for detection rate: "the brand was named in 17 of 40 runs". The naive
    interval around 17/40 can extend below zero at small n; this one cannot.
    """
    if n <= 0:
        raise ValueError("n must be positive")
    if not 0 <= successes <= n:
        raise ValueError(f"successes {successes} out of range for n {n}")

    z = z_for(confidence)
    p = successes / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    spread = z / denom * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return Interval(
        point=p,
        low=max(0.0, center - spread),
        high=min(1.0, center + spread),
        confidence=confidence,
        n_units=n,
        method="wilson",
    )


def _prompt_weighted_mean(clusters: Sequence[Cluster]) -> float:
    """Mean of per-prompt means.

    Each prompt gets equal weight regardless of how many times it was asked.
    Pooling every run instead would let a heavily repeated prompt dominate,
    which is a weighting decision disguised as an average.
    """
    means = [float(np.mean(c)) for c in clusters if len(c) > 0]
    if not means:
        raise ValueError("no non-empty clusters")
    return float(np.mean(means))


def cluster_bootstrap_ci(
    clusters: Sequence[Cluster],
    statistic: Callable[[Sequence[Cluster]], float] = _prompt_weighted_mean,
    *,
    resamples: int = 2000,
    confidence: float = 0.95,
    seed: int = 0,
) -> Interval:
    """Percentile bootstrap CI where the prompt, not the run, is resampled.

    Args:
        clusters: one sequence of per-run values per prompt.
        statistic: maps clusters to the number being estimated. Default is the
            prompt-weighted mean.
        resamples: bootstrap draws. 2000 is enough for a 95% percentile
            interval; raise it for tails.
        confidence: two-sided confidence level.
        seed: explicit, because a measurement instrument that cannot be
            re-run to the same digits is not an instrument.

    Why clustered: run-level resampling assumes the k repeats of a prompt are
    independent draws from the population. They are not, they share a prompt.
    Ignoring that inflates the effective sample size by roughly k and produces
    intervals that are too narrow to cover the truth.
    """
    non_empty = [np.asarray(c, dtype=float) for c in clusters if len(c) > 0]
    if not non_empty:
        raise ValueError("no non-empty clusters")
    if resamples < 1:
        raise ValueError("resamples must be positive")

    rng = np.random.default_rng(seed)
    n = len(non_empty)
    point = statistic(non_empty)

    idx_matrix = rng.integers(0, n, size=(resamples, n))
    if statistic is _prompt_weighted_mean:
        # The default statistic is the mean of the per-cluster means, so the
        # clusters can be collapsed once and the resampling done on the means.
        # Same draws, same order, same arithmetic; the loop below is the same
        # expression evaluated one row at a time. It is kept for statistics
        # that cannot be collapsed, and skipped for the one that can, because
        # a family-wide interval needs ten times the draws and paying for them
        # in a Python loop is how a correction gets dropped for being slow.
        means = np.array([c.mean() for c in non_empty], dtype=float)
        draws = means[idx_matrix].mean(axis=1)
    else:
        draws = np.empty(resamples, dtype=float)
        for b in range(resamples):
            picked = [non_empty[i] for i in idx_matrix[b]]
            draws[b] = statistic(picked)

    alpha = (1.0 - confidence) / 2.0
    low, high = np.quantile(draws, [alpha, 1.0 - alpha])
    return Interval(
        point=float(point),
        low=float(low),
        high=float(high),
        confidence=confidence,
        n_units=n,
        method=f"cluster_bootstrap(B={resamples},seed={seed})",
    )


def published_binomial_moe(n_observations: int, confidence: float = 0.95) -> float:
    """The margin of error one competitor in this category actually publishes.

    A vendor states that around 800 conversations per run is "enough to
    estimate your overall visibility within +/-5 percentage points at 95
    percent confidence", from MoE = 0.98 / sqrt(n). That constant is the
    worst-case binomial half-width at p=0.5: z * sqrt(0.25) = 1.96 * 0.5.

    The arithmetic is right and the assumption is wrong. It treats all n
    observations as independent draws, when they are k repeats of n/k prompts.
    Repeats of one prompt are correlated, so the effective sample size is
    nearer the prompt count than the observation count, and the published
    interval comes out too narrow by roughly sqrt of the design effect.

    Kept here as a named, testable competitor baseline rather than a claim in a
    slide. `tests/test_intervals.py` measures how often it covers the truth.
    """
    if n_observations <= 0:
        raise ValueError("n_observations must be positive")
    return z_for(confidence) * 0.5 / math.sqrt(n_observations)


def naive_bootstrap_ci(
    clusters: Sequence[Cluster],
    *,
    resamples: int = 2000,
    confidence: float = 0.95,
    seed: int = 0,
) -> Interval:
    """The wrong way, kept on purpose.

    Pools every run and resamples runs independently, which is what you get if
    you hand a flat list of scores to a standard bootstrap. Exists so the test
    suite can demonstrate that it produces a narrower interval than the
    clustered version whenever repeats are correlated, and so the difference
    can be shown to a customer rather than asserted.
    """
    flat = np.concatenate([np.asarray(c, dtype=float) for c in clusters if len(c) > 0])
    if flat.size == 0:
        raise ValueError("no observations")
    rng = np.random.default_rng(seed)
    draws = rng.choice(flat, size=(resamples, flat.size), replace=True).mean(axis=1)
    alpha = (1.0 - confidence) / 2.0
    low, high = np.quantile(draws, [alpha, 1.0 - alpha])
    return Interval(
        point=float(flat.mean()),
        low=float(low),
        high=float(high),
        confidence=confidence,
        n_units=int(flat.size),
        method=f"naive_bootstrap(B={resamples},seed={seed})",
    )
