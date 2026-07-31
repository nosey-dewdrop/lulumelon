"""What a round actually cost, from what the provider said about it.

This is the meter behind the claim the library exists to make. A claim about
money is worth what its arithmetic is worth, so nothing here is estimated when
it was measured and nothing is presented as measured when it was estimated.

Answered calls fall into exactly three buckets and they never merge:

  **metered**  the response stated an amount. Used verbatim, no band. This is
               an invoice line, not a model of one.
  **counted**  no stated amount, but the response reported its token counts.
               Priced from the published rates, which carry a band because the
               per-request fee depends on a search context size the response
               does not always name.
  **silent**   neither. Only the request fee is known, so only the request fee
               is charged, and the result is labelled a floor. The alternative
               is to add a zero token term and call the sum an estimate, which
               produces the same digits under a claim nobody measured.

Failed calls are priced at nothing and counted out loud. Whether a rejected
call is billed is not something the response says, and a collector that guessed
either way would be inventing the most interesting number on the page.

Records written before usage was recorded at all are a fourth category, kept
apart from `silent`. "This build did not collect it" and "the provider did not
report it" are different facts about different parties, and only the second is
evidence about a provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from .collect.ledger import Record
from .prices import Cost, Price, estimate, request_fees


@dataclass(frozen=True, slots=True)
class Spend:
    """What a set of recorded calls cost, and how much of that is known.

    Every count is here rather than a single "measured" flag, because a round
    is usually a mixture and a flag cannot say "eleven of two hundred". The
    fraction that is exact is the number a buyer should read first.
    """

    calls: int
    answered: int
    failed: int
    metered: int
    counted: int
    silent: int
    unrecorded: int
    input_tokens: int
    output_tokens: int
    metered_usd: float
    counted_cost: Cost | None
    floor_cost: Cost | None
    price: Price | None

    @property
    def low_usd(self) -> float:
        return self.metered_usd + _low(self.counted_cost) + _low(self.floor_cost)

    @property
    def high_usd(self) -> float:
        return self.metered_usd + _high(self.counted_cost) + _high(self.floor_cost)

    @property
    def exact(self) -> bool:
        """True when every answered call priced itself."""
        return self.answered > 0 and self.metered == self.answered

    @property
    def per_call_low_usd(self) -> float:
        return self.low_usd / self.answered if self.answered else 0.0

    @property
    def per_call_high_usd(self) -> float:
        return self.high_usd / self.answered if self.answered else 0.0

    def as_text(self) -> str:
        lines = [
            f"{self.calls} calls recorded: {self.answered} answered, {self.failed} failed",
        ]
        if self.unrecorded:
            lines.append(
                f"  {self.unrecorded} were written before this build recorded usage, "
                "so they carry no cost and are not counted below"
            )

        lines.append("")
        lines.append("TOKENS, as the provider reported them")
        if self.counted or self.metered:
            lines.append(f"  input   {self.input_tokens:,}")
            lines.append(f"  output  {self.output_tokens:,}")
        reporting = self.answered - self.silent - self.unrecorded
        lines.append(
            f"  reported by {reporting} of {self.answered - self.unrecorded} answered calls"
        )

        lines.append("")
        lines.append("COST")
        if self.metered:
            lines.append(f"  stated by the provider, over {_calls(self.metered)}")
            lines.append(f"    ${self.metered_usd:.6f}")
        if self.counted_cost is not None:
            lines.append(
                f"  computed for {_calls(self.counted)} that reported tokens but no amount"
            )
            lines.append(f"    {self.counted_cost.as_text()}")
        if self.floor_cost is not None:
            lines.append(f"  a floor for {_calls(self.silent)} that reported neither")
            lines.append(f"    {self.floor_cost.as_text()}")
        if self.failed:
            lines.append(
                f"  {_calls(self.failed)} failed and {'is' if self.failed == 1 else 'are'} not "
                "priced: the response does not say whether a rejected call is billed"
            )
        if self.price is None and not self.metered:
            lines.append("  no published price on file for this model, so nothing can be priced")

        lines.append("")
        if self.exact:
            lines.append(f"  total  ${self.low_usd:.6f}, every call metered by the provider")
        elif self.answered:
            lines.append(
                f"  total  ${self.low_usd:.6f} to ${self.high_usd:.6f}"
                f"   ({self.metered} of {self.answered} answered calls metered)"
            )
            lines.append(
                f"  per call  ${self.per_call_low_usd:.6f} to ${self.per_call_high_usd:.6f}"
            )
        return "\n".join(lines)


def _calls(n: int) -> str:
    return f"{n} call" if n == 1 else f"{n} calls"


def _low(cost: Cost | None) -> float:
    return cost.low_usd if cost else 0.0


def _high(cost: Cost | None) -> float:
    return cost.high_usd if cost else 0.0


def spend_of(records: Iterable[Record], price: Price | None) -> Spend:
    """Total what a set of records cost, keeping the three bases apart.

    `price` may be None. A model whose price has not been read gets "nothing
    can be priced" rather than the rate of its nearest relative, because the
    nearest relative is where a fifteen-fold error comes from.
    """
    calls = answered = failed = 0
    metered = counted = silent = unrecorded = 0
    metered_in = metered_out = counted_in = counted_out = 0
    metered_usd = 0.0

    for record in records:
        calls += 1
        if record.status != "ok":
            failed += 1
            continue
        answered += 1

        usage = record.usage()
        if usage is None:
            unrecorded += 1
            continue

        if usage.cost_usd is not None:
            metered += 1
            metered_usd += usage.cost_usd
            # Still summed: the provider stated these, and the total is what a
            # customer checks their own bill against.
            metered_in += usage.input_tokens or 0
            metered_out += usage.output_tokens or 0
        elif usage.input_tokens is not None and usage.output_tokens is not None:
            counted += 1
            counted_in += usage.input_tokens
            counted_out += usage.output_tokens
        else:
            silent += 1

    counted_cost = None
    floor_cost = None
    if price is not None and counted:
        # Priced from the tokens those calls themselves reported. The metered
        # calls already carry the provider's own figure; adding a published
        # rate on top would bill the same tokens twice.
        counted_cost = estimate(
            price, input_tokens=counted_in, output_tokens=counted_out, requests=counted
        )
    if price is not None and silent:
        floor_cost = request_fees(price, requests=silent)

    return Spend(
        calls=calls,
        answered=answered,
        failed=failed,
        metered=metered,
        counted=counted,
        silent=silent,
        unrecorded=unrecorded,
        input_tokens=metered_in + counted_in,
        output_tokens=metered_out + counted_out,
        metered_usd=metered_usd,
        counted_cost=counted_cost,
        floor_cost=floor_cost,
        price=price,
    )


def token_rate(records: Sequence[Record]) -> tuple[int, int] | None:
    """Median input and output tokens over the calls that reported both.

    The median rather than the mean: one truncated answer or one unusually long
    one should not move the rate a whole plan is priced from. Returns None when
    nothing reported, which is the honest input to a planner that would
    otherwise quietly price a round at zero tokens.
    """
    pairs = [
        (r.usage().input_tokens, r.usage().output_tokens)
        for r in records
        if r.status == "ok"
        and r.usage() is not None
        and r.usage().input_tokens is not None
        and r.usage().output_tokens is not None
    ]
    if not pairs:
        return None
    return _median([p[0] for p in pairs]), _median([p[1] for p in pairs])


def _median(values: list[int]) -> int:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) // 2
