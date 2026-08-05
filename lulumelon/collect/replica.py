"""Asking the same question with the source list handed over, on purpose.

A live answer engine picks its own sources, so what it retrieves and what it
says move together and neither can be held still. A replica holds them still:
the same model is asked the same question with a source list supplied as
context, and the list is ours to change. Removing one source and asking again
is the only contrast in this repo that can support a sentence about cause
rather than about company.

Nothing here computes anything, in keeping with the wall this package is built
around. It composes a prompt, hands it to a provider, and labels what comes
back. Whether the replica may be reasoned from at all is decided in
`mirror.ablation`, from the numbers, after the fact.

**The wording is the instrument.** Two replicas built with different phrasing
are two different experiments, so `INSTRUCTION` is a versioned constant rather
than an f-string assembled at the call site, and its version is recorded with
every round. A result that cannot be traced to the exact instrument that
produced it is a result nobody can repeat, including us.

**It supplies, it does not instruct.** The wording deliberately does not say
"answer from these" or "prefer these". A prompt that does turns the model into
a summariser of whatever it was handed, and a summariser will name a brand
because the brand is in the text, which is the finding, arriving as an artefact
of the question. What the wording does is put the material in front of the
model the way a retrieval step would, and then ask the question it would have
been asked anyway.

**A replica is its own surface, and so is each arm of one.** Rounds collected
this way are recorded under a surface beginning `replica`, so a snapshot mixing
them with live answers is not a single condition and `mirror` refuses to pool
it. The one place the two are compared is the gate, which exists to compare
them and says so on screen.

The rest of that surface string is a digest of the exact material the arm was
shown. Without it, two replica rounds sitting in a ledger are indistinguishable:
the list a round was asked under lives only in the process that asked it, so an
ablation's treatment would be a claim on the command line rather than a fact in
the evidence file, and `without`'s refusal to remove nothing would guard the
collection and nothing afterwards. With it, a later reader supplies the list it
believes was used and the ledger either agrees or does not.

The digest covers the wording as well as the sources, so an edit to the
instruction changes it whether or not anybody remembered to bump the version
beside it. The version number is there to be read; the digest is what binds.
And because it is one-way, the ledger ends up proving which list was used
without storing the customer's list.

**An ablation that removes nothing is refused.** `without` raises when the
source it was told to drop is not in the list. A silent no-op would produce two
identical arms, a difference of zero, and a confident conclusion that the
source does not matter, which is the most damaging wrong answer this file could
return.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field, replace

from .ask import Answer, Provider

#: The surface family a replica round is recorded under. Not one of the live
#: doors, because it is not a door: nobody reaches an answer engine this way,
#: and a number collected here must never be presented as what a user sees.
#: A round's own surface extends this with the digest of what it was shown.
REPLICA_SURFACE = "replica"

#: Hex characters kept from the digest. Enough that two different lists
#: colliding is not a thing that happens; short enough to read off a filename,
#: since the surface goes into the snapshot id.
FINGERPRINT_CHARS = 12

#: Version of the wording below. Recorded with every replica round. Bump it for
#: any edit at all, including punctuation: a replica is only comparable with
#: another replica built by the same instrument, and "it was only a comma" is
#: how two incomparable rounds get averaged together.
INSTRUCTION_VERSION = 1

#: Supplies material and then asks the question. It does not tell the model
#: what to do with the material, because an instruction to use it manufactures
#: the effect being measured.
INSTRUCTION = (
    "The following pages are available to you.\n\n"
    "{sources}\n\n"
    "Question: {question}"
)

#: How each supplied page is rendered. Numbered so a later verdict can name
#: which position a source held, since position in a supplied list is itself a
#: treatment and a replica that shuffles silently is measuring two things.
SOURCE_LINE = "[{n}] {url}"


def replica_prompt(question: str, sources: Sequence[str]) -> str:
    """The exact string a replica asks, for one question and one source list.

    Order is preserved rather than sorted. Where a source sits in the list is a
    condition of the experiment, so reordering it here would silently change
    the treatment between two arms that are supposed to differ in one thing.
    """
    if not question.strip():
        raise ValueError("a replica needs a question to ask")
    if not sources:
        raise ValueError(
            "a replica with no sources is not a replica, it is the ungrounded model; "
            "that is a legitimate arm of an experiment and it is asked for explicitly"
        )
    listed = "\n".join(SOURCE_LINE.format(n=i, url=url) for i, url in enumerate(sources, start=1))
    return INSTRUCTION.format(sources=listed, question=question.strip())


def source_fingerprint(
    sources: Sequence[str],
    *,
    instruction_version: int = INSTRUCTION_VERSION,
    instruction: str = INSTRUCTION,
) -> str:
    """A short, order-sensitive digest of exactly what one arm was shown.

    Order is inside the digest because position in a supplied list is part of
    the treatment, so the same three pages in a different order are a different
    arm and have to be a different string.

    The wording is inside it too. `INSTRUCTION_VERSION` asks a person to
    remember; this does not need them to. Two arms built by instruments that
    differ by a comma are not the same experiment, and here they cannot claim
    to be.
    """
    if not sources:
        raise ValueError("a replica arm with no sources has no treatment to fingerprint")
    canonical = json.dumps(
        [instruction_version, instruction, list(sources)],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return digest[:FINGERPRINT_CHARS]


def replica_surface(
    sources: Sequence[str],
    *,
    instruction_version: int = INSTRUCTION_VERSION,
    instruction: str = INSTRUCTION,
) -> str:
    """The surface one replica arm records itself under.

    Reads as `replica-v1-3f2a...`: the family, the instrument version for a
    human, and the digest that actually binds the round to its treatment.
    """
    fingerprint = source_fingerprint(
        sources, instruction_version=instruction_version, instruction=instruction
    )
    return f"{REPLICA_SURFACE}-v{instruction_version}-{fingerprint}"


def is_replica_surface(surface: str) -> bool:
    """True for any laboratory surface, including rounds written before digests.

    A bare `replica` is accepted here because it is one, and refusing to read it
    would make an old evidence file unreadable rather than unverifiable. What it
    cannot do is prove which list it was asked under, and the caller that needs
    that proof asks for it separately rather than inferring it from this.
    """
    return surface == REPLICA_SURFACE or surface.startswith(f"{REPLICA_SURFACE}-")


def without(sources: Sequence[str], drop: str) -> tuple[str, ...]:
    """The same list with one source removed, or an error saying it was not there.

    Raising is the point. An ablation that removed nothing produces two
    identical arms, a measured difference of zero, and the conclusion that the
    source does not matter, which is indistinguishable on screen from a real
    finding and is the opposite of one.
    """
    if drop not in sources:
        raise ValueError(
            f"{drop!r} is not in this source list, so removing it changes nothing and the "
            "two arms would be the same experiment run twice"
        )
    return tuple(url for url in sources if url != drop)


@dataclass
class ReplicaProvider:
    """A provider that asks through a fixed source list.

    Wraps any `Provider`, so the collector, the ledger and the whole replay
    path are reached unchanged, and a replica round can be driven end to end
    against the deterministic stub with no key and no spend.

    `sources` is fixed at construction rather than passed per call, for the
    same reason `surface` is an attribute of a provider: an arm of an
    experiment whose treatment can change halfway through is not an arm.
    """

    base: Provider
    sources: tuple[str, ...]
    instruction_version: int = INSTRUCTION_VERSION
    surface: str = field(init=False)
    name: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.sources:
            raise ValueError(
                "a replica provider needs the sources it is holding constant; pass the "
                "list explicitly, including when it is the full one"
            )
        self.sources = tuple(self.sources)
        seen = sorted({url for url in self.sources if self.sources.count(url) > 1})
        if seen:
            raise ValueError(
                f"the source list repeats {seen}: a page supplied twice is a page given "
                "twice the room, which is a treatment nobody chose"
            )
        # Derived, never accepted. A surface that can be passed in is a label
        # that can be passed in wrong, and the one mistake worth engineering
        # against here is two arms filed under one treatment.
        self.surface = replica_surface(
            self.sources, instruction_version=self.instruction_version
        )
        self.name = self.base.name

    @property
    def max_output_tokens(self) -> int:
        """The cap the engine underneath carries, reported rather than held.

        A wrapper that kept its own copy would be a second place the number
        lives, which is the defect this attribute exists to close.
        """
        return self.base.max_output_tokens

    def with_output_cap(self, max_output_tokens: int) -> ReplicaProvider:
        return replace(self, base=self.base.with_output_cap(max_output_tokens))

    def without_search(self) -> ReplicaProvider:
        """Itself. This instrument's whole treatment is the sources it holds constant.

        The surface it reports names those sources, and a copy that turned the
        base engine's tool off would carry the same name while being a
        different treatment.
        """
        return self

    def ask(self, question: str) -> Answer:
        """Ask through the source list, and label the answer as a replica.

        The surface is overwritten on the way back rather than trusted from the
        base provider, which reports the door it used and has no idea it is
        being used as an instrument. A replica answer that reached the ledger
        labelled `api` would be poolable with live data, and the wall between
        what a user sees and what a laboratory produced would be gone.
        """
        answer = self.base.ask(replica_prompt(question, self.sources))
        return Answer(
            text=answer.text,
            model=answer.model,
            surface=self.surface,
            latency_ms=answer.latency_ms,
            citations=answer.citations,
            status=answer.status,
            error=answer.error,
            usage=answer.usage,
        )

    def dropping(self, source: str) -> ReplicaProvider:
        """The other arm: the same instrument with one source taken out.

        The surface is not carried over. Handing the child its parent's label
        would file two different treatments under one name, which is the exact
        thing the label was added to prevent.
        """
        return ReplicaProvider(
            base=self.base,
            sources=without(self.sources, source),
            instruction_version=self.instruction_version,
        )
