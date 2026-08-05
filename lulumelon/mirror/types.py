"""Core data model.

A single ask of a single prompt against a single engine produces one `Run`.
Everything downstream is computed from a collection of runs, never from a
vendor-supplied summary. The whole point of this engine is that one run is a
draw from a distribution, so a run is the atom and a single run is never
enough to report a number.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Run:
    """One observation: one prompt, asked once, on one engine.

    Attributes:
        prompt_id: stable identifier of the tracked prompt.
        engine: the surface that was asked (e.g. "chatgpt", "ai_overviews").
        model: the model version the surface reported, or "unknown". Recorded
            because a silent provider-side model change invalidates comparisons
            across time, and we refuse to hide that.
        asked_at: ISO-8601 timestamp supplied by the caller. Never generated
            here, so results stay reproducible.
        brands: brands named in the answer, in the order they appear. Empty
            tuple means the answer named nobody we track.
        citations: source URLs the answer cited, in order.
        surface: where the question was asked. "logged_in", "logged_out",
            "api", or "unspecified".

    On `surface`. A study of three OpenAI access surfaces on the same day, 300
    trials each, reported one brand at 30.0% on logged-in ChatGPT and 62.3%
    logged out, another at 48.3% logged-in and 0% logged out, and a third at
    18.0% logged-in and 0% through the API: a 32 point swing for the same
    brand across doors. Top-five brand overlap between logged-in and API was
    0.25 Jaccard. Error across surfaces measured 1.5 to 3.6 times the error
    within one.
    (petralabs.com/intelligence/how-accurate-are-ai-visibility-tools, Feb 2026)

    That makes the surface a bigger variable than the non-determinism this
    library was built to quantify, so it is recorded per run and treated as a
    confound rather than an implementation detail. Mixing surfaces inside one
    measurement, or comparing across them, produces a number about the
    collection method rather than about the brand.
    """

    prompt_id: str
    engine: str
    model: str
    asked_at: str
    brands: tuple[str, ...] = ()
    citations: tuple[str, ...] = ()
    surface: str = "unspecified"

    def mentions(self, brand: str) -> bool:
        """True when `brand` is named anywhere in this answer."""
        return brand in self.brands

    def rank_of(self, brand: str) -> int | None:
        """1-based position of `brand`, or None when it is absent.

        None is not zero and not last. A missing brand has no rank, and
        averaging it in as if it did is one of the ways a visibility score
        gets quietly fabricated.
        """
        try:
            return self.brands.index(brand) + 1
        except ValueError:
            return None


@dataclass(frozen=True, slots=True)
class Reply:
    """One recorded answer, whole, as the engine wrote it.

    A `Run` is an answer already read: it carries the brands somebody declared
    and went looking for. This carries the words, and it exists for the one
    question that cannot be answered from a list of names decided in advance,
    which is who else the model names when nobody suggested anybody.

    Built by the caller from the ledger and handed in. Nothing in this package
    opens a file, so a count that could not be reproduced from records on disk
    cannot be produced here at all.
    """

    prompt_id: str
    draw: int
    text: str


@dataclass(frozen=True, slots=True)
class PromptSample:
    """Every run of one prompt on one engine: the k repeats.

    This is the unit that carries non-determinism. Variance measured inside a
    PromptSample is the model's own dice; variance measured across samples is
    the prompt set's sampling error. Keeping them in separate containers is
    what lets us separate them later.
    """

    prompt_id: str
    engine: str
    runs: tuple[Run, ...]

    def __post_init__(self) -> None:
        if not self.runs:
            raise ValueError(f"PromptSample {self.prompt_id!r} has no runs")
        bad = [r for r in self.runs if r.prompt_id != self.prompt_id or r.engine != self.engine]
        if bad:
            raise ValueError(
                f"PromptSample {self.prompt_id!r}/{self.engine!r} received runs "
                f"belonging to another prompt or engine"
            )

    @property
    def k(self) -> int:
        """Number of repeats of this prompt."""
        return len(self.runs)

    @property
    def models(self) -> tuple[str, ...]:
        """Distinct model versions seen across the repeats, sorted."""
        return tuple(sorted({r.model for r in self.runs}))

    @property
    def surfaces(self) -> tuple[str, ...]:
        """Distinct surfaces seen across the repeats, sorted."""
        return tuple(sorted({r.surface for r in self.runs}))

    def detections(self, brand: str) -> tuple[int, ...]:
        """Per-run 1/0 indicator of whether `brand` was named."""
        return tuple(int(r.mentions(brand)) for r in self.runs)

    def ranks(self, brand: str) -> tuple[int, ...]:
        """Ranks of `brand` across repeats, skipping runs where it is absent."""
        found = (r.rank_of(brand) for r in self.runs)
        return tuple(x for x in found if x is not None)


@dataclass(frozen=True, slots=True)
class Snapshot:
    """One measurement round: many prompts, each asked k times.

    A Snapshot is what a competing product would collapse into a single
    "visibility score". Here it stays a collection so the score can carry an
    interval.
    """

    label: str
    samples: tuple[PromptSample, ...]
    meta: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.samples:
            raise ValueError(f"Snapshot {self.label!r} has no samples")
        seen: set[tuple[str, str]] = set()
        for s in self.samples:
            key = (s.prompt_id, s.engine)
            if key in seen:
                raise ValueError(
                    f"Snapshot {self.label!r} has two samples for {key!r}; "
                    "merge their runs into one PromptSample instead"
                )
            seen.add(key)

    @property
    def n_prompts(self) -> int:
        return len(self.samples)

    @property
    def total_runs(self) -> int:
        return sum(s.k for s in self.samples)

    @property
    def engines(self) -> tuple[str, ...]:
        return tuple(sorted({s.engine for s in self.samples}))

    @property
    def is_balanced(self) -> bool:
        """True when every prompt was asked the same number of times."""
        return len({s.k for s in self.samples}) == 1

    @property
    def model_drift(self) -> dict[str, tuple[str, ...]]:
        """Engines that reported more than one model version in this snapshot.

        A non-empty result means part of any change you observe may be the
        provider's, not yours. It is surfaced, never smoothed over.
        """
        by_engine: dict[str, set[str]] = defaultdict(set)
        for s in self.samples:
            by_engine[s.engine].update(s.models)
        return {e: tuple(sorted(m)) for e, m in by_engine.items() if len(m) > 1}

    @property
    def surface_mix(self) -> dict[str, tuple[str, ...]]:
        """Engines measured on more than one surface in this snapshot.

        Non-empty means the score blends logged-in, logged-out and API answers,
        which the published measurement says differ more from each other than
        reruns of the same surface do. The blend is not an average of the
        customer experience, it is an artefact of the collector.
        """
        by_engine: dict[str, set[str]] = defaultdict(set)
        for s in self.samples:
            by_engine[s.engine].update(s.surfaces)
        return {e: tuple(sorted(v)) for e, v in by_engine.items() if len(v) > 1}

    def for_engine(self, engine: str) -> Snapshot:
        """A new Snapshot narrowed to a single engine."""
        kept = tuple(s for s in self.samples if s.engine == engine)
        if not kept:
            raise ValueError(f"Snapshot {self.label!r} has no samples for engine {engine!r}")
        return Snapshot(label=f"{self.label}:{engine}", samples=kept, meta=dict(self.meta))

    def brands(self) -> tuple[str, ...]:
        """Every brand named at least once, sorted."""
        out: set[str] = set()
        for s in self.samples:
            for r in s.runs:
                out.update(r.brands)
        return tuple(sorted(out))


def group_runs(runs: Iterable[Run]) -> tuple[PromptSample, ...]:
    """Bundle a flat list of runs into one PromptSample per (prompt, engine).

    Order of runs inside a sample follows input order, so a caller that feeds
    runs chronologically keeps them chronological.
    """
    buckets: dict[tuple[str, str], list[Run]] = defaultdict(list)
    for r in runs:
        buckets[(r.prompt_id, r.engine)].append(r)
    return tuple(
        PromptSample(prompt_id=pid, engine=eng, runs=tuple(rs))
        for (pid, eng), rs in buckets.items()
    )


def snapshot_from_runs(label: str, runs: Sequence[Run], **meta: str) -> Snapshot:
    """Convenience builder: flat runs in, Snapshot out."""
    return Snapshot(label=label, samples=group_runs(runs), meta=dict(meta))
