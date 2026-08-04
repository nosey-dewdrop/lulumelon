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
    Answer,
    Budget,
    Usage,
    token_ceiling,
)
from lulumelon.prices import price_for

OPUS = price_for("anthropic", "claude-opus-5")  # $5/$25 per Mtok, $10 per 1k searches
SONAR = price_for("perplexity", "sonar")  # $1/$1 per Mtok, $5 to $12 per 1k requests

#: The cap the calls in these rounds carry. Every round states one, because a
#: budget with no cap to price is refused: what a call may write back is not a
#: thing to be guessed at, it is a number the request carries.
CAP = 400

#: One search on the per-search price, in dollars.
SEARCH_FEE = 0.01
#: The per-request fee this charges at, which is the top of the published band.
REQUEST_FEE = 0.012


def answered(**usage) -> Answer:
    """A reply that came back, carrying only what the provider actually said."""
    return Answer(
        text="Ornek leads.",
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
            Budget(price=OPUS, limit_usd=limit, max_output_tokens=CAP)


def test_a_call_that_runs_no_search_is_not_the_call_being_priced():
    with pytest.raises(ValueError, match="at least one fee"):
        Budget(price=OPUS, limit_usd=1.0, max_searches=0, max_output_tokens=CAP)


def test_the_input_guess_is_used_until_the_round_has_measured_itself():
    b = Budget(price=OPUS, limit_usd=1.0, max_searches=1, max_output_tokens=CAP)
    assert b.measured_rate is None

    guess = (
        UNMEASURED_INPUT_TOKENS * OPUS.input_per_mtok_usd + CAP * OPUS.output_per_mtok_usd
    ) / 1_000_000 + SEARCH_FEE
    assert b.next_call_ceiling_usd() == pytest.approx(guess)
    assert b.next_call_ceiling_usd() == pytest.approx(0.08)

    # 1000 in is $0.005, and the output term stays at the cap: $0.01.
    b.charge(answered(input_tokens=1000, output_tokens=200, searches=1))
    assert b.measured_rate == (1000, 200)
    assert b.next_call_ceiling_usd() == pytest.approx(0.005 + 0.01 + SEARCH_FEE)


def test_the_output_term_of_a_ceiling_never_drops_to_what_the_round_wrote():
    """A round that wrote 200 tokens is not a round whose next call cannot write 400.

    The input half of a ceiling is a guess about a prompt nobody has built yet,
    so a round replaces it with its own measured rate. The output half is not a
    guess at all: it is the cap the request carries, the provider stops there,
    and nothing the round has already written lowers it. Averaging it is how a
    guard came to print $0.0440 as the most one call could cost and pay
    $0.0467 for the next one.
    """
    b = Budget(price=OPUS, limit_usd=1.0, max_searches=1, max_output_tokens=CAP)
    for _ in range(5):
        b.charge(answered(input_tokens=1000, output_tokens=1, searches=1))

    assert b.measured_rate == (1000, 1)
    assert b.next_call_ceiling_usd() == pytest.approx(0.005 + 0.01 + SEARCH_FEE)


def test_a_call_costs_no_more_than_the_ceiling_printed_for_it():
    """The whole promise of this class, in the numbers that broke it.

    A proposing call was allowed 1,024 output tokens by the request layer and
    priced at 400 by the guard. The round printed $0.0440 as the most one call
    could cost, the call came back having consumed 11,574 in and exactly its
    1,024 out, and the invoice said $0.0467. Both figures were correct about a
    call that was not the one being made.
    """
    haiku = price_for("anthropic", "claude-haiku-4-5")
    b = Budget(price=haiku, limit_usd=0.05, max_searches=3, max_output_tokens=1024)

    ceiling = b.next_call_ceiling_usd()
    paid = b.charge(answered(input_tokens=11_574, output_tokens=1_024))

    assert paid == pytest.approx(0.046694)
    assert paid <= ceiling


def test_a_caller_holding_the_prompt_is_priced_on_it_rather_than_on_the_guess():
    """The guess describes a prompt nobody has built yet. One that exists is measured.

    A round of one-line questions is what 12,000 input tokens describes. The
    call that opens a draft sends the customer's whole site, and priced at the
    guess it is charged for 12,000 whatever it actually carries: the ceiling
    stops being a ceiling at exactly the size where it starts to matter.
    """
    b = Budget(price=OPUS, limit_usd=1.0, max_searches=1, max_output_tokens=CAP)
    big = 3 * UNMEASURED_INPUT_TOKENS

    assert b.next_call_ceiling_usd(input_tokens=big) > b.next_call_ceiling_usd()
    assert b.next_call_ceiling_usd(input_tokens=big) == pytest.approx(
        (big * OPUS.input_per_mtok_usd + CAP * OPUS.output_per_mtok_usd) / 1_000_000 + SEARCH_FEE
    )


def test_a_prompt_that_exists_is_counted_high_rather_than_low():
    """Three characters to the token, against the three and a half to four latin gets.

    The two ways to be wrong are not symmetric. Counting high refuses a call
    that would have fit and costs nothing; counting low pays for one that did
    not fit and reports the difference afterwards.
    """
    assert token_ceiling("") == 0
    assert token_ceiling("a" * 12) == 4
    assert token_ceiling("a" * 13) == 5, "a part of a token is charged as a whole one"


def test_the_measured_rate_is_this_round_s_own_average():
    b = Budget(price=OPUS, limit_usd=1.0, max_searches=1, max_output_tokens=CAP)
    b.charge(answered(input_tokens=1000, output_tokens=200, searches=1))
    b.charge(answered(input_tokens=3000, output_tokens=400, searches=1))

    assert b.metered_calls == 2
    assert b.measured_rate == (2000, 300)


def test_the_fee_term_stays_at_the_cap_after_the_tokens_are_measured():
    # tokens are what the last calls did; searches are what the next call may
    # choose to do. Measuring the first out of history does not make the second
    # knowable, and the cap is the only figure that cannot be exceeded.
    b = Budget(price=OPUS, limit_usd=1.0, max_searches=3, max_output_tokens=CAP)
    b.charge(answered(input_tokens=1000, output_tokens=200, searches=1))

    assert b.next_call_ceiling_usd() == pytest.approx(0.005 + 0.01 + 3 * SEARCH_FEE)


def test_a_per_search_price_charges_the_whole_cap_when_the_count_is_missing():
    # the fee is charged per search and the response is the only place the
    # count exists. Absent it, the call is charged for every search it was
    # allowed to run.
    blind = Budget(price=OPUS, limit_usd=1.0, max_searches=3, max_output_tokens=CAP)
    cost = blind.charge(answered(input_tokens=1000, output_tokens=200))
    assert cost == pytest.approx(0.01 + 3 * SEARCH_FEE)

    told = Budget(price=OPUS, limit_usd=1.0, max_searches=3, max_output_tokens=CAP)
    assert told.charge(
        answered(input_tokens=1000, output_tokens=200, searches=1)
    ) == pytest.approx(0.01 + SEARCH_FEE)


def test_a_per_request_price_charges_one_fee_whatever_the_searches_were():
    # the same nine searches cost nine fees on one provider and one on the
    # other. Reading `searches` here would multiply a bill that is not per
    # search.
    busy = Budget(price=SONAR, limit_usd=1.0, max_searches=3, max_output_tokens=CAP)
    quiet = Budget(price=SONAR, limit_usd=1.0, max_searches=3, max_output_tokens=CAP)

    with_count = busy.charge(answered(input_tokens=1000, output_tokens=200, searches=9))
    without_count = quiet.charge(answered(input_tokens=1000, output_tokens=200))

    assert with_count == pytest.approx(0.0012 + REQUEST_FEE)
    assert without_count == pytest.approx(with_count)


def test_the_arm_that_cannot_search_is_charged_no_search_fee():
    """The fee is per search, and this arm was never handed the tool.

    Charged at the cap the way an unmetered call is, a 50 call round would
    reserve $1.50 of fees that cannot be incurred, stop a third of the way
    through, and report the rest as a budget it never spent.
    """
    b = Budget(price=OPUS, limit_usd=1.0, max_searches=3, can_search=False, max_output_tokens=CAP)
    tokens_only = (
        UNMEASURED_INPUT_TOKENS * OPUS.input_per_mtok_usd + CAP * OPUS.output_per_mtok_usd
    ) / 1_000_000

    assert b.next_call_ceiling_usd() == pytest.approx(tokens_only)
    assert b.next_call_ceiling_usd() == pytest.approx(0.07)
    assert b.charge(answered(input_tokens=1000, output_tokens=200)) == pytest.approx(0.01)


def test_one_call_sent_without_the_tool_pays_no_fee_inside_a_searching_round():
    """The round searches; this one request does not carry the tool.

    The fee is owed per search and a request sent without the tool runs none,
    so a round that charged its cap here would reserve money it cannot spend on
    a call it can see the shape of. It is stated by the caller for the same
    reason the arm is: the guard is asked before the call exists.
    """
    b = Budget(price=OPUS, limit_usd=1.0, max_searches=3, max_output_tokens=CAP)
    tokens_only = (
        UNMEASURED_INPUT_TOKENS * OPUS.input_per_mtok_usd + CAP * OPUS.output_per_mtok_usd
    ) / 1_000_000

    assert b.next_call_ceiling_usd(searches=0) == pytest.approx(tokens_only)
    assert b.next_call_ceiling_usd() == pytest.approx(tokens_only + 3 * SEARCH_FEE)
    assert b.charge(answered(input_tokens=1000, output_tokens=200), searches=0) == pytest.approx(
        0.01
    )


def test_a_search_the_provider_reports_anyway_is_charged_anyway():
    """What the provider says it did outranks what the request said it may do.

    The zero above is a fact about a request we sent, and this is the case
    where that fact turns out to be wrong. A guard that trusted its own
    argument over the response would under-count exactly when it is wrong about
    the arm it is guarding.
    """
    b = Budget(price=OPUS, limit_usd=1.0, max_searches=3, can_search=False, max_output_tokens=CAP)
    assert b.charge(
        answered(input_tokens=1000, output_tokens=200, searches=2)
    ) == pytest.approx(0.01 + 2 * SEARCH_FEE)


def test_a_cap_is_not_required_on_an_arm_that_cannot_search():
    """The cap bounds a fee, and there is no fee here to bound."""
    b = Budget(price=OPUS, limit_usd=1.0, max_searches=0, can_search=False, max_output_tokens=CAP)
    assert b.next_call_ceiling_usd() == pytest.approx(0.07)


def test_an_unmetered_call_on_the_unsearched_arm_is_still_charged_at_its_ceiling():
    """Only the fee term is known to be zero; the tokens are still unknown."""
    b = Budget(price=OPUS, limit_usd=1.0, max_searches=3, can_search=False, max_output_tokens=CAP)
    assert b.charge(answered()) == pytest.approx(0.07)
    assert b.unmetered_calls == 1


def test_a_per_request_price_is_unmoved_by_which_arm_it_is_guarding():
    """The other provider bills once per call, and both arms are one call."""
    searching = Budget(price=SONAR, limit_usd=1.0, max_searches=3, max_output_tokens=CAP)
    not_searching = Budget(price=SONAR, limit_usd=1.0, max_searches=3, can_search=False, max_output_tokens=CAP)

    assert not_searching.next_call_ceiling_usd() == pytest.approx(
        searching.next_call_ceiling_usd()
    )
    assert not_searching.charge(answered(input_tokens=1000, output_tokens=200)) == pytest.approx(
        0.0012 + REQUEST_FEE
    )


def test_a_call_that_failed_is_charged_nothing():
    # the one zero here that is a measurement rather than an absence: the
    # provider states that a search which errors is not billed.
    b = Budget(price=OPUS, limit_usd=1.0, max_searches=3, max_output_tokens=CAP)
    assert b.charge(failed()) == 0.0
    assert b.spent_usd == 0.0
    assert b.metered_calls == 0
    assert b.unmetered_calls == 0


def test_a_call_nobody_metered_is_charged_at_its_ceiling():
    # the failure this exists to prevent: a provider stops reporting usage, the
    # guard reads the silence as no spend, and the round runs until the account
    # refuses it.
    b = Budget(price=OPUS, limit_usd=1.0, max_searches=3, max_output_tokens=CAP)
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
    b = Budget(price=OPUS, limit_usd=1.0, max_searches=1, max_output_tokens=CAP)
    cost = b.charge(answered(input_tokens=1000, searches=1))

    assert b.unmetered_calls == 1
    assert b.metered_calls == 0
    assert cost == pytest.approx(0.07 + SEARCH_FEE)


def test_remaining_never_reads_below_zero():
    # a call already made cannot be given back, so overspending is possible and
    # is not softened into a negative balance nobody is owed.
    b = Budget(price=OPUS, limit_usd=0.05, max_searches=3, max_output_tokens=CAP)
    b.charge(answered())

    assert b.spent_usd == pytest.approx(0.10)
    assert b.remaining_usd == 0.0
    assert not b.can_afford_another()


def test_the_last_call_that_fits_is_made_and_the_next_one_is_not():
    # the check is asked before the call, so a budget of exactly one ceiling
    # buys exactly one call rather than one and an overrun.
    b = Budget(price=OPUS, limit_usd=0.08, max_searches=1, max_output_tokens=CAP)
    assert b.can_afford_another()

    b.charge(answered())

    assert b.spent_usd == pytest.approx(0.08)
    assert b.remaining_usd == pytest.approx(0.0)
    assert not b.can_afford_another()


def test_a_metered_round_gets_more_calls_than_its_first_ceiling_allowed_for():
    # the guess is deliberately larger than a small call, so the first check is
    # the strictest one the round ever faces. $0.25 at $0.02 a call is twelve,
    # not the three the opening ceiling would have implied.
    b = Budget(price=OPUS, limit_usd=0.25, max_searches=1, max_output_tokens=CAP)
    made = 0
    while b.can_afford_another():
        b.charge(answered(input_tokens=1000, output_tokens=200, searches=1))
        made += 1

    assert made == 12
    assert b.spent_usd == pytest.approx(0.24)
    assert b.remaining_usd == pytest.approx(0.01)


def test_the_ceiling_sentence_is_printed_only_when_something_was_unmetered():
    metered = Budget(price=OPUS, limit_usd=1.0, max_searches=1, max_output_tokens=CAP)
    metered.charge(answered(input_tokens=1000, output_tokens=200, searches=1))
    text = metered.as_text()

    assert "ceiling" not in text, "a fully metered round has nothing to disclaim"
    assert "1 call the provider metered" in text
    assert "measured 1000 in / 200 out tokens per call" in text
    assert "$0.0200 of $1.00" in text

    blind = Budget(price=OPUS, limit_usd=1.0, max_searches=1, max_output_tokens=CAP)
    blind.charge(answered())
    blind.charge(answered())

    assert "0 calls the provider metered, 2 it did not, charged at the ceiling" in blind.as_text()
    assert "tokens per call" not in blind.as_text(), "no metered call, no rate to quote"
