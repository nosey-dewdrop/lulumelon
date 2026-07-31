"""One measurement round: ask the prompts k times, write down everything.

This is the loop the whole category gets wrong, and the mistakes are not subtle.
They ask each prompt once a day, they retry until they get a reply, and they
report the answers that survived. Each of those is a decision that moves the
number, and none of them is usually written down.

What this module does instead:

**k is a parameter, not a default of one.** A single ask is one draw from a
distribution. `mirror.variance.decompose` refuses to work on k=1 designs because
with one run per prompt the model's own dice and the prompt-to-prompt spread are
algebraically indistinguishable. The collector has to make k reachable or the
engine downstream has nothing to decompose.

**Nothing is retried and nothing is dropped.** A failed ask is appended with
`status="error"` and its reason. Retrying until success is a filter, and a
filter applied to answers is a thumb on the scale.

**The clock is injected.** `Run.asked_at` is documented as caller-supplied so
results stay reproducible; a round replayed from the ledger has to produce the
same timestamps it had the first time, which cannot happen if this file reads
the system clock on its own.

**One round, one surface, one engine.** Both come from the provider, so a round
cannot silently mix a logged-out browser with an API. The surface effect is
larger than the noise being measured, so mixing them would produce a number
about the collector rather than about the brand.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable, Sequence

from .ask import Answer, Provider
from .detect import Brand, detect
from .ledger import Ledger, Record


def utc_now() -> str:
    """Default clock. Injected rather than called inline so rounds replay."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True, slots=True)
class Prompt:
    """A tracked question and the id it will carry for the rest of its life.

    The id is what `mirror` groups by, so it has to be stable across rounds. If
    the text is edited the id must change, otherwise two different questions get
    pooled into one sample and the interval that comes out is meaningless.
    """

    id: str
    text: str


@dataclass(frozen=True, slots=True)
class RoundResult:
    """What a completed round is, in numbers, before anything is computed.

    `errors` is surfaced here rather than logged because a round that half
    failed is not a smaller round, it is a different one, and the caller has to
    decide what to do about that before reading any score.
    """

    snapshot_id: str
    asked: int
    ok: int
    errors: int

    @property
    def error_rate(self) -> float:
        return self.errors / self.asked if self.asked else 0.0


def run_round(
    *,
    ledger: Ledger,
    provider: Provider,
    prompts: Sequence[Prompt],
    brands: Sequence[Brand],
    k: int,
    subject: str,
    clock: Callable[[], str] = utc_now,
) -> RoundResult:
    """Ask every prompt `k` times and append every result to a new snapshot.

    Returns counts, never a score. Computing anything here would put a number
    on the same side of the wall as the network, and the reason `mirror` is
    reproducible from a file is that it never is.

    `k < 2` is refused. It is not an unsupported option, it is a design whose
    output cannot carry an interval, and accepting it here would let a caller
    produce a ledger that looks measurable and is not.
    """
    if k < 2:
        raise ValueError(
            f"k={k} cannot support an interval: with one draw per prompt the "
            "model's rerun noise and the prompt-to-prompt spread are not "
            "separable. Ask for at least 2, and see variance.runs_needed for "
            "how many this design actually requires."
        )
    if not prompts:
        raise ValueError("a round with no prompts is not a round")

    snapshot_id = ledger.next_snapshot_id(subject, provider.name, provider.surface)

    asked = ok = 0
    for prompt in prompts:
        for repeat in range(k):
            answer: Answer = provider.ask(prompt.text)
            asked += 1
            if answer.ok:
                ok += 1
            ledger.append(
                snapshot_id,
                Record(
                    snapshot_id=snapshot_id,
                    seq=0,  # the ledger assigns the real one; it owns the order
                    prompt_id=prompt.id,
                    repeat=repeat,
                    engine=provider.name,
                    surface=answer.surface,
                    model=answer.model,
                    asked_at=clock(),
                    status=answer.status,
                    latency_ms=answer.latency_ms,
                    answer_text=answer.text,
                    brands=detect(answer.text, tuple(brands)) if answer.ok else (),
                    citations=answer.citations,
                    provider=provider.name,
                    error=answer.error,
                ),
            )

    return RoundResult(snapshot_id=snapshot_id, asked=asked, ok=ok, errors=asked - ok)
