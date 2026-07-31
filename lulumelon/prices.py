"""What a call costs, from the provider's own page, with the date it was read.

The claim this library is built to support is that the same judgement can be
reached for a fraction of what it is sold for. A claim about money needs a
meter, and a meter that runs on invented numbers measures nothing.

Two rules hold everything here.

**Every number carries its source and the day it was read.** Prices move. A
figure without a date is a figure nobody can check, and a stale figure quoted
confidently is worse than no figure, because it survives into a pitch.

**A cost is reported as a band unless the provider states the exact amount.**
For a search-grounded model the fee is not a rounding error next to the tokens:
at the published rates one `sonar` call costs half a cent to a cent in fees and
a small fraction of that in tokens. Collapsing that to a single number would
mean choosing a search context size on the user's behalf and then presenting
the guess as an invoice.

**A fee carries the unit it is charged in.** One provider bills per request and
another bills per search, and the two numbers are close enough to look
interchangeable. They are not: a single request is one fee on the first and as
many fees as the model chose to search on the second. A field named for one
unit and holding the other is how a bill comes out several times larger than
the screen said, so the unit is stored beside the number instead of implied by
the name of the field.
"""

from __future__ import annotations

from dataclasses import dataclass

#: A million, kept named because every published price is quoted per million
#: tokens and the conversion is where an order of magnitude gets lost.
MILLION = 1_000_000

#: What one fee is charged for. `request` means one fee per call, whatever the
#: model does inside it. `search` means one fee per search the model ran, so a
#: call that searched five times pays five.
FEE_PER_REQUEST = "request"
FEE_PER_SEARCH = "search"
FEE_UNITS = (FEE_PER_REQUEST, FEE_PER_SEARCH)


@dataclass(frozen=True, slots=True)
class Price:
    """The published price of one model, as written on the provider's page.

    `fee_per_k_low` and `_high` bracket the fee across the bands the provider
    bills for, per thousand of whatever `fee_unit` names. They are equal when
    the provider publishes one figure, and both are zero when there is no fee.
    """

    provider: str
    model: str
    input_per_mtok_usd: float
    output_per_mtok_usd: float
    fee_per_k_low_usd: float
    fee_per_k_high_usd: float
    fee_unit: str
    #: Where the token rates were read.
    source: str
    #: Where the fee was read. Often the same page, and not always: one
    #: provider publishes the tokens and the per-search charge separately, and
    #: a single `source` field would have cited one page for two numbers.
    fee_source: str
    read_on: str

    def __post_init__(self) -> None:
        if self.fee_unit not in FEE_UNITS:
            raise ValueError(
                f"fee_unit {self.fee_unit!r} is not one of {FEE_UNITS}; a fee whose unit is "
                "not stated is a number nobody can multiply correctly"
            )

    @property
    def has_fee(self) -> bool:
        return self.fee_per_k_high_usd > 0

    @property
    def fee_text(self) -> str:
        # Spelled out rather than an `s` on the end. "searchs" reached a
        # customer's screen on the first real run of this command.
        unit = {FEE_PER_REQUEST: "requests", FEE_PER_SEARCH: "searches"}[self.fee_unit]
        if self.fee_per_k_low_usd == self.fee_per_k_high_usd:
            return f"${self.fee_per_k_low_usd:g} per thousand {unit}"
        return f"${self.fee_per_k_low_usd:g} to ${self.fee_per_k_high_usd:g} per thousand {unit}"

    @property
    def sources(self) -> tuple[str, ...]:
        """Every page one of these numbers came off, deduplicated, in order."""
        return tuple(dict.fromkeys((self.source, self.fee_source)))

    def provenance(self) -> str:
        return f"{' and '.join(self.sources)}, read {self.read_on}"


#: What Anthropic charges for one web search, per thousand, whichever model ran
#: it. Published as a single figure rather than a band, and a search that errors
#: is not billed. Read 2026-08-01 from the tool's own page.
_SEARCH_FEE_PER_K = 10.0
_ANTHROPIC_SEARCH_SOURCE = "https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool"


def _anthropic(model: str, input_usd: float, output_usd: float) -> Price:
    """One Claude model, priced from the model table plus the search fee.

    Two pages, because Anthropic publishes them apart: tokens on the model
    overview, the per-search fee on the web search tool page. Both are recorded
    so a later reader can check either half without trusting this line.
    """
    return Price(
        provider="anthropic",
        model=model,
        input_per_mtok_usd=input_usd,
        output_per_mtok_usd=output_usd,
        fee_per_k_low_usd=_SEARCH_FEE_PER_K,
        fee_per_k_high_usd=_SEARCH_FEE_PER_K,
        fee_unit=FEE_PER_SEARCH,
        source="https://platform.claude.com/docs/en/about-claude/models/overview",
        fee_source=_ANTHROPIC_SEARCH_SOURCE,
        read_on="2026-08-01",
    )


PRICES: dict[tuple[str, str], Price] = {
    ("perplexity", "sonar"): Price(
        provider="perplexity",
        model="sonar",
        input_per_mtok_usd=1.0,
        output_per_mtok_usd=1.0,
        fee_per_k_low_usd=5.0,
        fee_per_k_high_usd=12.0,
        fee_unit=FEE_PER_REQUEST,
        source="https://docs.perplexity.ai/getting-started/pricing",
        fee_source="https://docs.perplexity.ai/getting-started/pricing",
        read_on="2026-07-31",
    ),
    ("perplexity", "sonar-pro"): Price(
        provider="perplexity",
        model="sonar-pro",
        input_per_mtok_usd=3.0,
        output_per_mtok_usd=15.0,
        fee_per_k_low_usd=6.0,
        fee_per_k_high_usd=14.0,
        fee_unit=FEE_PER_REQUEST,
        source="https://docs.perplexity.ai/getting-started/pricing",
        fee_source="https://docs.perplexity.ai/getting-started/pricing",
        read_on="2026-07-31",
    ),
    ("perplexity", "sonar-reasoning-pro"): Price(
        provider="perplexity",
        model="sonar-reasoning-pro",
        input_per_mtok_usd=2.0,
        output_per_mtok_usd=8.0,
        fee_per_k_low_usd=6.0,
        fee_per_k_high_usd=14.0,
        fee_unit=FEE_PER_REQUEST,
        source="https://docs.perplexity.ai/getting-started/pricing",
        fee_source="https://docs.perplexity.ai/getting-started/pricing",
        read_on="2026-07-31",
    ),
    # Sonnet 5 carries an introductory rate of $2/$10 through 31 August 2026.
    # The standing rate is recorded instead, because a plan priced at a rate
    # that expires inside the window it covers is a plan that quietly goes over.
    ("anthropic", "claude-opus-5"): _anthropic("claude-opus-5", 5.0, 25.0),
    ("anthropic", "claude-sonnet-5"): _anthropic("claude-sonnet-5", 3.0, 15.0),
    ("anthropic", "claude-haiku-4-5"): _anthropic("claude-haiku-4-5", 1.0, 5.0),
}


def price_for(provider: str, model: str) -> Price | None:
    """The price of a model, or None when we have not read one for it.

    None is a supported answer. A model whose price has not been checked gets
    "no published price on file" rather than the price of its nearest relative,
    because the nearest relative is where a fifteen-fold error comes from:
    `sonar` and `sonar-pro` differ by that much on output tokens.
    """
    return PRICES.get((provider, model.split("/")[-1]))


@dataclass(frozen=True, slots=True)
class Cost:
    """What a set of calls cost, and how firmly that is known.

    `low` and `high` are equal when the provider reported the amount itself.
    `measured` says which of those two worlds this is, so a caller never has to
    infer it from the width of the band.
    """

    low_usd: float
    high_usd: float
    measured: bool
    basis: str

    @property
    def exact(self) -> bool:
        return self.low_usd == self.high_usd

    def as_text(self) -> str:
        if self.exact:
            return f"${self.low_usd:.6f} ({self.basis})"
        return f"${self.low_usd:.6f} to ${self.high_usd:.6f} ({self.basis})"


def estimate(price: Price, *, input_tokens: int, output_tokens: int, fee_units: int = 1) -> Cost:
    """Token cost plus the fee band, from the published rates.

    `fee_units` counts whatever `price.fee_unit` names, so it is the number of
    calls for a provider that bills per request and the number of searches for
    one that bills per search. The caller states it rather than having it
    inferred from the call count, because on a per-search price those two are
    the same number only by accident.

    Both token counts are required and must be known. Passing zero for a count
    nobody measured produces a figure that looks like an invoice and is missing
    a term, so an unknown count is refused here and priced by `fees` instead,
    which says out loud that it is a floor.
    """
    if input_tokens is None or output_tokens is None:
        raise ValueError(
            "estimate needs both token counts; an unmeasured call has no token cost to add, "
            "so use fees() and let the result say it is a floor"
        )
    tokens = (input_tokens * price.input_per_mtok_usd + output_tokens * price.output_per_mtok_usd) / MILLION
    low = tokens + fee_units * price.fee_per_k_low_usd / 1000
    high = tokens + fee_units * price.fee_per_k_high_usd / 1000
    return Cost(low_usd=low, high_usd=high, measured=False, basis=f"published rates, {price.provenance()}")


def fees(price: Price, fee_units: int = 1) -> Cost:
    """What the calls cost before a single token is counted.

    Used when nothing has been metered yet. It is the same arithmetic as
    `estimate` with the token term dropped, and the only difference that
    matters is the label: this result is a floor, and a floor presented as an
    estimate is how a quote turns into a surprise.

    For a search-grounded model the floor is most of the bill. At the published
    rates one `sonar` call is half a cent to over a cent in fees and a small
    fraction of that in tokens, which is why the missing term is not the one
    that decides whether a measurement is affordable.
    """
    return Cost(
        low_usd=fee_units * price.fee_per_k_low_usd / 1000,
        high_usd=fee_units * price.fee_per_k_high_usd / 1000,
        measured=False,
        basis=f"{price.fee_unit} fees only, no call metered yet; {price.provenance()}",
    )


def reported(amount_usd: float) -> Cost:
    """The provider stated the amount. No band, no arithmetic of ours."""
    return Cost(low_usd=amount_usd, high_usd=amount_usd, measured=True, basis="reported by the provider")
