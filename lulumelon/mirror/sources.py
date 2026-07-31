"""Which pages the answer engine read, and whether your name travels with them.

Listing the domains an answer cited is cheap and it is where source analysis
usually ends. The list on its own does not answer the question that follows it,
which is *which one of these is worth getting into*.

This module takes one step past the list and then stops on purpose, because the
step after that one is a different kind of claim and it needs different data.

**What is computed here is association, not effect.** For a given source, we
compare how often the brand appears in the runs that cited it against the runs
that did not. That contrast is real and it is measurable from data we already
collected. It is not the counterfactual. A source can travel with the brand
because it causes the mention, or because both are symptoms of the model having
decided to answer the question a particular way that draw. Nothing in an
observational round separates those.

The honest name for the number is a difference in appearance rate conditional
on citation, and every printed line says so. The causal version needs the model
to answer the same question with a source removed, which is an ablation on a
controlled replica, and it is deliberately not faked here.

**Citation is not the same as influence.** A model reads pages it does not
cite, and cites pages it barely used. What is measured is what the provider
reported, which is citation. Calling it "the sources the model used" would be a
claim about the inside of a system we cannot see.

**The prompt stays the resampling unit.** The k repeats of one question are not
independent, so the pooled interval bootstraps over prompts, exactly as
everything else in this package does. Pooling over runs would make every source
look decisive.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .intervals import Interval, cluster_bootstrap_ci
from .types import Snapshot

#: A prompt contributes to a source's contrast only when both arms have at
#: least this many runs. With fewer, the per-prompt rate is 0 or 1 by accident
#: and the pooled mean inherits that accident.
MIN_ARM = 2

#: Fewer usable prompts than this and the interval is decoration: a percentile
#: bootstrap over two clusters cannot describe a population.
MIN_PROMPTS = 3


@dataclass(frozen=True, slots=True)
class SourceUse:
    """How often one source turned up at all.

    `prompts` is how many distinct questions ever cited it, `runs` is how many
    individual answers did. The pair matters: a source cited in every run of one
    question is a fact about that question, while one cited across many
    questions is a fact about the category.
    """

    url: str
    prompts: int
    runs: int
    share_of_runs: float


@dataclass(frozen=True, slots=True)
class SourceAssociation:
    """One source, and how the brand's appearance rate differs alongside it.

    `difference` is `rate_when_cited - rate_when_not`, pooled with the prompt as
    the resampling unit. `verdict` is the honest reading, including the cases
    where there is nothing to read.
    """

    url: str
    brand: str
    prompts_used: int
    prompts_dropped: int
    rate_when_cited: float
    rate_when_not: float
    difference: float
    interval: Interval | None
    verdict: str

    @property
    def is_reportable(self) -> bool:
        return self.interval is not None

    def as_text(self) -> str:
        if self.interval is None:
            return f"{self.url}\n  {self.verdict}"
        pts = self.difference * 100
        lo, hi = self.interval.low * 100, self.interval.high * 100
        return (
            f"{self.url}\n"
            f"  appears in {self.rate_when_cited * 100:.1f}% of answers citing it, "
            f"{self.rate_when_not * 100:.1f}% of answers not citing it\n"
            f"  difference {pts:+.1f} pts (95% CI {lo:+.1f}..{hi:+.1f}) "
            f"over {self.prompts_used} prompts\n"
            f"  {self.verdict}"
        )


def source_use(snapshot: Snapshot) -> tuple[SourceUse, ...]:
    """Every source seen in the round, most-cited first."""
    per_source_runs: dict[str, int] = defaultdict(int)
    per_source_prompts: dict[str, set[str]] = defaultdict(set)
    total_runs = 0

    for sample in snapshot.samples:
        for run in sample.runs:
            total_runs += 1
            for url in dict.fromkeys(run.citations):
                per_source_runs[url] += 1
                per_source_prompts[url].add(sample.prompt_id)

    out = [
        SourceUse(
            url=url,
            prompts=len(per_source_prompts[url]),
            runs=runs,
            share_of_runs=runs / total_runs if total_runs else 0.0,
        )
        for url, runs in per_source_runs.items()
    ]
    out.sort(key=lambda s: (-s.runs, s.url))
    return tuple(out)


def _per_prompt_contrast(snapshot: Snapshot, brand: str, url: str) -> tuple[list[float], list[float], list[float], int]:
    """Per-prompt (rate_cited, rate_not, difference), and how many were unusable."""
    with_rates: list[float] = []
    without_rates: list[float] = []
    diffs: list[float] = []
    dropped = 0

    for sample in snapshot.samples:
        cited = [r for r in sample.runs if url in r.citations]
        uncited = [r for r in sample.runs if url not in r.citations]
        if len(cited) < MIN_ARM or len(uncited) < MIN_ARM:
            # no contrast inside this question: the source was always there or
            # never there. Not a zero, an absence of comparison.
            dropped += 1
            continue
        a = sum(r.mentions(brand) for r in cited) / len(cited)
        b = sum(r.mentions(brand) for r in uncited) / len(uncited)
        with_rates.append(a)
        without_rates.append(b)
        diffs.append(a - b)

    return with_rates, without_rates, diffs, dropped


def associate(
    snapshot: Snapshot,
    brand: str,
    url: str,
    *,
    seed: int = 0,
    confidence: float = 0.95,
) -> SourceAssociation:
    """How the brand's appearance rate differs between runs citing `url` and runs not.

    Returns a refusal rather than a number whenever the design cannot support
    one. The refusals are the product: a source that was cited in every single
    answer carries no information about what happens without it, and printing a
    difference of zero there would read as "this source does not matter".
    """
    with_rates, without_rates, diffs, dropped = _per_prompt_contrast(snapshot, brand, url)

    if not diffs:
        return SourceAssociation(
            url=url,
            brand=brand,
            prompts_used=0,
            prompts_dropped=dropped,
            rate_when_cited=0.0,
            rate_when_not=0.0,
            difference=0.0,
            interval=None,
            verdict=(
                "NO CONTRAST: in every question this source was either always cited "
                "or never cited, so this round contains no comparison to make. "
                f"{dropped} prompts had no usable split."
            ),
        )

    mean_with = sum(with_rates) / len(with_rates)
    mean_without = sum(without_rates) / len(without_rates)
    mean_diff = sum(diffs) / len(diffs)

    if len(diffs) < MIN_PROMPTS:
        return SourceAssociation(
            url=url,
            brand=brand,
            prompts_used=len(diffs),
            prompts_dropped=dropped,
            rate_when_cited=mean_with,
            rate_when_not=mean_without,
            difference=mean_diff,
            interval=None,
            verdict=(
                f"WITHHELD: only {len(diffs)} prompt(s) offered a split, and the "
                f"prompt is the resampling unit here. An interval over "
                f"{len(diffs)} clusters describes this round, not the question."
            ),
        )

    # the prompt is the unit: one cluster per prompt, carrying its difference
    interval = cluster_bootstrap_ci(
        [[d] for d in diffs], resamples=2000, confidence=confidence, seed=seed
    )

    if interval.contains(0.0):
        verdict = (
            "ASSOCIATION NOT SEPARABLE FROM ZERO: the interval spans no difference, "
            "so this round cannot say the brand travels with this source."
        )
    else:
        direction = "more" if mean_diff > 0 else "less"
        verdict = (
            f"ASSOCIATION, NOT EFFECT: answers citing this source name the brand "
            f"{direction} often. Whether getting into this source would move the "
            f"rate is a counterfactual, and it needs an ablation, not this round."
        )

    return SourceAssociation(
        url=url,
        brand=brand,
        prompts_used=len(diffs),
        prompts_dropped=dropped,
        rate_when_cited=mean_with,
        rate_when_not=mean_without,
        difference=mean_diff,
        interval=interval,
        verdict=verdict,
    )


def source_graph(
    snapshot: Snapshot,
    brand: str,
    *,
    top: int = 10,
    seed: int = 0,
) -> tuple[SourceAssociation, ...]:
    """The most-cited sources in the round, each with its association or refusal.

    Ordered by how often the source was cited, not by the size of its
    difference. Sorting by effect size is how a list of noise gets a headline:
    the largest number in a set of unstable estimates is the least trustworthy
    one in it.
    """
    ranked = source_use(snapshot)[:top]
    return tuple(associate(snapshot, brand, s.url, seed=seed) for s in ranked)
