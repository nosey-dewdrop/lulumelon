"""The audit must never accuse a site of something its files do not say."""

from __future__ import annotations

from lulumelon.collect.audit import audit, is_disallowed, parse_robots

PAGE = """<html><head>
<title>Ornek</title>
<meta name="description" content="trading agents">
<link rel="canonical" href="https://ornek.com/">
<script type="application/ld+json">{"@type":"Organization","name":"Ornek"}</script>
</head><body>%s</body></html>""" % ("word " * 100)


def fetcher(pages):
    def fetch(url):
        if url in pages:
            return pages[url]
        return (404, "")

    return fetch


BASE = "https://ornek.com/"


def base_pages(**over):
    pages = {
        BASE: (200, PAGE),
        "https://ornek.com/robots.txt": (200, "User-agent: *\nDisallow:\n"),
        "https://ornek.com/llms.txt": (200, "# Ornek\nTrading agents.\n"),
    }
    pages.update(over)
    return pages


# -- robots parsing ---------------------------------------------------------


def test_consecutive_user_agents_share_one_record():
    groups = parse_robots("User-agent: GPTBot\nUser-agent: ClaudeBot\nDisallow: /\n")
    assert len(groups) == 1
    assert groups[0].agents == ("GPTBot", "ClaudeBot")


def test_a_named_group_beats_the_wildcard():
    # a site that shuts everything out but names GPTBot with an empty Disallow
    # is ALLOWING GPTBot. Reading only the wildcard invents a violation.
    robots = "User-agent: *\nDisallow: /\n\nUser-agent: GPTBot\nDisallow:\n"
    groups = parse_robots(robots)
    blocked, _ = is_disallowed(groups, "GPTBot", "/")
    assert not blocked
    blocked_other, _ = is_disallowed(groups, "PerplexityBot", "/")
    assert blocked_other


def test_the_longest_matching_rule_wins_and_allow_breaks_ties():
    robots = "User-agent: GPTBot\nDisallow: /docs\nAllow: /docs/public\n"
    groups = parse_robots(robots)
    assert is_disallowed(groups, "GPTBot", "/docs/private")[0]
    assert not is_disallowed(groups, "GPTBot", "/docs/public/a")[0]


def test_an_empty_disallow_blocks_nothing():
    groups = parse_robots("User-agent: *\nDisallow:\n")
    assert not is_disallowed(groups, "GPTBot", "/anything")[0]


def test_comments_do_not_become_rules():
    groups = parse_robots("User-agent: GPTBot  # our friend\nDisallow: /  # everything\n")
    blocked, line = is_disallowed(groups, "GPTBot", "/")
    assert blocked and "#" not in line


# -- findings ---------------------------------------------------------------


def test_a_clean_site_produces_no_blocking_finding():
    a = audit(BASE, fetch=fetcher(base_pages()))
    assert a.by_severity("blocking") == ()
    assert a.unreachable == ()


def test_a_blocked_crawler_is_named_with_the_line_that_blocks_it():
    robots = (200, "User-agent: GPTBot\nDisallow: /\n")
    a = audit(BASE, fetch=fetcher(base_pages(**{"https://ornek.com/robots.txt": robots})))

    blocking = a.by_severity("blocking")
    assert len(blocking) == 1
    f = blocking[0]
    assert "GPTBot" in f.title and "ChatGPT" in f.title
    assert "Disallow: /" in f.evidence, "a finding without its line is an accusation"
    assert "content changes cannot move" in f.blocks


def test_an_unreachable_file_is_not_reported_as_an_absent_one():
    # status 0 is a network failure. "we could not reach it" and "you do not
    # have one" are different statements.
    pages = base_pages(**{"https://ornek.com/robots.txt": (0, "")})
    a = audit(BASE, fetch=fetcher(pages))
    assert "https://ornek.com/robots.txt" in a.unreachable
    assert not any(f.id.startswith("robots.") for f in a.findings)


def test_missing_robots_is_stated_as_permitting_everything():
    pages = base_pages(**{"https://ornek.com/robots.txt": (404, "")})
    a = audit(BASE, fetch=fetcher(pages))
    ids = {f.id: f for f in a.findings}
    assert ids["robots.absent"].severity == "ok"


def test_an_offsite_canonical_is_blocking_not_cosmetic():
    html = PAGE.replace('href="https://ornek.com/"', 'href="https://old.github.io/"')
    a = audit(BASE, fetch=fetcher(base_pages(**{BASE: (200, html)})))
    ids = {f.id for f in a.by_severity("blocking")}
    assert "canonical.offsite" in ids


def test_a_page_that_needs_javascript_to_have_words_is_blocking():
    html = "<html><head><title>x</title></head><body><div id=root></div></body></html>"
    a = audit(BASE, fetch=fetcher(base_pages(**{BASE: (200, html)})))
    ids = {f.id for f in a.by_severity("blocking")}
    assert "body.thin" in ids


def test_broken_structured_data_is_called_out_separately_from_missing():
    html = PAGE.replace('{"@type":"Organization","name":"Ornek"}', '{"@type": broken,}')
    a = audit(BASE, fetch=fetcher(base_pages(**{BASE: (200, html)})))
    ids = {f.id for f in a.findings}
    assert "jsonld.invalid" in ids
    assert "jsonld.absent" in ids


def test_noindex_is_blocking():
    html = PAGE.replace("<title>", '<meta name="robots" content="noindex, follow"><title>')
    a = audit(BASE, fetch=fetcher(base_pages(**{BASE: (200, html)})))
    assert "page.noindex" in {f.id for f in a.by_severity("blocking")}


def test_there_is_no_score():
    a = audit(BASE, fetch=fetcher(base_pages()))
    assert not hasattr(a, "score")
    assert not hasattr(a, "grade")
    # a composite would hide which findings close a channel and which are style
    assert all(f.severity in ("blocking", "degrading", "missing", "ok") for f in a.findings)
