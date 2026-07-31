"""The customer-facing layer, and the things it refuses to print.

Two behaviours are the product: a headline number never appears without its
noise floor, and a rank is withheld when the ordering does not repeat. Both are
asserted here on constructed data where the right answer is known.
"""

from __future__ import annotations

import numpy as np
import pytest

from lulumelon.mirror.report import brand_report
from lulumelon.mirror.types import PromptSample, Run, Snapshot, group_runs, snapshot_from_runs


def _runs(prompt: str, engine: str, model: str, answers: list[tuple[str, ...]]) -> list[Run]:
    return [
        Run(prompt, engine, model, f"2026-07-30T{i:02d}:00:00Z", brands)
        for i, brands in enumerate(answers)
    ]


def test_run_rank_is_none_when_absent_not_zero_or_last() -> None:
    r = Run("p1", "chatgpt", "gpt-5.2", "t", ("nike", "adidas"))
    assert r.rank_of("nike") == 1
    assert r.rank_of("adidas") == 2
    assert r.rank_of("puma") is None
    assert r.mentions("nike") and not r.mentions("puma")


def test_prompt_sample_rejects_runs_from_another_prompt() -> None:
    good = _runs("p1", "chatgpt", "m", [("nike",), ("nike",)])
    PromptSample("p1", "chatgpt", tuple(good))
    with pytest.raises(ValueError):
        PromptSample("p2", "chatgpt", tuple(good))
    with pytest.raises(ValueError):
        PromptSample("p1", "chatgpt", ())


def test_snapshot_rejects_a_split_prompt() -> None:
    """Two half-samples of the same prompt would understate k."""
    s = PromptSample("p1", "chatgpt", tuple(_runs("p1", "chatgpt", "m", [("nike",)])))
    with pytest.raises(ValueError, match="two samples"):
        Snapshot("bad", (s, s))


def test_group_runs_bundles_by_prompt_and_engine() -> None:
    runs = _runs("p1", "chatgpt", "m", [("nike",), ("nike",)]) + _runs(
        "p1", "perplexity", "m", [("nike",)]
    )
    samples = group_runs(runs)
    assert len(samples) == 2
    assert {s.engine for s in samples} == {"chatgpt", "perplexity"}


def _stable_snapshot(seed: int, p: float, n: int = 30, k: int = 8) -> Snapshot:
    """Prompts where the ordering repeats, so a rank is meaningful."""
    rng = np.random.default_rng(seed)
    runs: list[Run] = []
    for i in range(n):
        for j in range(k):
            hit = rng.random() < p
            brands = ("nike", "adidas", "puma") if hit else ("adidas", "puma")
            runs.append(Run(f"p{i}", "chatgpt", "gpt-5.2", f"t{j}", brands))
    return snapshot_from_runs("stable", runs)


def test_headline_always_carries_its_noise_floor() -> None:
    report = brand_report(_stable_snapshot(1, 0.5), "nike")
    assert "+/-" in report.headline
    assert report.variance.noise_floor > 0
    assert "visibility:" in report.as_text()


def test_detection_matches_the_planted_rate() -> None:
    report = brand_report(_stable_snapshot(2, 0.60), "nike")
    assert report.detection_by_prompt.point == pytest.approx(0.60, abs=0.06)
    assert report.detection_by_prompt.contains(0.60)


def test_rank_is_withheld_when_the_ordering_reshuffles() -> None:
    """A number exists; printing it would describe the sampling, not the brand."""
    rng = np.random.default_rng(3)
    pool = ["nike", "adidas", "puma", "asics", "reebok", "hoka"]
    runs: list[Run] = []
    for i in range(20):
        for j in range(8):
            order = list(rng.permutation(pool))[:3]
            runs.append(Run(f"p{i}", "chatgpt", "gpt-5.2", f"t{j}", tuple(order)))
    report = brand_report(snapshot_from_runs("shuffled", runs), "nike")

    assert report.mean_rank is not None
    assert not report.rank_reportable
    assert "WITHHELD" in report.as_text()


def test_rank_is_reported_when_the_leader_holds() -> None:
    report = brand_report(_stable_snapshot(4, 0.95), "nike")
    assert report.rank_reportable
    assert report.mean_rank == pytest.approx(1.0)
    assert "average position" in report.as_text()


def test_a_brand_never_named_has_no_rank_at_all() -> None:
    report = brand_report(_stable_snapshot(5, 0.5), "brooks")
    assert report.mean_rank is None
    assert report.detection.point == 0.0
    assert "no rank exists" in report.as_text()


def test_model_drift_is_surfaced_in_the_report_text() -> None:
    runs = [
        Run("p1", "chatgpt", "gpt-5.2", "t0", ("nike",)),
        Run("p1", "chatgpt", "gpt-5.6", "t1", ("nike",)),
        Run("p2", "chatgpt", "gpt-5.2", "t0", ("nike",)),
        Run("p2", "chatgpt", "gpt-5.6", "t1", ()),
    ]
    report = brand_report(snapshot_from_runs("drifted", runs), "nike")
    assert "chatgpt" in report.model_drift
    assert "WARNING" in report.as_text()


def test_advice_says_add_repeats_when_the_model_is_the_noisy_part() -> None:
    """High rerun noise, near-identical prompts: repeats are the right spend."""
    rng = np.random.default_rng(6)
    runs: list[Run] = []
    for i in range(40):
        for j in range(4):
            hit = rng.random() < 0.5
            runs.append(
                Run(f"p{i}", "chatgpt", "m", f"t{j}", ("nike",) if hit else ())
            )
    report = brand_report(snapshot_from_runs("noisy-model", runs), "nike")
    text = report.advice(target_half_width=0.03)
    assert "repeats" in text


def test_advice_says_add_prompts_when_the_prompt_set_is_the_noisy_part() -> None:
    """The incumbent's counter-argument, honoured rather than argued with.

    Prompts here are deterministic and wildly different from each other. No
    number of repeats narrows the interval, and the advice says so instead of
    selling more runs.
    """
    runs: list[Run] = []
    for i in range(12):
        always = i % 2 == 0
        for j in range(6):
            runs.append(
                Run(f"p{i}", "chatgpt", "m", f"t{j}", ("nike",) if always else ())
            )
    report = brand_report(snapshot_from_runs("varied-prompts", runs), "nike")
    assert report.variance.icc > 0.9
    text = report.advice(target_half_width=0.02)
    assert "prompt" in text and "repeats will not get you there" in text


def test_report_refuses_a_single_run_design() -> None:
    """k=1 is what the category ships. It cannot carry an interval."""
    runs = [Run(f"p{i}", "chatgpt", "m", "t0", ("nike",)) for i in range(30)]
    with pytest.raises(ValueError, match="asked once"):
        brand_report(snapshot_from_runs("daily-single", runs), "nike")


def test_engine_filter_narrows_a_snapshot() -> None:
    runs = _runs("p1", "chatgpt", "m", [("nike",), ("nike",)]) + _runs(
        "p1", "perplexity", "m", [("nike",), ()]
    )
    snap = snapshot_from_runs("both", runs)
    assert snap.engines == ("chatgpt", "perplexity")
    only = snap.for_engine("perplexity")
    assert only.engines == ("perplexity",)
    assert only.total_runs == 2
    with pytest.raises(ValueError):
        snap.for_engine("gemini")


def test_snapshot_reports_its_own_shape() -> None:
    snap = _stable_snapshot(7, 0.5, n=12, k=5)
    assert snap.n_prompts == 12
    assert snap.total_runs == 60
    assert snap.is_balanced
    assert "nike" in snap.brands()
