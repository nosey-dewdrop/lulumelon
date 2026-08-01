"""Separating the model's dice from the prompt set's sampling error.

When a tracked number moves, there are three candidate explanations and a
dashboard that reports one number cannot tell them apart:

  1. the model answered differently this time (prediction noise),
  2. the prompt set happens to be a small sample of all the things buyers ask
     (data noise),
  3. something real changed.

This module estimates (1) and (2) so that (3) becomes a claim that can be
tested instead of assumed. The model is the standard one-way random effects
decomposition, with the prompt as the grouping factor:

    y_ij = mu + a_i + e_ij,   a_i ~ (0, s2_between),  e_ij ~ (0, s2_within)

s2_within is the model rerunning itself and disagreeing. s2_between is genuine
prompt-to-prompt difference. Published measurement finds the first can exceed
the second, which is exactly why running each prompt once and bootstrapping
over prompts understates the uncertainty.

The practical output is `noise_floor`: the smallest movement this measurement
design can distinguish from nothing. Anything under it is not a finding.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from ..text import counted
from .intervals import Cluster, z_for


@dataclass(frozen=True, slots=True)
class VarianceSplit:
    """Where the wobble in a measured mean actually comes from."""

    n_prompts: int
    k_effective: float
    within: float
    between: float
    grand_mean: float
    confidence: float

    @property
    def icc(self) -> float:
        """Share of variance attributable to real prompt differences.

        Near 0 means the spread is almost entirely the model rerolling, so more
        repeats buy precision. Near 1 means repeats are nearly redundant and
        precision comes from adding prompts instead. This single number decides
        where the measurement budget should go.
        """
        total = self.within + self.between
        return 0.0 if total <= 0 else self.between / total

    @property
    def se_mean(self) -> float:
        """Standard error of the prompt-weighted mean under this design."""
        if self.n_prompts <= 0:
            return float("nan")
        per_prompt = self.between + self.within / max(self.k_effective, 1e-12)
        return math.sqrt(max(per_prompt, 0.0) / self.n_prompts)

    @property
    def noise_floor(self) -> float:
        """Half-width of the interval around the mean at `confidence`.

        A difference smaller than this cannot be called real with this many
        prompts and this many repeats. It is the number to put next to every
        headline score, and the number no competing product publishes.
        """
        return z_for(self.confidence) * self.se_mean

    @property
    def within_dominates(self) -> bool:
        """True when the model's own rerun noise exceeds prompt-set noise."""
        return self.within > self.between

    def as_text(self, scale: float = 1.0) -> str:
        return (
            f"mean={self.grand_mean * scale:.3f} "
            f"noise_floor=+/-{self.noise_floor * scale:.3f} "
            f"within={self.within * scale * scale:.5f} "
            f"between={self.between * scale * scale:.5f} "
            f"icc={self.icc:.3f} n={self.n_prompts} k_eff={self.k_effective:.2f}"
        )


def decompose(clusters: Sequence[Cluster], confidence: float = 0.95) -> VarianceSplit:
    """Split observed variance into within-prompt and between-prompt parts.

    Args:
        clusters: one sequence of per-run values per prompt. At least one
            prompt must carry two or more repeats, otherwise within-prompt
            variance is not identifiable from the data.
        confidence: confidence level used for `noise_floor`.

    Raises:
        ValueError: when every prompt was asked exactly once. This is not a
            limitation to work around, it is the whole point. With k=1 the
            model's rerun noise and real prompt differences are algebraically
            indistinguishable, so any confidence interval printed from such a
            design is decoration. Competing tools run each prompt once a day
            and report a single score; this refuses to.
    """
    arrays = [np.asarray(c, dtype=float) for c in clusters if len(c) > 0]
    n = len(arrays)
    if n == 0:
        raise ValueError("no non-empty clusters")
    sizes = np.array([a.size for a in arrays], dtype=float)
    if sizes.max() < 2:
        raise ValueError(
            "every prompt was asked once (k=1), so prediction noise cannot be "
            "separated from prompt-set noise; ask at least one prompt twice"
        )

    total_runs = float(sizes.sum())
    prompt_means = np.array([a.mean() for a in arrays], dtype=float)
    # Prompt-weighted grand mean: each prompt counts once regardless of k.
    grand = float(prompt_means.mean())

    # Within-prompt mean square, pooled over prompts with k >= 2.
    ss_within = float(sum(((a - a.mean()) ** 2).sum() for a in arrays))
    df_within = total_runs - n
    s2_within = ss_within / df_within if df_within > 0 else 0.0

    if n < 2:
        # One prompt: no between-prompt information at all.
        return VarianceSplit(
            n_prompts=n,
            k_effective=float(sizes.mean()),
            within=s2_within,
            between=0.0,
            grand_mean=grand,
            confidence=confidence,
        )

    # Effective group size for unbalanced designs (Satterthwaite-style k0).
    k0 = (total_runs - float((sizes**2).sum()) / total_runs) / (n - 1)
    k0 = max(k0, 1.0)

    ms_between = float((sizes * (prompt_means - grand) ** 2).sum()) / (n - 1)
    # Method-of-moments estimate, clamped: a negative variance estimate means
    # the data show less prompt-to-prompt spread than rerun noise alone would
    # produce, so the honest report is zero, not a negative number.
    s2_between = max((ms_between - s2_within) / k0, 0.0)

    return VarianceSplit(
        n_prompts=n,
        k_effective=k0,
        within=s2_within,
        between=s2_between,
        grand_mean=grand,
        confidence=confidence,
    )


@dataclass(frozen=True, slots=True)
class DesignRequirement:
    """What a measurement design must be to reach a stated precision."""

    target_half_width: float
    confidence: float
    n_prompts: int | None
    k_runs: int | None
    reachable: bool
    reason: str

    def as_text(self) -> str:
        if not self.reachable:
            return f"unreachable: {self.reason}"
        return (
            f"n_prompts={self.n_prompts} k_runs={self.k_runs} "
            f"for +/-{self.target_half_width:.4f} at {int(self.confidence * 100)}%"
        )


def runs_needed(
    split: VarianceSplit,
    target_half_width: float,
    *,
    n_prompts: int | None = None,
    confidence: float | None = None,
    max_k: int = 1000,
) -> DesignRequirement:
    """How many repeats per prompt to reach a target precision.

    Solves z * sqrt(s2_b/n + s2_w/(n*k)) <= h for k.

    When the prompt set alone already blows the budget (z^2 * s2_b / n > h^2),
    no number of repeats helps and the honest answer is "add prompts", which is
    what gets returned rather than an inflated k.
    """
    if target_half_width <= 0:
        raise ValueError("target_half_width must be positive")
    conf = split.confidence if confidence is None else confidence
    n = split.n_prompts if n_prompts is None else n_prompts
    if n <= 0:
        raise ValueError("n_prompts must be positive")

    z = z_for(conf)
    budget = (target_half_width / z) ** 2
    from_prompts = split.between / n
    slack = budget - from_prompts
    if slack <= 0:
        return DesignRequirement(
            target_half_width=target_half_width,
            confidence=conf,
            n_prompts=None,
            k_runs=None,
            reachable=False,
            reason=(
                f"prompt-set noise alone needs more than {counted(n, 'prompt')}: "
                f"between-prompt variance {split.between:.6f} implies a floor of "
                f"+/-{z * math.sqrt(from_prompts):.4f} at this n"
            ),
        )
    if split.within <= 0:
        k = 1
    else:
        k = math.ceil(split.within / (n * slack))
    if k > max_k:
        return DesignRequirement(
            target_half_width=target_half_width,
            confidence=conf,
            n_prompts=None,
            k_runs=None,
            reachable=False,
            reason=f"needs k={counted(k, 'repeat')}, above the max_k={max_k} you allowed",
        )
    return DesignRequirement(
        target_half_width=target_half_width,
        confidence=conf,
        n_prompts=n,
        k_runs=max(k, 1),
        reachable=True,
        reason="",
    )


def prompts_needed(
    split: VarianceSplit,
    target_half_width: float,
    *,
    k_runs: int,
    confidence: float | None = None,
    max_n: int = 100_000,
) -> DesignRequirement:
    """How many prompts to reach a target precision at a fixed repeat count.

    Solves z * sqrt((s2_b + s2_w/k) / n) <= h for n.
    """
    if target_half_width <= 0:
        raise ValueError("target_half_width must be positive")
    if k_runs < 1:
        raise ValueError("k_runs must be at least 1")
    conf = split.confidence if confidence is None else confidence
    z = z_for(conf)
    per_prompt = split.between + split.within / k_runs
    if per_prompt <= 0:
        return DesignRequirement(
            target_half_width=target_half_width,
            confidence=conf,
            n_prompts=1,
            k_runs=k_runs,
            reachable=True,
            reason="",
        )
    n = math.ceil(per_prompt / (target_half_width / z) ** 2)
    if n > max_n:
        return DesignRequirement(
            target_half_width=target_half_width,
            confidence=conf,
            n_prompts=None,
            k_runs=None,
            reachable=False,
            reason=f"needs n={counted(n, 'prompt')}, above the max_n={max_n} you allowed",
        )
    return DesignRequirement(
        target_half_width=target_half_width,
        confidence=conf,
        n_prompts=n,
        k_runs=k_runs,
        reachable=True,
        reason="",
    )
