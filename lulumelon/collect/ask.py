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
from dataclasses import dataclass, field, replace
from typing import Protocol

from ..keys import redact

#: Values allowed in `Run.surface`. Anything else is a bug in a provider.
#:
#: `replica` is not a door anybody reaches an engine through. It marks a round
#: collected with the sources supplied as context, which is a laboratory
#: condition, and it is a surface so that `mirror` treats a snapshot mixing it
#: with live answers as the mixed condition it is rather than pooling the two.
SURFACES = ("logged_in", "logged_out", "api", "api_unsearched", "replica", "unspecified")

#: The API with no search tool attached. A separate surface from `api` because
#: it is a separate condition: the same question answered from the weights alone
#: rather than from pages fetched while answering, which is the whole point of
#: collecting it. Two arms both filed under `api` would be two conditions
#: wearing one name, poolable by everything downstream, and the measured surface
#: effect runs 1.5 to 3.6 times the run-to-run noise this library exists to
#: quantify, so pooling them would swamp the number being measured with the
#: difference between the arms.
#:
#: It is a surface rather than a flag on the round because a surface is already
#: carried on every record, printed into the snapshot's file name and read by
#: `mirror.compare.surface_confounds`, which voids a comparison across two of
#: them. A new field would have to be taught to all three.
UNSEARCHED_SURFACE = "api_unsearched"

UNKNOWN_MODEL = "unknown"

#: Where the calls below are asked from, which is nowhere in particular. Both
#: engines here publish a field for stating a location and neither request built
#: in this module carries one, so an answer is whatever the engine serves a call
#: that named none.
#:
#: It is a sentence here rather than a line on a screen because the surfaces
#: that print it must print the same words, and it is printed at all because an
#: unstated location reads as a location somebody chose. A round collected from
#: one country and read in another is a different measurement, and the reader is
#: the only person who can tell whether that matters to them.
NO_LOCATION = (
    "no location was requested, so the answers are whatever the engine serves a call "
    "that named none"
)

#: What a searched round can say about the ceiling it was collected under, which
#: is nothing. `DEFAULT_MAX_SEARCHES` is sent on every call as the tool's
#: `max_uses` and no field of a `Record` carries it, so two rounds collected
#: under two different caps read identically on disk. Stated rather than
#: defaulted to the constant below: the constant is what this build sends today,
#: not what the round on the reader's disk was collected with.
SEARCH_CAP_UNRECORDED = (
    "the cap on how many searches a call may run is not written to the ledger, so it is "
    "not recoverable from this round"
)

#: The same fact for the other arm, where it is recoverable. The arm is a
#: surface, the surface is on every record, and a call with no search tool
#: attached ran no searches.
NO_SEARCH_TOOL = "no search tool was attached to this arm, so no call could run a search"


def is_unsearched_surface(surface: str) -> bool:
    """Whether a round on this surface could have run a search at all.

    Read by anything that prices a recorded call. A fee charged per search is
    owed once per search, and a call that was never given the tool ran none, so
    the absence of a search count on one of these records is a measured zero
    rather than a silence to be charged at the floor.
    """
    return surface == UNSEARCHED_SURFACE


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
    #: How many searches the provider says it ran for this one call. Only some
    #: providers bill per search rather than per call, and on those this is the
    #: number the fee multiplies, so a call is not priceable without it.
    #:
    #: Written to disk from schema v3 on. It waited for a real response rather
    #: than for a specification, and it got one: the first billed call this
    #: repo ever made reported it. `request_cost` is still carried nowhere for
    #: exactly the same rule, having never arrived in any response.
    searches: int | None = None

    @property
    def known(self) -> bool:
        """True when the provider stated at least one of these."""
        return any(
            x is not None
            for x in (self.input_tokens, self.output_tokens, self.cost_usd, self.searches)
        )


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
    usage: Usage = field(default_factory=lambda: Usage())

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def provider_for(
    name: str,
    api_key: str,
    *,
    model: str | None = None,
    max_searches: int | None = None,
    can_search: bool = True,
) -> Provider:
    """The live provider for one engine name, or a refusal that lists the rest.

    One place where an engine name becomes a class. Without it every command
    that spends money picks a provider by hand, and the first one somebody
    forgets to update calls the wrong engine with the right key.

    `max_searches` is accepted and passed on only where it means something. A
    caller that wants the cheapest possible call sets it to one, and on an
    engine billed per request it changes nothing and is dropped rather than
    raising, so a caller does not have to know which engine it got.

    `can_search=False` is the opposite: it is refused where it means nothing,
    because it names a condition rather than a preference. An engine that
    answers by searching and cannot be asked not to would quietly collect the
    searched arm under the unsearched arm's name, and the two would then be
    compared as if one thing had changed between them.
    """
    builders = {"perplexity": PerplexityProvider, "anthropic": AnthropicProvider}
    try:
        builder = builders[name]
    except KeyError:
        known = ", ".join(sorted(builders))
        raise ValueError(f"no provider in this build can call {name!r}; it can call: {known}") from None
    kwargs: dict = {"api_key": api_key}
    if model:
        kwargs["model"] = model
    if max_searches is not None and builder is AnthropicProvider:
        kwargs["max_searches"] = max_searches
    if not can_search:
        if builder is not AnthropicProvider:
            raise ValueError(
                f"{name} answers by searching and this build cannot ask it not to, so there is "
                "no unsearched arm to collect from it. the contrast is between one engine asked "
                "with the tool and the same engine asked without it, and half of that is not a "
                "contrast"
            )
        kwargs["can_search"] = False
    return builder(**kwargs)


class Provider(Protocol):
    """Anything that can be asked a question on one named surface.

    `name` is the engine as it will be recorded (`chatgpt`, `perplexity`), and
    `surface` is which door was used. The pair is what makes two measurements
    comparable or not, so both are attributes of the provider rather than
    arguments to `ask`: a single provider instance cannot silently drift
    between surfaces halfway through a round.

    `max_output_tokens` is here for the opposite reason. It was a private
    number inside one provider, and both the layer that asked for forty
    answers in one call and the layer that priced that call were written as if
    it did not exist. It is the ceiling on everything a call can write back, so
    a guard that cannot read it is pricing a call it has not seen.

    A call whose answer will be longer asks for a provider capped for it rather
    than raising the cap on the one the round is using, because a round's
    ceiling is the same number for every draw in it and a cap raised mid-round
    would be a different experiment priced as the old one.
    """

    name: str
    surface: str
    max_output_tokens: int

    def ask(self, prompt: str) -> Answer: ...

    def with_output_cap(self, max_output_tokens: int) -> Provider: ...

    def without_search(self) -> Provider: ...


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
    max_output_tokens: int = 1024
    _calls: int = 0

    def with_output_cap(self, max_output_tokens: int) -> FakeProvider:
        """Cap in place, and hand back the same stub.

        The live providers hand back a copy, because a round's ceiling is one
        number and a cap raised inside it would be priced as the old one. This
        one has no ceiling to protect and does have a script and a call
        counter, and both live on the instance: a copy would make every capped
        call the first call again, and a test that set up a third reply would
        pass while reading the first.
        """
        self.max_output_tokens = max_output_tokens
        return self

    def without_search(self) -> FakeProvider:
        """The stub under the surface a call with no search tool records itself on."""
        return replace(self, surface=UNSEARCHED_SURFACE)

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
#: example shows it a hundred times larger than the token cost. It is still not
#: read and still not stored, and schema v3 opened and closed without it. The
#: schema a figure lands in is settled by a real response rather than by a
#: specification, and this endpoint has never answered this build: the only
#: calls it has ever billed went to the other provider, which publishes no cost
#: figure at all. A column standing empty for a name nobody has seen would read
#: as a figure that was collected and came back absent, which is a different
#: claim about a provider from the true one, that nobody has asked it yet.
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
    documents. Both are live. An unauthenticated probe returns 401 from each
    and 404 from a made-up path, so routing happens before auth and neither is
    gone. `/v1/sonar` is used because it is the documented one: an undocumented
    route gets no deprecation notice, and the response shape this class parses
    is only specified for the documented one.

    Sonar itself is soft-deprecated in favour of the Agent API, with no
    retirement date published anywhere. That migration is not made here, and
    the reason is that the Agent API's presets are unversioned by design: the
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
    #: Sent rather than left to the model's own default, because the guard
    #: prices this number and a cap that is only sent on one engine is a
    #: ceiling that is only true on one engine.
    max_output_tokens: int = 1024
    endpoint: str = "https://api.perplexity.ai/v1/sonar"
    timeout_s: float = 45.0

    def with_output_cap(self, max_output_tokens: int) -> PerplexityProvider:
        return replace(self, max_output_tokens=max_output_tokens)

    def without_search(self) -> PerplexityProvider:
        """Itself, because this engine answers by searching and cannot be asked not to.

        Returning the same object rather than raising, so a caller does not
        have to know which engine it got. What it must not do is assume the
        request it hands back runs no searches: the surface still says this one
        can, and the fee is priced off that.
        """
        return self

    def ask(self, prompt: str) -> Answer:
        body = json.dumps(
            {
                "model": self.model,
                "max_tokens": self.max_output_tokens,
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
            except Exception:  # noqa: BLE001 - the body is a courtesy, the status is the answer
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


# -- anthropic messages, with the search tool -------------------------------

#: The tool version this asks for, pinned rather than tracking the newest.
#: Later versions default `allowed_callers` to the code execution tool, which
#: turns on dynamic filtering: the model writes and runs code that filters the
#: search results before they reach its own context. That is a good feature and
#: a bad instrument. What the model was shown is the condition being measured,
#: and a filter composed afresh on every call is a condition that changes
#: between two runs of the same question with nothing on screen to say so.
WEB_SEARCH_TOOL = "web_search_20250305"

#: Version of the Messages API this speaks. Sent on every request and required.
ANTHROPIC_API_VERSION = "2023-06-01"

#: Searches one call may run before the provider refuses further ones. It is
#: not a tuning knob. The fee is charged per search and the documentation says
#: a comparative question can run ten or more, so an uncapped round has no
#: knowable price; and two rounds that searched different numbers of times are
#: two different conditions. Capping fixes both, and the cap is recorded with
#: the round by being part of the provider that collected it.
DEFAULT_MAX_SEARCHES = 3

#: Where the count of searches performed is reported. Documented on the web
#: search tool's own page, and the only number that makes a call priceable when
#: the fee is per search.
_SEARCH_COUNT_PATH = ("server_tool_use", "web_search_requests")


def _anthropic_usage(payload: dict) -> Usage:
    raw = payload.get("usage")
    if not isinstance(raw, dict):
        return Usage()
    node: object = raw
    for step in _SEARCH_COUNT_PATH:
        node = node.get(step) if isinstance(node, dict) else None
    searches = None if type(node) is bool or not isinstance(node, (int, float)) else int(node)
    return Usage(
        input_tokens=_first_int(raw, ("input_tokens",)),
        output_tokens=_first_int(raw, ("output_tokens",)),
        searches=searches,
        # No cost figure is published in this response, and inventing one from
        # our own table would turn our arithmetic into their invoice.
        cost_usd=None,
    )


def _anthropic_text(content: list) -> str:
    parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
    return "".join(parts)


def _anthropic_sources(content: list) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The pages retrieved, and the error codes any search came back with.

    Retrieved rather than cited, on purpose. This response reports both: the
    results a search returned, and the subset the answer actually quoted. They
    are different observations, and the other engine here reports only the
    first, so the first is what travels. Pooling one engine's retrievals with
    another's citations would give the source graph two meanings and no label.

    A failed search arrives inside a successful response, as a single error
    object where the result list would be. Read as an empty list it becomes
    "this question had no sources", which is a measurement claim nobody made.
    """
    urls: list[str] = []
    errors: list[str] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "web_search_tool_result":
            continue
        results = block.get("content")
        if isinstance(results, dict):
            errors.append(str(results.get("error_code") or "unspecified"))
            continue
        for item in results or []:
            if isinstance(item, dict) and item.get("type") == "web_search_result" and item.get("url"):
                urls.append(str(item["url"]))
    return tuple(urls), tuple(errors)


@dataclass
class AnthropicProvider:
    """Claude on the Messages API, with the web search tool on or left off.

    The second engine here, and the reason for a second one is not redundancy.
    A visibility number is about one door, and the published gap between doors
    is larger than the run-to-run noise this library exists to quantify, so an
    engine is a condition rather than an implementation detail. One engine
    measured well is a fact about that engine.

    It qualifies for this product on the same ground the first one did: it
    searches, and it reports the pages it retrieved as structured data rather
    than leaving them to be scraped back out of prose.

    **The fee is charged per search, not per call.** One call may run several,
    and the provider's own guidance says a comparative question can run ten or
    more. So `max_searches` is not a nicety, it is what makes a round's price
    knowable in advance and what keeps two rounds the same experiment.

    **A search that failed is not a search that found nothing.** The API
    answers 200 and puts the failure inside the body, so a reader that only
    looks at the result list records an absence of sources that never happened.
    Those codes come back on the answer and the round is marked failed, because
    an answer composed without the search it asked for is a different condition
    from the one being collected.

    **A paused turn is not a short answer.** The API can stop a long search turn
    with `pause_turn` and expects the message sent back to continue. Recording
    the fragment would enter a half-finished answer as an observation, and every
    such fragment is one where the brand had less room to be named.

    **`can_search=False` is the other arm, not a cheaper version of this one.**
    The tool is left off the request entirely rather than capped at nothing, so
    the model answers from its weights instead of from pages it fetched while
    answering. That difference is the measurement: it separates a brand the
    model knows from one it finds. A cap of zero with the tool still attached
    would be a third thing again, a model told it may look and then refused,
    and it is not what either arm is asking.

    The arm records itself under its own surface, derived here and never
    accepted from a caller, so no round can be filed under the other arm's
    name. That is what stops the two being pooled: everything downstream reads
    the condition off the record and the file name, and a label that could be
    passed in is a label that can be passed in wrong.
    """

    api_key: str = field(repr=False)
    name: str = "anthropic"
    surface: str = "api"
    model: str = "claude-opus-5"
    max_searches: int = DEFAULT_MAX_SEARCHES
    can_search: bool = True
    #: Enough for one answer to one question, which is what this default is
    #: for. A caller asking for a list of forty things sets its own, and the
    #: guard prices whatever this says, because the same number cannot be a
    #: private detail of the request and an input to the ceiling on it.
    max_output_tokens: int = 1024
    endpoint: str = "https://api.anthropic.com/v1/messages"
    timeout_s: float = 90.0

    def __post_init__(self) -> None:
        if not self.can_search:
            # Derived, never accepted, for the same reason a replica arm derives
            # its own: two conditions filed under one surface are poolable by
            # everything that reads a round, and nothing on disk would disagree.
            self.surface = UNSEARCHED_SURFACE
            return
        if self.max_searches < 1:
            raise ValueError(
                f"max_searches={self.max_searches} would collect answers with no search behind "
                "them, which is the ungrounded model and a different experiment. that experiment "
                "is collected with can_search=False, which sends no search tool at all"
            )

    def with_output_cap(self, max_output_tokens: int) -> AnthropicProvider:
        return replace(self, max_output_tokens=max_output_tokens)

    def without_search(self) -> AnthropicProvider:
        """The same engine with the tool left off, for a call that supplies its own pages.

        The copy files itself under the unsearched surface, which is where the
        rest of this library reads the condition off. That is what lets a
        caller price the call at no search fee without asserting anything: the
        arm says so itself.
        """
        return replace(self, can_search=False)

    def ask(self, prompt: str) -> Answer:
        payload: dict = {
            "model": self.model,
            "max_tokens": self.max_output_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if self.can_search:
            # Absent rather than empty on the other arm. A tool sent with a cap
            # of zero is still a tool the model was offered, and what is being
            # measured is an answer composed without one.
            payload["tools"] = [
                {
                    "type": WEB_SEARCH_TOOL,
                    "name": "web_search",
                    "max_uses": self.max_searches,
                }
            ]
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint,
            data=body,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": ANTHROPIC_API_VERSION,
                "content-type": "application/json",
            },
            method="POST",
        )

        started = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:400]
            except Exception:  # noqa: BLE001 - the body is a courtesy, the status is the answer
                pass
            return self._failed(started, f"http {e.code}: {detail or e.reason}")
        except Exception as e:  # noqa: BLE001 - recorded, never swallowed
            return self._failed(started, f"{type(e).__name__}: {e}")

        content = payload.get("content")
        if not isinstance(content, list):
            return self._failed(started, f"unexpected response shape: {str(payload)[:300]}")

        stop = payload.get("stop_reason")
        if stop == "pause_turn":
            return self._failed(
                started, "the turn paused mid-search, so this answer is a fragment rather than a reply"
            )
        if stop == "max_tokens":
            # The same rule as the line above, applied to the fragment this
            # class makes itself. An answer that stopped at the cap is one the
            # model had not finished writing, and the first one to reach a
            # reader arrived as a JSON array cut inside a value: nothing could
            # read it, so it was reported as forty candidates that failed to
            # parse rather than as a call that was not given room to answer.
            return self._failed(
                started,
                f"the reply stopped at its cap of {self.max_output_tokens} output tokens, so it "
                "is a fragment rather than a reply; the call needed more room than it was given",
            )

        urls, search_errors = _anthropic_sources(content)
        if search_errors:
            return self._failed(
                started, f"the search failed inside a successful call: {', '.join(search_errors)}"
            )

        return Answer(
            text=_anthropic_text(content),
            model=str(payload.get("model") or UNKNOWN_MODEL),
            surface=self.surface,
            latency_ms=int((time.monotonic() - started) * 1000),
            citations=urls,
            usage=_anthropic_usage(payload),
        )

    def _failed(self, started: float, why: str) -> Answer:
        return Answer(
            text="",
            model=UNKNOWN_MODEL,
            surface=self.surface,
            latency_ms=int((time.monotonic() - started) * 1000),
            status="error",
            error=redact(why, self.api_key),
        )
