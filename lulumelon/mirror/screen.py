"""The gates a generated question passes before anyone pays to ask it.

A model can write forty plausible questions about any brand in one call. That
part is cheap and nobody's advantage. What decides whether the questions are
worth a round is what happens next, and everything in this module is that: pure
functions, no model, no network, no money.

**The rule is not that a model may not write the questions. The rule is that
nothing it wrote is trusted.** Generation followed by measurement does not
break that rule, it is how the rule is kept.

Four gates run here, cheapest and most certain first, and the first one a
candidate trips is the reason recorded. That ordering is part of the contract
rather than an accident of implementation, so it is tested.

1. **shape** — a candidate carries its source page and a verbatim quote from
   it, or it is not a candidate. Both or neither is not an option here: a
   question with no citation cannot be checked against anything.
2. **name** — a question containing a tracked brand name is dropped. This is
   the single most common thing a model produces and the most damaging: a
   question carrying the name is answered with the name whatever the model
   knows, so it measures its own echo. One such question inflated a real
   headline by ten points before this gate existed.
3. **evidence** — the quote has to appear in **the page the candidate cites**
   as a literal substring, and a candidate citing a page that was never read
   fails here too, because a citation that resolves to nothing cannot be
   checked against anything. A model that invents a quote fails here, and it
   cannot route around it, because inventing a passing quote means reproducing
   text it was never given.

   Checked page by page rather than against the whole corpus on purpose. A
   quote lifted from one page and filed under another is a real quote and a
   false citation, and pooling every page into one haystack passes it. The
   rejection this gate writes says "the page it cites", so that is what it has
   to read.
4. **duplicate** — near-identical candidates collapse. This one is a
   heuristic and is labelled as such wherever it appears, since a Jaccard
   threshold is a judgement call and the other three are not.

Every rejection is returned with the gate that stopped it and a reason. A
candidate that vanishes silently is indistinguishable from one that was never
generated, and the difference is the whole audit trail.

**What the evidence gate does not prove.** It establishes that the quote is
real. It does not establish that the question follows from it, and a model
holding the page in its context can pair a genuine quote with an unrelated
question. That gap is deliberate and is closed downstream rather than here: a
question that has nothing to do with the site measures nothing, and the
measurement gate drops it as barren. Adding a third similarity heuristic here
would trade a checkable fact for a judgement, which is the trade this module
exists to avoid.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass

from .intervals import Interval, wilson_interval
from .variance import VarianceSplit, decompose

#: Word n-gram width for near-duplicate comparison. Three is the usual working
#: figure: pairs collide on any shared phrasing, and longer windows stop
#: catching a reordered question.
SHINGLE = 3

#: Jaccard overlap at or above which two questions are the same question.
#: A judgement, not a derivation, which is why the gate that uses it is the
#: only one of the four labelled a heuristic.
DEFAULT_DUPLICATE_THRESHOLD = 0.8

_WORD = re.compile(r"[\w']+", re.UNICODE)

#: The gates, in the order they run. Exported so a caller can report the
#: sequence without restating it and drifting from what the code does.
GATES = ("shape", "name", "evidence", "duplicate")


def normalise(text: str) -> str:
    """Case-folded, punctuation-free, single-spaced.

    Applied identically to a quote and to the page it claims to come from, so
    the literal check survives the ways HTML mangles whitespace without ever
    becoming a fuzzy match.
    """
    return " ".join(_WORD.findall(text.casefold()))


def shingles(text: str, width: int = SHINGLE) -> frozenset[tuple[str, ...]]:
    words = normalise(text).split()
    if len(words) < width:
        return frozenset({tuple(words)}) if words else frozenset()
    return frozenset(tuple(words[i : i + width]) for i in range(len(words) - width + 1))


def jaccard(left: str, right: str, width: int = SHINGLE) -> float:
    a, b = shingles(left, width), shingles(right, width)
    if not a or not b:
        return 1.0 if a == b else 0.0
    return len(a & b) / len(a | b)


@dataclass(frozen=True, slots=True)
class Candidate:
    """One generated question, with the page it claims to come from."""

    id: str
    text: str
    source: str = ""
    evidence: str = ""


@dataclass(frozen=True, slots=True)
class Rejection:
    """A candidate that did not survive, and what stopped it."""

    candidate: Candidate
    gate: str
    reason: str

    def as_text(self) -> str:
        return f"[{self.gate}] {self.candidate.id}: {self.reason}"


@dataclass(frozen=True, slots=True)
class ScreenResult:
    kept: tuple[Candidate, ...]
    rejected: tuple[Rejection, ...]

    @property
    def counts(self) -> dict[str, int]:
        """How many fell at each gate, including the gates that caught none.

        Reported whole rather than sparse, because a gate with a zero is a
        gate that ran and found nothing, and a gate missing from a summary
        reads as a gate that was never applied.
        """
        tally = dict.fromkeys(GATES, 0)
        for rejection in self.rejected:
            tally[rejection.gate] += 1
        return tally


#: A detector takes a text and returns the tracked names found in it. Passed in
#: rather than imported, because brand matching lives on the collecting side
#: and this module is not allowed to reach across that wall.
Detector = Callable[[str], Sequence[str]]


def screen(
    candidates: Iterable[Candidate],
    *,
    pages: Mapping[str, str],
    detect_names: Detector,
    duplicate_threshold: float = DEFAULT_DUPLICATE_THRESHOLD,
) -> ScreenResult:
    """Run every gate, keep what survives, and say why the rest did not.

    `pages` maps the url of every page that was actually read to its quotable
    text. A mapping rather than one joined corpus, because the evidence gate
    checks a quote against the page it was attributed to; given one string it
    could only check that the quote exists somewhere on the site, which is a
    weaker claim than the one the rejection prints.
    """
    if not 0.0 < duplicate_threshold <= 1.0:
        raise ValueError(f"duplicate threshold must be in (0, 1], got {duplicate_threshold}")

    haystacks = {url: normalise(text) for url, text in pages.items()}
    kept: list[Candidate] = []
    rejected: list[Rejection] = []

    for candidate in candidates:
        text = candidate.text.strip()
        if not text:
            rejected.append(Rejection(candidate, "shape", "the question is empty"))
            continue
        if not candidate.source or not candidate.evidence.strip():
            rejected.append(
                Rejection(
                    candidate,
                    "shape",
                    "carries no source page and quote, so nothing about it can be checked",
                )
            )
            continue

        named = tuple(detect_names(text))
        if named:
            rejected.append(
                Rejection(
                    candidate,
                    "name",
                    f"names a tracked brand ({', '.join(named)}), so it would measure its own echo",
                )
            )
            continue

        haystack = haystacks.get(candidate.source)
        if haystack is None:
            rejected.append(
                Rejection(
                    candidate,
                    "evidence",
                    "cites a page that was never read, so the quote resolves to nothing",
                )
            )
            continue
        if normalise(candidate.evidence) not in haystack:
            rejected.append(
                Rejection(
                    candidate,
                    "evidence",
                    "the quote is not in the page it cites",
                )
            )
            continue

        twin = next(
            (k for k in kept if jaccard(k.text, text) >= duplicate_threshold),
            None,
        )
        if twin is not None:
            rejected.append(
                Rejection(
                    candidate,
                    "duplicate",
                    f"near-identical to {twin.id} (heuristic, {duplicate_threshold:.2f} overlap)",
                )
            )
            continue

        kept.append(candidate)

    return ScreenResult(kept=tuple(kept), rejected=tuple(rejected))


def stable_ids(
    kept: Sequence[Candidate], previous: dict[str, str], prefix: str = "p"
) -> tuple[Candidate, ...]:
    """Keep the id of a question whose text has not changed.

    Ids are the join key every comparison groups by, so renumbering a set
    between rounds silently breaks the thing this repo exists to measure. A
    question that survives keeps its id; only genuinely new text gets a new
    one, and new ones never reuse a retired number.

    `previous` maps normalised question text to the id it already holds.
    """
    taken = set(previous.values())
    out: list[Candidate] = []
    counter = 0
    for candidate in kept:
        existing = previous.get(normalise(candidate.text))
        if existing is not None:
            out.append(Candidate(existing, candidate.text, candidate.source, candidate.evidence))
            continue
        counter += 1
        fresh = f"{prefix}{counter}"
        while fresh in taken:
            counter += 1
            fresh = f"{prefix}{counter}"
        taken.add(fresh)
        out.append(Candidate(fresh, candidate.text, candidate.source, candidate.evidence))
    return tuple(out)


# -- the measurement gate ---------------------------------------------------
#
# Everything above is free. This is the part that costs money, and it is the
# part the four gates exist to protect: no candidate reaches a paid draw until
# it has been shown to be real, grounded and distinct.

#: The question moved a rival's odds of being named. Keep it.
CARRIES = "carries"
#: The question named rivals in too few of its draws to be worth asking again.
BARREN = "barren"
#: The interval straddles the floor. Deliberately NOT a pass, for the same
#: reason `ablation.UNDECIDED` is not: a gate that opens when it cannot tell
#: opens exactly when the evidence is thinnest.
UNDECIDED = "undecided"

#: Ceiling on the derived draw count, so an unreachable floor returns a refusal
#: instead of a budget nobody would approve.
MAX_DERIVED_DRAWS = 60


def minimum_draws(floor: float, confidence: float = 0.95, cap: int = MAX_DERIVED_DRAWS) -> int:
    """Smallest `k` at which a clean sweep clears `floor`.

    Derived, never fixed. If a question is asked `k` times and names a rival
    every time, the Wilson lower bound on `k/k` still has to sit above the
    floor before that sweep means anything. Below this `k`, a perfect result
    is not evidence and the round buys undecideds.

    The count therefore follows the floor rather than a constant in this file:
    a stricter floor costs more draws, and the caller sees the price before
    paying it.
    """
    if not 0.0 <= floor < 1.0:
        raise ValueError(f"floor must be in [0, 1), got {floor}")
    for k in range(1, cap + 1):
        if wilson_interval(k, k, confidence=confidence).low > floor:
            return k
    raise ValueError(
        f"no draw count up to {cap} clears a floor of {floor:.3f} at "
        f"{int(confidence * 100)}% confidence; lower the floor or raise the cap"
    )


@dataclass(frozen=True, slots=True)
class PromptScreen:
    """One candidate, asked for real, and what its draws decided."""

    candidate: Candidate
    rival_hits: int
    draws: int
    floor: float
    interval: Interval
    verdict: str

    @property
    def kept(self) -> bool:
        return self.verdict == CARRIES

    def as_text(self) -> str:
        return (
            f"[{self.verdict}] {self.candidate.id}: rivals named in "
            f"{self.rival_hits}/{self.draws}, "
            f"{int(self.interval.confidence * 100)}% interval "
            f"{self.interval.low:.3f}..{self.interval.high:.3f} "
            f"against a floor of {self.floor:.3f}"
        )


def verdict_for(rival_hits: int, draws: int, floor: float, confidence: float = 0.95) -> PromptScreen:
    """Three-valued, and blind to the subject's own rate on purpose.

    **`rival_hits` counts answers naming a RIVAL, never the tracked brand.**
    That choice is the whole gate. Screening on the subject's own mentions
    means dropping the questions it scored zero on, which raises the headline
    by deleting the evidence against it. That is the inflation this repo was
    built to name, and a screen that did it would be doing it on purpose.

    The name of the field is the enforcement. A pure function cannot check
    where its integer came from, so the parameter is named for the only thing
    it is allowed to be.
    """
    if draws < 1:
        raise ValueError(f"a verdict needs at least one draw, got {draws}")
    if not 0 <= rival_hits <= draws:
        raise ValueError(f"rival_hits must be within 0..{draws}, got {rival_hits}")
    if not 0.0 <= floor < 1.0:
        raise ValueError(f"floor must be in [0, 1), got {floor}")

    interval = wilson_interval(rival_hits, draws, confidence=confidence)
    if interval.low > floor:
        verdict = CARRIES
    elif interval.high < floor:
        verdict = BARREN
    else:
        verdict = UNDECIDED
    return PromptScreen(
        candidate=Candidate("", ""),
        rival_hits=rival_hits,
        draws=draws,
        floor=floor,
        interval=interval,
        verdict=verdict,
    )


def screen_by_discrimination(
    observations: Sequence[tuple[Candidate, Sequence[float]]],
    *,
    floor: float,
    confidence: float = 0.95,
) -> tuple[PromptScreen, ...]:
    """Score every candidate from its own draws.

    Each entry pairs a candidate with one value per draw, 1 where the answer
    named a rival and 0 where it did not. Nothing here asks a model or a
    network; the draws are already recorded by the time they arrive.
    """
    out: list[PromptScreen] = []
    for candidate, draws in observations:
        values = list(draws)
        if not values:
            raise ValueError(f"candidate {candidate.id} carries no draws")
        scored = verdict_for(
            rival_hits=sum(1 for v in values if v > 0),
            draws=len(values),
            floor=floor,
            confidence=confidence,
        )
        out.append(
            PromptScreen(
                candidate=candidate,
                rival_hits=scored.rival_hits,
                draws=scored.draws,
                floor=scored.floor,
                interval=scored.interval,
                verdict=scored.verdict,
            )
        )
    return tuple(out)


def pool_variance(
    observations: Sequence[tuple[Candidate, Sequence[float]]], confidence: float = 0.95
) -> VarianceSplit:
    """The variance split across the whole candidate pool.

    The screening round is also the pilot, so the draws that decide which
    questions survive are the same draws that say how much the choice of
    question moves a score at all. `noise_floor` read off this pool is the
    number nobody in the category publishes, and it costs nothing extra
    because the calls were already made.
    """
    return decompose([list(draws) for _, draws in observations], confidence=confidence)
