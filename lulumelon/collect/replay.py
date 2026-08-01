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

from .ledger import Ledger, is_diagnostic


@dataclass(frozen=True, slots=True)
class Replay:
    """A snapshot, split into what can be measured and what cannot.

    `dropped` counts asks with a non-ok status, and the record that closes a
    round is not an ask, so it is in neither number. `engines`, `surfaces` and
    `models` are the distinct values seen in the round: more than one of any of
    them means the snapshot mixes conditions, and `mirror.compare` will refuse
    to compare it with anything. Surfaced here so that refusal is not a surprise
    later.

    The engine is on that list for the same reason the other two are, and it
    was the one missing. `session.run_round` asks through a single provider and
    stamps its name on every record, and the engine is part of the snapshot's
    own file name, so a round is one engine the way it is one surface. Two of
    them in one file is not a round, and a reader that could see the mixed
    surface but not the mixed engine could be told a number was about one
    provider when half of it came from another.
    """

    runs: tuple[Run, ...]
    dropped: int
    engines: tuple[str, ...]
    surfaces: tuple[str, ...]
    models: tuple[str, ...]

    @property
    def total(self) -> int:
        return len(self.runs) + self.dropped

    @property
    def is_single_condition(self) -> bool:
        return len(self.engines) <= 1 and len(self.surfaces) <= 1 and len(self.models) <= 1

    def as_text(self) -> str:
        head = f"{len(self.runs)} usable of {self.total} asked"
        if self.dropped:
            head += f", {self.dropped} recorded as errors and excluded"
        if not self.is_single_condition:
            head += (
                f"\nWARNING: this round mixes conditions "
                f"(engines: {', '.join(self.engines)}; "
                f"surfaces: {', '.join(self.surfaces)}; models: {', '.join(self.models)}); "
                "a score computed across them describes the collector as much as the brand"
            )
        return head


def replay(ledger: Ledger, snapshot_id: str) -> Replay:
    """Read one snapshot and hand back the measurable part of it, plus the rest.

    A diagnostic round is refused here rather than filtered out further along.
    This is the one door between a written round and a `Run`, and `Run` is the
    only thing `mirror` consumes, so refusing at this door is what makes "a
    check call is never pooled into a brand measurement" a property of the code
    instead of a rule in a comment. The call still cost money and is still on
    the record; `lulu usage` reads it from the ledger without coming through
    here.
    """
    if is_diagnostic(snapshot_id):
        raise ValueError(
            f"{snapshot_id} is a diagnostic round: it is one call made to prove a key "
            "spends, asked with no brand list and answered once. it is priced by lulu "
            "usage and it is not a sample, so nothing is scored from it"
        )

    runs: list[Run] = []
    dropped = 0
    engines: dict[str, None] = {}
    surfaces: dict[str, None] = {}
    models: dict[str, None] = {}

    for rec in ledger.read(snapshot_id):
        if rec.is_seal:
            # The record that says how long the round was is not one of the
            # asks it counts. Left to the branch below it would be excluded as
            # a failure, and `dropped` is printed as the number of asks that
            # did not come back: one seal would report every round as having
            # lost a call it never made.
            continue
        if rec.status != "ok":
            dropped += 1
            continue
        engines[rec.engine] = None
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
        engines=tuple(engines),
        surfaces=tuple(surfaces),
        models=tuple(models),
    )
