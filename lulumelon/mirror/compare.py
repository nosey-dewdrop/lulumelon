"""Did it change, or did it wobble?

The question a customer actually asks is never "what is my score". It is "my
score moved four points, do I care". Answering that requires a paired
comparison, because the same prompts appear on both sides and pairing removes
prompt-to-prompt variation from the difference.

Three things live here:

  `paired_difference` — cluster bootstrap on per-prompt differences.
  `mcnemar_detection` — exact test for a binary appear/not-appear flip.
  `holm_adjust` — family-wise correction, because a dashboard that tests forty
  prompts and highlights the two that moved has run forty tests and reported
  the winners.

And one refusal: if the two sides were measured on different model versions,
the comparison is confounded and the verdict says so instead of printing a
number. Providers update hosted models without changelogs; a tool that ignores
that will confidently attribute the provider's change to the customer's work.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable, Mapping, Sequence

import numpy as np
from scipy import stats

from .intervals import Interval, z_for
from .types import Snapshot


@dataclass(frozen=True, slots=True)
class Verdict:
    """The outcome of one comparison, with its own reason for existing."""

    label: str
    diff: float
    interval: Interval
    n_paired: int
    p_value: float | None
    confounded_by: tuple[str, ...]
    method: str

    @property
    def significant(self) -> bool:
        """True only when the interval excludes zero and nothing is confounded.

        A confounded comparison is never significant here, no matter how wide
        the gap. That is a deliberate refusal: the arithmetic would still
        produce a number, and printing it would be the exact failure this
        engine exists to prevent.
        """
        return self.interval.excludes_zero and not self.confounded_by

    def as_text(self, scale: float = 1.0) -> str:
        if self.confounded_by:
            return (
                f"{self.label}: CONFOUNDED, no verdict. "
                f"model version changed on {', '.join(self.confounded_by)}. "
                f"raw diff would have been {self.diff * scale:+.3f}"
            )
        head = "CHANGED" if self.significant else "within noise"
        p = "" if self.p_value is None else f" p={self.p_value:.4f}"
        return (
            f"{self.label}: {head} {self.diff * scale:+.3f} "
            f"({int(self.interval.confidence * 100)}% CI "
            f"{self.interval.low * scale:+.3f}..{self.interval.high * scale:+.3f}){p} "
            f"[{self.n_paired} paired prompts]"
        )


def _paired_means(
    before: Mapping[Hashable, Sequence[float]],
    after: Mapping[Hashable, Sequence[float]],
) -> tuple[list[Hashable], np.ndarray]:
    """Per-unit difference of means, over the units present on both sides.

    The key is whatever the two sides are paired on and this module does not
    choose it, but both sides have to have chosen the same thing: pairing is by
    equal keys, so a side keyed more narrowly than the other pairs on nothing.
    The callers in this repo key by the sample, which is one prompt on one
    engine.
    """
    keys = sorted(set(before) & set(after))
    keys = [k for k in keys if len(before[k]) > 0 and len(after[k]) > 0]
    if not keys:
        raise ValueError("no prompt appears in both snapshots with observations")
    diffs = np.array(
        [float(np.mean(after[k])) - float(np.mean(before[k])) for k in keys],
        dtype=float,
    )
    return keys, diffs


def paired_difference(
    before: Mapping[Hashable, Sequence[float]],
    after: Mapping[Hashable, Sequence[float]],
    *,
    label: str = "diff",
    confidence: float = 0.95,
    resamples: int = 2000,
    seed: int = 0,
    confounded_by: Sequence[str] = (),
) -> Verdict:
    """Bootstrap CI for the mean per-prompt change, resampling prompts.

    Pairing matters: the unpaired difference of two means carries the full
    prompt-set variance twice, so a real change of a few points disappears into
    it. Pairing cancels the prompt effect and leaves the model's rerun noise,
    which is the thing repeats are there to average down.
    """
    keys, diffs = _paired_means(before, after)
    rng = np.random.default_rng(seed)
    n = diffs.size
    draws = rng.choice(diffs, size=(resamples, n), replace=True).mean(axis=1)
    alpha = (1.0 - confidence) / 2.0
    low, high = np.quantile(draws, [alpha, 1.0 - alpha])

    interval = Interval(
        point=float(diffs.mean()),
        low=float(low),
        high=float(high),
        confidence=confidence,
        n_units=n,
        method=f"paired_cluster_bootstrap(B={resamples},seed={seed})",
    )
    # Two-sided sign of the bootstrap distribution, reported as a p-value for
    # readers who expect one. It is a bootstrap tail proportion, not a t-test.
    tail = float(min((draws <= 0).mean(), (draws >= 0).mean()))
    p = min(1.0, 2.0 * tail)
    return Verdict(
        label=label,
        diff=float(diffs.mean()),
        interval=interval,
        n_paired=len(keys),
        p_value=p,
        confounded_by=tuple(confounded_by),
        method=interval.method,
    )


def mcnemar_detection(
    before: Mapping[Hashable, Sequence[float]],
    after: Mapping[Hashable, Sequence[float]],
    *,
    label: str = "detection",
    confidence: float = 0.95,
    confounded_by: Sequence[str] = (),
) -> Verdict:
    """Exact McNemar test on per-prompt appear/not-appear, using majorities.

    Each prompt is collapsed to a single 1/0 by majority over its repeats, then
    the test counts only the prompts that flipped. Prompts that behaved the same
    way both times carry no information about change and are correctly ignored,
    which is why this is more sensitive than comparing two proportions.

    Ties inside a prompt (exactly half the repeats found the brand) are dropped
    rather than rounded, because rounding a coin flip invents a direction.
    """
    keys = sorted(set(before) & set(after))
    b01 = 0  # absent before, present after
    b10 = 0  # present before, absent after
    used = 0
    for k in keys:
        pb, pa = np.mean(before[k]), np.mean(after[k])
        if pb == 0.5 or pa == 0.5:
            continue
        vb, va = pb > 0.5, pa > 0.5
        used += 1
        if not vb and va:
            b01 += 1
        elif vb and not va:
            b10 += 1
    if used == 0:
        raise ValueError("no usable paired prompts for mcnemar")

    discordant = b01 + b10
    if discordant == 0:
        p = 1.0
    else:
        # Exact binomial on the discordant pairs.
        p = float(stats.binomtest(b01, discordant, 0.5).pvalue)

    diff = (b01 - b10) / used
    # Wilson-style interval on the flip asymmetry, expressed on the same scale.
    z = z_for(confidence)
    se = np.sqrt(max(discordant, 1)) / used
    interval = Interval(
        point=diff,
        low=diff - z * se,
        high=diff + z * se,
        confidence=confidence,
        n_units=used,
        method="mcnemar_exact",
    )
    if discordant == 0:
        interval = Interval(0.0, 0.0, 0.0, confidence, used, "mcnemar_exact")
    return Verdict(
        label=label,
        diff=diff,
        interval=interval,
        n_paired=used,
        p_value=p,
        confounded_by=tuple(confounded_by),
        method=f"mcnemar_exact(b01={b01},b10={b10})",
    )


def holm_adjust(p_values: Sequence[float], alpha: float = 0.05) -> tuple[bool, ...]:
    """Holm-Bonferroni step-down: which hypotheses survive at family-wise alpha.

    Uniformly more powerful than plain Bonferroni and makes no independence
    assumption, which matters because prompts in one topic move together.
    Without a correction, testing 40 prompts at 0.05 produces about two false
    alarms per run, and those two are exactly the ones a dashboard puts on the
    front page.
    """
    m = len(p_values)
    if m == 0:
        return ()
    order = sorted(range(m), key=lambda i: p_values[i])
    survives = [False] * m
    for rank, idx in enumerate(order):
        threshold = alpha / (m - rank)
        if p_values[idx] <= threshold:
            survives[idx] = True
        else:
            break  # step-down: once one fails, all larger p-values fail too
    return tuple(survives)


def surface_confounds(before: Snapshot, after: Snapshot) -> tuple[str, ...]:
    """Engines whose measurement surface is not identical across snapshots.

    Separate from `model_confounds` because it is a bigger effect. Measured on
    one day across three OpenAI access surfaces, one brand moved 32 points
    between logged-in and logged-out ChatGPT, and the top-five brand overlap
    between logged-in and API was 0.25 Jaccard. Switching collection surface
    between two rounds can therefore manufacture a swing far larger than
    anything the customer did.

    Runs marked "unspecified" are treated as one surface, since an unlabelled
    collector is at least consistent about being unlabelled.
    """
    def by_engine(s: Snapshot) -> dict[str, set[str]]:
        out: dict[str, set[str]] = {}
        for sample in s.samples:
            out.setdefault(sample.engine, set()).update(sample.surfaces)
        return out

    b, a = by_engine(before), by_engine(after)
    bad = []
    for engine in sorted(set(b) & set(a)):
        if b[engine] != a[engine] or len(b[engine]) > 1 or len(a[engine]) > 1:
            bad.append(engine)
    return tuple(bad)


def design_confounds(before: Snapshot, after: Snapshot) -> tuple[str, ...]:
    """Every reason these two snapshots should not be compared, deduplicated.

    Both model version and collection surface, labelled so the verdict text
    says which one voided the comparison.
    """
    out: list[str] = []
    for engine in model_confounds(before, after):
        out.append(f"{engine} (model version)")
    for engine in surface_confounds(before, after):
        out.append(f"{engine} (surface)")
    return tuple(out)


def model_confounds(before: Snapshot, after: Snapshot) -> tuple[str, ...]:
    """Engines whose reported model version is not identical across snapshots.

    Includes engines that drifted inside a single snapshot. Any engine listed
    here makes a before/after comparison uninterpretable, and the caller is
    expected to pass the result into the verdict rather than discard it.
    """
    def by_engine(s: Snapshot) -> dict[str, set[str]]:
        out: dict[str, set[str]] = {}
        for sample in s.samples:
            out.setdefault(sample.engine, set()).update(sample.models)
        return out

    b, a = by_engine(before), by_engine(after)
    bad = []
    for engine in sorted(set(b) & set(a)):
        if b[engine] != a[engine] or len(b[engine]) > 1 or len(a[engine]) > 1:
            bad.append(engine)
    return tuple(bad)
