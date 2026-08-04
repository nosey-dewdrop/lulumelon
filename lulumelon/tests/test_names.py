"""Counting names nobody declared, stated as the ways a heading becomes a company.

The hard part of this module is not counting. It is that a model writing a
structured answer capitalises its section titles, its table headers and its
adjectives exactly the way it capitalises a company, so the first pass at this
reported `Reliability` and `Key Considerations` beside `Alpha Vantage`.

Two pieces of evidence separate them and both come out of the answers
themselves rather than out of a list kept here. A name turns up inside a
sentence at least once, where a heading never does; and a round that wrote a
word in lower case anywhere has told us it is a word. The tests below are the
cases each of those was written for, and the last one is the round this module
was built to reproduce.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lulumelon.mirror.names import names_in
from lulumelon.mirror.types import Reply

ROOT = Path(__file__).resolve().parents[2]

#: The round the first, throwaway version of this was written against. Not in
#: the repository, because a ledger is a customer's record and this one is
#: ignored by git, so the acceptance test below skips rather than failing on a
#: machine that never collected it.
DISCOVERY = ROOT / "ledger" / "agentfin__anthropic__api_unsearched__20260804T112551Z__0001.jsonl"


def replies(*texts: str, prompt_id: str = "q1") -> tuple[Reply, ...]:
    return tuple(Reply(prompt_id=prompt_id, draw=i, text=t) for i, t in enumerate(texts))


def named(*replies_in: Reply) -> dict[str, int]:
    """Name to the draws it was seen in, flattened, for a test that asserts on both."""
    return {one.name: one.draws for one in names_in(replies_in)}


# -- a heading is not a company ---------------------------------------------


def test_a_section_heading_is_not_a_name():
    """The defect this module was rewritten around, in the shape it arrived in."""
    answer = """## Reliability
Most teams start with Finnhub and stay there.

**Key Considerations**
- Rate limits apply.
"""
    found = named(*replies(answer))
    assert "Finnhub" in found
    assert "Reliability" not in found
    assert "Key Considerations" not in found


def test_a_table_cell_label_is_not_a_name():
    """A table is the other place a model writes labels the way it writes companies."""
    answer = """Here is the comparison you asked for.

| Provider | Cost | Use Case |
|---|---|---|
| Polygon.io | Free | Stocks |

Polygon.io covers equities, and its free tier is generous.
"""
    found = named(*replies(answer))
    assert "Polygon.io" in found
    assert "Use Case" not in found
    assert "Cost" not in found


def test_a_word_the_round_also_wrote_in_lower_case_is_not_a_name():
    """Capitalisation only means something where the round is consistent about it.

    `Enterprise` opens a sentence in one answer and sits in the middle of
    another, which is exactly the pattern a company has. The difference is that
    somewhere in the same round it is also written as an ordinary word.
    """
    found = named(
        *replies(
            "Teams pick Refinitiv when Enterprise support matters.",
            "Most enterprise buyers already pay for one of these.",
        )
    )
    assert "Refinitiv" in found
    assert "Enterprise" not in found


def test_a_name_spelled_like_no_word_survives_a_round_that_never_wrote_it_in_prose():
    """Some names only ever appear in a list, and their spelling is the evidence.

    `3Commas` and `Collective2` were lost by the positional rule alone, because
    twenty four answers listed them and never once put them in a sentence. A
    digit or an interior capital is a mark English does not give an ordinary
    word, so it stands in for the sentence that never came.
    """
    answer = """Platforms worth a look:
- 3Commas
- Collective2
- TradingView
- Considerations
"""
    found = named(*replies(answer))
    assert set(found) >= {"3Commas", "Collective2", "TradingView"}
    assert "Considerations" not in found


# -- what counts as one name ------------------------------------------------


def test_two_names_joined_by_a_conjunction_stay_two_names():
    found = named(*replies("Teams use TradingView and QuantConnect for this."))
    assert set(found) == {"TradingView", "QuantConnect"}


def test_a_year_ending_a_sentence_does_not_join_the_word_after_it():
    found = named(*replies("The market consolidated in 2026. However, Numerai stayed independent."))
    assert "2026. However" not in found
    assert "Numerai" in found


def test_a_single_character_is_not_a_name():
    """`I` sits mid sentence in half the answers a model writes in the first person.

    The cost is a company whose whole name is one letter, and it is worth it:
    the class of false positives that letter brings with it is larger than the
    class of companies named after one.
    """
    found = named(*replies("Teams pair I with Finnhub when they can."))
    assert "I" not in found
    assert "Finnhub" in found


def test_every_name_printed_appears_in_an_answer_character_for_character():
    """The same rule the evidence gate holds a quote to, applied to a count."""
    answers = (
        "Teams use Alpha Vantage and IEX Cloud as the usual starting points.",
        "For crypto, most agents call CoinGecko first.",
    )
    for one in names_in(replies(*answers)):
        assert any(one.name in text for text in answers), one.name


# -- the unit is the question, not the answer -------------------------------


def test_a_name_is_counted_per_question_and_per_draw():
    """Six draws of one question and one draw of six are not the same finding.

    Reported as a single total they read identically, and they are opposite
    observations: one is a question with a settled answer, the other is a name
    the model reaches for whatever it is asked.
    """
    everywhere = names_in(
        replies("Most teams use Finnhub.", "We use Finnhub.", "Nobody leads.", prompt_id="q1")
        + replies("Start with Finnhub.", "Nobody leads.", prompt_id="q2")
    )
    finnhub = next(one for one in everywhere if one.name == "Finnhub")

    assert finnhub.in_questions == 2
    assert finnhub.draws == 3
    assert [(one.prompt_id, one.draws, one.of_draws) for one in finnhub.questions] == [
        ("q1", 2, 3),
        ("q2", 1, 2),
    ]
    assert finnhub.as_text().startswith("Finnhub")
    assert "q1 2/3, q2 1/2" in finnhub.as_text()


def test_a_round_with_nothing_in_it_counts_nothing():
    assert names_in(()) == ()


def test_the_order_puts_the_names_that_span_questions_first():
    """Two questions outrank more draws of one, and both outrank the alphabet.

    A name the model reaches for whatever it is asked is the finding a reader
    is looking for, and sorting the table by anything else buries it under
    whichever company starts with an A.
    """
    found = names_in(
        replies("Teams use Zeta and Alpha Vantage both.", prompt_id="q1")
        + replies("Most teams use Zeta.", "We use Zeta.", prompt_id="q2")
    )
    assert [one.name for one in found] == ["Zeta", "Alpha Vantage"]


# -- the round this was built to reproduce ----------------------------------


@pytest.mark.skipif(not DISCOVERY.exists(), reason="the discovery round is not on this machine")
def test_the_discovery_round_is_reproduced_from_its_own_records():
    """The table that was read by hand once, re-derived from the file it came from.

    Free, in every sense that matters: the round was paid for on 4 August, the
    answers are on disk, and this asserts the counts a person wrote down from a
    script that no longer exists. Twelve of the thirteen names that were carried
    out of that reading come back with the counts they were carried out with.
    """
    replies_in = tuple(
        Reply(prompt_id=rec["prompt_id"], draw=int(rec["repeat"]), text=rec["answer_text"])
        for rec in map(json.loads, DISCOVERY.read_text(encoding="utf-8").splitlines())
        if rec.get("prompt_id") and rec.get("status") == "ok" and rec.get("answer_text")
    )
    assert len(replies_in) == 24, "four questions, six draws each"

    counted_by = {one.name: one for one in names_in(replies_in)}
    for name, prompt_id, draws in (
        ("TradingView", "d1", 6),
        ("QuantConnect", "d1", 5),
        ("Numerai", "d1", 3),
        ("Collective2", "d1", 2),
        ("3Commas", "d1", 2),
        ("Bloomberg Terminal", "d2", 4),
        ("Refinitiv", "d2", 3),
        ("LSEG", "d2", 2),
        ("Alpha Vantage", "d4", 6),
        ("Polygon.io", "d4", 6),
        ("Finnhub", "d4", 6),
        ("IEX Cloud", "d4", 6),
        ("CoinGecko", "d4", 4),
    ):
        found = counted_by.get(name)
        assert found is not None, f"{name} was carried out of this round by hand"
        seen = {one.prompt_id: one.draws for one in found.questions}
        assert seen.get(prompt_id) == draws, f"{name} in {prompt_id}: {seen}"

    assert "Reliability" not in counted_by
    assert "Key Considerations" not in counted_by
    assert "Use Case" not in counted_by
