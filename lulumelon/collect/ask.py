"""The boundary where a question leaves this machine.

Everything under `mirror/` is arithmetic over runs that already exist, and
`ledger.py` is where a run becomes a fact on disk. This module is the only
place that talks to something we do not control, which is why the interface is
narrow and why it records more than it is asked to.

Three rules shape it, and each one is a measurement decision rather than a
style preference.

**The surface is part of the answer, not part of the plumbing.** Published
measurement puts the same brand at 30% on logged-in ChatGPT, 62% logged out and
0% through the API on the same day, an effect 1.5 to 3.6 times larger than the
run-to-run randomness this whole library exists to quantify. A provider
therefore has to declare which surface it speaks for, and it travels with every
answer. A collector that leaves this implicit produces a number about itself.

**The model version comes from the response, never from the request.** Asking
for a model name and recording that name assumes the provider honoured it.
Providers rotate hosted models without a changelog; in August 2025 a ChatGPT
change made citation links vanish from the HTML and every tracking product in
the category told its customers their score had dropped. What is recorded is
what came back, and `unknown` when the response does not say.

**A failed ask is an observation.** It is returned as an `Answer` with a status
of `error`, not raised and not retried here. An engine that refuses to answer
about a brand is telling you something about that brand, and a collector that
quietly retries until it gets a reply reports only the survivors.
"""

from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol

from ..keys import redact

#: Values allowed in `Run.surface`. Anything else is a bug in a provider.
SURFACES = ("logged_in", "logged_out", "api", "unspecified")

UNKNOWN_MODEL = "unknown"


@dataclass(frozen=True, slots=True)
class Usage:
    """What the provider says the call consumed, and what it says it cost.

    Every field is `None` until the response states it. Not `0`: a zero token
    count is a claim that the call was metered and consumed nothing, and a
    provider that renames a field would otherwise hand us that claim for free.
    The difference between "we did not observe this" and "we observed nothing"
    is the difference between an unknown cost and a wrong invoice.

    `cost_usd` is the provider's own figure, never ours. Perplexity's pricing
    page says the final cost is metered from the response's usage field, so
    when that figure is present it is used verbatim; filling it in from a price
    table and calling it metered would turn our arithmetic into their invoice.
    """

    input_tokens: int | None = None
    output_tokens: int | None = None
    search_context: str | None = None
    cost_usd: float | None = None

    @property
    def known(self) -> bool:
        """True when the provider stated at least one of these."""
        return any(x is not None for x in (self.input_tokens, self.output_tokens, self.cost_usd))


@dataclass(frozen=True, slots=True)
class Answer:
    """One reply, or one recorded failure to get a reply.

    `text` is empty when `status` is not `ok`. `citations` are the sources the
    provider itself reported, in the order it reported them; they are never
    scraped out of the prose, because a URL written in a sentence and a URL the
    provider says it consulted are different observations and conflating them
    would make the source graph unreadable.
    """

    text: str
    model: str
    surface: str
    latency_ms: int
    status: str = "ok"
    error: str = ""
    citations: tuple[str, ...] = ()
    usage: "Usage" = field(default_factory=lambda: Usage())

    @property
    def ok(self) -> bool:
        return self.status == "ok"


class Provider(Protocol):
    """Anything that can be asked a question on one named surface.

    `name` is the engine as it will be recorded (`chatgpt`, `perplexity`), and
    `surface` is which door was used. The pair is what makes two measurements
    comparable or not, so both are attributes of the provider rather than
    arguments to `ask`: a single provider instance cannot silently drift
    between surfaces halfway through a round.
    """

    name: str
    surface: str

    def ask(self, prompt: str) -> Answer: ...


# -- deterministic stub -----------------------------------------------------


@dataclass
class FakeProvider:
    """A provider with no network, used by the tests and by the demo.

    It is deterministic given a seed, which is the property that lets the whole
    collection path be exercised in CI with no key and no spend. `script` maps a
    prompt to the replies it should cycle through, so a test can set up a brand
    that appears in three answers out of five without patching anything.

    `usage` exists so the populated path is reachable without a network. A stub
    that always reports nothing would let the lines that carry token counts
    into the ledger be deleted with the whole suite still green, and those are
    the numbers a cost claim rests on.
    """

    name: str = "fake"
    surface: str = "api"
    model: str = "fake-1"
    script: dict[str, tuple[str, ...]] = field(default_factory=dict)
    citations: tuple[str, ...] = ()
    fail_on: tuple[int, ...] = ()
    usage: Usage = field(default_factory=Usage)
    _calls: int = 0

    def ask(self, prompt: str) -> Answer:
        i = self._calls
        self._calls += 1
        if i in self.fail_on:
            return Answer(
                text="",
                model=self.model,
                surface=self.surface,
                latency_ms=0,
                status="error",
                error="fake provider was told to fail on this draw",
            )
        replies = self.script.get(prompt) or ("no tracked brand was named.",)
        return Answer(
            text=replies[i % len(replies)],
            model=self.model,
            surface=self.surface,
            latency_ms=1,
            citations=self.citations,
            usage=self.usage,
        )


# -- perplexity sonar -------------------------------------------------------

#: Fields Perplexity has used for the source list across API versions. Read in
#: order, first hit wins. Listed rather than assumed because a rename would
#: otherwise show up as "this question has no sources", which is a measurement
#: claim we would be making by accident.
_CITATION_FIELDS = ("citations", "search_results")


#: Names the token counts have appeared under. Read in order, first hit wins,
#: for the same reason the citation fields are listed: a rename must show up as
#: "unknown", never as zero, because zero tokens is a cost claim.
_INPUT_TOKEN_FIELDS = ("prompt_tokens", "input_tokens")
_OUTPUT_TOKEN_FIELDS = ("completion_tokens", "output_tokens")
#: Where the provider's own total, when it reports one, has been seen.
_COST_PATHS = (("cost", "total_cost"), ("cost", "total_cost_usd"), ("total_cost",))


def _first_int(d: dict, names: tuple[str, ...]) -> int | None:
    """The first of `names` the response actually carries, or None.

    `None` and not `0`, so a rename shows up as unknown rather than as a
    metered zero. Booleans are refused on the way past: `isinstance(True, int)`
    is True in Python, so a field carrying `true` would otherwise be recorded
    as one token.
    """
    for name in names:
        value = d.get(name)
        if type(value) is bool:
            continue
        if isinstance(value, (int, float)):
            return int(value)
    return None


def _reported_cost(usage: dict) -> float | None:
    for path in _COST_PATHS:
        node: object = usage
        for step in path:
            node = node.get(step) if isinstance(node, dict) else None
        if type(node) is bool:
            continue
        if isinstance(node, (int, float)) and math.isfinite(node):
            return float(node)
    return None


def _usage(payload: dict) -> Usage:
    raw = payload.get("usage")
    if not isinstance(raw, dict):
        return Usage()
    context = raw.get("search_context_size")
    return Usage(
        input_tokens=_first_int(raw, _INPUT_TOKEN_FIELDS),
        output_tokens=_first_int(raw, _OUTPUT_TOKEN_FIELDS),
        # Read the key rather than coalescing it. `or ""` turns "the provider
        # said nothing" into "the provider said empty", permanently, in the one
        # field that decides which request-fee band applies.
        search_context=str(context) if context is not None else None,
        cost_usd=_reported_cost(raw),
    )


def _urls(payload: dict) -> tuple[str, ...]:
    for key in _CITATION_FIELDS:
        raw = payload.get(key)
        if not raw:
            continue
        out: list[str] = []
        for item in raw:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict) and item.get("url"):
                out.append(str(item["url"]))
        if out:
            return tuple(out)
    return ()


@dataclass
class PerplexityProvider:
    """Perplexity Sonar, over the documented chat-completions endpoint.

    Chosen first because it returns its sources as structured data. The source
    graph cannot be built from a surface that only returns prose, and guessing
    at which pages a model read is the part of this category that is currently
    all guesswork.

    Recorded honestly: this is the **api** surface. It is not what a person
    typing into a browser sees, and the published gap between those two is
    larger than the noise we are here to measure. Treating this number as the
    user-facing one would be the same mistake the category makes.
    """

    #: `repr=False` is not cosmetic. A dataclass prints its fields, so a
    #: traceback that mentions this object, a logged round, or a debugger frame
    #: would otherwise carry the customer's key with it.
    api_key: str = field(repr=False)
    name: str = "perplexity"
    surface: str = "api"
    model: str = "sonar"
    endpoint: str = "https://api.perplexity.ai/chat/completions"
    timeout_s: float = 45.0

    def ask(self, prompt: str) -> Answer:
        body = json.dumps(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        started = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # the body often carries the real reason; the status alone is not
            # enough to tell a bad key from a rate limit from a bad model name.
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:400]
            except Exception:
                pass
            return self._failed(started, f"http {e.code}: {detail or e.reason}")
        except Exception as e:  # noqa: BLE001 - recorded, never swallowed
            return self._failed(started, f"{type(e).__name__}: {e}")

        elapsed = int((time.monotonic() - started) * 1000)
        try:
            text = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return self._failed(started, f"unexpected response shape: {str(payload)[:300]}")

        return Answer(
            text=text,
            # what came back, not what was asked for
            model=str(payload.get("model") or UNKNOWN_MODEL),
            surface=self.surface,
            latency_ms=elapsed,
            citations=_urls(payload),
            usage=_usage(payload),
        )

    def _failed(self, started: float, why: str) -> Answer:
        # The reason travels into the ledger and onto the screen, and it is
        # partly the provider's own words about a request that carried a key.
        # Scrubbing happens here, at the one place those words are created.
        return Answer(
            text="",
            model=UNKNOWN_MODEL,
            surface=self.surface,
            latency_ms=int((time.monotonic() - started) * 1000),
            status="error",
            error=redact(why, self.api_key),
        )
