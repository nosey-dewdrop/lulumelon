"""Detection tests.

Grouped by the way a visibility number gets faked. Every false positive here
would inflate a score we sell as defensible, and every false negative would
deflate a competitor's.
"""

from __future__ import annotations

from collect.detect import Brand, detect, normalise, occurrences

NIKE = Brand("Nike", ("nike.com", "Nike, Inc."))
APPLE = Brand("Apple", ("apple.com",))
FORD = Brand("Ford",)


# -- the false positives that would inflate a score -----------------------

def test_substring_does_not_count() -> None:
    """The failure that matters most: a brand firing inside a longer word."""
    assert detect("We went to Applebee's for dinner.", (APPLE,)) == ()
    assert detect("She lives in Stafford.", (FORD,)) == ()
    assert detect("Nikke is a video game.", (NIKE,)) == ()


def test_no_fuzzy_matching() -> None:
    assert detect("Try Nikey shoes.", (NIKE,)) == ()
    assert detect("Aple is a fruit company.", (APPLE,)) == ()


def test_case_insensitive_but_still_bounded() -> None:
    assert detect("NIKE is here.", (NIKE,)) == ("Nike",)
    assert detect("nike is here.", (NIKE,)) == ("Nike",)
    assert detect("NIKKE is here.", (NIKE,)) == ()


# -- boundaries that punctuation would otherwise break --------------------

def test_punctuation_around_the_name() -> None:
    for text in ("Nike.", "(Nike)", "'Nike'", "Nike, and others", "—Nike—", "Nike?"):
        assert detect(text, (NIKE,)) == ("Nike",), text


def test_possessive_and_plural_still_match() -> None:
    assert detect("Nike's new runner.", (NIKE,)) == ("Nike",)


def test_domain_alias_dot_is_literal() -> None:
    assert detect("See nike.com for details.", (NIKE,)) == ("Nike",)
    # The dot must not behave as "any character".
    assert detect("See nikeXcom for details.", (NIKE,)) == ()


def test_regex_metacharacters_in_brand_names() -> None:
    for name in ("AT&T", "Yahoo!", "L'Oréal", "Levi's", ".NET"):
        b = Brand(name)
        assert detect(f"I recommend {name} today.", (b,)) == (name,), name


# -- order, because rank_of reads it --------------------------------------

def test_order_follows_the_answer_not_the_caller() -> None:
    text = "First Apple, then Nike."
    assert detect(text, (NIKE, APPLE)) == ("Apple", "Nike")


def test_each_brand_reported_once() -> None:
    text = "Nike is good. Nike is fine. Nike again."
    assert detect(text, (NIKE,)) == ("Nike",)


def test_longer_form_does_not_double_report() -> None:
    nike_air = Brand("Nike", ("Nike Air",))
    assert detect("The Nike Air Max is popular.", (nike_air,)) == ("Nike",)


# -- typography folding ---------------------------------------------------

def test_curly_apostrophe_folds() -> None:
    b = Brand("Levi's")
    assert detect("I like Levi’s jeans.", (b,)) == ("Levi's",)


def test_non_breaking_space_folds() -> None:
    b = Brand("Nike, Inc.")
    assert detect("Filed by Nike, Inc. today.", (b,)) == ("Nike, Inc.",)


def test_normalise_preserves_length() -> None:
    """Offsets stay usable: folding must not shift character positions."""
    for s in ("plain", "curly’s", "nb space", "café"):
        assert len(normalise(s)) == len(s), s


# -- degenerate input -----------------------------------------------------

def test_empty_inputs() -> None:
    assert detect("", (NIKE,)) == ()
    assert detect("Nike", ()) == ()


def test_blank_alias_is_ignored() -> None:
    """A blank form would otherwise match at position 0 of every answer."""
    b = Brand("Nike", ("", "   "))
    assert b.forms == ("Nike",)
    assert detect("Nothing relevant here.", (b,)) == ()


# -- occurrences ----------------------------------------------------------

def test_occurrences_counts_repeats() -> None:
    assert occurrences("Nike, Nike and Nike.", NIKE) == 3


def test_occurrences_counts_overlap_once() -> None:
    nike_air = Brand("Nike", ("Nike Air",))
    assert occurrences("The Nike Air Max.", nike_air) == 1


def test_occurrences_zero_when_absent() -> None:
    assert occurrences("Nothing here.", NIKE) == 0
