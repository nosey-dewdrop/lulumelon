"""The one paid call in the draft path, and everything it is not allowed to do.

Three properties carry the rest and are tested hardest.

**The request is built out of the customer's site and nothing else.** A fixture
whose sections are not named in English is used on purpose: a vocabulary of
interesting topics kept in our source would pass an English fixture and quietly
return less on a real customer.

**Truncation runs one way.** The model is shown the opening of each page and
quotes are later checked against the whole page, so a shown page is always a
subset of a checked page. Reverse that and a quote could pass the gate on text
the model was never given, which is the one thing the gate exists to prevent.

**Nothing unreadable disappears.** A reply that half parses has to come back as
what it produced plus what it destroyed, because a parser that skips entries
reports a bad call and a good one identically.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from lulumelon.collect import Answer, Budget, Usage
from lulumelon.collect.harvest import Page, SiteCorpus
from lulumelon.collect.propose import (
    DEFAULT_WANTED,
    Malformed,
    Proposal,
    as_candidate_rows,
    output_cap_for,
    pages_for_screening,
    propose,
    read_reply,
    request_for,
)
from lulumelon.prices import price_for

HAIKU = price_for("anthropic", "claude-haiku-4-5")

#: The cap every call in these rounds carries. It is the number the request
#: states, so the guard prices it rather than guessing at it.
CAP = 1024

TARIFELER = "https://ornek.com/tarifeler"
HAKKIMIZDA = "https://ornek.com/hakkimizda"


def corpus(*pages: Page) -> SiteCorpus:
    return SiteCorpus(
        base_url="https://ornek.com",
        subject_name="Ornek",
        subject_name_source="domain label",
        pages=pages or (
            Page(
                url=TARIFELER,
                title="Tarifeler",
                description="Aylik abonelik",
                headings=("Fiyatlandirma",),
                text="Insaat riskini gunluk fiyatlandiriyoruz.",
            ),
            Page(
                url=HAKKIMIZDA,
                title="Hakkimizda",
                description="",
                headings=(),
                text="Sigortacilarimiz her hakedis dosyasini inceler.",
            ),
        ),
    )


@dataclass
class Stub:
    """A provider that says one thing and counts how often it was asked."""

    reply: str = "[]"
    status: str = "ok"
    name: str = "stub"
    surface: str = "api"
    model: str = "stub-1"
    usage: Usage = field(default_factory=Usage)
    seen: list[str] = field(default_factory=list)
    #: What a round's ordinary call may write back, and what a proposing call
    #: raised it to. The second is recorded rather than replaced so a test can
    #: read the number the paid call was actually allowed.
    max_output_tokens: int = 1024
    capped_to: int | None = None

    def with_output_cap(self, max_output_tokens: int) -> "Stub":
        self.capped_to = max_output_tokens
        return self

    def ask(self, prompt: str) -> Answer:
        self.seen.append(prompt)
        return Answer(
            text=self.reply if self.status == "ok" else "",
            model=self.model,
            surface=self.surface,
            latency_ms=5,
            status=self.status,
            error="" if self.status == "ok" else "the provider timed out",
            usage=self.usage,
        )


# -- the request, built from the site --------------------------------------


def test_the_request_carries_every_page_url_that_was_read():
    request = request_for(corpus())
    assert TARIFELER in request
    assert HAKKIMIZDA in request


def test_a_site_that_names_nothing_in_english_is_described_in_its_own_words():
    """No keyword list, so a Turkish site arrives whole rather than filtered."""
    request = request_for(corpus())
    assert "Insaat riskini gunluk fiyatlandiriyoruz." in request
    assert "Sigortacilarimiz her hakedis dosyasini inceler." in request


def test_the_request_asks_for_the_count_it_was_given():
    assert "Write 7 questions" in request_for(corpus(), wanted=7)
    assert f"Write {DEFAULT_WANTED} questions" in request_for(corpus())


def test_the_request_tells_the_model_the_two_rules_the_gates_enforce():
    request = request_for(corpus())
    assert "must not contain the company's name" in request
    assert "Copy the quote character for character" in request


def test_a_corpus_with_no_pages_is_refused_before_anything_is_paid_for():
    empty = SiteCorpus(base_url="https://ornek.com", subject_name="Ornek", subject_name_source="domain label")
    with pytest.raises(ValueError, match="nothing to ground a question in"):
        request_for(empty)


def test_a_request_for_no_questions_is_refused():
    with pytest.raises(ValueError, match="not a call worth paying for"):
        request_for(corpus(), wanted=0)


# -- truncation runs one way ------------------------------------------------


def test_a_page_is_truncated_on_the_way_in():
    long_page = Page(
        url=TARIFELER, title="Tarifeler", description="", headings=(), text="a" * 50 + "SONRASI"
    )
    request = request_for(corpus(long_page), page_chars=20)
    assert "SONRASI" not in request


def test_the_screening_map_carries_the_whole_page_the_request_cut():
    """The asymmetry the evidence gate depends on.

    What the model was shown is a subset of what its quote is checked against,
    so truncation can only cost a candidate. If this ever inverted, a quote
    could clear the gate on text nobody gave the model.
    """
    long_page = Page(
        url=TARIFELER, title="Tarifeler", description="", headings=(), text="a" * 50 + "SONRASI"
    )
    site = corpus(long_page)
    shown = request_for(site, page_chars=20)
    checked = pages_for_screening(site)[TARIFELER]
    assert "SONRASI" not in shown
    assert "SONRASI" in checked
    assert shown.split("\n", 1)[-1].strip() != checked


def test_the_screening_map_keys_are_the_urls_the_request_offered():
    site = corpus()
    request = request_for(site)
    for url in pages_for_screening(site):
        assert url in request


# -- reading a reply --------------------------------------------------------


GOOD = """[
  {"question": "Which lenders price construction risk daily?",
   "source": "https://ornek.com/tarifeler",
   "evidence": "Insaat riskini gunluk fiyatlandiriyoruz."}
]"""


def test_a_clean_reply_becomes_a_proposal():
    proposals, malformed = read_reply(GOOD)
    assert malformed == ()
    assert proposals == (
        Proposal(
            text="Which lenders price construction risk daily?",
            source=TARIFELER,
            evidence="Insaat riskini gunluk fiyatlandiriyoruz.",
        ),
    )


def test_a_fenced_reply_is_read_rather_than_thrown_away():
    """A fence is the most common way a paid call would otherwise be wasted."""
    proposals, malformed = read_reply(f"```json\n{GOOD}\n```")
    assert len(proposals) == 1 and malformed == ()


def test_prose_around_the_array_does_not_cost_the_call():
    proposals, _ = read_reply(f"Here they are:\n{GOOD}\nHope that helps.")
    assert len(proposals) == 1


def test_a_quote_is_carried_exactly_as_the_model_wrote_it():
    """Whitespace included. The literal check downstream normalises; this must not."""
    reply = '[{"question": "Who?", "source": "u", "evidence": "  spaced   quote  "}]'
    proposals, _ = read_reply(reply)
    assert proposals[0].evidence == "  spaced   quote  "


def test_a_reply_with_no_array_is_recorded_whole():
    proposals, malformed = read_reply("I cannot help with that.")
    assert proposals == ()
    assert len(malformed) == 1
    assert "no JSON array" in malformed[0].reason
    assert "I cannot help" in malformed[0].raw


def test_an_array_that_does_not_parse_is_recorded_with_the_parser_error():
    proposals, malformed = read_reply('[{"question": "Who?",]')
    assert proposals == ()
    assert "does not parse" in malformed[0].reason


def test_an_entry_that_is_not_an_object_is_recorded_not_skipped():
    proposals, malformed = read_reply(f'["just a string", {GOOD[1:-1]}]')
    assert len(proposals) == 1
    assert len(malformed) == 1
    assert malformed[0].reason == "entry is not an object"


def test_an_entry_with_no_question_is_recorded_not_skipped():
    proposals, malformed = read_reply('[{"source": "u", "evidence": "e"}]')
    assert proposals == ()
    assert malformed[0].reason == "entry carries no question text"


def test_an_entry_missing_its_citation_is_passed_on_for_the_gates_to_refuse():
    """Shape is judged once, in the pure layer, not twice in two places."""
    proposals, malformed = read_reply('[{"question": "Which lenders are fastest?"}]')
    assert malformed == ()
    assert proposals[0].source == "" and proposals[0].evidence == ""


# -- the call itself --------------------------------------------------------


def test_one_call_is_made_and_it_is_not_retried_when_it_fails():
    stub = Stub(status="error")
    result = propose(corpus(), provider=stub)
    assert len(stub.seen) == 1
    assert result.asked is True
    assert result.answer is not None and not result.answer.ok
    assert result.proposals == ()


def test_a_reply_that_parsed_comes_back_with_its_answer_for_the_ledger():
    result = propose(corpus(), provider=Stub(reply=GOOD))
    assert result.usable == 1
    assert result.answer is not None and result.answer.ok


def test_a_budget_that_cannot_cover_the_call_stops_it_before_the_network():
    stub = Stub(reply=GOOD)
    budget = Budget(price=HAIKU, limit_usd=0.000001, max_searches=1, max_output_tokens=CAP)
    result = propose(corpus(), provider=stub, budget=budget)
    assert stub.seen == []
    assert result.asked is False
    assert "of the ceiling is left" in result.refusal
    assert budget.spent_usd == 0.0


def test_a_call_that_was_made_is_charged_to_the_budget():
    budget = Budget(price=HAIKU, limit_usd=5.0, max_searches=1, max_output_tokens=CAP)
    propose(corpus(), provider=Stub(reply=GOOD), budget=budget)
    assert budget.spent_usd > 0.0


def test_a_failed_call_is_handed_to_the_budget_and_the_budget_prices_it():
    """Pricing a failure is the budget's call, and it charges nothing for one.

    Asserted from this side too, because the alternative failure mode is silent:
    a proposal round that skipped the charge entirely would look identical here
    while spending real money on the day that rule changes.
    """
    budget = Budget(price=HAIKU, limit_usd=5.0, max_searches=1, max_output_tokens=CAP)
    propose(corpus(), provider=Stub(status="error"), budget=budget)
    assert budget.spent_usd == 0.0
    assert budget.metered_calls == 0 and budget.unmetered_calls == 0


def test_the_call_is_given_room_for_the_list_it_was_told_to_write():
    """Forty answers under a cap sized for one is the whole of what went wrong.

    The cap lived in the network layer as a private constant while this module
    asked for forty candidates, each carrying a question, a URL and a quote. It
    is derived here instead, so the number that decides whether the answer fits
    is set by the layer that knows how long the answer has to be.
    """
    stub = Stub(reply=GOOD)
    propose(corpus(), provider=stub, wanted=40)

    assert stub.capped_to == output_cap_for(40)
    assert stub.capped_to > 1024, "the cap that cut the first paid call short"
    assert output_cap_for(40) > output_cap_for(10) > output_cap_for(1)


def test_a_call_asking_for_nothing_has_no_room_to_size():
    with pytest.raises(ValueError, match="not a call worth paying for"):
        output_cap_for(0)


def test_the_budget_is_told_the_shape_of_the_call_it_is_guarding():
    """A ceiling for an ordinary draw is not a ceiling for this call.

    The proposing call sends the whole site and asks for a list; a draw sends
    one question. This budget can afford a draw many times over and cannot
    afford the proposing call once, and a guard priced on the round's ordinary
    shape would have let it through and read the difference off the invoice.
    """
    room = Budget(price=HAIKU, limit_usd=0.05, max_searches=1, max_output_tokens=CAP)
    assert room.can_afford_another(), "an ordinary draw fits inside this ceiling"

    stub = Stub(reply=GOOD)
    result = propose(corpus(), provider=stub, wanted=400, budget=room)

    assert stub.seen == [], "nothing reached the network"
    assert result.asked is False
    assert room.spent_usd == 0.0


def test_the_summary_says_what_happened_including_the_refusal():
    budget = Budget(price=HAIKU, limit_usd=0.000001, max_searches=1, max_output_tokens=CAP)
    refused = propose(corpus(), provider=Stub(), budget=budget)
    assert refused.as_text().startswith("no call was made")

    mixed = propose(corpus(), provider=Stub(reply=f'["oops", {GOOD[1:-1]}]'))
    assert "1 proposals read" in mixed.as_text()
    assert "1 entries unreadable" in mixed.as_text()


# -- handing over to the pure layer ----------------------------------------


def test_rows_carry_the_field_names_the_gates_read():
    rows = as_candidate_rows([Proposal("Who?", "https://u", "quote")])
    assert rows == ({"text": "Who?", "source": "https://u", "evidence": "quote"},)


def test_this_module_does_not_import_the_pure_layer():
    """The wall, asserted rather than remembered."""
    from lulumelon.collect import propose as module

    source = open(module.__file__, encoding="utf-8").read()
    assert "from ..mirror" not in source
    assert "import mirror" not in source
