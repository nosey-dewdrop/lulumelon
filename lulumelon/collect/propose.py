"""Ask a model for candidate questions, and trust nothing it sends back.

This is the only step in the whole draft path that costs money before any
measurement exists, and it is deliberately the least clever one. It builds a
request out of pages that were already read, makes one call, and turns the
reply into records. It decides nothing about whether a question is any good;
that judgement is made by pure functions downstream, on evidence, and it is
made after this module has already handed everything over.

**The rule is not that a model may not write the questions.** It is that
nothing it writes is trusted. A generated question arrives here with a page it
claims to come from and a quote it claims is on that page, and both claims are
checkable against text the model was given rather than against the model's own
confidence. Generation followed by verification does not bend that rule, it is
how the rule is kept.

**Nothing about the request comes from a list kept in this file.** There is no
vocabulary of interesting topics, no bank of question templates, no category
dictionary. Every noun the model sees is the customer's own text, which is the
whole reason a site that describes itself in Turkish or in a field nobody here
has heard of gets the same treatment as one that reads like every SaaS
homepage. The fixed part is the instruction, and the instruction names no
subject matter at all.

**One call, no retry, and a reply that cannot be read is kept.** A retry loop
is a filter over model output, and a filter over model output is the thing this
repo exists to refuse. A malformed entry is recorded with what arrived and why
it could not be read, so a round that produced ten usable candidates out of
forty is distinguishable from one that produced ten.

**A page is truncated on the way in, never on the way out.** The model is shown
the opening of each page so a large site still fits one call, and the evidence
gate later checks quotes against the *whole* page. That asymmetry is safe in
the only direction that matters: the model can only quote what it was shown,
and what it was shown is a subset of what it is checked against, so truncation
can cost a candidate and can never pass a false one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Sequence

from .ask import Answer, Provider
from .budget import Budget, token_ceiling, tokens_for_chars
from .harvest import SiteCorpus

#: Characters of each page shown to the model. A ceiling on the request, not a
#: claim about where a page stops being interesting: the opening of a page is
#: what a site puts its own summary in, and the evidence check runs against the
#: entire page regardless of how much of it was shown.
DEFAULT_PAGE_CHARS = 4_000

#: Candidates asked for in one call. Asked for, never relied on: the gates
#: downstream decide how many survive, and a model that returns nine when it
#: was asked for forty has produced a smaller pool, not a failure.
DEFAULT_WANTED = 40

#: Characters one candidate takes in the reply, measured off a real one rather
#: than assumed: the first paid proposing call this repo made wrote entries of
#: 219 characters, a question with the URL it cites, the words it quotes and
#: the JSON framing all three. 300 is that with room for a longer quote and a
#: deeper URL than the one that happened to come first.
CHARS_PER_CANDIDATE = 300

#: The array's own brackets, the code fence a model wraps them in, and the
#: line it sometimes writes before starting.
FRAME_CHARS = 300


def output_cap_for(wanted: int) -> int:
    """The room one call needs to write `wanted` candidates and stop on its own.

    Derived from the size of a candidate, because the only thing this number
    has to be true about is whether the answer fits. A round one was the reason
    for the derivation: forty candidates were asked for under a cap of 1,024
    tokens that lived in the network layer, the reply stopped inside a value,
    and a call that cost real money came back as zero candidates and one entry
    nobody could read. Nothing in the reply said it had been cut off; it simply
    ended, and a JSON array that ends early is indistinguishable from a model
    that writes bad JSON until you notice you set the ending yourself.
    """
    if wanted < 1:
        raise ValueError(f"a call asking for {wanted} questions is not a call worth paying for")
    return tokens_for_chars(wanted * CHARS_PER_CANDIDATE + FRAME_CHARS)


@dataclass(frozen=True, slots=True)
class Proposal:
    """One question a model wrote, exactly as it wrote it.

    Carried verbatim, including whitespace the model chose, because the quote
    is about to be checked as a literal substring and normalising it here would
    move that decision into the part of the system that is allowed to be wrong.
    """

    text: str
    source: str
    evidence: str


@dataclass(frozen=True, slots=True)
class Malformed:
    """An entry in the reply that could not be read as a proposal at all.

    Kept rather than skipped. A model that returns forty entries of which
    twelve are unreadable has told us something about the call, and a parser
    that dropped them silently would report the same twenty-eight candidates as
    a model that behaved perfectly.
    """

    raw: str
    reason: str


@dataclass(frozen=True, slots=True)
class ProposalResult:
    """What one paid call produced, including the case where it was refused."""

    proposals: tuple[Proposal, ...] = ()
    malformed: tuple[Malformed, ...] = ()
    #: The provider's reply, kept whole so the caller can write it to the
    #: ledger. This module does not touch the ledger; a proposal round that
    #: wrote its own record would be a second place rounds are appended from.
    answer: Answer | None = None
    #: False when no call was made, and then `refusal` says why. A round that
    #: could not afford its call and a round whose model returned nothing are
    #: different events and cost different amounts.
    asked: bool = False
    refusal: str = ""

    @property
    def usable(self) -> int:
        return len(self.proposals)

    def as_text(self) -> str:
        if not self.asked:
            return f"no call was made: {self.refusal}"
        line = f"{len(self.proposals)} proposals read"
        if self.malformed:
            line += f", {len(self.malformed)} entries unreadable"
        if self.answer is not None and not self.answer.ok:
            line += f"; the call failed: {self.answer.error}"
        return line


def pages_for_screening(corpus: SiteCorpus) -> dict[str, str]:
    """The mapping the evidence gate checks against, whole pages, untruncated.

    Built here rather than by the caller so the urls a candidate may cite and
    the urls it is checked against come from one place. Two call sites building
    this dict differently is how a citation becomes uncheckable.
    """
    return {page.url: page.quotable for page in corpus.pages}


def request_for(
    corpus: SiteCorpus, *, wanted: int = DEFAULT_WANTED, page_chars: int = DEFAULT_PAGE_CHARS
) -> str:
    """The one prompt this module sends, built entirely out of the site.

    The instruction below names no industry, no product category and no example
    question. It describes the shape of the answer and the two properties every
    entry has to carry, and everything it has to write about arrives underneath
    it as the customer's own pages.
    """
    if wanted < 1:
        raise ValueError(f"a call asking for {wanted} questions is not a call worth paying for")
    if page_chars < 1:
        raise ValueError(f"page_chars must be positive, got {page_chars}")
    if corpus.is_empty:
        raise ValueError(
            "no page of this site was read, so there is nothing to ground a question in; "
            "harvest reported what it could not reach and that is the thing to fix first"
        )

    blocks = []
    for page in corpus.pages:
        body = page.quotable[:page_chars]
        blocks.append(f"URL: {page.url}\n{body}")
    body = "\n\n".join(blocks)

    return (
        f"Below are pages from one company's website, each with its URL.\n\n"
        f"Write {wanted} questions a person might type into an AI assistant when they are "
        f"looking for what this company sells, without knowing this company exists.\n\n"
        f"Rules for every question:\n"
        f"- It must not contain the company's name, or any brand name at all. A question "
        f"carrying the name is answered with the name and measures nothing.\n"
        f"- It must be answerable by naming companies, not by explaining a concept.\n"
        f"- It must cite one URL from the list below, and quote from that page the words "
        f"that made you write it. Copy the quote character for character from the page. A "
        f"quote you reworded will be rejected automatically, and so will a quote taken from "
        f"a page other than the one you cite.\n\n"
        f"Reply with a JSON array and nothing else. Every element is an object with exactly "
        f'the keys "question", "source" and "evidence".\n\n'
        f"{body}"
    )


def _entries(text: str) -> tuple[list[object], str]:
    """The reply as a list of entries, or an empty list and the reason why.

    The array is found by scanning to the outermost brackets rather than by
    parsing the whole reply, which is what makes a fenced or prefaced answer
    readable without a rule per wrapper. A stripper for code fences was written
    here first and deleted: a mutation test put it back to the plain scan and
    the suite stayed green, so it was decoration standing where a reader would
    look for the thing doing the work.
    """
    stripped = text.strip()
    start, end = stripped.find("["), stripped.rfind("]")
    if start == -1 or end <= start:
        return [], "the reply contains no JSON array"
    try:
        parsed = json.loads(stripped[start : end + 1])
    except (json.JSONDecodeError, ValueError) as exc:
        return [], f"the JSON array in the reply does not parse ({exc})"
    if not isinstance(parsed, list):
        return [], "the reply parsed to something that is not a list"
    return parsed, ""


def _field(entry: dict, *names: str) -> str:
    for name in names:
        value = entry.get(name)
        if isinstance(value, str):
            return value
    return ""


def read_reply(text: str) -> tuple[tuple[Proposal, ...], tuple[Malformed, ...]]:
    """Turn a reply into proposals, and say what could not be turned into one.

    Only unreadable entries are rejected here. An entry that parses but carries
    an empty quote is passed on intact, because the gate that refuses it lives
    in the pure layer and refusing it twice in two places is how the two
    definitions drift apart.
    """
    entries, failure = _entries(text)
    if failure:
        return (), (Malformed(raw=text[:400], reason=failure),)

    proposals: list[Proposal] = []
    malformed: list[Malformed] = []
    for entry in entries:
        if not isinstance(entry, dict):
            malformed.append(Malformed(raw=str(entry)[:200], reason="entry is not an object"))
            continue
        question = _field(entry, "question", "text", "prompt")
        if not question.strip():
            malformed.append(
                Malformed(raw=json.dumps(entry)[:200], reason="entry carries no question text")
            )
            continue
        proposals.append(
            Proposal(
                text=question.strip(),
                source=_field(entry, "source", "url").strip(),
                evidence=_field(entry, "evidence", "quote"),
            )
        )
    return tuple(proposals), tuple(malformed)


def propose(
    corpus: SiteCorpus,
    *,
    provider: Provider,
    wanted: int = DEFAULT_WANTED,
    page_chars: int = DEFAULT_PAGE_CHARS,
    budget: Budget | None = None,
) -> ProposalResult:
    """Make one call and hand back what came of it.

    Returns rather than raises when the budget will not cover the call, for the
    same reason a round that runs out of money comes back short instead of
    throwing: the caller has already done free work worth keeping, and a
    traceback would take the corpus down with the refusal.

    A failed call is not retried. It comes back with the provider's own error
    on the answer, and the caller writes that to the ledger like any other
    failure, because a call that failed is a fact about the round.
    """
    request = request_for(corpus, wanted=wanted, page_chars=page_chars)
    cap = output_cap_for(wanted)
    room = token_ceiling(request)

    if budget is not None and not budget.can_afford_another(input_tokens=room, output_tokens=cap):
        ceiling = budget.next_call_ceiling_usd(input_tokens=room, output_tokens=cap)
        return ProposalResult(
            asked=False,
            refusal=(
                f"the next call could cost {ceiling:.6f} usd and "
                f"{budget.remaining_usd:.6f} usd of the ceiling is left"
            ),
        )

    # Capped for this call rather than for the round. The provider handed in
    # is the one the measuring draws will use afterwards, and each of those is
    # one answer to one question; raising its cap here would price every draw
    # in the round at the size of this one call.
    answer = provider.with_output_cap(cap).ask(request)
    if budget is not None:
        budget.charge(answer, input_tokens=room, output_tokens=cap)

    if not answer.ok:
        return ProposalResult(answer=answer, asked=True)

    proposals, malformed = read_reply(answer.text)
    return ProposalResult(proposals=proposals, malformed=malformed, answer=answer, asked=True)


def as_candidate_rows(proposals: Sequence[Proposal]) -> tuple[dict[str, str], ...]:
    """Proposals as plain dicts, for a caller that builds the pure layer's type.

    `collect/` does not import `mirror/`, so the object the gates run on is
    built above both walls. This hands over the fields under the names that
    type uses and stops there.
    """
    return tuple(
        {"text": p.text, "source": p.source, "evidence": p.evidence} for p in proposals
    )
