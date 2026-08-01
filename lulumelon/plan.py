"""How many calls a judgement needs, before any of them are made.

Everything else in this package prices a round that already happened. This
sizes one that has not, which is the only place a measurement budget can still
be changed.

The arithmetic is the repo's own variance model, rearranged. For a mean over
`n` prompts asked `k` times each,

    se² = s2_between/n + s2_within/(n·k) = (V/n)·(ρ + (1-ρ)/k)

with `V = s2_within + s2_between` the variance of a single draw and `ρ` the
share of it that is real prompt-to-prompt difference. A target half-width `h`
at critical value `z` sets

    T = h²·n / (z²·V)      and      k = (1-ρ) / (T - ρ)

which says something the single-number version hides: **T is the largest ρ any
number of repeats can overcome.** Past it, `se²` is still above budget with
`k` infinite, because repeats only ever shrink the within term. The answer
there is more prompts, and saying so is more useful than returning a large `k`.

Two facts make this sizeable with no data at all.

**V is not a guess for a yes-or-no outcome.** By the law of total variance,
E[p_i(1-p_i)] + Var(p_i) = p̄ - p̄², so the total per-draw variance of "was the
brand named" is exactly p(1-p), and at most 1/4. That is arithmetic, and the
test beside this module measures it against `decompose` rather than asserting it.

**ρ has no such bound, and that is the whole point.** Assuming ρ=0 treats every
answer as an independent observation, which is the assumption behind the
familiar "±5 points at about 800 conversations" rule and is the error this
library exists to name. Assuming ρ=1 says repeats are worthless. So with no
pilot this module refuses to emit one number and emits the bracket instead,
priced at both ends, next to what the pilot that would close it costs.

Brands do not multiply calls. One answer is read for every tracked brand at
once, so `B` brands cost what one does. What `B` changes is the critical value:
`B` brands is `B` intervals, and a leaderboard is one claim about all of them,
so a family-wide claim uses a Bonferroni `z` and pays for the stronger
statement in calls rather than pretending it is free.

**An axis this does not yet size, and why not.** A variance-components study of
brand answers (arXiv:2607.13304, July 2026) attributes about 35% of the
movement to repeated draws and 26-32% to the language the question is asked in,
and finds a block of three extra languages worth roughly fifteen times a block
of five extra repeats. If that transfers, budget spent on repeats is budget
spent on the smaller axis. It has not been shown to transfer: the paper's
outcome is sentiment polarity, 92% of which scored exactly neutral, and it
names the was-the-brand-named refit as unrun future work whose ICCs would be
"outcome-conditional". Its corpus is also collected at temperature 0.3, which
its own limitations say makes the value of repeats a lower bound. So the
language axis is a live lead and not a plan, and this module does not price
what nobody has measured.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .mirror.intervals import z_for
from .mirror.variance import VarianceSplit
from .prices import Cost, Price, estimate, fees
from .text import counted

#: Below this, a round cannot be decomposed at all: with one draw per prompt
#: the model's rerun noise and the prompt-to-prompt spread are algebraically
#: the same quantity. It is a floor on identifiability, not on precision.
MIN_DRAWS = 2


def total_variance(rate: float) -> float:
    """Variance of a single yes-or-no draw at appearance rate `rate`.

    Exact, not approximate: for a binary outcome the within- and
    between-prompt variances sum to p(1-p) whatever the split between them.
    """
    if not 0.0 <= rate <= 1.0:
        raise ValueError(f"an appearance rate must be in [0, 1], got {rate}")
    return rate * (1.0 - rate)


def critical_value(confidence: float, brands: int, *, family: bool) -> float:
    """`z` for one interval, or for `brands` of them held at once.

    Bonferroni, which is conservative here by an unmeasured amount: brands
    named in the same answer are not independent, since naming one crowds out
    another. Conservative in the direction that costs calls rather than the one
    that overstates confidence.
    """
    if brands < 1:
        raise ValueError("a plan needs at least one brand")
    if not family or brands == 1:
        return z_for(confidence)
    return z_for(1.0 - (1.0 - confidence) / brands)


@dataclass(frozen=True, slots=True)
class Design:
    """One sampling design, or the reason there is not one."""

    n_prompts: int
    icc: float
    k_runs: int | None
    reachable: bool
    reason: str

    @property
    def calls(self) -> int | None:
        return None if self.k_runs is None else self.n_prompts * self.k_runs

    def as_text(self) -> str:
        if not self.reachable:
            return f"icc {self.icc:.2f}   unreachable: {self.reason}"
        return f"icc {self.icc:.2f}   k={self.k_runs:<5} {counted(self.calls, 'call')}"


def reachable_icc(n_prompts: int, half_width: float, z: float, variance: float) -> float:
    """The largest ICC this many prompts can beat at any number of repeats.

    The single most useful number a planner can hand back, because it converts
    "how many calls" into "is this design possible at all".
    """
    if n_prompts < 1:
        raise ValueError("a plan needs at least one prompt")
    if half_width <= 0:
        raise ValueError("target half_width must be positive")
    if variance <= 0:
        return math.inf
    return half_width**2 * n_prompts / (z**2 * variance)


def draws_needed(
    n_prompts: int, half_width: float, z: float, variance: float, icc: float
) -> Design:
    """Repeats per prompt to reach `half_width`, at a stated ICC."""
    if not 0.0 <= icc <= 1.0:
        raise ValueError(f"icc must be in [0, 1], got {icc}")
    ceiling = reachable_icc(n_prompts, half_width, z, variance)
    if icc >= ceiling:
        floor = z * math.sqrt(icc * variance / n_prompts)
        return Design(
            n_prompts=n_prompts,
            icc=icc,
            k_runs=None,
            reachable=False,
            reason=(
                f"at this icc the prompt set alone carries +/-{floor * 100:.1f} points with "
                f"{counted(n_prompts, 'prompt')}, past the target, so no number of repeats "
                "closes it"
            ),
        )
    k = math.ceil((1.0 - icc) / (ceiling - icc))
    return Design(
        n_prompts=n_prompts,
        icc=icc,
        k_runs=max(k, MIN_DRAWS),
        reachable=True,
        reason="",
    )


def prompts_for_worst_case(half_width: float, z: float, variance: float) -> int:
    """Prompts needed when repeats buy nothing at all (ICC = 1).

    The ceiling of the whole design space: below this prompt count there is an
    ICC that defeats any budget.
    """
    return math.ceil(z**2 * variance / half_width**2)


def half_width_of(n_prompts: int, k_runs: int, icc: float, z: float, variance: float) -> float:
    """The +/- a stated design buys, in proportion units.

    The same variance model the rest of this module solves backwards, read
    forwards. A buyer who states the design instead of the target needs this
    direction, and since it is the one equation, a design sized by
    `draws_needed` and read back through here agrees with itself. The test
    beside this module asserts that round trip rather than trusting it.

    Note where `k` sits. It divides the within term only, so repeats buy
    precision against the model rerolling and nothing at all against the
    questions differing from each other. At `icc` 1 this returns the same
    number for every `k`, which is the arithmetic reason a schedule that asks
    more often does not measure better.
    """
    if n_prompts < 1:
        raise ValueError("a design needs at least one prompt")
    if k_runs < 1:
        raise ValueError("a design needs at least one run per prompt")
    if not 0.0 <= icc <= 1.0:
        raise ValueError(f"icc must be in [0, 1], got {icc}")
    if variance < 0:
        raise ValueError(f"variance cannot be negative, got {variance}")
    return z * math.sqrt((variance / n_prompts) * (icc + (1.0 - icc) / k_runs))


@dataclass(frozen=True, slots=True)
class Engine:
    """One engine in a stated design, priced on its own published table.

    Engines are counted apart all the way through, because their answers are
    never pooled into one proportion. Two engines asked the same question are
    two measurements of two different systems, not two draws from one.
    """

    provider: str
    model: str
    calls: int
    cost: Cost | None

    def as_text(self) -> str:
        priced = "no published price for this model" if self.cost is None else self.cost.as_text()
        return f"{self.provider}/{self.model}   {counted(self.calls, 'call')}   {priced}"


@dataclass(frozen=True, slots=True)
class SetDesign:
    """A design the buyer stated, sized and priced before a call is made.

    The forward direction of this module. The buyer fixes the prompts, the
    repeats and the engines, and gets back the bill and the precision it buys.
    It exists because the bill is the buyer's, so the design has to be
    answerable before the spend rather than after it.
    """

    n_prompts: int
    k_runs: int
    engines: tuple[Engine, ...]
    z: float
    variance: float

    @property
    def calls_per_engine(self) -> int:
        return self.n_prompts * self.k_runs

    @property
    def total_calls(self) -> int:
        return sum(engine.calls for engine in self.engines)

    @property
    def decomposable(self) -> bool:
        """Whether this design can carry an interval at all.

        With one draw per prompt the model's rerun noise and the prompt-to-
        prompt spread are algebraically the same quantity, so the split cannot
        be identified and no honest interval comes off the round. Such a design
        can still be worth running; what it returns is a reading, not a
        measurement.
        """
        return self.k_runs >= MIN_DRAWS

    def half_width(self, icc: float) -> float:
        """The +/- one engine's number carries, at a stated split."""
        return half_width_of(self.n_prompts, self.k_runs, icc, self.z, self.variance)

    def total_cost(self) -> Cost | None:
        """The bill across every engine, or None if any engine has no table.

        A partial total is worse than none. The buyer is being asked to approve
        a spend, and a figure that quietly drops one engine understates it in
        the direction that causes the complaint.
        """
        if not self.engines:
            return None
        priced = [engine.cost for engine in self.engines]
        if any(cost is None for cost in priced):
            return None
        return Cost(
            low_usd=sum(cost.low_usd for cost in priced),  # type: ignore[union-attr]
            high_usd=sum(cost.high_usd for cost in priced),  # type: ignore[union-attr]
            measured=all(cost.measured for cost in priced),  # type: ignore[union-attr]
            basis="summed across the engines in this design",
        )


def icc_of(split: VarianceSplit) -> float:
    return split.icc


def variance_of(split: VarianceSplit) -> float:
    return split.within + split.between


@dataclass(frozen=True, slots=True)
class Comparison:
    """A one-off designed round set beside a schedule that asks every day."""

    designed_calls: int | None
    daily_calls: int
    days: int
    scans_per_day: int
    n_prompts: int

    def as_text(self) -> str:
        lines = [
            f"asking each of {counted(self.n_prompts, 'prompt')} {_times(self.scans_per_day)} "
            f"a day for {counted(self.days, 'day')} spends {counted(self.daily_calls, 'call')}",
            f"  and returns {counted(self.days, 'reading')}, none of which can carry an "
            "interval: with a",
            "  single draw per prompt the model's rerun noise and the prompt-to-prompt spread",
            "  are the same quantity, so a round of that shape cannot be decomposed at all.",
        ]
        if self.designed_calls is not None:
            lines.append("")
            lines.append(
                f"the same {counted(self.n_prompts, 'prompt')} asked enough times inside one "
                f"window spend {counted(self.designed_calls, 'call')} and return a stated "
                "interval."
            )
            lines.append(
                "  the daily schedule is not being outspent, it is buying refresh rate."
            )
            lines.append("  refresh rate is not sample size, and waiting does not convert one into the other.")
        return "\n".join(lines)


def _times(n: int) -> str:
    return "once" if n == 1 else f"{n} times"


def price_of(
    price: Price | None,
    calls: int,
    tokens: tuple[int, int] | None,
    *,
    fee_units: int | None = None,
) -> Cost | None:
    """What `calls` cost, priced from measured tokens when there are any.

    With no measured token rate this returns the fee floor rather than an
    estimate padded out with zeros. For a search-grounded model the floor is
    most of the bill, so the missing term is not the one that decides whether a
    plan is affordable, and pretending to know it would be the one number here
    that came from nowhere.

    `fee_units` defaults to the call count, which is right for a provider that
    charges once per call and wrong for one that charges once per search. A
    caller pricing the second kind states the number itself, because this
    function cannot see how many searches a call will run and guessing would
    understate the bill by whatever the model decided to do.
    """
    if price is None:
        return None
    units = calls if fee_units is None else fee_units
    if tokens is None:
        return fees(price, fee_units=units)
    per_input, per_output = tokens
    return estimate(
        price,
        input_tokens=per_input * calls,
        output_tokens=per_output * calls,
        fee_units=units,
    )
