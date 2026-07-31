"""What a call costs, from the provider's own page, with the date it was read.

The claim this library is built to support is that the same judgement can be
reached for a fraction of what it is sold for. A claim about money needs a
meter, and a meter that runs on invented numbers measures nothing.

Two rules hold everything here.

**Every number carries its source and the day it was read.** Prices move. A
figure without a date is a figure nobody can check, and a stale figure quoted
confidently is worse than no figure, because it survives into a pitch.

**A cost is reported as a band unless the provider states the exact amount.**
For a search-grounded model the per-request fee is not a rounding error next to
the tokens: at the published rates one `sonar` call costs half a cent to a cent
in fees and a small fraction of that in tokens. Collapsing that to a single
number would mean choosing a search context size on the user's behalf and then
presenting the guess as an invoice.
"""

from __future__ import annotations

from dataclasses import dataclass

#: A million, kept named because every published price is quoted per million
#: tokens and the conversion is where an order of magnitude gets lost.
MILLION = 1_000_000


@dataclass(frozen=True, slots=True)
class Price:
    """The published price of one model, as written on the provider's page.

    `request_fee_per_k_low` and `_high` bracket the per-request fee across the
    search context sizes the provider bills for. They are equal when a model
    has no such fee.
    """

    provider: str
    model: str
    input_per_mtok_usd: float
    output_per_mtok_usd: float
    request_fee_per_k_low_usd: float
    request_fee_per_k_high_usd: float
    source: str
    read_on: str

    @property
    def has_request_fee(self) -> bool:
        return self.request_fee_per_k_high_usd > 0

    def provenance(self) -> str:
        return f"{self.source}, read {self.read_on}"


PRICES: dict[tuple[str, str], Price] = {
    ("perplexity", "sonar"): Price(
        provider="perplexity",
        model="sonar",
        input_per_mtok_usd=1.0,
        output_per_mtok_usd=1.0,
        request_fee_per_k_low_usd=5.0,
        request_fee_per_k_high_usd=12.0,
        source="https://docs.perplexity.ai/getting-started/pricing",
        read_on="2026-07-31",
    ),
    ("perplexity", "sonar-pro"): Price(
        provider="perplexity",
        model="sonar-pro",
        input_per_mtok_usd=3.0,
        output_per_mtok_usd=15.0,
        request_fee_per_k_low_usd=6.0,
        request_fee_per_k_high_usd=14.0,
        source="https://docs.perplexity.ai/getting-started/pricing",
        read_on="2026-07-31",
    ),
    ("perplexity", "sonar-reasoning-pro"): Price(
        provider="perplexity",
        model="sonar-reasoning-pro",
        input_per_mtok_usd=2.0,
        output_per_mtok_usd=8.0,
        request_fee_per_k_low_usd=6.0,
        request_fee_per_k_high_usd=14.0,
        source="https://docs.perplexity.ai/getting-started/pricing",
        read_on="2026-07-31",
    ),
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


def estimate(price: Price, *, input_tokens: int, output_tokens: int, requests: int = 1) -> Cost:
    """Token cost plus the per-request fee band, from the published rates."""
    tokens = (input_tokens * price.input_per_mtok_usd + output_tokens * price.output_per_mtok_usd) / MILLION
    low = tokens + requests * price.request_fee_per_k_low_usd / 1000
    high = tokens + requests * price.request_fee_per_k_high_usd / 1000
    return Cost(low_usd=low, high_usd=high, measured=False, basis=f"published rates, {price.provenance()}")


def reported(amount_usd: float) -> Cost:
    """The provider stated the amount. No band, no arithmetic of ours."""
    return Cost(low_usd=amount_usd, high_usd=amount_usd, measured=True, basis="reported by the provider")
