"""Side by side: what the category prints, and what the measurement says.

Run with:  python3 mirror/demo.py

The synthetic answer engine below is not tuned to flatter the argument. Its
parameters are set from published measurements of real systems: repeated asks
of the same prompt return brand sets that overlap only partially, and the
ordering rarely repeats exactly. Everything printed is computed by the engine,
nothing is hard-coded.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np

from mirror import brand_report, paired_difference, snapshot_from_runs
from mirror.types import Run

BRANDS = ["nike", "adidas", "puma", "asics", "reebok", "hoka", "brooks", "newbalance"]
TARGET = "nike"


def simulate(
    seed: int, n_prompts: int, k: int, base_rate: float, model: str = "gpt-5.2"
) -> list[Run]:
    """An answer engine that names three brands, unevenly, and rerolls each time.

    Each prompt has its own affinity for the target brand (prompt-to-prompt
    variation) and each individual ask is a fresh draw (rerun noise). That two
    layer structure is the whole reason a single ask is not a measurement.
    """
    rng = np.random.default_rng(seed)
    prompt_rates = np.clip(rng.normal(base_rate, 0.18, size=n_prompts), 0.02, 0.98)
    runs: list[Run] = []
    for i, rate in enumerate(prompt_rates):
        for j in range(k):
            others = list(rng.permutation([b for b in BRANDS if b != TARGET]))
            if rng.random() < rate:
                position = rng.integers(0, 3)
                answer = others[:2]
                answer.insert(int(position), TARGET)
            else:
                answer = others[:3]
            runs.append(
                Run(
                    prompt_id=f"p{i:02d}",
                    engine="chatgpt",
                    model=model,
                    asked_at=f"2026-07-30T{j:02d}:00:00Z",
                    brands=tuple(answer),
                )
            )
    return runs


def rule(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def main() -> None:
    n_prompts, k = 40, 12

    rule("1. what a single daily run reports")
    single = simulate(seed=101, n_prompts=n_prompts, k=1, base_rate=0.42)
    hits = sum(1 for r in single if TARGET in r.brands)
    leads = sum(1 for r in single if r.brands and r.brands[0] == TARGET)
    print(f"visibility score: {hits / len(single) * 100:.1f}%")
    print(f"average position: {np.mean([r.brands.index(TARGET) + 1 for r in single if TARGET in r.brands]):.2f}")
    print(f"you lead in {leads} of {len(single)} answers")
    print("one number, no interval, k=1: the cheap reading of the same data")

    rule("2. the same measurement, asked 12 times per prompt")
    snap = snapshot_from_runs("week-1", simulate(101, n_prompts, k, 0.42))
    report = brand_report(snap, TARGET, seed=7)
    print(report.as_text())
    print("\nadvice: " + report.advice(target_half_width=0.03))

    rule("3. a week later, nothing was changed")
    same = snapshot_from_runs("week-2", simulate(202, n_prompts, k, 0.42))
    before = {s.prompt_id: list(s.detections(TARGET)) for s in snap.samples}
    after = {s.prompt_id: list(s.detections(TARGET)) for s in same.samples}
    print(paired_difference(before, after, label="week 1 -> week 2", seed=3).as_text(scale=100))

    rule("4. a week later, something real happened")
    better = snapshot_from_runs("week-3", simulate(303, n_prompts, k, 0.52))
    after_real = {s.prompt_id: list(s.detections(TARGET)) for s in better.samples}
    print(paired_difference(before, after_real, label="week 1 -> week 3", seed=3).as_text(scale=100))

    rule("5. the same real gain, but the provider swapped the model underneath")
    drifted = snapshot_from_runs("week-3-drift", simulate(303, n_prompts, k, 0.52, model="gpt-5.6"))
    after_drift = {s.prompt_id: list(s.detections(TARGET)) for s in drifted.samples}
    print(
        paired_difference(
            before,
            after_drift,
            label="week 1 -> week 3",
            seed=3,
            confounded_by=["chatgpt (model version)"],
        ).as_text(scale=100)
    )

    rule("6. what it cost to know")
    print(f"observations: {snap.total_runs} vs {len(single)} for the single-run design")
    print(f"prompts: {snap.n_prompts}, repeats per prompt: {k}")
    print("no model was called to produce any number above; this is arithmetic over recorded runs")


if __name__ == "__main__":
    main()
