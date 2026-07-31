"""Turning a written round back into something the engine can measure.

`mirror` consumes `Run` objects and is not allowed to know that a disk or a
network exists. The ledger stores `Record` objects, which are a superset: they
also carry the answer text, the latency, the provider and the failure reason, so
a published number can be walked back to the sentence that produced it.

The only interesting decision here is what to do with the failures, and it is a
measurement decision rather than a plumbing one.

A run that errored is not a run where the brand went unmentioned. A timeout is
missing data; an answer that named nobody is an observed zero. Counting the
first as the second pushes every visibility number down by however often the
collector happened to be unlucky, which is a property of the network rather than
of the brand.

So failures are excluded from the sample and **returned alongside it**, never
silently. A caller cannot get the runs without also being handed the count of
what did not make it, because the tidy version of this function is exactly how
a biased measurement gets built by accident.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..mirror.types import Run

from .ledger import Ledger


@dataclass(frozen=True, slots=True)
class Replay:
    """A snapshot, split into what can be measured and what cannot.

    `dropped` counts records with a non-ok status. `surfaces` and `models` are
    the distinct values seen in the round: more than one of either means the
    snapshot mixes conditions, and `mirror.compare` will refuse to compare it
    with anything. Surfaced here so that refusal is not a surprise later.
    """

    runs: tuple[Run, ...]
    dropped: int
    surfaces: tuple[str, ...]
    models: tuple[str, ...]

    @property
    def total(self) -> int:
        return len(self.runs) + self.dropped

    @property
    def is_single_condition(self) -> bool:
        return len(self.surfaces) <= 1 and len(self.models) <= 1

    def as_text(self) -> str:
        head = f"{len(self.runs)} usable of {self.total} asked"
        if self.dropped:
            head += f", {self.dropped} recorded as errors and excluded"
        if not self.is_single_condition:
            head += (
                f"\nWARNING: this round mixes conditions "
                f"(surfaces: {', '.join(self.surfaces)}; models: {', '.join(self.models)}); "
                "a score computed across them describes the collector as much as the brand"
            )
        return head


def replay(ledger: Ledger, snapshot_id: str) -> Replay:
    """Read one snapshot and hand back the measurable part of it, plus the rest."""
    runs: list[Run] = []
    dropped = 0
    surfaces: dict[str, None] = {}
    models: dict[str, None] = {}

    for rec in ledger.read(snapshot_id):
        if rec.status != "ok":
            dropped += 1
            continue
        surfaces[rec.surface] = None
        models[rec.model] = None
        runs.append(
            Run(
                prompt_id=rec.prompt_id,
                engine=rec.engine,
                model=rec.model,
                asked_at=rec.asked_at,
                brands=rec.brands,
                citations=rec.citations,
                surface=rec.surface,
            )
        )

    return Replay(
        runs=tuple(runs),
        dropped=dropped,
        surfaces=tuple(surfaces),
        models=tuple(models),
    )
