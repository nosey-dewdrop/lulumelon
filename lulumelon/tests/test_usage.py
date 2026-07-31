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
from lulumelon.collect import Ledger, Record
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
    assert "1 of 3 answered calls metered" in spend.as_text()


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
    led = Ledger(tmp_path)
    for record in records:
        led.append(SID, record)
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
