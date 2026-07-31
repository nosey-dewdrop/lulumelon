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
    spend = spend_of([metered(), metered(), metered()], SONAR)
    assert spend.exact
    assert spend.low_usd == spend.high_usd == pytest.approx(3 * 0.005182)
    assert "every call metered" in spend.as_text()


def test_a_metered_call_is_not_priced_a_second_time_from_the_table():
    """The provider already charged for it. Adding our rate double-bills."""
    only_metered = spend_of([metered(), metered()], SONAR)
    assert only_metered.counted_cost is None
    assert only_metered.low_usd == pytest.approx(2 * 0.005182)


def test_calls_that_reported_tokens_are_priced_from_their_own_tokens():
    spend = spend_of([counted(), counted()], SONAR)
    assert spend.counted == 2
    # 240 input + 140 output at $1/M each, plus two request fees at $5-12/1k.
    assert spend.low_usd == pytest.approx((240 + 140) / 1_000_000 + 2 * 0.005)
    assert spend.high_usd == pytest.approx((240 + 140) / 1_000_000 + 2 * 0.012)


def test_a_call_that_reported_nothing_is_a_floor_not_an_estimate():
    spend = spend_of([silent()], SONAR)
    assert spend.silent == 1
    assert spend.floor_cost is not None
    assert "no call metered yet" in spend.floor_cost.basis
    assert "a floor for 1 call" in spend.as_text()


def test_a_failed_call_is_counted_and_never_priced():
    spend = spend_of([metered(), failed()], SONAR)
    assert (spend.answered, spend.failed) == (1, 1)
    assert spend.low_usd == pytest.approx(0.005182)
    assert "does not say whether a rejected call is billed" in spend.as_text()


def test_a_mixed_round_says_how_much_of_it_is_exact():
    spend = spend_of([metered(), counted(), silent()], SONAR)
    assert not spend.exact
    assert "1 of 3 answered calls metered" in spend.as_text()


def test_records_from_before_usage_existed_are_a_separate_category(tmp_path):
    """"This build did not collect it" is not "the provider said nothing"."""
    old = rec(v=1)
    spend = spend_of([old, silent()], SONAR)
    assert spend.unrecorded == 1
    assert spend.silent == 1
    assert "before this build recorded usage" in spend.as_text()


def test_a_model_with_no_published_price_prices_nothing():
    spend = spend_of([counted(), silent()], None)
    assert spend.counted_cost is None and spend.floor_cost is None
    assert spend.low_usd == 0.0
    assert "no published price on file" in spend.as_text()


def test_an_empty_ledger_is_not_a_free_one():
    spend = spend_of([], SONAR)
    assert spend.calls == 0
    assert spend.exact is False, "nothing measured is not the same as nothing spent"


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
