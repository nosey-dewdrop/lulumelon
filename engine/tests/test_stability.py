"""Stability metrics.

The published numbers this module exists to reproduce: repeated asks of the same
prompt return source sets overlapping around 0.23 to 0.43, and identical
ordered brand lists show up in well under one pair in a hundred. The tests
below check the metrics behave correctly on constructed cases where the right
answer is known by hand.
"""

from __future__ import annotations

import pytest

from mirror.stability import (
    exact_repeat_rate,
    jaccard,
    leader_repeat_rate,
    mean_pairwise_jaccard,
    mean_pairwise_rbo,
    rbo,
    stability_of,
)


def test_jaccard_hand_computed() -> None:
    assert jaccard(["a", "b"], ["a", "b"]) == 1.0
    assert jaccard(["a", "b"], ["c", "d"]) == 0.0
    # {a,b,c} vs {b,c,d}: intersection 2, union 4
    assert jaccard(["a", "b", "c"], ["b", "c", "d"]) == pytest.approx(0.5)


def test_jaccard_ignores_order_and_duplicates() -> None:
    assert jaccard(["a", "b"], ["b", "a"]) == 1.0
    assert jaccard(["a", "a", "b"], ["a", "b"]) == 1.0


def test_two_empty_answers_are_stable_not_undefined() -> None:
    """The model consistently naming nobody is a finding, not a divide by zero."""
    assert jaccard([], []) == 1.0
    assert rbo([], []) == 1.0
    assert jaccard([], ["a"]) == 0.0


def test_rbo_punishes_disagreement_at_the_top_more_than_at_the_bottom() -> None:
    """The property Jaccard cannot express."""
    base = ["a", "b", "c", "d"]
    swapped_top = ["b", "a", "c", "d"]
    swapped_bottom = ["a", "b", "d", "c"]

    assert jaccard(base, swapped_top) == jaccard(base, swapped_bottom) == 1.0
    assert rbo(base, swapped_top) < rbo(base, swapped_bottom)


def test_rbo_is_one_for_identical_orderings_and_low_for_reversed() -> None:
    order = ["a", "b", "c", "d", "e"]
    assert rbo(order, order) == pytest.approx(1.0)
    assert rbo(order, list(reversed(order))) < 0.6


def test_rbo_rejects_invalid_persistence() -> None:
    with pytest.raises(ValueError):
        rbo(["a"], ["a"], p=0.0)
    with pytest.raises(ValueError):
        rbo(["a"], ["a"], p=1.0)


def test_leader_repeat_rate_counts_the_modal_leader() -> None:
    answers = [["a", "b"], ["a", "c"], ["b", "a"], ["a"]]
    assert leader_repeat_rate(answers) == pytest.approx(0.75)


def test_an_empty_answer_is_its_own_outcome_for_the_leader() -> None:
    """Dropping "nobody was named" would overstate how often you lead."""
    answers = [["a"], [], [], []]
    assert leader_repeat_rate(answers) == pytest.approx(0.75)  # the modal leader is nobody


def test_exact_repeat_rate_requires_the_same_order() -> None:
    answers = [["a", "b"], ["a", "b"], ["b", "a"]]
    assert exact_repeat_rate(answers) == pytest.approx(2 / 3)


def test_a_single_observation_is_trivially_stable() -> None:
    assert mean_pairwise_jaccard([["a"]]) == 1.0
    assert mean_pairwise_rbo([["a"]]) == 1.0


def test_stability_declares_a_perfectly_repeatable_answer_orderable() -> None:
    answers = [["nike", "adidas", "puma"]] * 6
    st = stability_of(answers)
    assert st.set_overlap == 1.0
    assert st.rank_overlap == pytest.approx(1.0)
    assert st.leader_repeat == 1.0
    assert st.exact_repeat == 1.0
    assert st.is_orderable


def test_stability_refuses_to_call_a_reshuffling_answer_orderable() -> None:
    """The SparkToro case: every run a different list, so no rank exists."""
    answers = [
        ["nike", "adidas"],
        ["puma", "asics"],
        ["adidas", "reebok"],
        ["asics", "nike"],
        ["reebok", "puma"],
        ["hoka", "brooks"],
    ]
    st = stability_of(answers)
    assert st.set_overlap < 0.35
    assert st.leader_repeat < 0.5
    assert not st.is_orderable
    assert "NOT REPORTABLE" in st.as_text()


def test_stability_is_borderline_when_only_the_tail_moves() -> None:
    """A stable leader with a churning tail should stay reportable."""
    answers = [
        ["nike", "adidas", "puma"],
        ["nike", "adidas", "asics"],
        ["nike", "adidas", "reebok"],
        ["nike", "adidas", "hoka"],
        ["nike", "adidas", "brooks"],
    ]
    st = stability_of(answers)
    assert st.leader_repeat == 1.0
    assert st.exact_repeat < 0.5
    assert st.is_orderable


def test_stability_rejects_no_answers() -> None:
    with pytest.raises(ValueError):
        stability_of([])
