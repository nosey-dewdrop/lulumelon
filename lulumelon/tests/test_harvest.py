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
    USER_AGENT,
    Page,
    SiteCorpus,
    harvest,
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


# -- the name the round will track ------------------------------------------


def test_the_subject_name_comes_from_the_site_s_own_declaration():
    ld = (
        '<script type="application/ld+json">'
        '{"@type": "Organization", "name": "Marx Finance"}'
        "</script>"
    )
    corpus = harvest(BASE, fetch=fetcher({BASE: page("Home", extra=ld)}))
    assert corpus.subject_name == "Marx Finance"
    assert corpus.subject_name_source == "json-ld Organization.name"


def test_broken_json_ld_falls_back_instead_of_raising():
    ld = '<script type="application/ld+json">{not json</script>'
    corpus = harvest(BASE, fetch=fetcher({BASE: page("Home", extra=ld)}))
    assert corpus.subject_name == "example"


# -- the corpus is what a quote may be checked against ----------------------


def test_the_quotable_text_carries_title_description_and_body():
    extra = '<meta name="description" content="Loans for builders">'
    corpus = harvest(BASE, fetch=fetcher({BASE: page("Marx", "We price risk daily.", extra=extra)}))
    quotable = corpus.quotable
    assert "Marx" in quotable
    assert "Loans for builders" in quotable
    assert "We price risk daily." in quotable


def test_the_digest_changes_when_the_site_does():
    first = harvest(BASE, fetch=fetcher({BASE: page("Marx", "We price risk daily.")}))
    second = harvest(BASE, fetch=fetcher({BASE: page("Marx", "We price risk weekly.")}))
    assert first.digest != second.digest


def test_the_digest_is_stable_for_the_same_reading():
    site = {BASE: page("Marx", "We price risk daily.")}
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
    site = {BASE: page("Home"), f"{BASE}/llms.txt": "# Marx\nWe price risk."}
    assert harvest(BASE, fetch=fetcher(site)).llms_txt == "# Marx\nWe price risk."


def test_an_empty_llms_txt_is_not_mistaken_for_one():
    site = {BASE: page("Home"), f"{BASE}/llms.txt": "   "}
    assert harvest(BASE, fetch=fetcher(site)).llms_txt is None
