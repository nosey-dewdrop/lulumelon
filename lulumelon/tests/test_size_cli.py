"""The screen `lulu size` prints, driven end to end.

`plan` answers what a target needs. This answers what a stated design costs,
and it exists because the key is the buyer's: the spend lands on their account,
so every figure here is one they approve before it is made rather than one they
discover afterwards. That makes the screen part of the product rather than a
report on it, and the numbers on it are asserted here.

Three claims get particular attention, because each is one the category around
this tool gets wrong in the direction that flatters it.

**A single draw per prompt cannot carry an interval.** The command has to say
so rather than print a number, because at one run the model's rerun noise and
the prompt-to-prompt spread are the same quantity and no split is identifiable.

**Engines are never pooled.** A second engine buys coverage, not precision, and
a screen that lets a buyer read two engines as twice the sample is selling a
narrower interval than it delivers.

**A total that drops an unpriced engine understates the bill.** It is refused
rather than partially summed, since the buyer is approving a spend.
"""

from __future__ import annotations

import io

import pytest

from lulumelon.cli import Console, size


class Recorder:
    def __init__(self) -> None:
        self.out, self.err = io.StringIO(), io.StringIO()
        self.console = Console(out=self.out, err=self.err)

    @property
    def text(self) -> str:
        return self.out.getvalue() + self.err.getvalue()


def run(**kwargs) -> str:
    rec = Recorder()
    args = dict(prompts=24, runs=5, engines=["perplexity"])
    args.update(kwargs)
    assert size(rec.console, **args) == 0
    return rec.text


def bought(text: str) -> str:
    return text.split("WHAT IT BUYS", 1)[1]


def costs(text: str) -> str:
    return text.split("WHAT IT COSTS", 1)[1].split("WHAT IT BUYS", 1)[0]


# -- the design is echoed back before anything is priced --------------------


def test_the_design_the_buyer_set_is_read_back_to_them():
    text = run(prompts=24, runs=5, engines=["perplexity", "anthropic"])
    assert "24 prompts, asked 5 times each, on 2 engines" in text


def test_the_bill_is_named_as_the_buyer_s_own():
    assert "the key is yours" in run()


# -- one draw per prompt is a reading, not a measurement --------------------


def test_a_single_run_per_prompt_is_refused_an_interval():
    text = bought(run(runs=1))
    assert "nothing that carries an interval" in text
    assert "a reading is not a" in text
    assert "points" not in text, "no half-width may be quoted for an unidentifiable split"


def test_two_runs_per_prompt_is_the_floor_and_it_prints_one():
    text = bought(run(runs=2))
    assert "nothing that carries an interval" not in text
    assert "points" in text


# -- engines are counted apart all the way through --------------------------


def test_a_second_engine_doubles_the_calls_and_leaves_the_interval_alone():
    one = run(engines=["perplexity"])
    two = run(engines=["perplexity", "anthropic"])
    assert "120 calls" in costs(one)
    assert "240 calls" in costs(two)
    assert bought(one).split("icc 0.25")[1] == bought(two).split("icc 0.25")[1]


def test_the_screen_says_engines_are_not_pooled():
    text = run(engines=["perplexity", "anthropic"])
    assert "never" in text and "pooled into one proportion" in text
    assert "coverage across" in text


# -- the price is a floor, and it says so -----------------------------------


def test_an_unmetered_design_is_priced_as_a_floor():
    text = costs(run())
    assert "these are floors" in text


def test_a_model_can_be_named_beside_its_provider():
    text = run(engines=["anthropic:claude-haiku-4-5"])
    assert "anthropic/claude-haiku-4-5" in text


def test_an_engine_this_build_cannot_call_is_refused_by_name():
    with pytest.raises(ValueError, match="unknown provider 'chatgpt'"):
        run(engines=["chatgpt"])


def test_the_refusal_lists_what_this_build_can_call():
    with pytest.raises(ValueError, match="anthropic, perplexity"):
        run(engines=["gemini"])


# -- the inputs a person actually mistypes ----------------------------------


def test_zero_prompts_is_an_error_and_not_a_traceback_shaped_one():
    with pytest.raises(ValueError, match="at least one prompt"):
        run(prompts=0)


def test_zero_runs_is_refused():
    with pytest.raises(ValueError, match="at least one run"):
        run(runs=0)


def test_holding_every_brand_at_once_widens_the_interval():
    one = run(brands=1)
    five = run(brands=5)
    assert _first_width(five) > _first_width(one)


def _first_width(text: str) -> float:
    line = next(ln for ln in bought(text).splitlines() if "icc 0.00" in ln)
    return float(line.split("+/-")[1].split(" points")[0])
