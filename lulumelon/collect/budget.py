"""A ceiling on what one round may spend, enforced while it spends it.

Everywhere else money is counted after the fact. `usage.py` prices rounds that
already happened and `plan.py` prices rounds nobody has bought yet, and neither
can stop one halfway. This can, and it exists because a round is now allowed to
run while nobody is watching it.

The number this defends is small and hard, which is the worst combination. A
prepaid account holds what it holds; past that the provider refuses, the round
stops wherever it happened to be, and what is left is a ledger too short to
answer the question it was bought for. The money is gone either way. What is
lost on top is the round.

Three decisions make this a guard rather than a counter.

**An unmetered call is charged at its ceiling, never at zero.** The provider's
usage block has gone missing in production before, and a budget that reads a
missing figure as no spend is a budget that runs forever precisely when it has
stopped being able to see. So a call nobody metered costs the most it could
have: the full search cap, plus tokens at the rate this round has been running
at, or at a stated worst case before anything has been measured.

**The check happens before the call, not after it.** Asking whether the last
call fit is one call too late; every overrun is discovered by committing it.
What is asked instead is whether the next one still fits at its own ceiling.

**Stopping is reported as an outcome, not as an error.** A round that ran out
of budget is a real, readable, shorter round, and the count of what it did not
ask is what tells a reader the interval is wider than the design intended. A
guard that raised would leave that fact in a stack trace.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..prices import FEE_PER_SEARCH, Price
from .ask import Answer

#: Tokens one call is assumed to burn before any call has been measured. Set
#: from the first real call this repo ever made: a question of eleven words
#: came back having consumed 10,046 input tokens, because the pages a search
#: returns arrive as context and context is input. It is a starting guess and
#: it is replaced by the round's own measured rate as soon as there is one.
UNMEASURED_INPUT_TOKENS = 12_000
UNMEASURED_OUTPUT_TOKENS = 400


def _calls(n: int) -> str:
    """`1 call`, not `1 calls`. The first count this prints is usually one."""
    return "1 call" if n == 1 else f"{n} calls"


@dataclass
class Budget:
    """What a round may spend, and what it has spent so far.

    `limit_usd` is the ceiling for this round alone. It is not the account
    balance and should be set below it, because a ceiling equal to the balance
    leaves nothing for the calls this cannot see, and this can only see its own
    round.
    """

    price: Price
    limit_usd: float
    max_searches: int = 1
    spent_usd: float = 0.0
    metered_calls: int = 0
    unmetered_calls: int = 0
    _input_tokens: int = field(default=0, repr=False)
    _output_tokens: int = field(default=0, repr=False)

    def __post_init__(self) -> None:
        if not self.limit_usd > 0:
            raise ValueError(
                f"a budget of {self.limit_usd} buys nothing; a round with no ceiling is the "
                "thing this class exists to refuse"
            )
        if self.max_searches < 1:
            raise ValueError("a call runs at least one search, so its ceiling is at least one fee")

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.limit_usd - self.spent_usd)

    @property
    def measured_rate(self) -> tuple[int, int] | None:
        """Input and output tokens per metered call, or None before there are any."""
        if self.metered_calls == 0:
            return None
        return (
            self._input_tokens // self.metered_calls,
            self._output_tokens // self.metered_calls,
        )

    def next_call_ceiling_usd(self) -> float:
        """The most the next call could cost, priced from what is known so far.

        Once a call has been metered the token term comes from this round's own
        rate rather than the guess, so the ceiling gets sharper as the round
        goes on. The fee term does not: a call may search up to its cap and the
        cap is what is charged, because the alternative is discovering the
        difference after paying it.
        """
        per_input, per_output = self.measured_rate or (
            UNMEASURED_INPUT_TOKENS,
            UNMEASURED_OUTPUT_TOKENS,
        )
        tokens = (
            per_input * self.price.input_per_mtok_usd + per_output * self.price.output_per_mtok_usd
        ) / 1_000_000
        searches = self.max_searches if self.price.fee_unit == FEE_PER_SEARCH else 1
        return tokens + searches * self.price.fee_per_k_high_usd / 1000

    def can_afford_another(self) -> bool:
        """Whether the next call still fits, at that call's own ceiling."""
        return self.next_call_ceiling_usd() <= self.remaining_usd

    def charge(self, answer: Answer) -> float:
        """Record what one answer cost, and return it.

        A failed call is charged nothing. The provider states that a search
        which errors is not billed, and a call that never reached it cannot
        have been. That is the one place a zero here is a measurement rather
        than an absence.
        """
        if not answer.ok:
            return 0.0

        usage = answer.usage
        counted = usage.input_tokens is not None and usage.output_tokens is not None
        if counted:
            self.metered_calls += 1
            self._input_tokens += usage.input_tokens
            self._output_tokens += usage.output_tokens
            tokens = (
                usage.input_tokens * self.price.input_per_mtok_usd
                + usage.output_tokens * self.price.output_per_mtok_usd
            ) / 1_000_000
        else:
            # Charged at the ceiling. A provider that stopped reporting usage
            # is a provider this cannot see, and a budget that spends nothing
            # while blind spends everything.
            self.unmetered_calls += 1
            per_input, per_output = self.measured_rate or (
                UNMEASURED_INPUT_TOKENS,
                UNMEASURED_OUTPUT_TOKENS,
            )
            tokens = (
                per_input * self.price.input_per_mtok_usd
                + per_output * self.price.output_per_mtok_usd
            ) / 1_000_000

        if self.price.fee_unit == FEE_PER_SEARCH:
            searches = usage.searches if usage.searches is not None else self.max_searches
        else:
            searches = 1
        cost = tokens + searches * self.price.fee_per_k_high_usd / 1000

        self.spent_usd += cost
        return cost

    def as_text(self) -> str:
        lines = [
            f"spent ${self.spent_usd:.4f} of ${self.limit_usd:.2f}, "
            f"${self.remaining_usd:.4f} left",
            f"  {_calls(self.metered_calls)} the provider metered"
            + (f", {self.unmetered_calls} it did not, charged at the ceiling"
               if self.unmetered_calls else ""),
        ]
        rate = self.measured_rate
        if rate is not None:
            lines.append(f"  measured {rate[0]} in / {rate[1]} out tokens per call")
        return "\n".join(lines)
