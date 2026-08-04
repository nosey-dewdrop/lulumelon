"""Which names an engine reaches for, counted off answers that named nobody for it.

Every other count in this package is about names somebody declared first. This
one is the opposite direction: the questions carry no company in them, and what
comes back is whatever the model already believed. Reading that list is how a
customer finds out who it is actually competing with inside an answer, which is
not the list it would have written down.

**Nothing here is a rival.** This module counts names and judges none of them.
A rival is a name a person recognises as one, and a table that decided for them
would be this library asserting a market it cannot see. What it produces is
countable and checkable, and the judgement stays where it belongs.

**A name is only a name if it survives being read as a heading.** The first
pass at this, written as a throwaway script, reported `Reliability` and `Key
Considerations` alongside `Alpha Vantage`, because a model writing a structured
answer capitalises its section titles exactly the way it capitalises a company.
A stop word list would have removed those two and waited for the next three, so
the rule here is positional instead: a candidate counts only if it appears at
least once inside a sentence, somewhere that is not the first word. A heading
never does. A company mentioned in prose always will.

**The unit is the question, not the answer.** A name in all six draws of one
question and a name in one draw of six questions are not the same finding, and
counting either as "six" makes them look identical. The first is that question
having a stable answer, and the second is the model reaching for that name
whatever it is asked. So the count is kept per question and the number of
questions is reported beside it.

**Nothing is inferred, extracted or corrected.** Every name printed appears
character for character in a recorded answer, which is the same rule the
evidence gate holds a quote to. There is no model call in this file and no
network anywhere near it: the same records produce the same table forever.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Sequence

from ..text import counted
from .types import Reply

#: One word of a name. It has to open with a capital or a digit, because names
#: like `3Commas` exist, and it has to carry a capital somewhere, because years
#: and quantities otherwise arrive as names. The inner characters allow the
#: punctuation that lives inside real ones: `Polygon.io`, `S&P`, `Moody's`.
_WORD = r"[A-Z0-9][\w&.'’-]*"

#: A candidate is adjacent capitalised words and nothing else. No connective is
#: allowed through, and that is deliberate: reading `and` as part of a name
#: turns `TradingView and QuantConnect` into one company that does not exist.
#: A word that ends in a full stop ends the run for the same reason, or the
#: year closing one sentence joins the word opening the next.
_CANDIDATE = re.compile(rf"{_WORD}(?:(?<![.!?]) {_WORD})*")

#: Characters that end a sentence, so what follows opens one. The colon is in
#: here because a model labels with it, and `Reliability: Most platforms` puts
#: an ordinary adjective exactly where a company would otherwise stand.
_ENDS_A_SENTENCE = ".!?;:"

#: Where a cell begins. A table is the other place a model writes labels the
#: way it writes companies, and the first words of a cell are that table's
#: vocabulary rather than its findings: `Free`, `Excellent`, `Use Case`.
_STARTS_A_CELL = "|\n"

#: Markdown a model puts before a line without starting a sentence with it. A
#: name behind one of these is still at the start of its line, which is where a
#: heading lives, so these are stepped over rather than treated as text.
_DECORATION = "*#->_`~ \t"

#: Marks no English sentence gives an ordinary word, so a word carrying one is
#: a name wherever it stands. This is what keeps `3Commas`, `Collective2` and
#: `Polygon.io` when a round never once wrote them into a sentence, and it is
#: morphology rather than a list of companies: nothing here knows who they are.
_A_MARK_NOT_A_WORD = re.compile(r"\w[A-Z]|\d|&|\w\.\w")

#: A word the round also wrote in lower case is a word, not a name. This is
#: the second piece of evidence and it comes from the same place as the first,
#: which is the answers themselves: `most`, `free`, `enterprise` and `real-time`
#: all turn up in a sentence somewhere in twenty four answers, and `Finnhub`,
#: `Refinitiv` and `Alpha Vantage` never do. A stop word list is this rule
#: written out by hand for the words somebody thought of first.
_A_WORD_NOT_A_NAME = "the round wrote this in lower case too"

#: A single character is not a name. `I` opens a clause in half the answers a
#: model writes in the first person, and no company in a table of them is worth
#: the whole class of false positives it brings with it.
_SHORTEST_NAME = 2


@dataclass(frozen=True, slots=True)
class InQuestion:
    """One name, in one question, in however many of that question's draws."""

    prompt_id: str
    draws: int
    of_draws: int

    def as_text(self) -> str:
        return f"{self.prompt_id} {self.draws}/{self.of_draws}"


@dataclass(frozen=True, slots=True)
class Named:
    """One name, and every question it turned up in.

    `questions` is the whole finding. A single total would hide the difference
    between a name the model gives to one question every time and a name it
    gives to every question once, and those are opposite observations about how
    settled that part of the market is inside the model.
    """

    name: str
    questions: tuple[InQuestion, ...]

    @property
    def in_questions(self) -> int:
        return len(self.questions)

    @property
    def draws(self) -> int:
        return sum(one.draws for one in self.questions)

    def as_text(self) -> str:
        where = ", ".join(one.as_text() for one in self.questions)
        return f"{self.name:<24} {counted(self.in_questions, 'question')}   {where}"


def candidates_in(text: str) -> tuple[set[str], set[str]]:
    """Every capitalised thing this text states, and which of them prose used.

    The second set is the evidence a candidate is a name at all. It is smaller
    than the first on purpose and it is not what gets counted: a company can go
    a whole answer without leaving a table, and dropping it there would report
    the answer that mentions it in a sentence and miss the four that list it in
    a row of its own.
    """
    all_of_them: set[str] = set()
    in_prose: set[str] = set()
    for match in _CANDIDATE.finditer(text):
        name = match.group().strip(".'’-")
        if not _is_a_name(name):
            continue
        all_of_them.add(name)
        if not _opens_a_line(text, match.start()):
            in_prose.add(name)
    return all_of_them, in_prose


def _is_a_name(name: str) -> bool:
    """Whether a candidate carries a capital at all, past the digits and marks."""
    return len(name) >= _SHORTEST_NAME and any(ch.isupper() for ch in name)


def _opens_a_line(text: str, at: int) -> bool:
    """Whether what stands before this candidate leaves it opening a line, cell or sentence.

    Walked backwards over decoration rather than matched against a pattern,
    because a model writes the same heading as `## Reliability`, `**Reliability**`
    and `- Reliability` in the same answer, and the position is the fact all
    three have in common.
    """
    i = at - 1
    while i >= 0 and text[i] in _DECORATION:
        i -= 1
    if i < 0:
        return True
    return text[i] in _ENDS_A_SENTENCE or text[i] in _STARTS_A_CELL


def names_in(replies: Sequence[Reply]) -> tuple[Named, ...]:
    """Every name the round reached for, with the questions that produced it.

    Failed calls are expected to have been left out by the caller; an empty
    answer contributes nothing here either way, and a round is not asked to
    pretend a call it never got is a call that named nobody.
    """
    draws_of: dict[str, set[int]] = defaultdict(set)
    seen: dict[str, dict[str, set[int]]] = defaultdict(lambda: defaultdict(set))
    prose: set[str] = set()
    for reply in replies:
        draws_of[reply.prompt_id].add(reply.draw)
        written, in_prose = candidates_in(reply.text)
        prose |= in_prose
        for name in written:
            seen[name][reply.prompt_id].add(reply.draw)

    lowercased = _lower_case_words(replies, seen)

    found = []
    for name, questions in seen.items():
        # Qualified over the round rather than inside one answer. A name that
        # earned its place in one sentence anywhere is a name in every table it
        # appears in afterwards, and one that never left a table in any of them
        # is that table's vocabulary, unless it is spelled in a way no English
        # sentence spells a word.
        if name in lowercased:
            continue
        if name not in prose and not _A_MARK_NOT_A_WORD.search(name):
            continue
        found.append(
            Named(
                name=name,
                questions=tuple(
                    InQuestion(
                        prompt_id=prompt_id,
                        draws=len(draws),
                        of_draws=len(draws_of[prompt_id]),
                    )
                    for prompt_id, draws in sorted(questions.items())
                ),
            )
        )
    return tuple(sorted(found, key=lambda one: (-one.in_questions, -one.draws, one.name)))


def _lower_case_words(replies: Sequence[Reply], candidates) -> set[str]:
    """Of these candidates, the ones the round also wrote in lower case.

    Searched over the round rather than the answer that raised the candidate,
    because the evidence that a word is a word is the same evidence wherever it
    turns up, and a name that is capitalised in every one of two dozen answers
    is being treated as a name by the only witness available.
    """
    written = "\n".join(reply.text for reply in replies)
    return {
        name
        for name in candidates
        if re.search(rf"(?<![\w.]){re.escape(name.lower())}(?!\w)", written)
    }
