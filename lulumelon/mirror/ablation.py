"""Is a replica of the live surface close enough to reason from?

Everything else in this package measures what an engine said. This asks the
question the product's central sentence depends on, and it is the one question
that can retire the whole approach.

The sentence worth selling is not "you appear in 38% of answers". It is "being
cited by source three takes you from 38% to 61%, plus or minus 6". The second
is causal, and nothing observational can support it: sources and appearance
move together for a dozen reasons, most of them the brand's own doing. The only
way to get at it is to control the sources, which means asking the same model
the same questions with the source list supplied as context. That is a
**replica**, and a replica is a laboratory instrument.

So before anything is concluded from one, the replica has to be shown to behave
like the surface it stands in for. If it does not, the whole line of work is a
laboratory toy, and finding that out costs one round rather than three months.

**Why "the intervals overlap" is the wrong test.** Two rates whose intervals
overlap can be genuinely alike, or they can be two noisy measurements that were
never asked to disagree. A comparison with too few calls overlaps with
everything, so a gate built on overlap rewards not looking. Reading a
non-significant difference as sameness is the same error, wearing the opposite
hat: absence of evidence arriving as evidence of absence, at the exact point in
the argument where it is most expensive.

**So the gate is an equivalence test.** It asks whether the difference between
replica and surface is provably *smaller than a margin we name in advance*.
That yields three answers rather than two, and the third one is not a failure
of the code:

  `stands_in`   the whole interval sits inside the margin. The replica differs
                from the surface by less than the precision the product quotes
                its own findings at, so reasoning from it is reasoning at that
                precision.
  `differs`     the whole interval sits outside the margin. The replica is not
                the surface. Turn back, and publish the number that says so.
  `undecided`   the interval straddles the margin. This design cannot tell the
                two apart, which is a fact about the design, not about the
                replica. It comes with the number of calls that would settle
                it, computed rather than guessed.

**The margin is not a taste.** It is the half-width the measurement is planned
at. A replica that differs from the surface by less than the width of the
product's own error bars cannot change any claim the product is willing to
make. Picking a tighter margin than that would reject a replica for a
difference nothing downstream can see; picking a looser one would accept a
replica capable of moving a published figure.

**And the call count is not a taste either.** It comes from the same sampling
model the rest of the library sizes rounds with, on the measured split rather
than an assumed one, and it carries the factor of the square root of two that a
paired comparison costs: two rounds compared carry both rounds' error, so each
has to be tighter than the difference they are being asked to resolve.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

from ..plan import critical_value, draws_needed, icc_of, variance_of
from .compare import Verdict, paired_difference
from .variance import decompose

#: The three answers this module can give. `undecided` is a result, not an
#: error: a design that cannot separate two things has said something true
#: about itself, and printing it as either of the other two would be a claim
#: nobody measured.
STANDS_IN = "stands_in"
DIFFERS = "differs"
UNDECIDED = "undecided"


@dataclass(frozen=True, slots=True)
class Gate:
    """Whether a replica may stand in for the surface, and what says so."""

    verdict: str
    margin: float
    difference: Verdict
    calls_made: int
    calls_needed: int | None
    reachable: bool
    reason: str

    @property
    def passed(self) -> bool:
        """True only for `stands_in`.

        `undecided` is deliberately not a pass. A gate that opens when it
        cannot tell is a gate that opens when the evidence is thinnest, which
        is precisely when a wrong answer travels furthest.
        """
        return self.verdict == STANDS_IN

    @property
    def shortfall(self) -> int | None:
        """Calls still owed before this comparison could decide anything."""
        if self.calls_needed is None:
            return None
        return max(0, self.calls_needed - self.calls_made)

    def as_text(self) -> str:
        band = self.margin * 100
        interval = self.difference.interval
        lines = [
            f"REPLICA GATE: {self.verdict.replace('_', ' ').upper()}",
            "",
            f"  the replica appears {interval.point * 100:+.1f} points "
            f"relative to the live surface",
            f"  {int(interval.confidence * 100)}% interval "
            f"{interval.low * 100:+.1f} to {interval.high * 100:+.1f} points, "
            f"over {self.difference.n_paired} paired prompts",
            f"  margin of equivalence +/-{band:.1f} points, "
            "the precision this measurement is planned at",
            "",
            f"  {self.reason}",
        ]
        if self.difference.confounded_by:
            lines.append("")
            lines.append(
                "  CONFOUNDED: " + "; ".join(self.difference.confounded_by)
            )
            lines.append(
                "  the two sides did not differ only in the thing being tested, so this "
                "verdict is about the difference between two conditions, not about the replica"
            )
        if self.verdict == UNDECIDED:
            lines.append("")
            if not self.reachable:
                lines.append(
                    "  no number of repeats settles this at this prompt count: the "
                    "prompt-to-prompt spread alone is wider than the margin"
                )
            elif self.shortfall:
                lines.append(
                    f"  {self.calls_needed} calls a side would decide it, "
                    f"{self.calls_made} were made, so {self.shortfall} short"
                )
        return "\n".join(lines)


def replica_gate(
    live: Mapping[str, Sequence[float]],
    replica: Mapping[str, Sequence[float]],
    *,
    margin: float,
    confidence: float = 0.95,
    brands: int = 1,
    family: bool = True,
    resamples: int = 2000,
    seed: int = 0,
    confounded_by: Sequence[str] = (),
) -> Gate:
    """Decide whether `replica` may stand in for `live`, at `margin`.

    Both sides are per-prompt sequences of 1/0 detections for one brand, keyed
    by prompt id, and they are compared pairwise over the prompts they share.

    `margin` is in rate units, so 0.05 is five points, and it is required. A
    default would be this module inventing the one number that decides what
    counts as the same, and every verdict here rests on it.
    """
    if not margin > 0:
        raise ValueError(
            f"an equivalence margin must be positive, got {margin}; a margin of zero asks "
            "for two measurements to be identical, which no finite number of calls shows"
        )
    if margin >= 1.0:
        raise ValueError(
            f"a margin of {margin} covers the whole range a rate can take, so every replica "
            "passes and the gate decides nothing"
        )

    difference = paired_difference(
        live,
        replica,
        label="replica minus live",
        confidence=confidence,
        resamples=resamples,
        seed=seed,
        confounded_by=confounded_by,
    )
    interval = difference.interval
    calls_made = min(_calls_in(live), _calls_in(replica))

    if interval.low >= -margin and interval.high <= margin:
        return Gate(
            verdict=STANDS_IN,
            margin=margin,
            difference=difference,
            calls_made=calls_made,
            calls_needed=None,
            reachable=True,
            reason=(
                "the whole interval sits inside the margin, so the replica differs from the "
                "live surface by less than the precision anything here is reported at"
            ),
        )

    if interval.low > margin or interval.high < -margin:
        return Gate(
            verdict=DIFFERS,
            margin=margin,
            difference=difference,
            calls_made=calls_made,
            calls_needed=None,
            reachable=True,
            reason=(
                "the whole interval sits outside the margin, so the replica is measurably not "
                "the surface and nothing causal should be read off it"
            ),
        )

    design = design_that_would_decide(
        live, replica, margin=margin, confidence=confidence, brands=brands, family=family
    )
    return Gate(
        verdict=UNDECIDED,
        margin=margin,
        difference=difference,
        calls_made=calls_made,
        calls_needed=design.calls,
        reachable=design.reachable,
        reason=(
            "the interval straddles the margin, so this round cannot tell a replica that "
            "stands in from one that does not. that is a fact about the design, not a "
            "finding about the replica"
        ),
    )


def _calls_in(side: Mapping[str, Sequence[float]]) -> int:
    return sum(len(v) for v in side.values())


def design_that_would_decide(
    live: Mapping[str, Sequence[float]],
    replica: Mapping[str, Sequence[float]],
    *,
    margin: float,
    confidence: float,
    brands: int = 1,
    family: bool = True,
):
    """How large each side would have to be to resolve `margin`.

    The split is decomposed from the observed rounds rather than assumed, which
    is the whole reason a pilot is worth running. The target half-width is
    `margin / sqrt(2)`, because the difference of two rounds carries both
    rounds' error and a margin resolved at full width on each side is not
    resolved at all on the difference.

    Public because two different comparisons in this package have to answer the
    same question, and a second copy of this arithmetic would eventually give a
    different answer to the same round.
    """
    shared = sorted(set(live) & set(replica))
    clusters = [list(live[k]) + list(replica[k]) for k in shared]
    split = decompose(clusters)
    z = critical_value(confidence, brands, family=family)
    return draws_needed(
        len(shared),
        margin / math.sqrt(2.0),
        z,
        variance_of(split),
        icc_of(split),
    )
