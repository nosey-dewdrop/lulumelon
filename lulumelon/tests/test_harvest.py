"""Reading a customer's site, before anything is asked of a model.

Two properties carry the rest of the pipeline and are tested hardest.

**A page that could not be read is not a page that said nothing.** Every
failure has to survive into the corpus with its status, because the next step
turns this text into questions and a corpus that quietly shrank produces fewer
questions with no record of why.

**Which pages get read is derived from the site.** The ranking is asserted
against a site whose sections are not named in English, since a keyword list
kept in our source would pass an English fixture and fail a real customer.
"""

from __future__ import annotations

import pytest

from lulumelon.collect.harvest import (
    NOT_DOCUMENT_SUFFIXES,
    USER_AGENT,
    Page,
    SiteCorpus,
    declares_not_a_document,
    harvest,
    opens_as_document,
    rank_pages,
)

BASE = "https://example.com"


def fetcher(pages: dict[str, str], *, status: dict[str, int] | None = None):
    """A site in a dict. Anything not in it is a 404, like a real one."""
    codes = status or {}

    def fetch(url: str) -> tuple[int, str]:
        key = url.rstrip("/") or url
        if key in codes:
            return codes[key], pages.get(key, "")
        if key in pages:
            return 200, pages[key]
        return 404, ""

    return fetch


def page(title: str, body: str = "", *, links: list[str] | None = None, extra: str = "") -> str:
    hrefs = "".join(f'<a href="{h}">x</a>' for h in (links or []))
    return f"<html><head><title>{title}</title>{extra}</head><body>{hrefs}{body}</body></html>"


# -- ranking is read off the site, not off a list we keep -------------------


def test_a_path_the_homepage_links_twice_outranks_one_it_links_once():
    ranked = rank_pages([f"{BASE}/a", f"{BASE}/a", f"{BASE}/b"], [], BASE)
    assert ranked[0] == f"{BASE}/a"


def test_a_homepage_link_outranks_a_bare_sitemap_entry():
    """Deliberate, and the opposite of what a sitemap's size suggests.

    A sitemap lists everything a site has, including every leaf nobody links
    to, so membership in it is weak evidence of importance. A homepage link is
    a choice somebody made. So one link beats one listing, even when the
    linked path is deeper.
    """
    ranked = rank_pages([f"{BASE}/deep/leaf"], [f"{BASE}/listed"], BASE)
    assert ranked.index(f"{BASE}/deep/leaf") < ranked.index(f"{BASE}/listed")


def test_a_sitemap_entry_outranks_a_page_nothing_declares_at_all():
    ranked = rank_pages([], [f"{BASE}/listed"], BASE)
    assert ranked == [f"{BASE}/listed"]


def test_a_guessed_sitemap_that_is_absent_is_not_reported_as_a_failure():
    """Most sites have no sitemap.xml. That is not a problem to show anyone."""
    corpus = harvest(BASE, fetch=fetcher({BASE: page("Home")}))
    assert corpus.unreachable == ()


def test_a_sitemap_promised_in_robots_and_missing_is_reported():
    def fetch(url: str) -> tuple[int, str]:
        key = url.rstrip("/")
        if key == f"{BASE}/robots.txt":
            return 200, f"Sitemap: {BASE}/sitemap.xml"
        if key == BASE:
            return 200, page("Home")
        return 404, ""

    corpus = harvest(BASE, fetch=fetch)
    assert [(u.url, u.reason) for u in corpus.unreachable] == [
        (f"{BASE}/sitemap.xml", "sitemap declared but not read")
    ]


def test_a_shallower_path_outranks_a_deeper_one_on_equal_signals():
    ranked = rank_pages([], [f"{BASE}/a/b/c", f"{BASE}/a"], BASE)
    assert ranked[0] == f"{BASE}/a"


def test_ranking_does_not_depend_on_english_section_names():
    """The same shape in another language has to rank the same way.

    If this ever diverges, a keyword list has crept into the ranking and the
    harvester has started working better for sites that name things our way.
    """
    english = rank_pages([f"{BASE}/pricing", f"{BASE}/pricing"], [f"{BASE}/about"], BASE)
    turkish = rank_pages([f"{BASE}/tarifeler", f"{BASE}/tarifeler"], [f"{BASE}/hakkinda"], BASE)
    assert [u.rsplit("/", 1)[0] for u in english] == [u.rsplit("/", 1)[0] for u in turkish]
    assert english[0].endswith("/pricing") and turkish[0].endswith("/tarifeler")


def test_the_homepage_is_never_ranked_as_an_extra_page():
    assert BASE not in rank_pages([BASE, BASE], [BASE], BASE)


# -- what could not be read is named ----------------------------------------


def test_a_page_that_failed_is_recorded_with_its_status():
    corpus = harvest(
        BASE,
        fetch=fetcher(
            {BASE: page("Home", links=["/gone"])},
            status={f"{BASE}/gone": 500},
        ),
    )
    assert [(u.url, u.status) for u in corpus.unreachable] == [(f"{BASE}/gone", 500)]


def test_a_robots_disallowed_path_is_reported_and_never_fetched():
    asked: list[str] = []

    def fetch(url: str) -> tuple[int, str]:
        asked.append(url)
        if url.rstrip("/") == f"{BASE}/robots.txt":
            return 200, f"User-agent: {USER_AGENT}\nDisallow: /private"
        if url.rstrip("/") == BASE:
            return 200, page("Home", links=["/private"])
        return 404, ""

    corpus = harvest(BASE, fetch=fetch)
    assert corpus.disallowed == (f"{BASE}/private",)
    assert f"{BASE}/private" not in asked


def test_a_dead_homepage_still_returns_a_named_corpus():
    corpus = harvest(BASE, fetch=fetcher({}, status={BASE: 500}))
    assert corpus.is_empty
    assert corpus.subject_name == "example"
    assert corpus.subject_name_source == "domain label"
    assert any(u.url == BASE for u in corpus.unreachable)


# -- only a document may enter the corpus -----------------------------------
#
# The gate this section defends is the evidence check downstream. It passes a
# candidate whose quote appears literally in the corpus, so whatever is in the
# corpus is what a quote may be proven against. Admit a stylesheet and a quote
# can be proven against bytes no reader ever saw.

PNG = "\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00"
CSS = ".hero{display:flex;gap:1rem}.nav a{color:#111}"
BUNDLE = '(self.webpackChunk=self.webpackChunk||[]).push([[404],{}])'


def test_a_stylesheet_the_nav_links_to_is_never_even_requested():
    """The suffix gate exists to save the request, not to make the decision."""
    asked: list[str] = []

    def fetch(url: str) -> tuple[int, str]:
        asked.append(url)
        if url.rstrip("/") == BASE:
            return 200, page("Home", links=["/static/app.css", "/logo.png"])
        return 200, CSS

    corpus = harvest(BASE, fetch=fetch)
    assert not any(u.endswith((".css", ".png")) for u in asked)
    assert {n.url for n in corpus.not_documents} == {
        f"{BASE}/static/app.css",
        f"{BASE}/logo.png",
    }


def test_a_query_string_does_not_hide_a_suffix_from_the_gate():
    assert declares_not_a_document(f"{BASE}/static/app.css?v=2b41f")


def test_a_dot_in_a_directory_name_is_not_read_as_a_suffix():
    """Or a docs site under `/v1.2/` would lose every page below it."""
    assert not declares_not_a_document(f"{BASE}/v1.2/pricing")


def test_no_suffix_on_the_list_contains_a_slash():
    """The invariant the test above rests on, asserted where it can be seen.

    Nothing separates a suffix from a dotted directory name except this: what
    follows the last dot in `/v1.2/pricing` still carries a slash, so it can
    never match. Add a suffix with a slash in it and that stops being true.
    """
    assert not any("/" in s for s in NOT_DOCUMENT_SUFFIXES)


def test_a_bundle_served_from_a_clean_url_is_still_kept_out():
    """The body is the gate that a server cannot evade by naming.

    A suffix is the site's claim about a URL. This is the one that holds when
    the claim is absent or wrong, and it is why the suffix list does not have
    to be complete to be safe.
    """
    site = {BASE: page("Home", links=["/_next/chunk"]), f"{BASE}/_next/chunk": BUNDLE}
    corpus = harvest(BASE, fetch=fetcher(site))
    assert [p.url for p in corpus.pages] == [BASE]
    assert [(n.url, n.reason) for n in corpus.not_documents] == [
        (f"{BASE}/_next/chunk", "body does not open as a document")
    ]


def test_image_bytes_are_not_a_document():
    assert not opens_as_document(PNG)


def test_a_byte_order_mark_does_not_make_a_page_stop_being_a_document():
    assert opens_as_document("﻿<!doctype html><html></html>")


def test_leading_whitespace_does_not_make_a_page_stop_being_a_document():
    assert opens_as_document("\n\n  <html></html>")


def test_bytes_that_were_kept_out_are_absent_from_what_a_quote_is_checked_against():
    """The point of the whole gate, stated as one assertion."""
    site = {
        BASE: page("Home", "We price risk daily.", links=["/theme"]),
        f"{BASE}/theme": CSS,
    }
    quotable = harvest(BASE, fetch=fetcher(site)).quotable
    assert "We price risk daily." in quotable
    assert "display:flex" not in quotable


def test_something_kept_out_is_not_reported_as_something_that_failed():
    """Two different facts about a site, and merging them loses one.

    A page that did not arrive is a gap in the corpus worth chasing. A
    stylesheet that was skipped is not, and filing it under failures would
    hand the customer a list of problems they do not have.
    """
    site = {BASE: page("Home", links=["/logo.png"])}
    corpus = harvest(BASE, fetch=fetcher(site))
    assert corpus.unreachable == ()
    assert len(corpus.not_documents) == 1


def test_a_homepage_that_is_not_a_document_leaves_an_empty_corpus_not_a_page():
    corpus = harvest(BASE, fetch=fetcher({BASE: PNG}))
    assert corpus.is_empty
    assert [(n.url, n.reason) for n in corpus.not_documents] == [
        (BASE, "body does not open as a document")
    ]


def test_a_skipped_link_does_not_spend_the_page_budget():
    """Otherwise a nav full of icons quietly shrinks the corpus."""
    links = ["/i1.png", "/i2.png", "/i3.png", "/a", "/b"]
    site = {BASE: page("Home", links=links), f"{BASE}/a": page("A"), f"{BASE}/b": page("B")}
    corpus = harvest(BASE, fetch=fetcher(site), max_pages=2)
    assert [p.url for p in corpus.pages] == [BASE, f"{BASE}/a", f"{BASE}/b"]


# -- the name the round will track ------------------------------------------


def test_the_subject_name_comes_from_the_site_s_own_declaration():
    ld = (
        '<script type="application/ld+json">'
        '{"@type": "Organization", "name": "Ornek Finance"}'
        "</script>"
    )
    corpus = harvest(BASE, fetch=fetcher({BASE: page("Home", extra=ld)}))
    assert corpus.subject_name == "Ornek Finance"
    assert corpus.subject_name_source == "json-ld Organization.name"


def test_broken_json_ld_falls_back_instead_of_raising():
    ld = '<script type="application/ld+json">{not json</script>'
    corpus = harvest(BASE, fetch=fetcher({BASE: page("Home", extra=ld)}))
    assert corpus.subject_name == "example"


# -- the corpus is what a quote may be checked against ----------------------


def test_the_quotable_text_carries_title_description_and_body():
    extra = '<meta name="description" content="Loans for builders">'
    corpus = harvest(BASE, fetch=fetcher({BASE: page("Ornek", "We price risk daily.", extra=extra)}))
    quotable = corpus.quotable
    assert "Ornek" in quotable
    assert "Loans for builders" in quotable
    assert "We price risk daily." in quotable


def test_the_digest_changes_when_the_site_does():
    first = harvest(BASE, fetch=fetcher({BASE: page("Ornek", "We price risk daily.")}))
    second = harvest(BASE, fetch=fetcher({BASE: page("Ornek", "We price risk weekly.")}))
    assert first.digest != second.digest


def test_the_digest_is_stable_for_the_same_reading():
    site = {BASE: page("Ornek", "We price risk daily.")}
    assert harvest(BASE, fetch=fetcher(site)).digest == harvest(BASE, fetch=fetcher(site)).digest


# -- budget and shape -------------------------------------------------------


def test_the_page_budget_is_respected():
    links = [f"/p{i}" for i in range(20)]
    site = {BASE: page("Home", links=links)}
    site.update({f"{BASE}{link}": page(f"P{link}") for link in links})
    corpus = harvest(BASE, fetch=fetcher(site), max_pages=3)
    assert len(corpus.pages) == 4, "the homepage plus the budget"


def test_a_negative_budget_is_refused():
    with pytest.raises(ValueError, match="cannot be negative"):
        harvest(BASE, fetch=fetcher({}), max_pages=-1)


def test_offsite_and_non_http_links_are_never_followed():
    asked: list[str] = []

    def fetch(url: str) -> tuple[int, str]:
        asked.append(url)
        if url.rstrip("/") == BASE:
            return 200, page("Home", links=["https://other.com/x", "mailto:a@b.c", "#top"])
        return 404, ""

    harvest(BASE, fetch=fetch)
    assert not any("other.com" in u or u.startswith("mailto:") for u in asked)


def test_a_sitemap_index_is_followed_one_level():
    index = "<urlset><loc>https://example.com/sm-1.xml</loc></urlset>"
    child = "<urlset><loc>https://example.com/deep</loc></urlset>"
    site = {
        BASE: page("Home"),
        f"{BASE}/sitemap.xml": index,
        f"{BASE}/sm-1.xml": child,
        f"{BASE}/deep": page("Deep"),
    }
    corpus = harvest(BASE, fetch=fetcher(site))
    assert f"{BASE}/deep" in corpus.sitemap_urls
    assert any(p.url == f"{BASE}/deep" for p in corpus.pages)


def test_llms_txt_is_kept_when_the_site_publishes_one():
    site = {BASE: page("Home"), f"{BASE}/llms.txt": "# Ornek\nWe price risk."}
    assert harvest(BASE, fetch=fetcher(site)).llms_txt == "# Ornek\nWe price risk."


def test_an_empty_llms_txt_is_not_mistaken_for_one():
    site = {BASE: page("Home"), f"{BASE}/llms.txt": "   "}
    assert harvest(BASE, fetch=fetcher(site)).llms_txt is None


# -- one page under two urls is one page ------------------------------------


def test_a_page_the_site_declares_as_another_one_is_not_read_twice():
    """The site is asked rather than a rule about query parameters applied.

    `?view=grid` is a layout of one page on one site and a different page on
    the next, so the only honest source for this is the tag the standard exists
    for. The first customer corpus this ran against carried `/feed` and
    `/feed?view=grid` and spent two of the thirteen slots the model sees on one
    document.
    """
    canonical = '<link rel="canonical" href="https://example.com/feed"/>'
    site = {
        BASE: page("Ana", "Giris", links=["/feed", "/feed?view=grid"]),
        f"{BASE}/feed": page("Akis", "Akis metni", extra=canonical),
        f"{BASE}/feed?view=grid": page("Akis", "Izgara metni", extra=canonical),
    }
    corpus = harvest(BASE, fetch=fetcher(site))

    urls = [p.url for p in corpus.pages]
    assert f"{BASE}/feed" in urls
    assert f"{BASE}/feed?view=grid" not in urls
    assert [(d.url, d.same_as) for d in corpus.duplicates] == [
        (f"{BASE}/feed?view=grid", f"{BASE}/feed")
    ]
    assert "declares this url as the other one" in corpus.duplicates[0].reason


def test_a_page_whose_words_are_already_in_the_corpus_is_not_read_twice():
    """A site that declares nothing still cannot spend the budget twice.

    The evidence is the page itself. Identical to the character means the model
    would be shown the same document under two headings, and the second one
    costs a slot and buys nothing.
    """
    site = {
        BASE: page("Ana", "Giris", links=["/tarifeler", "/fiyatlar"]),
        f"{BASE}/tarifeler": page("Tarifeler", "Gunluk fiyatlandiriyoruz."),
        f"{BASE}/fiyatlar": page("Tarifeler", "Gunluk fiyatlandiriyoruz."),
    }
    corpus = harvest(BASE, fetch=fetcher(site))

    urls = [p.url for p in corpus.pages]
    assert urls.count(f"{BASE}/tarifeler") + urls.count(f"{BASE}/fiyatlar") == 1
    assert len(corpus.duplicates) == 1
    assert "the same to the character" in corpus.duplicates[0].reason


def test_two_pages_that_only_look_alike_are_both_kept():
    """The rule is identity, not similarity. A near miss is a different page."""
    site = {
        BASE: page("Ana", "Giris", links=["/tarifeler", "/fiyatlar"]),
        f"{BASE}/tarifeler": page("Tarifeler", "Gunluk fiyatlandiriyoruz."),
        f"{BASE}/fiyatlar": page("Tarifeler", "Gunluk fiyatlandiriyoruz ve aylik da."),
    }
    corpus = harvest(BASE, fetch=fetcher(site))

    assert len(corpus.pages) == 3
    assert corpus.duplicates == ()


def test_a_canonical_tag_pointing_at_a_page_nobody_read_leaves_the_page_alone():
    """A declaration about a page this corpus does not hold decides nothing.

    Dropping on the strength of it would lose a page whose only sin is naming a
    url the crawl never reached, and the corpus would be short with no record
    of why.
    """
    site = {
        BASE: page("Ana", "Giris", links=["/feed"]),
        f"{BASE}/feed": page(
            "Akis", "Akis metni", extra='<link rel="canonical" href="https://example.com/other"/>'
        ),
    }
    corpus = harvest(BASE, fetch=fetcher(site))

    assert [p.url for p in corpus.pages] == [BASE, f"{BASE}/feed"]
    assert corpus.duplicates == ()


def test_a_page_that_declares_itself_is_not_a_duplicate_of_itself():
    site = {
        BASE: page("Ana", "Giris", links=["/feed"]),
        f"{BASE}/feed": page(
            "Akis", "Akis metni", extra='<link rel="canonical" href="https://example.com/feed"/>'
        ),
    }
    corpus = harvest(BASE, fetch=fetcher(site))

    assert [p.url for p in corpus.pages] == [BASE, f"{BASE}/feed"]
    assert corpus.duplicates == ()
