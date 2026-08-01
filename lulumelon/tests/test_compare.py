"""Before/after comparison, including the refusals.

Two behaviours here matter more than the arithmetic: a real shift has to be
detected, and a comparison across a silent model version change has to produce
no verdict at all rather than a confident wrong one.
"""

from __future__ import annotations

import numpy as np
import pytest

from lulumelon.mirror.compare import (
    holm_adjust,
    mcnemar_detection,
    model_confounds,
    paired_difference,
)
from lulumelon.mirror.types import Run, snapshot_from_runs


def _paired_sets(
    rng: np.random.Generator, n: int, k: int, p_before: float, p_after: float
) -> tuple[dict[str, list[float]], dict[str, list[float]]]:
    """Same prompts on both sides, each with its own baseline difficulty."""
    offsets = rng.normal(0.0, 0.15, size=n)
    before, after = {}, {}
    for i, off in enumerate(offsets):
        pb = float(np.clip(p_before + off, 0.02, 0.98))
        pa = float(np.clip(p_after + off, 0.02, 0.98))
        before[f"p{i}"] = list(rng.binomial(1, pb, size=k).astype(float))
        after[f"p{i}"] = list(rng.binomial(1, pa, size=k).astype(float))
    return before, after


def test_a_real_shift_is_detected() -> None:
    rng = np.random.default_rng(5)
    before, after = _paired_sets(rng, n=60, k=8, p_before=0.30, p_after=0.45)
    v = paired_difference(before, after, seed=1)
    assert v.significant
    assert v.diff > 0
    assert "CHANGED" in v.as_text()


def test_no_shift_is_reported_as_noise() -> None:
    rng = np.random.default_rng(6)
    before, after = _paired_sets(rng, n=60, k=8, p_before=0.35, p_after=0.35)
    v = paired_difference(before, after, seed=1)
    assert not v.significant
    assert v.interval.contains(0.0)
    assert "within noise" in v.as_text()


def test_pairing_beats_ignoring_the_pairing() -> None:
    """Why the comparison is paired at all.

    The same shift, measured with pairing, produces a tighter interval than
    treating the two rounds as unrelated samples, because prompt difficulty
    cancels.
    """
    from lulumelon.mirror.intervals import cluster_bootstrap_ci

    rng = np.random.default_rng(8)
    before, after = _paired_sets(rng, n=50, k=6, p_before=0.30, p_after=0.38)

    paired = paired_difference(before, after, seed=2)
    ci_b = cluster_bootstrap_ci(list(before.values()), seed=2)
    ci_a = cluster_bootstrap_ci(list(after.values()), seed=3)
    unpaired_width = ci_a.half_width + ci_b.half_width

    assert paired.interval.half_width < unpaired_width


def test_a_model_version_change_voids_the_verdict() -> None:
    """The refusal. A confounded comparison never reads as significant."""
    rng = np.random.default_rng(9)
    before, after = _paired_sets(rng, n=60, k=8, p_before=0.20, p_after=0.60)

    clean = paired_difference(before, after, seed=1)
    assert clean.significant

    confounded = paired_difference(before, after, seed=1, confounded_by=["chatgpt"])
    assert not confounded.significant
    assert confounded.diff == pytest.approx(clean.diff)
    assert "CONFOUNDED" in confounded.as_text()


def test_model_confounds_finds_a_silent_version_change() -> None:
    def snap(label: str, model: str) -> object:
        return snapshot_from_runs(
            label,
            [
                Run("p1", "chatgpt", model, "2026-07-30T00:00:00Z", ("nike",)),
                Run("p1", "chatgpt", model, "2026-07-30T01:00:00Z", ("nike",)),
                Run("p2", "chatgpt", model, "2026-07-30T00:00:00Z", ("adidas",)),
                Run("p2", "chatgpt", model, "2026-07-30T01:00:00Z", ("adidas",)),
            ],
        )

    same = model_confounds(snap("a", "gpt-5.2"), snap("b", "gpt-5.2"))
    assert same == ()

    drifted = model_confounds(snap("a", "gpt-5.2"), snap("b", "gpt-5.6"))
    assert drifted == ("chatgpt",)


def test_drift_inside_one_snapshot_is_also_a_confound() -> None:
    mixed = snapshot_from_runs(
        "mixed",
        [
            Run("p1", "chatgpt", "gpt-5.2", "t0", ("nike",)),
            Run("p1", "chatgpt", "gpt-5.6", "t1", ("nike",)),
        ],
    )
    steady = snapshot_from_runs(
        "steady",
        [
            Run("p1", "chatgpt", "gpt-5.2", "t0", ("nike",)),
            Run("p1", "chatgpt", "gpt-5.2", "t1", ("nike",)),
        ],
    )
    assert model_confounds(steady, mixed) == ("chatgpt",)
    assert mixed.model_drift == {"chatgpt": ("gpt-5.2", "gpt-5.6")}


def test_surface_change_between_rounds_is_a_confound() -> None:
    """The largest confound found, and the one nobody else records.

    Measured on one day across three OpenAI access surfaces, one brand moved
    32 points between logged-in and logged-out ChatGPT. Swapping surface
    between two rounds can manufacture a bigger swing than anything the
    customer did.
    """
    from lulumelon.mirror.compare import design_confounds, surface_confounds

    def snap(label: str, surface: str) -> object:
        return snapshot_from_runs(
            label,
            [
                Run("p1", "chatgpt", "gpt-5.2", "t0", ("nike",), (), surface),
                Run("p1", "chatgpt", "gpt-5.2", "t1", ("nike",), (), surface),
                Run("p2", "chatgpt", "gpt-5.2", "t0", ("adidas",), (), surface),
                Run("p2", "chatgpt", "gpt-5.2", "t1", ("adidas",), (), surface),
            ],
        )

    assert surface_confounds(snap("a", "logged_out"), snap("b", "logged_out")) == ()
    assert surface_confounds(snap("a", "logged_out"), snap("b", "api")) == ("chatgpt",)

    both = design_confounds(snap("a", "logged_out"), snap("b", "api"))
    assert both == ("chatgpt (surface)",)


def test_model_and_surface_confounds_are_reported_separately() -> None:
    from lulumelon.mirror.compare import design_confounds

    a = snapshot_from_runs(
        "a",
        [
            Run("p1", "chatgpt", "gpt-5.2", "t0", ("nike",), (), "logged_out"),
            Run("p1", "chatgpt", "gpt-5.2", "t1", ("nike",), (), "logged_out"),
        ],
    )
    b = snapshot_from_runs(
        "b",
        [
            Run("p1", "chatgpt", "gpt-5.6", "t0", ("nike",), (), "api"),
            Run("p1", "chatgpt", "gpt-5.6", "t1", ("nike",), (), "api"),
        ],
    )
    assert design_confounds(a, b) == ("chatgpt (model version)", "chatgpt (surface)")


def test_a_snapshot_that_blends_surfaces_is_flagged() -> None:
    blended = snapshot_from_runs(
        "blended",
        [
            Run("p1", "chatgpt", "m", "t0", ("nike",), (), "logged_in"),
            Run("p1", "chatgpt", "m", "t1", ("nike",), (), "logged_out"),
        ],
    )
    assert blended.surface_mix == {"chatgpt": ("logged_in", "logged_out")}

    clean = snapshot_from_runs(
        "clean",
        [
            Run("p1", "chatgpt", "m", "t0", ("nike",), (), "logged_out"),
            Run("p1", "chatgpt", "m", "t1", ("nike",), (), "logged_out"),
        ],
    )
    assert clean.surface_mix == {}


def test_unlabelled_runs_are_treated_as_one_consistent_surface() -> None:
    """An unlabelled collector is at least consistently unlabelled."""
    plain = snapshot_from_runs(
        "plain",
        [
            Run("p1", "chatgpt", "m", "t0", ("nike",)),
            Run("p1", "chatgpt", "m", "t1", ("nike",)),
        ],
    )
    assert plain.surface_mix == {}


def test_mcnemar_detects_a_one_directional_flip() -> None:
    before = {f"p{i}": [0.0, 0.0, 0.0] for i in range(20)}
    after = {f"p{i}": ([1.0, 1.0, 1.0] if i < 9 else [0.0, 0.0, 0.0]) for i in range(20)}
    v = mcnemar_detection(before, after)
    assert v.p_value is not None and v.p_value < 0.01
    assert v.diff > 0


def test_mcnemar_ignores_prompts_that_did_not_move() -> None:
    before = {f"p{i}": [1.0, 1.0] for i in range(50)}
    after = {f"p{i}": [1.0, 1.0] for i in range(50)}
    v = mcnemar_detection(before, after)
    assert v.p_value == 1.0
    assert v.diff == 0.0


def test_mcnemar_drops_ties_rather_than_rounding_a_coin_flip() -> None:
    before = {"p1": [1.0, 0.0], "p2": [0.0, 0.0]}
    after = {"p1": [1.0, 1.0], "p2": [1.0, 1.0]}
    v = mcnemar_detection(before, after)
    assert v.n_paired == 1  # p1 was an exact tie before and is excluded


def test_holm_is_stricter_than_no_correction_and_stops_at_the_first_failure() -> None:
    """Forty prompts tested at 0.05 will hand you two false alarms."""
    p_values = [0.001, 0.02, 0.03, 0.6]
    survives = holm_adjust(p_values, alpha=0.05)
    # thresholds: 0.0125, 0.0167, 0.025, 0.05
    assert survives == (True, False, False, False)


def test_holm_passes_everything_when_all_are_tiny() -> None:
    assert holm_adjust([1e-6, 1e-6, 1e-6]) == (True, True, True)


def test_holm_on_empty_input() -> None:
    assert holm_adjust([]) == ()


def test_comparison_needs_overlapping_prompts() -> None:
    with pytest.raises(ValueError):
        paired_difference({"a": [1.0]}, {"b": [1.0]})


def _confounded(reasons: tuple[str, ...]) -> str:
    """One confounded verdict's text, over data that would otherwise be decisive."""
    before = {f"p{i}": [0.0] * 5 for i in range(10)}
    after = {f"p{i}": [1.0] * 5 for i in range(10)}
    return paired_difference(before, after, label="arm", confounded_by=reasons).as_text(scale=100)


def test_the_verdict_states_the_reason_it_was_given_and_not_one_of_its_own() -> None:
    """The renderer used to name the reason itself, and always named the same one.

    It printed that the model version had changed for any confound at all. The
    first real comparison of two collection arms hit that on a round where one
    model answered both sides, so the screen carried a sentence about a version
    change that had not happened. The caller knows which check fired; this
    class does not, so it prints what it was handed.
    """
    text = _confounded(("anthropic (surface)",))
    assert "confounded by anthropic (surface)" in text
    assert "model version" not in text


def test_a_model_change_still_says_so_when_that_is_what_was_passed() -> None:
    text = _confounded(("anthropic (model version)",))
    assert "confounded by anthropic (model version)" in text


def test_every_reason_reaches_the_screen() -> None:
    """Two reasons, both printed. Dropping one would understate why a round is void."""
    text = _confounded(("anthropic (model version)", "anthropic (surface)"))
    assert "anthropic (model version)" in text
    assert "anthropic (surface)" in text
    assert "raw diff would have been +100.000" in text
