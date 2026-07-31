"""One measurement round: ask the prompts k times, write down everything.

A collection loop makes three choices that move the resulting number, and each
one is easy to make by accident: how many times a prompt is asked, what happens
to an ask that fails, and whether one round is allowed to mix conditions. None
of them announce themselves, and all three are usually invisible by the time
anyone reads a score.

They are made explicitly here:

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

**Running out of money ends the round rather than raising.** The asks already
made are observations and a traceback would throw them away, so a round that
hit its ceiling comes back shorter, with the count of what it never asked. That
count is the only thing that tells a reader the interval is wider than the
design asked for, because the ledger of a round cut short and the ledger of a
small round look the same on disk.

**A round closes by writing down how long it was.** Every exit from the loop
below leads to one seal, including the exit where the budget stopped the round
before its first call. A round the budget cut short and a round somebody has
deleted lines from are then different files rather than the same one: the first
states the number of calls it made and holds exactly that many, and the second
states nothing, because the record that would have stated it is the first thing
removing the tail of a file takes away.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable, Sequence

from .ask import Answer, Provider
from .budget import Budget
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

    A round stopped by its budget is the same kind of fact, which is why
    `planned` sits next to `asked` instead of being recoverable from the
    arguments. Nothing on disk distinguishes a round that was cut short from a
    round that was small, so without those two side by side the missing draws
    become invisible at exactly the moment they matter: they are what makes the
    interval downstream wider than the design was sized for.
    """

    snapshot_id: str
    asked: int
    ok: int
    errors: int
    planned: int
    stopped_for_budget: bool = False

    @property
    def error_rate(self) -> float:
        return self.errors / self.asked if self.asked else 0.0

    @property
    def unasked(self) -> int:
        """Asks the round was sized for and never made."""
        return max(0, self.planned - self.asked)

    def as_text(self) -> str:
        line = f"asked {self.asked} of {self.planned}, {self.ok} answered, {self.errors} failed"
        if self.stopped_for_budget:
            line += f"; stopped for budget, {self.unasked} never asked"
        return line


def run_round(
    *,
    ledger: Ledger,
    provider: Provider,
    prompts: Sequence[Prompt],
    brands: Sequence[Brand],
    k: int,
    subject: str,
    clock: Callable[[], str] = utc_now,
    budget: Budget | None = None,
) -> RoundResult:
    """Ask every prompt `k` times and append every result to a new snapshot.

    Returns counts, never a score. Computing anything here would put a number
    on the same side of the wall as the network, and the reason `mirror` is
    reproducible from a file is that it never is.

    `k < 2` is refused. It is not an unsupported option, it is a design whose
    output cannot carry an interval, and accepting it here would let a caller
    produce a ledger that looks measurable and is not.

    Without a `budget` the round asks everything it was given, which is the
    right default for a round somebody is watching. With one, each ask is
    checked against that ask's own ceiling before it is made, because the
    cheapest place to find out a call did not fit is before paying for it.
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

    # Flattened before the loop so that running out of budget leaves through
    # one exit. A nested break needs a flag to carry it out of the inner loop,
    # and a flag read one indent later is where a round quietly asks one more.
    draws = [(prompt, repeat) for prompt in prompts for repeat in range(k)]

    asked = ok = 0
    stopped_for_budget = False
    for prompt, repeat in draws:
        if budget is not None and not budget.can_afford_another():
            stopped_for_budget = True
            break

        answer: Answer = provider.ask(prompt.text)
        asked += 1
        if answer.ok:
            ok += 1
        if budget is not None:
            # Charged here rather than after the write, because the call is
            # paid for the moment it comes back and the ledger cannot undo it.
            budget.charge(answer)
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
                # Written from what the provider reported, and left unknown
                # when it reported nothing. This is the only place a call's
                # cost enters the permanent record; a round collected
                # without it can never be priced afterwards, because the
                # response it would have been priced from is gone.
                input_tokens=answer.usage.input_tokens,
                output_tokens=answer.usage.output_tokens,
                search_context=answer.usage.search_context,
                reported_cost_usd=answer.usage.cost_usd,
                # The number a per-search fee multiplies. Stored from v3 on,
                # so a round priced off this file bills the searches it made
                # rather than one per call, which is what the budget guard was
                # already charging while it was running.
                searches=answer.usage.searches,
            ),
        )

    # After the loop and before the counts are handed back, so the round is
    # closed on disk by the same pass that made it. A caller that had to
    # remember to seal would eventually not, and a round nobody sealed is
    # indistinguishable from one somebody shortened.
    ledger.seal(snapshot_id, asked=asked, ok=ok, errors=asked - ok, at=clock())

    return RoundResult(
        snapshot_id=snapshot_id,
        asked=asked,
        ok=ok,
        errors=asked - ok,
        planned=len(draws),
        stopped_for_budget=stopped_for_budget,
    )
