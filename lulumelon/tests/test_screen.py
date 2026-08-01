"""The gates that stand between a model's output and a paid round.

These are the tests that decide whether generating questions is measurement or
decoration. The evidence gate in particular has to hold against text that was
merely *reworded* from the page, not just against text invented whole, since a
model asked for a quote will happily paraphrase one.

Gate order is asserted rather than assumed. A candidate can trip several gates
at once, and which reason gets recorded is a contract the caller reads.
"""

from __future__ import annotations

import pytest

from lulumelon.mirror.screen import (
    GATES,
    Candidate,
    jaccard,
    normalise,
    screen,
    stable_ids,
)

PAGE = (
    "Marx Finance prices construction risk daily. "
    "Our underwriters review every draw schedule before funds release."
)


def no_brands(_: str) -> tuple[str, ...]:
    return ()


def brands_named(*names: str):
    def detector(text: str) -> tuple[str, ...]:
        low = text.casefold()
        return tuple(n for n in names if n.casefold() in low)

    return detector


def good(id_: str, text: str, evidence: str = "prices construction risk daily") -> Candidate:
    return Candidate(id=id_, text=text, source="https://marx.example/about", evidence=evidence)


def run(candidates, *, corpus: str = PAGE, detect=no_brands, threshold: float = 0.8):
    return screen(candidates, corpus=corpus, detect_names=detect, duplicate_threshold=threshold)


# -- a clean candidate survives ---------------------------------------------


def test_a_grounded_question_that_names_nobody_is_kept():
    result = run([good("p1", "Which lenders price construction risk daily?")])
    assert [c.id for c in result.kept] == ["p1"]
    assert result.rejected == ()


def test_every_gate_appears_in_the_counts_even_when_it_caught_nothing():
    counts = run([good("p1", "Which lenders underwrite draw schedules?")]).counts
    assert set(counts) == set(GATES)
    assert sum(counts.values()) == 0


# -- shape ------------------------------------------------------------------


def test_an_empty_question_is_refused():
    result = run([Candidate("p1", "   ", "https://x", "prices construction risk daily")])
    assert result.rejected[0].gate == "shape"


def test_a_question_with_no_quote_is_refused():
    result = run([Candidate("p1", "Which lenders are fastest?", "https://x", "")])
    assert result.rejected[0].gate == "shape"
    assert "nothing about it can be checked" in result.rejected[0].reason


def test_a_question_with_a_quote_but_no_source_is_refused():
    result = run([Candidate("p1", "Which lenders are fastest?", "", "prices construction risk")])
    assert result.rejected[0].gate == "shape"


# -- name, the gate that exists because of a real ten point error -----------


def test_a_question_containing_a_tracked_name_is_dropped():
    result = run(
        [good("p1", "What is Marx Finance?")],
        detect=brands_named("Marx Finance"),
    )
    assert result.rejected[0].gate == "name"
    assert "measure its own echo" in result.rejected[0].reason


def test_the_same_question_without_the_name_survives():
    result = run(
        [good("p1", "Which lenders price construction risk daily?")],
        detect=brands_named("Marx Finance"),
    )
    assert len(result.kept) == 1


# -- evidence, the gate a model cannot route around -------------------------


def test_an_invented_quote_is_caught():
    result = run([good("p1", "Which lenders are fastest?", evidence="we guarantee same day funding")])
    assert result.rejected[0].gate == "evidence"
    assert "not in the page it cites" in result.rejected[0].reason


def test_a_paraphrase_of_the_page_is_caught_not_just_an_invention():
    """The failure mode that matters. A model told to quote will reword."""
    result = run([good("p1", "Which lenders are fastest?", evidence="prices construction risk every day")])
    assert result.rejected[0].gate == "evidence"


def test_a_quote_survives_whitespace_and_case_differences():
    messy = "Prices   Construction\n Risk  DAILY"
    assert len(run([good("p1", "Which lenders are fastest?", evidence=messy)]).kept) == 1


def test_a_quote_survives_punctuation_the_page_has_and_the_quote_lacks():
    result = run([good("p1", "Which lenders are fastest?", evidence="risk daily Our underwriters")])
    assert len(result.kept) == 1


# -- duplicate, and it says it is a heuristic -------------------------------


def test_a_near_identical_question_is_collapsed():
    result = run(
        [
            good("p1", "Which lenders price construction risk daily?"),
            good("p2", "Which lenders price construction risk daily"),
        ]
    )
    assert [c.id for c in result.kept] == ["p1"]
    assert result.rejected[0].gate == "duplicate"
    assert "heuristic" in result.rejected[0].reason


def test_a_differently_worded_question_is_not_collapsed():
    result = run(
        [
            good("p1", "Which lenders price construction risk daily?"),
            good("p2", "Who reviews a draw schedule before funds release?"),
        ]
    )
    assert len(result.kept) == 2


def test_the_threshold_is_refused_outside_its_range():
    with pytest.raises(ValueError, match="must be in"):
        run([good("p1", "Which lenders are fastest?")], threshold=0.0)


# -- gate order is a contract -----------------------------------------------


def test_a_candidate_tripping_several_gates_reports_the_first():
    """Names a brand and invents a quote. The name gate runs first."""
    result = run(
        [Candidate("p1", "What is Marx Finance?", "https://x", "we guarantee same day funding")],
        detect=brands_named("Marx Finance"),
    )
    assert result.rejected[0].gate == "name"


def test_shape_runs_before_name():
    result = run(
        [Candidate("p1", "What is Marx Finance?", "", "")],
        detect=brands_named("Marx Finance"),
    )
    assert result.rejected[0].gate == "shape"


# -- ids are the join key and do not move -----------------------------------


def test_an_unchanged_question_keeps_its_id():
    previous = {normalise("Which lenders price construction risk daily?"): "p7"}
    out = stable_ids([good("ignored", "Which lenders price construction risk daily?")], previous)
    assert out[0].id == "p7"


def test_a_new_question_never_reuses_a_live_id():
    previous = {normalise("old question here"): "p1"}
    out = stable_ids([good("x", "a brand new question about draw schedules")], previous)
    assert out[0].id != "p1"


def test_a_mixed_set_keeps_the_old_and_numbers_the_new():
    previous = {normalise("kept question"): "p2"}
    out = stable_ids([good("a", "kept question"), good("b", "fresh question")], previous)
    assert out[0].id == "p2"
    assert out[1].id not in {"p2"}


def test_jaccard_is_one_for_identical_text_and_zero_for_disjoint():
    assert jaccard("a b c d", "a b c d") == 1.0
    assert jaccard("a b c d", "w x y z") == 0.0
