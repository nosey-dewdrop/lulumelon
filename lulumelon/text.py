"""Counting out loud, so a screen that reports money can count to one.

The first line a stranger reads on most of these commands is a count with a
noun beside it, and the noun has to agree with the count. `searchs` reached a
customer's screen on the first real run of the command that prices a call, and
the same class of defect then appeared on four more surfaces, because every
one of them spelled its own count and its own noun by hand.

So there is one function and every surface goes through it.

**The plural is an argument, not an `s` on the end.** `search` pluralises to
`searches` and `entry` to `entries`, so a helper that appended an `s` would
reproduce the exact defect it was written to remove. The regular case is
allowed to stay short, because a rule that cannot be invoked in one line gets
bypassed by the next person in a hurry; the irregular case is refused rather
than guessed at, which is what `_needs_an_explicit_plural` is for.

**Agreement follows the number as printed, not as held.** A count rendered to
one decimal place reads `1.0 runs`, which is correct English, so the
formatting happens here and the choice of word is made on the result.

It sits above both walls and imports nothing. `mirror` prints counts and
reaches no network, `collect` prints counts and computes nothing, and a shared
sentence fragment must not become the reason either of them imports the other.
"""

from __future__ import annotations

#: Endings where an `s` is not the plural. A noun ending in one of these has
#: to be given its plural form, because guessing here is what produced
#: `searchs` in the first place.
_SIBILANT_ENDINGS = ("s", "x", "z", "ch", "sh")

_VOWELS = "aeiou"


def _needs_an_explicit_plural(singular: str) -> bool:
    """Whether `singular + "s"` would be the wrong word.

    Sibilants take `es`, and a `y` after a consonant becomes `ies`. Both are
    checked on the last word, since the nouns here are phrases as often as
    they are single words: `answered call` pluralises on `call`.
    """
    head = singular.rsplit(" ", 1)[-1].lower()
    if head.endswith(_SIBILANT_ENDINGS):
        return True
    return len(head) > 1 and head.endswith("y") and head[-2] not in _VOWELS


def counted(n: float, singular: str, plural: str | None = None, *, fmt: str = "") -> str:
    """`n` with its noun agreeing: `1 call`, `2 calls`, `1 search`, `3 searches`.

    `plural` is required wherever adding an `s` would produce the wrong word,
    and the requirement is enforced rather than documented: an unstated plural
    for a noun like `search` raises here, at the call site, instead of being
    printed to whoever is reading the bill.

    `fmt` is applied to `n` before anything is decided, so the word agrees with
    the digits on the screen rather than with the value behind them.
    """
    if plural is None:
        if _needs_an_explicit_plural(singular):
            raise ValueError(
                f"{singular!r} does not pluralise by adding an 's', so its plural has to be "
                "given: guessing it is what put 'searchs' on a customer's screen"
            )
        plural = singular + "s"
    shown = format(n, fmt)
    return f"{shown} {singular if shown == '1' else plural}"


def article(word: str) -> str:
    """`a` or `an`, agreeing with the word after it.

    The same defect as `searchs`, one line further down the same screen. The
    first thing a stranger with no key read was "Looking for a anthropic key",
    because the sentence was written once around a provider name that arrives
    from a registry, and the registry gained a second entry.

    The letter is the rule here, not the sound. Every word this is ever handed
    is a provider name out of `PROVIDERS`, all of them lowercase and none of
    them the English exceptions where the two disagree, so a vowel test is the
    whole of it. A name that broke that assumption would be a name whose own
    spelling had to be decided anyway.
    """
    return "an" if word[:1].lower() in _VOWELS else "a"
