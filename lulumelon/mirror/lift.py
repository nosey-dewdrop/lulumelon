"""What one source is worth, and when that number may be called a lift.

The sentence this library exists to earn is not "you appear in 38% of answers".
It is "being carried by source three takes you from 38 to 61, plus or minus 6".
Everything upstream of here measures the first kind of sentence. This module
measures the second, and spends most of its length on the conditions under which
it refuses to.

**The contrast.** One replica arm is asked with the full source list held in
front of the model. The other is asked with exactly one source removed and
nothing else touched. Both arms ask the same questions, so the comparison is
paired and prompt-to-prompt spread cancels out of the difference instead of
being carried twice. What is left is what that one source was worth inside the
replica.

**Inside the replica is the whole caveat.** The contrast is controlled: the
source list is ours, the removal is deliberate, one thing moved. So the
difference is a causal quantity from the moment it is measured, and no gate
makes it more causal than it already was. What a passing gate buys is somewhere
to carry it *to*. A replica that has not been shown to track the live surface
still yields a perfectly valid effect, in a world nobody buys anything in.

That is why `lift` is a name this result may be granted rather than the name it
is born with. Ungated, the same arithmetic is an **arm difference**: true, and
about a laboratory. The word is withheld rather than the number, because
withholding the number would invite it to be recomputed somewhere with no gate
in sight.

**What a passing gate does not cover.** The gate bounds the gap between replica
and live *levels* at its margin. It says nothing about the difference of
differences, which is the thing actually being transported. So a lift is a
transport resting on a named assumption, not a proof, and the assumption is
printed next to the number every time. What can be carried exactly is the
consequence for the levels: a rate quoted as the customer's rate inherits the
gate's margin on top of its own interval, and this module widens it rather than
quoting the laboratory's own precision as if it were the surface's.

**Four answers, and the fourth is the dangerous one.**

  `moves`        the whole interval sits outside the margin. The source is worth
                 a sentence, in the direction the sign gives.
  `negligible`   the whole interval sits inside the margin. Whatever the source
                 does is smaller than the precision anything here is published
                 at, so it cannot move a claim. This is a finding, and a
                 cheaper one to act on than most.
  `undecided`    the interval straddles the margin. This round cannot separate
                 the two, which is a fact about the round, and it arrives with
                 the call count that would settle it.
  `no_contrast`  the two arms produced the identical detections, prompt for
                 prompt. Either the same round was handed over twice or the
                 outcome has no variation in it. Both would otherwise land in
                 `negligible` with an interval of zero width and read as proof
                 that the source does not matter, which is the most expensive
                 wrong answer this file could return.

**Several sources at once is several tests.** Ablating five sources and
publishing the largest number runs five tests and reports the winner. The
correction is applied to the intervals rather than to a separate row of
p-values, so the interval on screen is the interval the decision was made with.
Holm is uniformly more powerful for the decisions alone, and taking it would put
a decision on screen that the printed interval disagrees with.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable, Mapping, Sequence

import numpy as np

from ..text import counted
from .ablation import Gate, design_that_would_decide
from .compare import Verdict, paired_difference
from .intervals import Interval, cluster_bootstrap_ci, resamples_for

#: What this round can say about the source that was removed.
MOVES = "moves"
NEGLIGIBLE = "negligible"
UNDECIDED = "undecided"
NO_CONTRAST = "no_contrast"

#: What the measured difference may be called on screen. The second one is not
#: a downgrade of the first, it is a different claim: one is about a customer's
#: surface, the other about two arms of an experiment.
LIFT = "lift"
ARM_DIFFERENCE = "arm difference"


@dataclass(frozen=True, slots=True)
class SourceEffect:
    """One source removed, what happened, and what the result may be called."""

    source: str
    verdict: str
    margin: float
    held: Interval
    dropped: Interval
    difference: Verdict
    prompts_paired: int
    prompts_unpaired: int
    calls_made: int
    calls_needed: int | None
    reachable: bool
    gate: Gate | None
    family_size: int
    reason: str

    @property
    def is_lift(self) -> bool:
        """True only when a gate was supplied and it passed.

        Absent a gate this is False rather than unknown. A result that cannot
        name the gate it passed has not passed one, and the two are
        indistinguishable to everything downstream.
        """
        return self.gate is not None and self.gate.passed

    @property
    def name(self) -> str:
        return LIFT if self.is_lift else ARM_DIFFERENCE

    @property
    def shortfall(self) -> int | None:
        """Calls still owed before this contrast could decide anything."""
        if self.calls_needed is None:
            return None
        return max(0, self.calls_needed - self.calls_made)

    @property
    def direction(self) -> str:
        """Which way the source moved the rate, in words."""
        if self.verdict == NO_CONTRAST or self.difference.diff == 0.0:
            return "neither"
        return "raises" if self.difference.diff > 0 else "lowers"

    def transported(self, interval: Interval) -> Interval | None:
        """A laboratory level restated as a claim about the live surface.

        Returns None when there is no passing gate, because there is then
        nothing to transport it with. When there is, the gate's margin is added
        to both ends: the replica was shown to sit within that margin of the
        surface, so a surface rate read off the replica is uncertain by its own
        interval *and* by the discrepancy the gate tolerated. Quoting the
        laboratory's own half-width as the customer's would spend precision the
        gate never bought.
        """
        if not self.is_lift:
            return None
        assert self.gate is not None  # is_lift
        by = self.gate.margin
        return Interval(
            point=interval.point,
            low=max(0.0, interval.low - by),
            high=min(1.0, interval.high + by),
            confidence=interval.confidence,
            n_units=interval.n_units,
            method=f"{interval.method}+gate_margin({by:.4f})",
        )

    def as_text(self) -> str:
        interval = self.difference.interval
        pct = int(round(interval.confidence * 100))
        lines = [
            f"ABLATION: {self.verdict.replace('_', ' ').upper()}",
            "",
            f"  {self.source}  (removed from the source list, nothing else changed)",
            "",
            f"  source held      {self.held.point * 100:.1f}% "
            f"({pct}% CI {self.held.low * 100:.1f}..{self.held.high * 100:.1f})",
            f"  source dropped   {self.dropped.point * 100:.1f}% "
            f"({pct}% CI {self.dropped.low * 100:.1f}..{self.dropped.high * 100:.1f})",
            f"  difference       {interval.point * 100:+.1f} points, "
            f"{pct}% interval {interval.low * 100:+.1f} to {interval.high * 100:+.1f}, "
            f"over {counted(self.prompts_paired, 'paired prompt')}",
            f"  margin of equivalence +/-{self.margin * 100:.1f} points, "
            "the precision this measurement is planned at",
        ]
        if self.prompts_unpaired:
            lines.append(
                f"  {counted(self.prompts_unpaired, 'prompt')} were asked in only one arm and "
                "take no part in this difference"
            )
        if self.family_size > 1:
            lines.append(
                f"  one of {self.family_size} sources ablated together, so every interval here is "
                f"wide enough for all {self.family_size} claims to be held at once"
            )
        lines.append("")
        lines.append(f"  NAMED: {self.name}")
        if self.is_lift:
            assert self.gate is not None
            held = self.transported(self.held)
            dropped = self.transported(self.dropped)
            assert held is not None and dropped is not None
            lines.append(
                f"  the replica stands in for the live surface at +/-{self.gate.margin * 100:.1f} "
                "points, so this contrast may be read as a lift"
            )
            lines.append(
                f"  as live-surface rates that margin rides on top: "
                f"{dropped.low * 100:.1f}..{dropped.high * 100:.1f}% without the source, "
                f"{held.low * 100:.1f}..{held.high * 100:.1f}% with it"
            )
            lines.append(
                "  the gate bounds the gap between replica and surface levels; it does not bound "
                "the difference of differences, so the difference transports on a named "
                "assumption rather than on a proof"
            )
        else:
            why = (
                "no gate was supplied with this contrast"
                if self.gate is None
                else f"the gate returned {self.gate.verdict.replace('_', ' ')}"
            )
            lines.append(
                f"  {why}, so this is a measured difference between two laboratory arms and "
                "not a claim about what a customer sees"
            )
        if self.difference.confounded_by:
            lines.append("")
            lines.append("  CONFOUNDED: " + "; ".join(self.difference.confounded_by))
            lines.append(
                "  the two arms did not differ only in the source that was removed, so this is "
                "about the difference between two conditions rather than about the source"
            )
        lines.append("")
        lines.append(f"  {self.reason}")
        if self.verdict == UNDECIDED:
            lines.append("")
            if not self.reachable:
                lines.append(
                    "  no number of repeats settles this at this prompt count: the "
                    "prompt-to-prompt spread alone is wider than the margin"
                )
            elif self.shortfall:
                lines.append(
                    f"  {counted(self.calls_needed, 'call')} an arm would decide it, "
                    f"{self.calls_made} were made, so {self.shortfall} short"
                )
        return "\n".join(lines)


def source_effect(
    held: Mapping[Hashable, Sequence[float]],
    dropped: Mapping[Hashable, Sequence[float]],
    *,
    source: str,
    margin: float,
    gate: Gate | None,
    confidence: float = 0.95,
    brands: int = 1,
    family: bool = True,
    resamples: int | None = None,
    seed: int = 0,
    family_size: int = 1,
    confounded_by: Sequence[str] = (),
) -> SourceEffect:
    """What removing `source` did, measured on the arms that did and did not carry it.

    `held` and `dropped` are sequences of 1/0 detections for one brand, keyed
    by the unit they were measured on and keyed the same way on both sides;
    `lulu` keys by the sample, which is one prompt on one engine. `held` is the
    arm asked with the full list.

    `gate` has no default. Passing `None` is allowed and says out loud that this
    contrast has no live surface behind it; a default would make the ungated
    reading the one that happens by not typing anything, which is the reading
    that travels furthest when it is wrong.
    """
    if not margin > 0:
        raise ValueError(
            f"an equivalence margin must be positive, got {margin}; at zero the question "
            "becomes whether a source changed nothing at all, which no finite round answers"
        )
    if margin >= 1.0:
        raise ValueError(
            f"a margin of {margin} covers the whole range a rate can take, so every source is "
            "negligible and the comparison decides nothing"
        )
    if not source.strip():
        raise ValueError(
            "the source that was removed has to be named: a contrast whose treatment is not "
            "recorded cannot be repeated, and it is what the resulting sentence is about"
        )

    paired = [
        k for k in sorted(set(held) & set(dropped)) if len(held[k]) > 0 and len(dropped[k]) > 0
    ]
    if not paired:
        raise ValueError(
            "no prompt was asked in both arms, so there is nothing to pair; an ablation "
            "compares the same questions with and without the source, not two question sets"
        )
    unpaired = len(set(held) | set(dropped)) - len(paired)

    draws = resamples_for(confidence) if resamples is None else resamples
    left = {k: list(dropped[k]) for k in paired}
    right = {k: list(held[k]) for k in paired}

    difference = paired_difference(
        left,
        right,
        label=f"held minus dropped: {source}",
        confidence=confidence,
        resamples=draws,
        seed=seed,
        confounded_by=confounded_by,
    )
    held_rate = cluster_bootstrap_ci(
        [right[k] for k in paired], resamples=draws, confidence=confidence, seed=seed
    )
    dropped_rate = cluster_bootstrap_ci(
        [left[k] for k in paired], resamples=draws, confidence=confidence, seed=seed
    )
    calls_made = min(
        sum(len(v) for v in right.values()), sum(len(v) for v in left.values())
    )

    common = dict(
        source=source,
        margin=margin,
        held=held_rate,
        dropped=dropped_rate,
        difference=difference,
        prompts_paired=len(paired),
        prompts_unpaired=unpaired,
        calls_made=calls_made,
        gate=gate,
        family_size=family_size,
    )

    if all(
        float(np.mean(right[k])) == float(np.mean(left[k])) for k in paired
    ):
        return SourceEffect(
            verdict=NO_CONTRAST,
            calls_needed=None,
            reachable=True,
            reason=(
                "both arms detected the brand identically in every prompt, so this round holds "
                "no contrast to measure. either the same arm was handed over twice, or the "
                "outcome did not vary at all under this design; a difference of zero here is "
                "not a measured zero"
            ),
            **common,
        )

    interval = difference.interval
    if interval.low >= -margin and interval.high <= margin:
        return SourceEffect(
            verdict=NEGLIGIBLE,
            calls_needed=None,
            reachable=True,
            reason=(
                "the whole interval sits inside the margin, so whatever this source is worth is "
                "smaller than the precision anything here is reported at and cannot move a claim"
            ),
            **common,
        )

    if interval.low > margin or interval.high < -margin:
        return SourceEffect(
            verdict=MOVES,
            calls_needed=None,
            reachable=True,
            reason=(
                f"the whole interval sits outside the margin, so carrying this source "
                f"{'raises' if interval.point > 0 else 'lowers'} the rate by more than the "
                "measurement's own precision"
            ),
            **common,
        )

    design = design_that_would_decide(
        left, right, margin=margin, confidence=confidence, brands=brands, family=family
    )
    settled = "the direction is settled and the size is not; " if difference.significant else ""
    return SourceEffect(
        verdict=UNDECIDED,
        calls_needed=design.calls,
        reachable=design.reachable,
        reason=(
            f"the interval straddles the margin, so {settled}this round cannot tell a source "
            "worth chasing from one that is not. that is a fact about the round, not a finding "
            "about the source"
        ),
        **common,
    )


def ablation_series(
    held: Mapping[Hashable, Sequence[float]],
    arms: Mapping[str, Mapping[Hashable, Sequence[float]]],
    *,
    margin: float,
    gate: Gate | None,
    confidence: float = 0.95,
    family: bool = True,
    brands: int = 1,
    resamples: int | None = None,
    seed: int = 0,
    confounded_by: Sequence[str] = (),
) -> tuple[SourceEffect, ...]:
    """Several sources ablated against one held arm, priced as one family of claims.

    `arms` maps each removed source to the arm that was asked without it. Order
    is preserved rather than sorted by effect size: the largest number in a set
    of unstable estimates is the least trustworthy one in it, and sorting on it
    is how a list of noise acquires a headline.

    With `family` set, every interval is computed at a level wide enough to hold
    all of them at once. That is Bonferroni, conservative here by an unmeasured
    amount, since sources removed from the same list are not independent of each
    other. Conservative in the direction that costs calls rather than the one
    that overstates confidence.

    Each arm bootstraps from its own seed. Sharing one would leave every source
    resampled along the same draws, which is a correlation nobody asked for
    across results that are read side by side.
    """
    if not arms:
        raise ValueError("an ablation series needs at least one source to remove")
    size = len(arms)
    each = confidence if (not family or size == 1) else 1.0 - (1.0 - confidence) / size
    return tuple(
        source_effect(
            held,
            arm,
            source=url,
            margin=margin,
            gate=gate,
            confidence=each,
            brands=brands,
            family=family,
            resamples=resamples,
            seed=seed + i,
            family_size=size,
            confounded_by=confounded_by,
        )
        for i, (url, arm) in enumerate(arms.items())
    )
