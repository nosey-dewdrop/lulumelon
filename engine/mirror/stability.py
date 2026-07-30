"""Stability of an answer across repeats.

A visibility number can be perfectly reproducible in its average and still be
built on answers that share almost nothing with each other. Published
measurements make this concrete: asking the same prompt minutes apart returns
source sets whose Jaccard overlap sits around 0.23 to 0.43 on ChatGPT, and one
study of 2961 runs found fewer than one pair in a hundred produced the same
brand list.

So stability is its own metric, not a footnote on the average. If it is low,
every ranking built on top of a single run is a coin flip, and this module is
what says so with a number.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from typing import Sequence

import numpy as np


def jaccard(a: Sequence[str], b: Sequence[str]) -> float:
    """Set overlap of two answers, ignoring order.

    Two empty answers count as identical (1.0): the model consistently named
    nobody, which is a stable finding, not an undefined one.
    """
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / len(sa | sb)


def rbo(a: Sequence[str], b: Sequence[str], p: float = 0.9) -> float:
    """Rank-biased overlap, truncated at the length of the shorter list.

    Jaccard treats "named first" and "named last" as the same event. RBO does
    not: it weights agreement at depth d by p^(d-1), so disagreement about who
    leads costs more than disagreement about who trails. p=0.9 puts roughly the
    top 10 positions in charge of the score.

    This is the truncated form, not the extrapolated one. It is a lower bound
    on the full-list RBO, which is the conservative direction for a stability
    claim.
    """
    if not 0.0 < p < 1.0:
        raise ValueError(f"p must be in (0, 1), got {p}")
    depth = min(len(a), len(b))
    if depth == 0:
        return 1.0 if len(a) == len(b) else 0.0

    total = 0.0
    weight_sum = 0.0
    seen_a: set[str] = set()
    seen_b: set[str] = set()
    for d in range(1, depth + 1):
        seen_a.add(a[d - 1])
        seen_b.add(b[d - 1])
        agreement = len(seen_a & seen_b) / d
        w = p ** (d - 1)
        total += w * agreement
        weight_sum += w
    return total / weight_sum


def _pairwise(values: Sequence[Sequence[str]], fn) -> float:
    """Mean of fn over all unordered pairs. One observation means perfect."""
    if len(values) < 2:
        return 1.0
    scores = [fn(x, y) for x, y in combinations(values, 2)]
    return float(np.mean(scores))


def mean_pairwise_jaccard(answers: Sequence[Sequence[str]]) -> float:
    """Average set overlap over every pair of repeats."""
    return _pairwise(answers, jaccard)


def mean_pairwise_rbo(answers: Sequence[Sequence[str]], p: float = 0.9) -> float:
    """Average rank-biased overlap over every pair of repeats."""
    return _pairwise(answers, lambda x, y: rbo(x, y, p))


def leader_repeat_rate(answers: Sequence[Sequence[str]]) -> float:
    """Share of repeats whose first-named entity equals the modal first entity.

    This is the number that kills "you rank #1 in ChatGPT" when it is low. An
    answer that names nobody counts as its own outcome rather than being
    dropped, because "no one was named" is a real result the customer needs to
    see.
    """
    if not answers:
        raise ValueError("no answers")
    leaders = [a[0] if len(a) > 0 else "" for a in answers]
    top = Counter(leaders).most_common(1)[0][1]
    return top / len(leaders)


def exact_repeat_rate(answers: Sequence[Sequence[str]]) -> float:
    """Share of repeats identical, in order, to the modal ordering."""
    if not answers:
        raise ValueError("no answers")
    keys = [tuple(a) for a in answers]
    top = Counter(keys).most_common(1)[0][1]
    return top / len(keys)


@dataclass(frozen=True, slots=True)
class Stability:
    """How much an answer agrees with itself across repeats."""

    k: int
    set_overlap: float
    rank_overlap: float
    leader_repeat: float
    exact_repeat: float

    @property
    def is_orderable(self) -> bool:
        """Whether reporting a ranking from this sample is defensible.

        The bar: the leading entity has to repeat in at least four runs out of
        five, and rank agreement between runs has to clear a half. Below that,
        a position number is describing the dice, not the brand. The thresholds
        are a stated editorial choice, not a derived constant, and they are
        deliberately visible in the code rather than buried in a dashboard.
        """
        return self.leader_repeat >= 0.8 and self.rank_overlap >= 0.5

    def as_text(self) -> str:
        verdict = "rank reportable" if self.is_orderable else "RANK NOT REPORTABLE"
        return (
            f"k={self.k} set={self.set_overlap:.3f} rank={self.rank_overlap:.3f} "
            f"leader={self.leader_repeat:.3f} exact={self.exact_repeat:.3f} -> {verdict}"
        )


def stability_of(answers: Sequence[Sequence[str]], p: float = 0.9) -> Stability:
    """Full stability picture for the repeats of one prompt."""
    if not answers:
        raise ValueError("no answers")
    return Stability(
        k=len(answers),
        set_overlap=mean_pairwise_jaccard(answers),
        rank_overlap=mean_pairwise_rbo(answers, p),
        leader_repeat=leader_repeat_rate(answers),
        exact_repeat=exact_repeat_rate(answers),
    )
