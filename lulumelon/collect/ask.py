"""The boundary where a question leaves this machine.

Everything under `mirror/` is arithmetic over runs that already exist, and
`ledger.py` is where a run becomes a fact on disk. This module is the only
place that talks to something we do not control, which is why the interface is
narrow and why it records more than it is asked to.

Three rules shape it, and each one is a measurement decision rather than a
style preference.

**The surface is part of the answer, not part of the plumbing.** A published
comparison of three OpenAI access surfaces on one day, 300 trials each, found
one brand at 30% on logged-in ChatGPT and 62% logged out, and a different brand
at 18% logged-in and nothing at all through the API. Error measured across
surfaces ran 1.5 to 3.6 times the error measured within one, so the door is a
bigger variable than the run-to-run randomness this whole library exists to
quantify. A provider therefore has to declare which surface it speaks for, and
it travels with every answer. A collector that leaves this implicit produces a
number about itself.
(petralabs.com/intelligence/how-accurate-are-ai-visibility-tools, 26 Feb 2026)

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

    The names are read from Perplexity's published OpenAPI rather than guessed
    at. They are still read defensively, in order, because the shape has gone
    missing in production before: the fields stopped arriving on 19 December
    2025 and were restored the same day. A spec says what should come back, not
    what did.
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

#: Fields Perplexity has used for the source list, newest first. The changelog
#: says `citations` "has been fully deprecated and removed" in favour of
#: `search_results`, while the published OpenAPI for the same endpoint still
#: declares `citations`. The two documents disagree, so both are read and the
#: current one is read first. A rename that went unnoticed would show up as
#: "this question has no sources", which is a measurement claim we would be
#: making by accident.
_CITATION_FIELDS = ("search_results", "citations")


#: Token count names, read in order, first hit wins. Both pairs are documented,
#: in different APIs: `prompt_tokens`/`completion_tokens` are required in the
#: Sonar response, `input_tokens`/`output_tokens` are required in the Agent
#: API's. Reading both is what lets one provider class survive the migration
#: between them. A name we cannot find must show up as unknown, never as zero,
#: because zero tokens is a cost claim.
_INPUT_TOKEN_FIELDS = ("prompt_tokens", "input_tokens")
_OUTPUT_TOKEN_FIELDS = ("completion_tokens", "output_tokens")

#: Where the provider states the amount it billed. `usage.cost.total_cost` is
#: required in both the Sonar and the Agent API response schemas; nothing else
#: is documented anywhere, so nothing else is looked for. Guessing at extra
#: names costs nothing until one of them accidentally matches.
#:
#: `usage.cost.request_cost` is documented too, and is the number that matters
#: most for this product: it is the per-search charge, and the provider's own
#: example shows it a hundred times larger than the token cost. It is not
#: stored yet on purpose. The schema a figure lands in should be settled by a
#: real response rather than by a specification, and no call has been made.
_COST_PATHS = (("cost", "total_cost"),)


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
    larger than the noise we are here to measure. A number collected here is a
    number about this door.

    On the endpoint. Two routes answer: `/chat/completions`, which is what this
    code used to post to, and `/v1/sonar`, which is the one the reference
    documents. Both are live — an unauthenticated probe returns 401 from each
    and 404 from a made-up path, so routing happens before auth and neither is
    gone. `/v1/sonar` is used because it is the documented one: an undocumented
    route gets no deprecation notice, and the response shape this class parses
    is only specified for the documented one.

    Sonar itself is soft-deprecated in favour of the Agent API, with no
    retirement date published anywhere. That migration is not made here, and
    the reason is that the Agent API's presets are unversioned by design — the
    docs say a preset name "always resolves to the latest recommended
    configuration". An instrument whose units change under it when the vendor
    ships is not an instrument, so any move there has to pin an explicit model
    id rather than a preset.
    """

    #: `repr=False` is not cosmetic. A dataclass prints its fields, so a
    #: traceback that mentions this object, a logged round, or a debugger frame
    #: would otherwise carry the customer's key with it.
    api_key: str = field(repr=False)
    name: str = "perplexity"
    surface: str = "api"
    model: str = "sonar"
    endpoint: str = "https://api.perplexity.ai/v1/sonar"
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
