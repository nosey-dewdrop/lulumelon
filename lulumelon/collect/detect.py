"""Turning an answer into the list of brands it named.

This module is deliberately boring, and that is the point. Deciding which
brands an answer mentioned is the step where a visibility number is most
easily inflated, so it is done with explicit rules that a reader can check by
hand rather than with a model that would have to be trusted.

Using an LLM here would also defeat the measurement. The thing being measured
is how much a model's answer moves between identical asks. A detector that is
itself a model adds its own movement on top, and the two can no longer be told
apart. Detection must be a pure function of the text, or the instrument is
measuring itself.

What it does NOT do, on purpose:

  - No fuzzy or approximate matching. "Nikke" is not "Nike". A false positive
    inflates the very number we sell as defensible.
  - No stemming or lemmatisation. Brands are proper nouns, not words.
  - No substring matching. "Apple" must not fire inside "Applebee's", and
    "Ford" must not fire inside "Stafford". Matching is bounded by
    non-word characters on both sides.
  - No inference. "the Swoosh company" is not Nike unless the caller listed
    that phrase as an alias. Aliases are the caller's declaration, and they
    are recorded with the measurement so a reader can see what counted.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Brand:
    """A tracked brand and the surface forms that count as naming it.

    `name` is what gets reported. `aliases` are additional literal strings
    that mean the same brand: legal suffixes ("Nike, Inc."), domains
    ("nike.com"), local spellings, common abbreviations.

    Aliases are a declaration, not a guess. Whatever is listed here is what
    the number means, which is why the resolved alias set travels with the
    measurement instead of living in someone's head.
    """

    name: str
    aliases: tuple[str, ...] = ()

    @property
    def forms(self) -> tuple[str, ...]:
        """Every literal string that counts, longest first.

        Longest first matters when one form contains another: "Nike Air" must
        be tried before "Nike", otherwise the shorter match consumes the span
        and the longer form can never fire.
        """
        seen: dict[str, None] = {}
        for f in (self.name, *self.aliases):
            f = f.strip()
            if f:
                seen[f] = None
        return tuple(sorted(seen, key=lambda s: (-len(s), s)))


def normalise(text: str) -> str:
    """Fold the differences that are typography rather than content.

    Answers arrive with curly apostrophes, non-breaking spaces and occasional
    decomposed accents. None of those change which brand was named, and all of
    them break a literal match, so they are folded before matching. Case is
    handled by the regex, not here, so offsets into the returned string still
    line up with the input character for character.
    """
    text = unicodedata.normalize("NFC", text)
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace(" ", " ").replace(" ", " ")
    return text


def _pattern(form: str) -> re.Pattern[str]:
    """A case-insensitive, boundary-anchored matcher for one literal form.

    `re.escape` is not optional. Brand names contain regex metacharacters more
    often than you would like: "L'Oréal", "Levi's", "AT&T", "Yahoo!", and
    every domain alias carries a dot that would otherwise match any character.

    The boundaries are lookarounds rather than \\b because \\b is defined
    against word characters and fails at the edges of forms that start or end
    with punctuation, such as "Yahoo!" or ".NET". Requiring a non-word
    neighbour on each side gives the same protection without that hole.
    """
    body = re.escape(form)
    return re.compile(rf"(?<![0-9A-Za-z]){body}(?![0-9A-Za-z])", re.IGNORECASE)


def detect(text: str, brands: tuple[Brand, ...]) -> tuple[str, ...]:
    """Brands named in `text`, in order of first appearance, each once.

    Order is the payload, not a detail. `Run.rank_of` reads position from this
    tuple, so "first brand mentioned" has to mean "earliest in the answer",
    not "first in the caller's list".

    Overlaps resolve by earliest position, then by longest form. An answer
    saying "Nike Air Max" reports Nike once, from the "Nike Air" form if the
    caller declared it, and never twice.
    """
    if not text or not brands:
        return ()

    hay = normalise(text)
    first: dict[str, int] = {}

    for brand in brands:
        for form in brand.forms:
            m = _pattern(form).search(hay)
            if m is not None:
                at = m.start()
                if brand.name not in first or at < first[brand.name]:
                    first[brand.name] = at

    return tuple(sorted(first, key=lambda n: (first[n], n)))


def occurrences(text: str, brand: Brand) -> int:
    """How many times `brand` is named, counting every declared form once each.

    Not used to compute visibility, which is a per-answer yes or no. Kept
    because "named once in passing" and "named nine times" are different
    facts about the same answer, and throwing that away at collection time
    means it can never be recovered from the ledger.

    Overlapping spans are counted once: "Nike Air" and "Nike" firing on the
    same words is one mention, not two.
    """
    hay = normalise(text)
    spans: list[tuple[int, int]] = []
    for form in brand.forms:
        for m in _pattern(form).finditer(hay):
            spans.append((m.start(), m.end()))

    spans.sort()
    count = 0
    reach = -1
    for start, end in spans:
        if start >= reach:
            count += 1
            reach = end
    return count
