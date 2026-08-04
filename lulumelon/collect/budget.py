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

The one exception is stated rather than inferred. A round collected with no
search tool attached has a search cap of nothing, because the call was never
able to run one, and there the missing count is a fact about the request we
sent rather than a silence from the provider. It is a constructor argument and
not a reading of the response, since the ceiling is needed before the response
exists.

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
from ..text import counted
from .ask import Answer

#: Tokens one call is assumed to burn before any call has been measured. Set
#: from the first real call this repo ever made: a question of eleven words
#: came back having consumed 10,046 input tokens, because the pages a search
#: returns arrive as context and context is input. It is a starting guess and
#: it is replaced by the round's own measured rate as soon as there is one.
#:
#: There is no matching guess for the output side, and the absence is the
#: point. What a call may write back is not observed, it is sent: every
#: request carries the cap and the provider stops there. A guard that guessed
#: at a number it had already chosen priced 400 tokens against a call it had
#: allowed 1,024, printed $0.0440 as the most one call could cost, and paid
#: $0.0467 for the next one.
UNMEASURED_INPUT_TOKENS = 12_000

#: Characters to the token when a prompt has to be priced before it is sent.
#: Latin script runs three and a half to four, so three counts high on
#: purpose. The two ways to be wrong here are not symmetric: counting high
#: refuses a call that would have fit and costs nothing, counting low pays for
#: one that did not and discovers the difference on the invoice.
CHARS_PER_TOKEN = 3


def tokens_for_chars(chars: int) -> int:
    """The most tokens that many characters can be."""
    return -(-chars // CHARS_PER_TOKEN)


def token_ceiling(text: str) -> int:
    """The most tokens a prompt this long can be, counted before it is sent."""
    return tokens_for_chars(len(text))


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
    #: The cap this round's calls carry, stated by whoever built the provider
    #: that will send it. There is no default, because a default is what this
    #: field replaced: one number written into the network layer and a second
    #: one written into the guard, each correct about a call the other was not
    #: describing. A call whose cap this does not know cannot be priced.
    max_output_tokens: int
    max_searches: int = 1
    #: Whether the round this guards was given a search tool at all. False is
    #: the unsearched arm, where no call can run a search and therefore no call
    #: can owe a fee charged per search. It is stated by the caller rather than
    #: inferred, because the ceiling is asked for before the first call exists
    #: to be looked at, and a ceiling that guessed would be the one number here
    #: that is a guess.
    can_search: bool = True
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
        if self.can_search and self.max_searches < 1:
            raise ValueError("a call runs at least one search, so its ceiling is at least one fee")
        if self.max_output_tokens < 1:
            raise ValueError(
                f"a cap of {self.max_output_tokens} output tokens is a call that cannot answer; "
                "this is the number the request carries, not a guess about it"
            )

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

    def next_call_ceiling_usd(
        self,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        searches: int | None = None,
    ) -> float:
        """The most the next call could cost, priced from what is known so far.

        A caller that has already built the prompt states its size and gets an
        exact ceiling rather than a guessed one. Nothing else in a round knows
        that number: the guard is asked before the call exists, so the only
        caller that can hand over the real shape is the one holding the text.

        Once a call has been metered the input term comes from this round's own
        rate rather than the opening guess, so the ceiling gets sharper as the
        round goes on. The output term never does. A round that averaged three
        hundred written tokens is not a round whose next call cannot write a
        thousand; the cap is what stops it, and the cap is known exactly.

        The fee term does not sharpen either: a call may search up to its cap
        and the cap is what is charged, because the alternative is discovering
        the difference after paying it.

        On the unsearched arm there is no fee term at all. That is not an
        optimistic reading of a silence, which is what every other zero in this
        file would be: the tool was never sent, so the next call cannot run a
        search whatever it does with the question. Charging the cap anyway
        would stop that arm at a fraction of the calls it can afford and report
        the difference as a budget it never spent. A single call sent without
        the tool inside a round that has it says so the same way, by stating
        its own count of zero.
        """
        per_input, per_output = self._shape(input_tokens, output_tokens)
        tokens = (
            per_input * self.price.input_per_mtok_usd + per_output * self.price.output_per_mtok_usd
        ) / 1_000_000
        return tokens + self._fees(searches) * self.price.fee_per_k_high_usd / 1000

    def _shape(self, input_tokens: int | None, output_tokens: int | None) -> tuple[int, int]:
        """The token counts to price an unmeasured call at, stated or inferred."""
        if input_tokens is None:
            measured = self.measured_rate
            input_tokens = measured[0] if measured else UNMEASURED_INPUT_TOKENS
        return input_tokens, self.max_output_tokens if output_tokens is None else output_tokens

    def _fees(self, searches: int | None) -> int:
        """How many fee units the next call owes, stated or taken at the round's cap."""
        if self.price.fee_unit != FEE_PER_SEARCH:
            return 1
        if searches is not None:
            return searches
        return self.max_searches if self.can_search else 0

    def can_afford_another(
        self,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        searches: int | None = None,
    ) -> bool:
        """Whether the next call still fits, at that call's own ceiling."""
        ceiling = self.next_call_ceiling_usd(
            input_tokens=input_tokens, output_tokens=output_tokens, searches=searches
        )
        return ceiling <= self.remaining_usd

    def charge(
        self,
        answer: Answer,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        searches: int | None = None,
    ) -> float:
        """Record what one answer cost, and return it.

        The token arguments are the shape the call was allowed, and they are
        read only when the provider metered nothing. A call charged at a
        ceiling has to be charged at its own, or the round that could not see
        what it spent also under-reports it.

        `searches` is read whenever the provider did not report a count, and a
        zero is the caller saying the tool was left off this one request. A
        count that arrives anyway is charged, because what the provider says it
        did outranks what we sent.

        A failed call is charged nothing. The provider states that a search
        which errors is not billed, and a call that never reached it cannot
        have been. That is the one place a zero here is a measurement rather
        than an absence.
        """
        if not answer.ok:
            return 0.0

        usage = answer.usage
        # Named as `usage.py` names the same expression, which also keeps it
        # from shadowing the counted-noun helper imported above.
        both_tokens = usage.input_tokens is not None and usage.output_tokens is not None
        if both_tokens:
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
            per_input, per_output = self._shape(input_tokens, output_tokens)
            tokens = (
                per_input * self.price.input_per_mtok_usd
                + per_output * self.price.output_per_mtok_usd
            ) / 1_000_000

        if self.price.fee_unit == FEE_PER_SEARCH and usage.searches is not None:
            # What the provider says it did outranks both the cap and anything
            # the caller declared about the request it sent.
            billed = usage.searches
        else:
            # The other honest zero in this file: a call that was never handed
            # the tool cannot have searched, so its silence is a measurement
            # rather than a provider that stopped reporting.
            billed = self._fees(searches)
        cost = tokens + billed * self.price.fee_per_k_high_usd / 1000

        self.spent_usd += cost
        return cost

    def as_text(self) -> str:
        lines = [
            f"spent ${self.spent_usd:.4f} of ${self.limit_usd:.2f}, "
            f"${self.remaining_usd:.4f} left",
            f"  {counted(self.metered_calls, 'call')} the provider metered"
            + (f", {self.unmetered_calls} it did not, charged at the ceiling"
               if self.unmetered_calls else ""),
        ]
        rate = self.measured_rate
        if rate is not None:
            lines.append(f"  measured {rate[0]} in / {rate[1]} out tokens per call")
        return "\n".join(lines)
