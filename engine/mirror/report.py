"""Assembling one honest answer about one brand.

This is the layer a customer sees. Its job is to refuse to print a bare number.
Every figure it produces carries the design that produced it: how many prompts,
how many repeats, how much of the wobble was the model rerolling, and what the
smallest movement is that this design could have detected.

One finding shaped this module more than any other. A vendor in this category
published a test of 753 prompts across 7 engines comparing once-daily sampling
against ten-times-daily, and found the portfolio-level scores differed by about
a quarter of a point. They are right, and it is the strongest argument against
naive "just run it more times" advice: when between-prompt variance dominates,
repeats buy almost nothing and prompts buy everything.

That is exactly why the answer cannot be a fixed k. `advice()` reads the
variance split and says which of the two to spend on, and `runs_needed` returns
"unreachable, add prompts" in precisely the regime where that vendor's
counter-argument holds. The claim here was never that everyone needs five runs.
It is that nobody currently measures which regime they are in, so the aggregate
can be stable while every per-prompt and every rank claim built on it is noise.
"""

from __future__ import annotations

from dataclasses import dataclass

from .intervals import Interval, cluster_bootstrap_ci, wilson_interval, z_for
from .stability import Stability, stability_of
from .types import Snapshot
from .variance import DesignRequirement, VarianceSplit, decompose, prompts_needed, runs_needed


@dataclass(frozen=True, slots=True)
class BrandReport:
    """Everything defensible that can be said about one brand in one snapshot."""

    brand: str
    snapshot: str
    engines: tuple[str, ...]
    n_prompts: int
    total_runs: int
    detection: Interval
    detection_by_prompt: Interval
    variance: VarianceSplit
    stability: Stability
    model_drift: dict[str, tuple[str, ...]]
    surface_mix: dict[str, tuple[str, ...]]
    mean_rank: float | None
    rank_reportable: bool

    @property
    def headline(self) -> str:
        """The number a competitor would print alone, printed with its floor."""
        pct = self.detection_by_prompt.point * 100
        floor = self.variance.noise_floor * 100
        return f"{pct:.1f}% +/- {floor:.1f}"

    def as_text(self) -> str:
        lines = [
            f"brand: {self.brand}   snapshot: {self.snapshot}",
            f"design: {self.n_prompts} prompts x {self.total_runs / max(self.n_prompts, 1):.1f} runs "
            f"= {self.total_runs} observations on {', '.join(self.engines)}",
            f"visibility: {self.headline}   "
            f"(95% CI {self.detection_by_prompt.low * 100:.1f}..{self.detection_by_prompt.high * 100:.1f})",
            f"run-level detection: {self.detection.as_text(digits=1, scale=100, unit='%')}",
            f"variance: {self.variance.as_text()}",
            f"stability: {self.stability.as_text()}",
        ]
        if self.mean_rank is None:
            lines.append("rank: never named, no rank exists")
        elif self.rank_reportable:
            lines.append(f"rank: {self.mean_rank:.2f} average position")
        else:
            lines.append(
                f"rank: WITHHELD. average position would read {self.mean_rank:.2f}, "
                "but the leading brand does not repeat often enough for a position "
                "to describe anything but the sampling"
            )
        if self.model_drift:
            for engine, models in self.model_drift.items():
                lines.append(
                    f"WARNING: {engine} reported more than one model version "
                    f"({', '.join(models)}); part of any movement is the provider's"
                )
        for engine, surfaces in self.surface_mix.items():
            lines.append(
                f"WARNING: {engine} was measured on more than one surface "
                f"({', '.join(surfaces)}); published measurement puts the gap "
                f"between surfaces above the gap between reruns, so this score "
                f"describes the collector as much as the brand"
            )
        return "\n".join(lines)

    def advice(self, target_half_width: float = 0.02) -> str:
        """Where to spend the next unit of measurement budget.

        Reads the variance split rather than applying a rule of thumb. When
        prompt-set noise dominates, it says add prompts and says so explicitly,
        because telling a customer to rerun the same prompts in that regime
        would burn their money for a quarter of a point.
        """
        more_runs: DesignRequirement = runs_needed(self.variance, target_half_width)
        if more_runs.reachable:
            current_k = self.total_runs / max(self.n_prompts, 1)
            if more_runs.k_runs is not None and more_runs.k_runs <= current_k:
                return (
                    f"design already reaches +/-{target_half_width * 100:.1f} points; "
                    f"the model's own rerun noise is not your limit"
                )
            return (
                f"raise repeats to k={more_runs.k_runs} on the same {self.n_prompts} "
                f"prompts to reach +/-{target_half_width * 100:.1f} points "
                f"(within-prompt noise is {self.variance.within:.5f}, "
                f"icc {self.variance.icc:.2f})"
            )
        wider = prompts_needed(self.variance, target_half_width, k_runs=3)
        if wider.reachable:
            # Careful with the wording. This is not a claim that prompt-to-
            # prompt variance is the larger share of the total, the icc often
            # says otherwise. It is that at this prompt count the prompt-set
            # contribution alone already overruns the precision budget, so
            # repeats cannot close the gap however many you buy.
            floor_from_prompts = (
                z_for(self.variance.confidence)
                * (self.variance.between / self.n_prompts) ** 0.5
            )
            return (
                f"repeats will not get you there: with {self.n_prompts} prompts the "
                f"prompt set alone already carries +/-{floor_from_prompts * 100:.1f} points, "
                f"past your +/-{target_half_width * 100:.1f} target. Reach it with "
                f"{wider.n_prompts} prompts at k=3 instead (icc {self.variance.icc:.2f})."
            )
        return (
            f"neither more repeats nor a realistic prompt count reaches "
            f"+/-{target_half_width * 100:.1f} points; loosen the target"
        )


def brand_report(
    snapshot: Snapshot,
    brand: str,
    *,
    confidence: float = 0.95,
    resamples: int = 2000,
    seed: int = 0,
) -> BrandReport:
    """Compute every defensible statement about `brand` in `snapshot`."""
    clusters = [list(s.detections(brand)) for s in snapshot.samples]
    successes = int(sum(sum(c) for c in clusters))
    n_runs = int(sum(len(c) for c in clusters))

    detection = wilson_interval(successes, n_runs, confidence)
    by_prompt = cluster_bootstrap_ci(
        clusters, resamples=resamples, confidence=confidence, seed=seed
    )
    split = decompose(clusters, confidence=confidence)

    # Stability is measured on the brand orderings themselves, pooled over the
    # repeats of every prompt: a prompt whose answer reshuffles every time
    # drags the whole snapshot's reportability down, which is correct.
    per_prompt_stability = [stability_of([r.brands for r in s.runs]) for s in snapshot.samples]
    n = len(per_prompt_stability)
    pooled = Stability(
        k=int(round(sum(st.k for st in per_prompt_stability) / n)),
        set_overlap=sum(st.set_overlap for st in per_prompt_stability) / n,
        rank_overlap=sum(st.rank_overlap for st in per_prompt_stability) / n,
        leader_repeat=sum(st.leader_repeat for st in per_prompt_stability) / n,
        exact_repeat=sum(st.exact_repeat for st in per_prompt_stability) / n,
    )

    all_ranks = [r for s in snapshot.samples for r in s.ranks(brand)]
    mean_rank = sum(all_ranks) / len(all_ranks) if all_ranks else None

    return BrandReport(
        brand=brand,
        snapshot=snapshot.label,
        engines=snapshot.engines,
        n_prompts=snapshot.n_prompts,
        total_runs=snapshot.total_runs,
        detection=detection,
        detection_by_prompt=by_prompt,
        variance=split,
        stability=pooled,
        model_drift=snapshot.model_drift,
        surface_mix=snapshot.surface_mix,
        mean_rank=mean_rank,
        rank_reportable=pooled.is_orderable,
    )
