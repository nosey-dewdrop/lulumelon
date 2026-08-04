"""The customer's own site, read once, so questions can be grounded in it.

This is the first half of asking nothing of the customer but a domain. It
gathers; it decides nothing. Every judgement about what a page is worth lives
downstream in the pure layer, and the wall holds here as everywhere else in
`collect/`.

**Which pages get read is derived from the site, not from a list kept here.**
A fixed vocabulary of interesting paths (pricing, docs, features) is a guess
about how one industry names things, and it silently returns less on a site
that names them otherwise. So the ranking is built from what the site itself
says is important: how often the homepage links to a path, whether the sitemap
carries it, and how shallow it is. A site with no sitemap and no nav still
works, it just ranks on fewer signals.

**A page that could not be read is never the same as a page that said nothing.**
Failures land in `unreachable` with their status, and a robots-disallowed path
lands in `disallowed` without being fetched at all. Both are reported, because
a corpus that quietly shrank is a corpus that will quietly produce fewer
candidates and never say why.

**Only a document can be quoted from.** Links on a page point at stylesheets,
icons and script bundles as readily as at pages, and the corpus is what an
evidence check verifies quotes against. A stylesheet admitted to it is a stretch
of text a candidate can be checked against and pass, which is the evidence gate
agreeing with itself about bytes no reader ever saw. Two gates keep it out: a
suffix the URL itself declares, which saves the request, and the opening of the
body, which is what actually decides. Everything excluded is named in
`not_documents` for the same reason failures are named.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
from dataclasses import dataclass, field

from .audit import (
    Fetcher,
    RobotsGroup,
    _HREF,
    _JSONLD,
    _META_DESC,
    _TITLE,
    http_get,
    is_disallowed,
    parse_robots,
    visible_text,
)

#: The agent string the collector presents, and therefore the one whose robots
#: rules apply to it. Reading the site under one name and obeying another's
#: rules would make the courtesy decorative.
USER_AGENT = "youkiddingme-audit"

#: Pages fetched beyond the homepage, unless a caller says otherwise. Twelve is
#: a budget, not a finding: each page is one request and the corpus stops being
#: worth its latency long before a large site is exhausted.
DEFAULT_MAX_PAGES = 12

#: Suffixes by which a URL declares it is not a document. Checked before the
#: request, so a stylesheet in the nav costs nothing at all. This list is not
#: the decision and is not meant to be complete: anything that gets past it is
#: still judged on its body, which is the gate that cannot be evaded by naming.
NOT_DOCUMENT_SUFFIXES = frozenset(
    {
        "png", "jpg", "jpeg", "gif", "webp", "avif", "svg", "ico", "bmp",
        "css", "js", "mjs", "cjs", "map", "json",
        "woff", "woff2", "ttf", "otf", "eot",
        "pdf", "zip", "gz", "tar", "rar",
        "mp3", "mp4", "webm", "mov", "wav", "ogg",
        "xml", "rss", "atom", "csv",
    }
)

_HEADING = re.compile(r"<h[1-3][^>]*>(.*?)</h[1-3]>", re.S | re.I)
_SITEMAP_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)
_SITEMAP_DIRECTIVE = re.compile(r"^\s*sitemap:\s*(\S+)", re.I | re.M)
_WHITESPACE = re.compile(r"\s+")


def _collapse(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


@dataclass(frozen=True, slots=True)
class Page:
    """One page that was read, reduced to the parts a question can cite."""

    url: str
    title: str
    description: str
    headings: tuple[str, ...]
    text: str

    @property
    def quotable(self) -> str:
        """Everything on this page a candidate is allowed to quote from.

        One string, whitespace-collapsed, so a literal substring check
        downstream means the same thing for every field of the page.
        """
        parts = [self.title, self.description, *self.headings, self.text]
        return _collapse(" ".join(p for p in parts if p))


@dataclass(frozen=True, slots=True)
class Unreachable:
    """A page that was asked for and did not arrive."""

    url: str
    status: int
    reason: str


@dataclass(frozen=True, slots=True)
class NotADocument:
    """Something that arrived, or was named, and is not prose.

    Separate from `Unreachable` because the two are opposite failures. A page
    that did not arrive might have said something; this one arrived and there
    was never anything in it to quote.
    """

    url: str
    reason: str


@dataclass(frozen=True, slots=True)
class SiteCorpus:
    """What one site said about itself, and what it would not say."""

    base_url: str
    subject_name: str
    subject_name_source: str
    pages: tuple[Page, ...] = ()
    unreachable: tuple[Unreachable, ...] = ()
    disallowed: tuple[str, ...] = ()
    not_documents: tuple[NotADocument, ...] = ()
    llms_txt: str | None = None
    sitemap_urls: tuple[str, ...] = ()

    @property
    def quotable(self) -> str:
        """The whole corpus as one string, for literal evidence checks."""
        return _collapse(" ".join(p.quotable for p in self.pages))

    @property
    def digest(self) -> str:
        """Pins the corpus an evidence check was run against.

        A quote verified against one reading of a site is not verified against
        the site, which changes. Recording the digest is what lets a later
        reader tell those two claims apart.
        """
        body = json.dumps(
            {
                "base_url": self.base_url,
                "pages": [{"url": p.url, "quotable": p.quotable} for p in self.pages],
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(body.encode("utf-8")).hexdigest()

    @property
    def is_empty(self) -> bool:
        return not self.pages


def _origin(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def _same_origin(url: str, base: str) -> bool:
    return _origin(url) == _origin(base) and url.startswith(("http://", "https://"))


def _normalise(href: str, base: str) -> str | None:
    """Absolute, fragment-free, same-origin, or None."""
    href = href.strip()
    if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
        return None
    absolute = urllib.parse.urljoin(base, href)
    absolute, _, _ = absolute.partition("#")
    if not _same_origin(absolute, base):
        return None
    return absolute.rstrip("/") or absolute


def declares_not_a_document(url: str) -> bool:
    """Whether the URL's own suffix says there is nothing here to read.

    Read off the path alone, so a cache-busting query cannot hide a suffix:
    `/style.css?v=2b41` is the same file as `/style.css`. A dot inside a
    directory name is safe without a separate guard, because what follows the
    last dot then still contains a slash and no suffix here does.
    """
    _, dot, suffix = urllib.parse.urlsplit(url).path.rpartition(".")
    return bool(dot) and suffix.lower() in NOT_DOCUMENT_SUFFIXES


def opens_as_document(body: str) -> bool:
    """Whether what arrived begins as markup, which is the real decision.

    A suffix is a claim the site makes about a URL and a server is free to
    contradict it, so the body is what settles it. Markup opens with a tag, a
    doctype or an XML declaration, and everything the corpus must not admit,
    image bytes, a stylesheet, a script bundle, a JSON payload, opens with
    something else. The leading byte-order mark is skipped because it is an
    encoding artefact and not the document.
    """
    return body.lstrip("﻿ \t\r\n").startswith("<")


def _depth(url: str) -> int:
    path = urllib.parse.urlsplit(url).path.strip("/")
    return 0 if not path else path.count("/") + 1


def rank_pages(
    homepage_links: list[str], sitemap_urls: list[str], base_url: str
) -> list[str]:
    """Order candidate pages by what the site itself treats as important.

    Three signals, all read off the site. How often the homepage links to a
    path, since a nav repeated in header and footer links twice. Whether the
    sitemap lists it, since that is the site's own declaration of what exists.
    And how shallow the path is, since a section index outranks a leaf.

    No keyword list. A site that calls its plans page `/tarifeler` ranks on the
    same three signals as one that calls it `/pricing`.
    """
    counts: dict[str, int] = {}
    for link in homepage_links:
        counts[link] = counts.get(link, 0) + 1

    in_sitemap = set(sitemap_urls)
    base = (base_url.rstrip("/") or base_url)
    candidates = set(counts) | in_sitemap
    candidates.discard(base)

    def key(url: str) -> tuple[int, int, int, str]:
        # Negated where larger is better, so a plain ascending sort ranks.
        return (-counts.get(url, 0), -int(url in in_sitemap), _depth(url), url)

    return sorted(candidates, key=key)


def _subject_name(html: str, base_url: str) -> tuple[str, str]:
    """The tracked name, from the site's own declaration where there is one."""
    for block in _JSONLD.findall(html):
        try:
            data = json.loads(block)
        except (json.JSONDecodeError, ValueError):
            continue
        for node in data if isinstance(data, list) else [data]:
            if not isinstance(node, dict):
                continue
            types = node.get("@type")
            types = types if isinstance(types, list) else [types]
            if any(str(t).lower() == "organization" for t in types) and node.get("name"):
                return str(node["name"]).strip(), "json-ld Organization.name"
    label = urllib.parse.urlsplit(base_url).netloc.split(":")[0]
    label = label[4:] if label.startswith("www.") else label
    return label.split(".")[0], "domain label"


def _page_from(url: str, html: str) -> Page:
    title = _TITLE.search(html)
    desc = _META_DESC.search(html)
    headings = tuple(
        h for h in (_collapse(visible_text(m)) for m in _HEADING.findall(html)) if h
    )
    return Page(
        url=url,
        title=_collapse(visible_text(title.group(1))) if title else "",
        description=_collapse(desc.group(1)) if desc else "",
        headings=headings,
        text=_collapse(visible_text(html)),
    )


def _sitemap_targets(robots_text: str, base_url: str, fetch: Fetcher) -> tuple[list[str], list[Unreachable]]:
    """URLs the site's own sitemap declares. One level of index following."""
    declared = _SITEMAP_DIRECTIVE.findall(robots_text)
    # A sitemap named in robots.txt is a promise, and a promise that does not
    # arrive is worth reporting. A sitemap we merely guessed at is not: most
    # sites have none, and filing that absence as a failure fills the report
    # with a problem the customer does not have.
    guessed = not declared
    if guessed:
        declared = [urllib.parse.urljoin(base_url + "/", "sitemap.xml")]

    found: list[str] = []
    missed: list[Unreachable] = []
    for sitemap_url in declared[:2]:
        status, body = fetch(sitemap_url)
        if status != 200 or not body:
            if not guessed:
                missed.append(Unreachable(sitemap_url, status, "sitemap declared but not read"))
            continue
        locs = [u for u in _SITEMAP_LOC.findall(body) if _same_origin(u, base_url)]
        # A sitemap index lists sitemaps, not pages. Follow one level so a
        # site that splits by section is not read as having no pages at all.
        if locs and all(loc.endswith(".xml") for loc in locs):
            for child in locs[:2]:
                child_status, child_body = fetch(child)
                if child_status == 200 and child_body:
                    found.extend(
                        u for u in _SITEMAP_LOC.findall(child_body) if _same_origin(u, base_url)
                    )
                else:
                    missed.append(Unreachable(child, child_status, "sitemap not read"))
            continue
        found.extend(locs)

    seen: dict[str, None] = {}
    for url in found:
        seen.setdefault(url.rstrip("/") or url, None)
    return list(seen), missed


def harvest(
    base_url: str,
    *,
    fetch: Fetcher = http_get,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> SiteCorpus:
    """Read a site once and return what it said, with the gaps named.

    Nothing here scores, filters on meaning, or calls a model. The corpus is
    the raw material a later pure step is allowed to quote from, and keeping
    the two apart is what makes an evidence check mean anything.
    """
    if max_pages < 0:
        raise ValueError(f"max_pages cannot be negative, got {max_pages}")
    base = base_url.rstrip("/") or base_url

    unreachable: list[Unreachable] = []
    disallowed: list[str] = []
    not_documents: list[NotADocument] = []

    robots_status, robots_text = fetch(f"{base}/robots.txt")
    groups: tuple[RobotsGroup, ...] = parse_robots(robots_text) if robots_status == 200 else ()

    def allowed(url: str) -> bool:
        path = urllib.parse.urlsplit(url).path or "/"
        blocked, _ = is_disallowed(groups, USER_AGENT, path)
        if blocked:
            disallowed.append(url)
        return not blocked

    llms_status, llms_body = fetch(f"{base}/llms.txt")
    llms_txt = llms_body if llms_status == 200 and llms_body.strip() else None

    sitemap_urls, sitemap_misses = _sitemap_targets(robots_text, base, fetch)
    unreachable.extend(sitemap_misses)

    pages: list[Page] = []
    home_links: list[str] = []
    home_html = ""
    if allowed(base):
        status, html = fetch(base)
        if status == 200 and html and opens_as_document(html):
            home_html = html
            pages.append(_page_from(base, html))
            home_links = [
                link for link in (_normalise(h, base) for h in _HREF.findall(html)) if link
            ]
        elif status == 200 and html:
            not_documents.append(NotADocument(base, "body does not open as a document"))
        else:
            unreachable.append(Unreachable(base, status, "homepage not read"))

    # Falls back to the domain label when the homepage never arrived, so a
    # blocked or dead site still produces a named corpus rather than an
    # exception the caller has to special-case.
    subject_name, name_source = _subject_name(home_html, base)

    ranked = [u for u in rank_pages(home_links, sitemap_urls, base) if u != base]
    for url in ranked:
        if len(pages) > max_pages:
            break
        if not allowed(url):
            continue
        if declares_not_a_document(url):
            not_documents.append(NotADocument(url, "url declares a non-document suffix"))
            continue
        status, html = fetch(url)
        if status == 200 and html and opens_as_document(html):
            pages.append(_page_from(url, html))
        elif status == 200 and html:
            not_documents.append(NotADocument(url, "body does not open as a document"))
        else:
            unreachable.append(Unreachable(url, status, "page not read"))

    return SiteCorpus(
        base_url=base,
        subject_name=subject_name,
        subject_name_source=name_source,
        pages=tuple(pages),
        unreachable=tuple(unreachable),
        disallowed=tuple(dict.fromkeys(disallowed)),
        not_documents=tuple(not_documents),
        llms_txt=llms_txt,
        sitemap_urls=tuple(sitemap_urls),
    )
