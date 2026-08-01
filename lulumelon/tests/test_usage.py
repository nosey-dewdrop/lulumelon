"""What a round cost, stated as the ways that figure must not be produced.

The meter is the part of this library a buyer checks against their own invoice,
so every test here is about a number that would be wrong in a way nobody
noticed: a call priced twice, a failure priced at all, a floor presented as a
total, or an invoice computed from a file that does not verify.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from lulumelon.cli import Console, usage as run_usage
from lulumelon.collect import UNSEARCHED_SURFACE, Ledger, Record
from lulumelon.prices import price_for
from lulumelon.usage import spend_of, token_rate

SONAR = price_for("perplexity", "sonar")
SID = "marx__perplexity__api__20260731T120000Z__0001"


def rec(**over) -> Record:
    base = dict(
        snapshot_id=SID,
        seq=0,
        prompt_id="p1",
        repeat=0,
        engine="perplexity",
        surface="api",
        model="sonar",
        asked_at="2026-07-31T12:00:00Z",
        status="ok",
        latency_ms=1100,
        answer_text="Marx does.",
        brands=("marx",),
        citations=(),
        provider="perplexity",
    )
    base.update(over)
    return Record(**base)


def metered(**over) -> Record:
    return rec(input_tokens=118, output_tokens=64, search_context="low", reported_cost_usd=0.005182, **over)


def counted(input_tokens: int = 120, output_tokens: int = 70, **over) -> Record:
    return rec(input_tokens=input_tokens, output_tokens=output_tokens, **over)


def silent(**over) -> Record:
    return rec(**over)


def failed(**over) -> Record:
    return rec(status="error", answer_text="", brands=(), error="timeout after 45s", model="unknown", **over)


class Recorder:
    def __init__(self) -> None:
        self.out, self.err = io.StringIO(), io.StringIO()
        self.console = Console(out=self.out, err=self.err)

    @property
    def text(self) -> str:
        return self.out.getvalue() + self.err.getvalue()


# -- the three bases stay apart ---------------------------------------------


def test_a_metered_round_carries_no_band_at_all():
    spend = spend_of([metered(), metered(), metered()])
    assert spend.exact
    assert spend.low_usd == spend.high_usd == pytest.approx(3 * 0.005182)
    assert "every call metered" in spend.as_text()


def test_a_metered_call_is_not_priced_a_second_time_from_the_table():
    """The provider already charged for it. Adding our rate double-bills."""
    only_metered = spend_of([metered(), metered()])
    assert only_metered.by_model == (), "a metered call opens no priced bucket at all"
    assert only_metered.low_usd == pytest.approx(2 * 0.005182)


def test_calls_that_reported_tokens_are_priced_from_their_own_tokens():
    spend = spend_of([counted(), counted()])
    assert spend.counted == 2
    # 240 input + 140 output at $1/M each, plus two request fees at $5-12/1k.
    assert spend.low_usd == pytest.approx((240 + 140) / 1_000_000 + 2 * 0.005)
    assert spend.high_usd == pytest.approx((240 + 140) / 1_000_000 + 2 * 0.012)


def test_a_call_that_reported_nothing_is_a_floor_not_an_estimate():
    spend = spend_of([silent()])
    assert spend.silent == 1
    floor = spend.by_model[0].floor_cost
    assert floor is not None
    assert "no call metered yet" in floor.basis
    assert "a floor for 1 call" in spend.as_text()


def test_a_failed_call_is_counted_and_never_priced():
    spend = spend_of([metered(), failed()])
    assert (spend.answered, spend.failed) == (1, 1)
    assert spend.low_usd == pytest.approx(0.005182)
    assert "does not say whether a rejected call is billed" in spend.as_text()


def test_a_mixed_round_says_how_much_of_it_is_exact():
    spend = spend_of([metered(), counted(), silent()])
    assert not spend.exact
    assert "1 of 3 priced calls metered" in spend.as_text()


def test_records_from_before_usage_existed_are_a_separate_category(tmp_path):
    """"This build did not collect it" is not "the provider said nothing"."""
    old = rec(v=1)
    spend = spend_of([old, silent()])
    assert spend.unrecorded == 1
    assert spend.silent == 1
    assert "before this build recorded usage" in spend.as_text()


def test_a_model_with_no_published_price_prices_nothing():
    unknown = dict(model="sonar-deep-research")
    spend = spend_of([counted(**unknown), silent(**unknown)])
    assert spend.by_model[0].price is None
    assert spend.by_model[0].counted_cost is None and spend.by_model[0].floor_cost is None
    assert spend.low_usd == 0.0
    assert spend.unpriced == 2
    assert "no published price on file" in spend.as_text()


def test_an_empty_ledger_is_not_a_free_one():
    spend = spend_of([])
    assert spend.calls == 0
    assert spend.exact is False, "nothing measured is not the same as nothing spent"


# -- a count nobody reported is not a count of zero -------------------------


def test_a_metered_call_that_reported_no_tokens_reports_no_tokens():
    """The scenario ask.py documents: an amount arrives, the token names moved.

    The old arm coerced both counts with `or 0`, so the screen read

        TOKENS, as the provider reported them
          input   0
          output  0
          reported by 1 of 1 answered call

    Every line of that is false. The provider reported neither count, and it
    was counted as the call that did.
    """
    priced_but_uncounted = rec(reported_cost_usd=0.005182)
    spend = spend_of([priced_but_uncounted])

    assert spend.metered == 1
    assert spend.token_reporters == 0
    text = spend.as_text()
    assert "reported by 0 of 1 answered call" in text
    assert "input   0" not in text and "output  0" not in text
    assert spend.low_usd == pytest.approx(0.005182), "the amount is still the amount"


def test_half_a_token_pair_is_not_a_report():
    """One count without the other cannot be summed into either total."""
    spend = spend_of([rec(input_tokens=118, reported_cost_usd=0.005182)])
    assert spend.token_reporters == 0
    assert spend.input_tokens == 0
    assert "reported by 0 of 1" in spend.as_text()


def test_the_reporters_line_counts_metered_and_counted_calls_alike():
    """Both arms report tokens, so both arms are behind that number."""
    spend = spend_of([metered(), counted(), silent(), rec(v=1)])
    assert spend.token_reporters == 2
    assert "reported by 2 of 3 answered calls" in spend.as_text()


# -- what a per-call figure is allowed to divide by -------------------------


def test_a_per_call_figure_divides_by_the_calls_that_carry_a_cost():
    """The exact arithmetic that made this wrong, from the audit that found it.

    One metered call at $0.005182 beside three rows written before usage was
    recorded. Divided by `answered` the screen printed $0.001295 a call, four
    times under, on the same screen that says those three rows are not counted.
    """
    spend = spend_of([metered(), rec(v=1), rec(v=1), rec(v=1)])
    assert (spend.answered, spend.unrecorded, spend.priced) == (4, 3, 1)
    assert spend.per_call_low_usd == pytest.approx(0.005182)
    assert spend.low_usd / spend.answered == pytest.approx(0.0012955)


def test_a_round_nobody_metered_is_not_reported_as_a_free_one():
    """Every row predates usage recording, so the cost is unknown, not zero."""
    spend = spend_of([rec(v=1), rec(v=1)])
    assert (spend.answered, spend.priced) == (2, 0)
    text = spend.as_text()
    assert "unknown rather than nothing" in text
    assert "total  $0.000000" not in text, "an unmeasured round must not print a total"


def test_a_silent_call_stays_in_the_divisor_because_it_carries_a_request_fee():
    """`silent` is missing tokens, not missing from the bill."""
    spend = spend_of([metered(), silent()])
    assert spend.priced == 2
    assert spend.per_call_low_usd == pytest.approx((0.005182 + 0.005) / 2)


def test_exactness_is_about_the_priced_calls_not_the_answered_ones():
    """Old rows carry no cost, so they cannot make a metered round inexact."""
    assert spend_of([metered(), metered(), rec(v=1)]).exact


# -- every call is priced at the rate of the model that answered it ---------


def test_a_call_is_priced_at_the_rate_of_the_model_that_answered_it():
    """The exact figures that made this a bug rather than a preference.

    Ten `sonar-pro` calls at 1200 in / 800 out each. Priced at `sonar-pro`'s
    published rates that is $0.216000 to $0.296000. Priced at `sonar`'s, which
    is what a round takes when the rate comes from a flag instead of from the
    record, it is $0.070000 to $0.140000: three times under at the low end and
    twice under at the high end, printed under a heading that says COST.
    """
    spend = spend_of([counted(1200, 800, model="sonar-pro") for _ in range(10)])

    assert spend.low_usd == pytest.approx(0.216)
    assert spend.high_usd == pytest.approx(0.296)
    assert spend.by_model[0].price.model == "sonar-pro"

    at_the_wrong_rate_low = (12_000 * 1.0 + 8_000 * 1.0) / 1_000_000 + 10 * 0.005
    at_the_wrong_rate_high = (12_000 * 1.0 + 8_000 * 1.0) / 1_000_000 + 10 * 0.012
    assert (at_the_wrong_rate_low, at_the_wrong_rate_high) == pytest.approx((0.07, 0.14))
    assert spend.low_usd / at_the_wrong_rate_low == pytest.approx(3.0857, rel=1e-3)
    assert spend.high_usd / at_the_wrong_rate_high == pytest.approx(2.1143, rel=1e-3)


def test_a_round_that_used_two_models_keeps_their_rates_apart():
    """One bucket per model, each at its own price, never one blended rate."""
    spend = spend_of(
        [counted(1000, 500, model="sonar"), counted(1000, 500, model="sonar-pro")]
    )
    assert [m.model for m in spend.by_model] == ["sonar", "sonar-pro"]

    cheap, dear = spend.by_model
    assert cheap.counted_cost.low_usd == pytest.approx(1500 / 1_000_000 + 0.005)
    assert dear.counted_cost.low_usd == pytest.approx((3000 + 7500) / 1_000_000 + 0.006)
    assert spend.low_usd == pytest.approx(cheap.low_usd + dear.low_usd)


def test_an_unpriced_model_never_borrows_the_rate_of_another_one():
    """The failure this replaces was silent, which is what made it expensive.

    `sonar-deep-research` has no row in the price table. Priced from a flag it
    took whichever model the flag named and produced a confident figure under
    a live source link. Here it is counted, named, and in no total.
    """
    spend = spend_of([counted(2000, 1000, model="sonar-deep-research") for _ in range(4)])
    assert spend.counted == 4
    assert spend.unpriced == 4
    assert spend.low_usd == 0.0 and spend.high_usd == 0.0

    text = spend.as_text()
    assert "perplexity/sonar-deep-research" in text
    assert "no published price on file" in text
    assert "4 of the answered calls could not be priced" in text


def test_the_screen_says_which_model_carried_which_price():
    """A cost the reader cannot attribute to a rate is a cost they must trust."""
    text = spend_of([counted(model="sonar-pro"), silent(model="sonar")]).as_text()
    assert "perplexity/sonar-pro: computed for 1 call" in text
    assert "perplexity/sonar: a floor for 1 call" in text
    assert "docs.perplexity.ai/getting-started/pricing" in text


def test_an_unpriced_model_does_not_take_the_rest_of_the_round_down_with_it():
    """A round is not unpriceable because one of the models in it is."""
    spend = spend_of([counted(model="sonar"), counted(model="sonar-deep-research")])
    assert spend.unpriced == 1
    assert spend.low_usd == pytest.approx(190 / 1_000_000 + 0.005)
    assert "a total for the rest of the round only" in spend.as_text()


# -- the token rate a planner would use -------------------------------------


def test_the_token_rate_is_the_median_of_what_reported_both():
    records = [counted(input_tokens=100, output_tokens=50), counted(input_tokens=120, output_tokens=70),
               counted(input_tokens=900, output_tokens=900), silent(), failed()]
    assert token_rate(records) == (120, 70)


def test_a_round_that_reported_no_tokens_has_no_rate():
    """None, so a planner cannot quietly price a round at zero tokens."""
    assert token_rate([silent(), silent(), failed()]) is None


# -- the command ------------------------------------------------------------


def _round(tmp_path: Path, *records: Record) -> Ledger:
    """One finished round on disk: these calls, then the seal that closes it.

    Sealed rather than left open, because `lulu usage` prices nothing off a
    round that does not verify and an unsealed round no longer does: on disk it
    is the same object as one whose last calls were deleted.
    """
    led = Ledger(tmp_path)
    for record in records:
        led.append(SID, record)
    answered = sum(1 for record in records if record.status == "ok")
    led.seal(SID, asked=len(records), ok=answered, errors=len(records) - answered)
    return led


def test_usage_reports_a_clean_round(tmp_path):
    _round(tmp_path, metered(), counted(), failed())
    rec_out = Recorder()
    assert run_usage(rec_out.console, ledger_dir=tmp_path) == 0
    text = rec_out.text
    assert "chain intact" in text
    assert "3 calls recorded: 2 answered, 1 failed" in text


def test_usage_refuses_to_price_a_doctored_round(tmp_path):
    """An invoice from a file that does not verify is not a cheaper invoice."""
    led = _round(tmp_path, metered(), metered(), metered())
    path = led.path_of(SID)
    lines = path.read_text(encoding="utf-8").splitlines()
    line = json.loads(lines[1])
    line["reported_cost_usd"] = 0.000001
    lines[1] = json.dumps(line, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    rec_out = Recorder()
    assert run_usage(rec_out.console, ledger_dir=tmp_path) == 1
    text = rec_out.text
    assert "CHAIN BROKEN" in text
    assert "No cost is computed from it" in text
    assert "COST" not in text, "a broken round must not print a cost section"
    assert "$" not in text, "and must not print a figure of any kind"


def test_usage_on_an_empty_directory_says_nothing_was_spent(tmp_path):
    rec_out = Recorder()
    assert run_usage(rec_out.console, ledger_dir=tmp_path) == 0
    assert "nothing has been spent" in rec_out.text.lower()


# -- a dated model id is the model, not a relative of it --------------------


def test_a_dated_snapshot_is_priced_as_the_model_it_is_a_snapshot_of():
    """The response names a snapshot; the price table names the model.

    `claude-haiku-4-5` answers as `claude-haiku-4-5-20251001`, and the record
    keeps what answered. Without resolving the date the first call this repo
    ever billed would be recorded honestly and then reported as having no
    published price. Both ids must reach the same published rate, because they
    are one row on the provider's own page.
    """
    alias = price_for("anthropic", "claude-haiku-4-5")
    dated = price_for("anthropic", "claude-haiku-4-5-20251001")
    assert alias is not None
    assert dated == alias


def test_only_the_date_is_stripped_and_never_a_model_name():
    """The rule resolves a snapshot to its own model, or to nothing at all.

    A name that is not in the table stays unpriced. `sonar-pro` keeps its own
    rate and cannot decay into `sonar`, which is the fifteen-fold error this
    file exists to refuse.
    """
    assert price_for("anthropic", "claude-haiku-4-5-2025100") is None, "not a date"
    assert price_for("anthropic", "claude-opus-9-9-20251001") is None, "no such model"
    assert price_for("perplexity", "sonar-pro").model == "sonar-pro"


def test_a_dated_model_is_priced_at_its_own_rate_through_a_whole_round():
    """The path a recorded call takes, on the figures of the one real call.

    10046 input tokens and 91 output, which is what the first billed call in
    this repo reported, at $1 and $5 per million plus one search fee at $10 per
    thousand: $0.020501. That is what the provider actually charged, so this
    arithmetic is checked against a bill rather than against itself.

    It agrees because that call ran exactly one search, and the record says so.
    """
    spend = spend_of(
        [counted(10046, 91, model="claude-haiku-4-5-20251001", provider="anthropic", searches=1)]
    )
    assert spend.unpriced == 0
    assert spend.low_usd == pytest.approx(0.020501)


# -- a fee charged per search is multiplied by the searches -----------------

HAIKU = dict(model="claude-haiku-4-5", provider="anthropic")


def test_a_call_that_searched_three_times_pays_three_fees():
    """The figure the ledger could not reconstruct until v3 stored the count.

    One call, 1000 in and 200 out at $1 and $5 per million is $0.002 of tokens.
    The fee is $10 per thousand searches and this call ran three, so the bill
    is $0.032 rather than the $0.012 a per-call fee would have printed: nearly
    three times under, on the line headed COST.
    """
    spend = spend_of([counted(1000, 200, searches=3, **HAIKU)])
    assert spend.by_model[0].fee_units == 3
    assert spend.low_usd == pytest.approx(0.002 + 3 * 0.01)
    assert spend.low_usd / (0.002 + 0.01) == pytest.approx(2.6667, rel=1e-3)


def test_the_ledger_and_the_budget_guard_agree_about_one_round(tmp_path):
    """The two money paths, run over the same calls, to the same total.

    One of them charges while the round is running and one prices it off the
    file afterwards, and until the search count was written down they could not
    agree: the guard multiplied the fee by the searches each call reported and
    the ledger had no way to know there had been more than one. A meter that
    disagrees with itself by a factor of the number of searches is not a meter.
    """
    from lulumelon.collect import Brand, Budget, FakeProvider, Ledger, Prompt, Usage, run_round

    led = Ledger(tmp_path)
    budget = Budget(price=price_for("anthropic", "claude-haiku-4-5"), limit_usd=5.0, max_searches=3)
    result = run_round(
        ledger=led,
        provider=FakeProvider(
            name="anthropic",
            model="claude-haiku-4-5",
            script={"q": ("Marx does.",)},
            usage=Usage(input_tokens=1000, output_tokens=200, searches=3),
        ),
        prompts=[Prompt(id="p1", text="q")],
        brands=[Brand(name="marx", aliases=())],
        k=4,
        subject="marx",
        clock=lambda: "2026-08-01T02:00:00Z",
        budget=budget,
    )

    spend = spend_of(led.read(result.snapshot_id))
    assert spend.by_model[0].fee_units == 12, "four calls, three searches each"
    assert spend.low_usd == pytest.approx(budget.spent_usd)
    assert spend.low_usd == pytest.approx(4 * (0.002 + 0.03))


def test_a_call_that_did_not_say_how_often_it_searched_is_charged_one_and_says_so():
    """One search is the least it can have been, and a floor is labelled one.

    Charging the search cap instead would be the guard's arithmetic, which is
    right while money can still be stopped and wrong afterwards: this screen
    reports what was billed, and inventing searches nobody reported inflates a
    customer's own invoice back at them.
    """
    spend = spend_of([counted(1000, 200, **HAIKU), counted(1000, 200, searches=2, **HAIKU)])
    bucket = spend.by_model[0]
    assert (bucket.fee_units, bucket.unreported_searches) == (3, 1)
    assert spend.low_usd == pytest.approx(0.004 + 3 * 0.01)

    text = spend.as_text()
    assert "charged 3 search fees over 2 calls" in text
    assert "1 did not report a search count" in text
    assert "which is a floor" in text


def test_the_arm_that_could_not_search_owes_no_fee_at_all():
    """The floor of one search rests on the call having been able to search.

    These calls were collected with no search tool attached, so the missing
    count is a fact about the request rather than a silence from the provider.
    Charged one each they would owe $0.02 of fees the account was never billed,
    on the screen a buyer checks against their own invoice.
    """
    spend = spend_of(
        [counted(1000, 200, surface=UNSEARCHED_SURFACE, **HAIKU) for _ in range(2)]
    )
    bucket = spend.by_model[0]

    assert (bucket.fee_units, bucket.unreported_searches, bucket.unsearched) == (0, 0, 2)
    assert spend.low_usd == pytest.approx(0.004)
    assert spend.low_usd == spend.high_usd

    text = spend.as_text()
    assert "no search fee over 2 calls" in text
    assert "no search tool attached" in text
    assert "which is a floor" not in text


def test_a_silent_call_that_could_not_search_has_no_floor_to_quote():
    """Nothing is known about what it cost, and $0.000000 is not nothing.

    A call that reported no tokens and could run no search leaves the fee at
    zero and the tokens unknown. Printing the sum as a floor would put a free
    call under a heading that reads COST.
    """
    spend = spend_of([silent(surface=UNSEARCHED_SURFACE, **HAIKU)])
    bucket = spend.by_model[0]

    assert bucket.floor_cost is None
    assert bucket.silent == 1
    assert (spend.unpriceable, spend.priced) == (1, 0)

    text = spend.as_text()
    assert "unknown rather than nothing" in text
    assert "no figure covers 1 call" in text
    assert "$0.000000" not in text, "a round with no known cost is not a free round"


def test_a_fee_charged_per_request_is_not_multiplied_by_anything():
    """The other provider bills once per call however often it looked."""
    spend = spend_of([counted(1000, 500, searches=4), counted(1000, 500, searches=4)])
    assert spend.by_model[0].fee_units == 2, "two calls, two request fees"
    assert spend.low_usd == pytest.approx(3000 / 1_000_000 + 2 * 0.005)
    assert "search fees" not in spend.as_text()
