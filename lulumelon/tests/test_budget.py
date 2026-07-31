"""What a spending guard promises, stated as the overruns it must not allow.

Every test here is about a way this could spend more than it was given while
still reporting that it stayed inside: a call priced at zero because nobody
metered it, a fee counted once on a provider that charges per search, or a
ceiling checked after the money was already gone.
"""

from __future__ import annotations

import pytest

from lulumelon.collect import (
    UNMEASURED_INPUT_TOKENS,
    UNMEASURED_OUTPUT_TOKENS,
    Answer,
    Budget,
    Usage,
)
from lulumelon.prices import price_for

OPUS = price_for("anthropic", "claude-opus-5")  # $5/$25 per Mtok, $10 per 1k searches
SONAR = price_for("perplexity", "sonar")  # $1/$1 per Mtok, $5 to $12 per 1k requests

#: One search on the per-search price, in dollars.
SEARCH_FEE = 0.01
#: The per-request fee this charges at, which is the top of the published band.
REQUEST_FEE = 0.012


def answered(**usage) -> Answer:
    """A reply that came back, carrying only what the provider actually said."""
    return Answer(
        text="Marx leads.",
        model="claude-opus-5",
        surface="api",
        latency_ms=1100,
        usage=Usage(**usage),
    )


def failed() -> Answer:
    return Answer(
        text="",
        model="unknown",
        surface="api",
        latency_ms=90_000,
        status="error",
        error="timeout after 90s",
    )


def test_a_ceiling_of_nothing_is_refused():
    # a budget object that permits everything is worse than no budget object,
    # because the caller believes there is one.
    for limit in (0.0, -0.01):
        with pytest.raises(ValueError, match="buys nothing"):
            Budget(price=OPUS, limit_usd=limit)


def test_a_call_that_runs_no_search_is_not_the_call_being_priced():
    with pytest.raises(ValueError, match="at least one fee"):
        Budget(price=OPUS, limit_usd=1.0, max_searches=0)


def test_the_guess_is_used_until_the_round_has_measured_itself():
    b = Budget(price=OPUS, limit_usd=1.0, max_searches=1)
    assert b.measured_rate is None

    guess = (
        UNMEASURED_INPUT_TOKENS * OPUS.input_per_mtok_usd
        + UNMEASURED_OUTPUT_TOKENS * OPUS.output_per_mtok_usd
    ) / 1_000_000 + SEARCH_FEE
    assert b.next_call_ceiling_usd() == pytest.approx(guess)
    assert b.next_call_ceiling_usd() == pytest.approx(0.08)

    # 1000 in and 200 out is $0.005 + $0.005 of tokens, plus one search.
    b.charge(answered(input_tokens=1000, output_tokens=200, searches=1))
    assert b.measured_rate == (1000, 200)
    assert b.next_call_ceiling_usd() == pytest.approx(0.02)


def test_the_measured_rate_is_this_round_s_own_average():
    b = Budget(price=OPUS, limit_usd=1.0, max_searches=1)
    b.charge(answered(input_tokens=1000, output_tokens=200, searches=1))
    b.charge(answered(input_tokens=3000, output_tokens=400, searches=1))

    assert b.metered_calls == 2
    assert b.measured_rate == (2000, 300)


def test_the_fee_term_stays_at_the_cap_after_the_tokens_are_measured():
    # tokens are what the last calls did; searches are what the next call may
    # choose to do. Measuring the first out of history does not make the second
    # knowable, and the cap is the only figure that cannot be exceeded.
    b = Budget(price=OPUS, limit_usd=1.0, max_searches=3)
    b.charge(answered(input_tokens=1000, output_tokens=200, searches=1))

    assert b.next_call_ceiling_usd() == pytest.approx(0.01 + 3 * SEARCH_FEE)


def test_a_per_search_price_charges_the_whole_cap_when_the_count_is_missing():
    # the fee is charged per search and the response is the only place the
    # count exists. Absent it, the call is charged for every search it was
    # allowed to run.
    blind = Budget(price=OPUS, limit_usd=1.0, max_searches=3)
    cost = blind.charge(answered(input_tokens=1000, output_tokens=200))
    assert cost == pytest.approx(0.01 + 3 * SEARCH_FEE)

    told = Budget(price=OPUS, limit_usd=1.0, max_searches=3)
    assert told.charge(
        answered(input_tokens=1000, output_tokens=200, searches=1)
    ) == pytest.approx(0.01 + SEARCH_FEE)


def test_a_per_request_price_charges_one_fee_whatever_the_searches_were():
    # the same nine searches cost nine fees on one provider and one on the
    # other. Reading `searches` here would multiply a bill that is not per
    # search.
    busy = Budget(price=SONAR, limit_usd=1.0, max_searches=3)
    quiet = Budget(price=SONAR, limit_usd=1.0, max_searches=3)

    with_count = busy.charge(answered(input_tokens=1000, output_tokens=200, searches=9))
    without_count = quiet.charge(answered(input_tokens=1000, output_tokens=200))

    assert with_count == pytest.approx(0.0012 + REQUEST_FEE)
    assert without_count == pytest.approx(with_count)


def test_a_call_that_failed_is_charged_nothing():
    # the one zero here that is a measurement rather than an absence: the
    # provider states that a search which errors is not billed.
    b = Budget(price=OPUS, limit_usd=1.0, max_searches=3)
    assert b.charge(failed()) == 0.0
    assert b.spent_usd == 0.0
    assert b.metered_calls == 0
    assert b.unmetered_calls == 0


def test_a_call_nobody_metered_is_charged_at_its_ceiling():
    # the failure this exists to prevent: a provider stops reporting usage, the
    # guard reads the silence as no spend, and the round runs until the account
    # refuses it.
    b = Budget(price=OPUS, limit_usd=1.0, max_searches=3)
    ceiling = b.next_call_ceiling_usd()

    cost = b.charge(answered())

    assert cost == pytest.approx(ceiling)
    assert cost == pytest.approx(0.10)
    assert b.unmetered_calls == 1
    assert b.metered_calls == 0
    assert b.measured_rate is None, "a call nobody metered teaches the rate nothing"


def test_half_a_usage_block_is_not_a_measurement():
    # one count present and the other missing is the shape a renamed field
    # arrives in. Pricing the half that came through would charge the tokens
    # nobody reported at zero.
    b = Budget(price=OPUS, limit_usd=1.0, max_searches=1)
    cost = b.charge(answered(input_tokens=1000, searches=1))

    assert b.unmetered_calls == 1
    assert b.metered_calls == 0
    assert cost == pytest.approx(0.07 + SEARCH_FEE)


def test_remaining_never_reads_below_zero():
    # a call already made cannot be given back, so overspending is possible and
    # is not softened into a negative balance nobody is owed.
    b = Budget(price=OPUS, limit_usd=0.05, max_searches=3)
    b.charge(answered())

    assert b.spent_usd == pytest.approx(0.10)
    assert b.remaining_usd == 0.0
    assert not b.can_afford_another()


def test_the_last_call_that_fits_is_made_and_the_next_one_is_not():
    # the check is asked before the call, so a budget of exactly one ceiling
    # buys exactly one call rather than one and an overrun.
    b = Budget(price=OPUS, limit_usd=0.08, max_searches=1)
    assert b.can_afford_another()

    b.charge(answered())

    assert b.spent_usd == pytest.approx(0.08)
    assert b.remaining_usd == pytest.approx(0.0)
    assert not b.can_afford_another()


def test_a_metered_round_gets_more_calls_than_its_first_ceiling_allowed_for():
    # the guess is deliberately larger than a small call, so the first check is
    # the strictest one the round ever faces. $0.25 at $0.02 a call is twelve,
    # not the three the opening ceiling would have implied.
    b = Budget(price=OPUS, limit_usd=0.25, max_searches=1)
    made = 0
    while b.can_afford_another():
        b.charge(answered(input_tokens=1000, output_tokens=200, searches=1))
        made += 1

    assert made == 12
    assert b.spent_usd == pytest.approx(0.24)
    assert b.remaining_usd == pytest.approx(0.01)


def test_the_ceiling_sentence_is_printed_only_when_something_was_unmetered():
    metered = Budget(price=OPUS, limit_usd=1.0, max_searches=1)
    metered.charge(answered(input_tokens=1000, output_tokens=200, searches=1))
    text = metered.as_text()

    assert "ceiling" not in text, "a fully metered round has nothing to disclaim"
    assert "1 call the provider metered" in text
    assert "measured 1000 in / 200 out tokens per call" in text
    assert "$0.0200 of $1.00" in text

    blind = Budget(price=OPUS, limit_usd=1.0, max_searches=1)
    blind.charge(answered())
    blind.charge(answered())

    assert "0 calls the provider metered, 2 it did not, charged at the ceiling" in blind.as_text()
    assert "tokens per call" not in blind.as_text(), "no metered call, no rate to quote"
