"""Whether the answer engines are even allowed to read you.

A low visibility number invites one recommendation above all others: write more.
There is a cheaper explanation worth ruling out before spending anything, and it
takes one HTTP request to check. If GPTBot is disallowed in robots.txt, no amount
of content changes the retrieval channel, because the channel is closed by
construction.

That makes this the one place where the advice is not a guess. "You are blocking
the crawler belonging to the engine you are trying to appear in, here is the
line, at this path" is a mechanism with evidence attached, and it is either true
or false about a file that anyone can open.

Three rules this module keeps.

**No score.** There is no number out of a hundred here. A composite score mixes
things that block retrieval outright with things that are stylistic, and once
they are averaged nobody can tell which is which. Findings carry a severity and
their own evidence instead.

**Every finding quotes the line it is about.** A finding without the literal
text it was derived from is an accusation, and this repo is going to be opened
by people looking for a reason to dismiss it.

**Nothing is inferred about what a crawler will do with what it reads.** This
checks permission and machine-readability, both of which are facts about files.
Whether being readable makes a model cite you is a measurement question, and it
is answered by the rest of this package, not here.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urljoin, urlparse

from ..text import counted

#: The crawlers that matter for appearing in generated answers, and who they
#: belong to. Blocking one of these is not an SEO nuance, it is an opt-out of
#: the surface the customer is paying to be measured on.
AI_CRAWLERS: dict[str, str] = {
    "GPTBot": "ChatGPT (OpenAI), training and browsing",
    "OAI-SearchBot": "ChatGPT search results",
    "ChatGPT-User": "ChatGPT when a user follows a link",
    "ClaudeBot": "Claude (Anthropic)",
    "Claude-User": "Claude when a user follows a link",
    "anthropic-ai": "Anthropic, legacy token still honoured by many sites",
    "PerplexityBot": "Perplexity index",
    "Perplexity-User": "Perplexity when a user follows a link",
    "Google-Extended": "Gemini grounding and AI Overviews",
    "Applebot-Extended": "Apple Intelligence",
    "Amazonbot": "Amazon assistants",
    "CCBot": "Common Crawl, an input to many models",
    "Bytespider": "ByteDance models",
    "meta-externalagent": "Meta AI",
}

SEVERITIES = ("blocking", "degrading", "missing", "ok")


@dataclass(frozen=True, slots=True)
class Finding:
    """One checkable statement about the site, with the text it came from.

    `blocks` names what the finding costs in plain terms, so a reader never has
    to translate a rule name into a consequence.
    """

    id: str
    severity: str
    title: str
    evidence: str
    blocks: str

    def as_text(self) -> str:
        head = f"[{self.severity.upper()}] {self.title}"
        body = f"    evidence: {self.evidence}" if self.evidence else "    evidence: (absent)"
        return f"{head}\n{body}\n    consequence: {self.blocks}"


@dataclass(frozen=True, slots=True)
class SiteAudit:
    """Findings for one site, and the fetches that failed while collecting them."""

    base_url: str
    findings: tuple[Finding, ...]
    unreachable: tuple[str, ...] = ()

    def by_severity(self, severity: str) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity == severity)

    @property
    def blocked_engines(self) -> tuple[str, ...]:
        return tuple(f.title for f in self.by_severity("blocking"))

    def as_text(self) -> str:
        lines = [f"site: {self.base_url}"]
        for sev in SEVERITIES:
            group = self.by_severity(sev)
            if group:
                lines.extend(f.as_text() for f in group)
        if self.unreachable:
            lines.append(
                "    not reached (recorded, not assumed absent): "
                + ", ".join(self.unreachable)
            )
        return "\n".join(lines)


# -- fetching ---------------------------------------------------------------


def http_get(url: str, timeout_s: float = 20.0) -> tuple[int, str]:
    """Return (status, body). Network failure is a status of 0, never an exception."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "youkiddingme-audit/0 (+measurement, respects robots)"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return 0, ""


Fetcher = Callable[[str], tuple[int, str]]


# -- robots.txt -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RobotsGroup:
    agents: tuple[str, ...]
    allow: tuple[str, ...] = ()
    disallow: tuple[str, ...] = ()


def parse_robots(text: str) -> tuple[RobotsGroup, ...]:
    """Group the file the way the standard reads it.

    Consecutive `User-agent` lines share one record. A rule line closes the run
    of agent lines, so the next `User-agent` after a rule starts a new group.
    Comments and unknown directives are ignored rather than guessed at.
    """
    groups: list[RobotsGroup] = []
    agents: list[str] = []
    allow: list[str] = []
    disallow: list[str] = []
    open_group = False

    def close() -> None:
        nonlocal agents, allow, disallow, open_group
        if agents:
            groups.append(
                RobotsGroup(tuple(agents), tuple(allow), tuple(disallow))
            )
        agents, allow, disallow = [], [], []
        open_group = False

    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field_name, _, value = line.partition(":")
        key = field_name.strip().lower()
        value = value.strip()

        if key == "user-agent":
            if open_group:
                close()
            agents.append(value)
        elif key == "allow":
            open_group = True
            allow.append(value)
        elif key == "disallow":
            open_group = True
            disallow.append(value)

    close()
    return tuple(groups)


def _matches(pattern: str, path: str) -> bool:
    """Prefix match with `*` wildcards and `$` anchor, as crawlers implement it."""
    if pattern == "":
        return False
    regex = "".join(".*" if ch == "*" else re.escape(ch) for ch in pattern.rstrip("$"))
    regex = "^" + regex + ("$" if pattern.endswith("$") else "")
    return re.match(regex, path) is not None


def is_disallowed(groups: tuple[RobotsGroup, ...], agent: str, path: str = "/") -> tuple[bool, str]:
    """Whether `agent` is barred from `path`, and the line that decided it.

    A named group wins over `*` entirely: a site that disallows everything for
    `*` but names GPTBot with its own empty Disallow is allowing GPTBot, and
    reading only the wildcard would produce a false accusation.

    Within the winning group, the longest matching rule wins, with Allow taking
    precedence at equal length. That is what Google and the RFC both do.
    """
    lowered = agent.lower()
    named = [g for g in groups if any(a.lower() == lowered for a in g.agents)]
    wildcard = [g for g in groups if any(a == "*" for a in g.agents)]
    chosen = named or wildcard
    if not chosen:
        return False, ""

    best_len, best_allow, best_line = -1, True, ""
    for group in chosen:
        for rule in group.disallow:
            if _matches(rule, path) and len(rule) > best_len:
                best_len, best_allow, best_line = len(rule), False, f"Disallow: {rule}"
        for rule in group.allow:
            if _matches(rule, path) and len(rule) >= best_len:
                best_len, best_allow, best_line = len(rule), True, f"Allow: {rule}"

    if best_len < 0:
        return False, ""
    agent_line = "User-agent: " + (chosen[0].agents[0] if chosen[0].agents else "*")
    return (not best_allow), f"{agent_line} / {best_line}"


# -- page level -------------------------------------------------------------

_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
_CANONICAL = re.compile(r"""<link[^>]+rel=["']?canonical["']?[^>]*>""", re.I)
_HREF = re.compile(r"""href=["']([^"']+)["']""", re.I)
_JSONLD = re.compile(
    r"""<script[^>]+type=["']application/ld\+json["'][^>]*>(.*?)</script>""", re.S | re.I
)
_META_DESC = re.compile(
    r"""<meta[^>]+name=["']?description["']?[^>]+content=["']([^"']*)["']""", re.I
)
_ROBOTS_META = re.compile(
    r"""<meta[^>]+name=["']?robots["']?[^>]+content=["']([^"']*)["']""", re.I
)
_TAG = re.compile(r"<[^>]+>")
_SCRIPT_STYLE = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)


def visible_text(html: str) -> str:
    return _TAG.sub(" ", _SCRIPT_STYLE.sub(" ", html))


def audit(
    base_url: str,
    *,
    fetch: Fetcher = http_get,
    crawlers: dict[str, str] | None = None,
) -> SiteAudit:
    """Check permission and machine-readability for one site.

    `fetch` is injected so the whole audit runs in tests with no network. A
    fetch that fails is recorded in `unreachable` rather than treated as an
    absent file, because "we could not reach your robots.txt" and "you have no
    robots.txt" are different statements and only one of them is a finding.
    """
    crawlers = crawlers or AI_CRAWLERS
    findings: list[Finding] = []
    unreachable: list[str] = []

    root = base_url if base_url.endswith("/") else base_url + "/"
    path = urlparse(base_url).path or "/"

    # robots.txt: the only check that can explain a zero all by itself
    robots_url = urljoin(root, "/robots.txt")
    status, body = fetch(robots_url)
    if status == 0:
        unreachable.append(robots_url)
    elif status == 404 or not body.strip():
        findings.append(
            Finding(
                id="robots.absent",
                severity="ok",
                title="no robots.txt, so nothing is opted out",
                evidence=f"GET {robots_url} -> {status}",
                blocks="nothing. an absent robots.txt permits every crawler.",
            )
        )
    else:
        groups = parse_robots(body)
        for agent, owner in crawlers.items():
            blocked, line = is_disallowed(groups, agent, path)
            if blocked:
                findings.append(
                    Finding(
                        id=f"robots.blocked.{agent}",
                        severity="blocking",
                        title=f"{agent} is disallowed ({owner})",
                        evidence=line,
                        blocks=(
                            f"this closes the retrieval channel for {owner}. "
                            "content changes cannot move a surface the crawler is "
                            "not allowed to read."
                        ),
                    )
                )

    # llms.txt: cheap, and its absence is a real gap rather than a style note
    llms_url = urljoin(root, "/llms.txt")
    status, body = fetch(llms_url)
    if status == 0:
        unreachable.append(llms_url)
    elif status == 200 and body.strip():
        findings.append(
            Finding(
                id="llms.present",
                severity="ok",
                title="llms.txt is served",
                evidence=f"GET {llms_url} -> 200, {counted(len(body.strip()), 'byte')}",
                blocks="nothing.",
            )
        )
    else:
        findings.append(
            Finding(
                id="llms.absent",
                severity="missing",
                title="no llms.txt",
                evidence=f"GET {llms_url} -> {status}",
                blocks=(
                    "the site states nothing about itself in the one file written "
                    "for model consumption. not a block, a missed declaration."
                ),
            )
        )

    # the page itself
    status, html = fetch(base_url)
    if status == 0 or not html:
        unreachable.append(base_url)
        return SiteAudit(base_url, tuple(findings), tuple(unreachable))

    meta_robots = _ROBOTS_META.search(html)
    if meta_robots and "noindex" in meta_robots.group(1).lower():
        findings.append(
            Finding(
                id="page.noindex",
                severity="blocking",
                title="the page asks not to be indexed",
                evidence=meta_robots.group(0)[:200],
                blocks="a page that opts out of indexing cannot be retrieved and cited.",
            )
        )

    canonical = _CANONICAL.search(html)
    if not canonical:
        findings.append(
            Finding(
                id="canonical.absent",
                severity="degrading",
                title="no canonical link",
                evidence="",
                blocks="duplicate addresses of this page compete with each other as sources.",
            )
        )
    else:
        href = _HREF.search(canonical.group(0))
        target = href.group(1) if href else ""
        same_host = urlparse(urljoin(base_url, target)).netloc == urlparse(base_url).netloc
        if not same_host:
            findings.append(
                Finding(
                    id="canonical.offsite",
                    severity="blocking",
                    title="canonical points to another host",
                    evidence=canonical.group(0)[:200],
                    blocks=(
                        "the site is telling crawlers the real version of this page "
                        "lives elsewhere, so citations accrue to that host, not this one."
                    ),
                )
            )

    blocks = [m.group(1) for m in _JSONLD.finditer(html)]
    parsed_types: list[str] = []
    for block in blocks:
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            findings.append(
                Finding(
                    id="jsonld.invalid",
                    severity="degrading",
                    title="a JSON-LD block does not parse",
                    evidence=block.strip()[:200],
                    blocks="an unparseable block is read by nothing; it is decoration.",
                )
            )
            continue
        for item in data if isinstance(data, list) else [data]:
            if isinstance(item, dict) and item.get("@type"):
                parsed_types.append(str(item["@type"]))

    if not parsed_types:
        findings.append(
            Finding(
                id="jsonld.absent",
                severity="missing",
                title="no structured data",
                evidence="no valid application/ld+json block on the page",
                blocks=(
                    "facts about the brand have to be inferred from prose rather "
                    "than read, which is where they get inferred wrong."
                ),
            )
        )

    title = _TITLE.search(html)
    if not title or not title.group(1).strip():
        findings.append(
            Finding(
                id="title.absent",
                severity="degrading",
                title="no title",
                evidence="",
                blocks="the shortest description of the page is missing.",
            )
        )

    if not _META_DESC.search(html):
        findings.append(
            Finding(
                id="description.absent",
                severity="missing",
                title="no meta description",
                evidence="",
                blocks="no supplied summary, so any snippet is generated from the body.",
            )
        )

    text = visible_text(html).strip()
    if len(re.sub(r"\s+", " ", text)) < 200:
        findings.append(
            Finding(
                id="body.thin",
                severity="blocking",
                title="almost no text without running scripts",
                evidence=f"{counted(len(text), 'character')} of markup-stripped text",
                blocks=(
                    "a crawler that does not execute javascript sees an empty page, "
                    "so there is nothing to quote regardless of what users see."
                ),
            )
        )

    return SiteAudit(base_url, tuple(findings), tuple(unreachable))
