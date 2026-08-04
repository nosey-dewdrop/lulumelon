"""`lulu`: the commands that stand between a person and a defensible number.

Two are about getting started, two are about money and evidence, and one is
about whether the causal half of this product is real at all.

`lulu init` asks for a key, stores it, and says out loud where it stored it.
`lulu doctor` answers "why is it not working" in one screen: every place that
was looked at, what was wrong with the key as a string, whether the endpoint is
reachable at all, and what the one test call cost.
`lulu plan` sizes a round before it is bought, and says where no number of
repeats would be enough.
`lulu collect` runs one round end to end and writes it down, under a ceiling it
prints before it spends anything.
`lulu report` prints what a collected round measured about one brand, with the
questions that name the brand excluded from the rate and said out loud, and
writes the same thing as a document that carries the ledger it came from.
`lulu usage` says what the rounds already on disk cost, and `lulu verify`
re-derives their chains so the person relying on that can check it themselves.
`lulu ablate` asks whether a replica round tracks the live surface closely
enough to reason from, and returns three answers rather than two, because a
design that cannot tell has not passed.
`lulu lift` measures what one source was worth, between the arm that carried it
and the arm that did not, and prints that number under a name it has to earn:
without a gate that passed, the same arithmetic is a fact about a laboratory.

All of them are written so nothing is guessed. Where the code cannot know
something it says so: an unknown price is "no published price on file", not a
plausible number; a rejected key names the states that produce that rejection
rather than printing a status code; and a round nobody metered is priced as a
floor rather than padded out with zeros and called an estimate.

Every stream and every prompt is injected, so the whole interaction is exercised
in tests without a terminal and without a key.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence, TextIO

from .collect.ask import (
    DEFAULT_MAX_SEARCHES,
    UNSEARCHED_SURFACE,
    Answer,
    Provider,
    provider_for,
)
from .collect.budget import UNMEASURED_INPUT_TOKENS, Budget
from .collect.ledger import (
    DIAGNOSTIC_SUBJECT,
    Ledger,
    LedgerFormatError,
    Record,
    is_diagnostic,
)
from .collect.replay import Replay, replay
from .collect.replica import (
    REPLICA_SURFACE,
    is_replica_surface,
    replica_surface,
    without,
)
from .collect.audit import http_get
from .collect.detect import Brand, detect
from .collect.harvest import DEFAULT_MAX_PAGES, harvest
from .collect.propose import (
    DEFAULT_PAGE_CHARS,
    DEFAULT_WANTED,
    call_for,
    pages_for_screening,
    propose,
)
from .collect.session import Prompt, run_round, utc_now
from .collect.subject import Subject, load_subject
from .mirror.screen import (
    CARRIES,
    Candidate,
    minimum_draws,
    pool_variance,
    screen,
    screen_by_discrimination,
    stable_ids,
)
from .mirror.ablation import DIFFERS, STANDS_IN, UNDECIDED, replica_gate
from .mirror.compare import model_confounds
from .mirror.lift import MOVES, NEGLIGIBLE, NO_CONTRAST
from .mirror.lift import UNDECIDED as EFFECT_UNDECIDED
from .mirror.lift import source_effect
from .mirror.names import names_in
from .mirror.report import NothingLeftToScore, brand_report
from .mirror.types import Reply, Snapshot, group_runs
from .mirror.variance import decompose
from .latex import Evidence, tex_document, tex_screening
from .keys import (
    KEYCHAIN_SERVICE,
    PROVIDERS,
    KeychainRefused,
    ProviderSpec,
    Resolution,
    ensure_gitignored,
    env_file_candidates,
    fingerprint,
    inspect_key,
    keychain_supported,
    keychain_write,
    redact,
    resolve,
    spec_for,
    write_env_file,
)
from .prices import FEE_PER_SEARCH, Cost, Price, estimate, fees, price_for, reported
from .plan import (
    MIN_DRAWS,
    Comparison,
    Design,
    Engine,
    SetDesign,
    critical_value,
    draws_needed,
    icc_of,
    price_of,
    prompts_for_worst_case,
    reachable_icc,
    total_variance,
    variance_of,
)
from .panel import Panel, Question, ScreenPanel, Screened
from .text import counted
from .usage import spend_of, token_rate

#: Where rounds are written unless a caller says otherwise. Relative on
#: purpose: a measurement belongs to the project it was made for.
DEFAULT_LEDGER = "./ledger"

#: The model a check call uses when nothing names one. Per provider, on the
#: spec, because the cheapest search-grounded model has a different name on
#: every price table and a default borrowed across providers is a 404.
def check_model_for(provider: str) -> str:
    return spec_for(provider).check_model


#: Searches a planned call is assumed to run, for providers that bill per
#: search. It is the collector's own cap, so the plan prices the same ceiling
#: the round will be collected under rather than a number chosen here.
SEARCHES_PER_CALL = DEFAULT_MAX_SEARCHES

#: The check call asks a question that cannot be answered without looking
#: something up, and caps the reply at a few words.
#:
#: A cheaper prompt was tried first and it proved less. "Reply with the word
#: ok" shows that the key is accepted and nothing else, and the two ways this
#: product actually fails on a new account are that the search tool is switched
#: off for the organisation and that the search runs but returns nothing. Both
#: of those pass a keys-only check and then break a whole round later. So the
#: diagnostic exercises the path it is diagnosing, and the extra searches are
#: cents against finding out on the first real measurement.
CHECK_PROMPT = "Search the web, then answer in under ten words: what is today's date?"


@dataclass(frozen=True, slots=True)
class Console:
    """Where output goes, so a test can read what a user would have seen.

    Every line is flushed. Python block-buffers a stdout that is not a
    terminal, so an unflushed wizard piped into anything asks for the key
    before printing the instructions that say where to get one.
    """

    out: TextIO
    err: TextIO

    def say(self, line: str = "") -> None:
        print(line, file=self.out, flush=True)

    def warn(self, line: str) -> None:
        print(line, file=self.err, flush=True)


# -- setup ------------------------------------------------------------------


def provider_of(key: str) -> str | None:
    """Which engine a key belongs to, read off the key itself.

    So that nobody has to be asked. A person who has just copied a key knows
    where they copied it from and should not have to translate that into a flag
    for a tool that can see the answer in front of it.
    """
    for name, spec in sorted(PROVIDERS.items()):
        if spec.key_prefix and key.startswith(spec.key_prefix):
            return name
    return None


def read_key(console: Console, stdin: TextIO, secret: Callable[[str], str]) -> str:
    """The key, through whichever of the two doors this shell actually has.

    Piped in where there is no terminal, typed invisibly where there is.
    Neither puts it in shell history, and neither asks the person to work out
    which case they are in.
    """
    if not stdin.isatty():
        return stdin.read().strip()
    console.say("Paste your API key and press enter. It will not be shown.")
    try:
        return secret("key: ").strip()
    except (EOFError, OSError):
        return ""


def setup(
    console: Console,
    *,
    key: str,
    cwd: Path,
    home: Path,
    provider: str | None = None,
    check: Callable[..., int] | None = None,
) -> int:
    """Store one key and prove it works, with nothing to decide on the way.

    This replaces a wizard that asked three questions, and it exists because
    the person it was written for could not finish it. Every question was a
    decision the tool was better placed to make than the customer, and every
    one of them was a place to stop. A setup step that offers options fails on
    whichever option the reader picks wrong.

    So the engine is read off the key, the safest storage the machine has is
    used without a menu, and the check call runs in the same breath. What is
    left to the person is the part only they can do, which is having a key.

    **The safest storage is the one that takes the key, not the one the
    platform implies.** This asked `keychain_available()` whether a Mac has a
    keychain, was told yes, and then had nowhere to go when the write failed:
    thirty seconds of nothing, a `TimeoutExpired` that the caller did not catch
    because it is not a `RuntimeError`, and a stack trace under a key that had
    been stored in no place at all. The file the page promises was written on
    the other side of a branch that a Mac could never reach. So the keychain is
    attempted, a refusal is reported in the reader's words, and the file that
    was always documented is where the key then goes.
    """
    key = key.strip()
    if not key:
        console.warn("No key arrived, so nothing was stored.")
        console.warn("On macOS, with the key on your clipboard:  pbpaste | lulu setup")
        return 1

    name = provider or provider_of(key)
    if name is None:
        known = ", ".join(f"{s.name} keys start with {s.key_prefix!r}" for s in PROVIDERS.values())
        console.warn(f"This key matches no engine this build can call. {known}.")
        console.warn("If it is right anyway, name the engine with --provider.")
        return 1
    spec = spec_for(name)

    for problem in inspect_key(spec, key):
        console.warn(f"note: {problem}")

    # No menu. The keychain first where the platform has one, the file the page
    # already documents where the keychain will not take it, and the answer
    # printed rather than asked.
    where = ""
    reread = ""
    refusal = ""
    if keychain_supported():
        try:
            keychain_write(KEYCHAIN_SERVICE, spec.name, key)
        except ValueError as e:
            # The key itself cannot be stored by any route here, so there is
            # nothing to fall back to and saying so is the whole of the job.
            console.warn(f"This key cannot be stored as it stands: {redact(str(e), key)}")
            return 1
        except KeychainRefused as e:
            refusal = redact(str(e), key)
        else:
            where = f"the OS keychain, service {KEYCHAIN_SERVICE}, account {spec.name}"
            reread = f"security find-generic-password -s {KEYCHAIN_SERVICE} -a {spec.name} -w"

    if not where:
        if refusal:
            console.warn(f"The keychain would not take it: {refusal}")
            console.warn("The key went to a file instead, which lulu reads after the keychain.")
        _, home_file = env_file_candidates(cwd, home)
        try:
            path = write_env_file(home_file, spec.env_var, key)
        except OSError as e:
            console.warn(f"{home_file} would not take it either: {e.strerror}.")
            console.warn(f"Nothing was stored. Export {spec.env_var} in this shell to get moving.")
            return 1
        where = f"{path}, permissions 600, owner only"
        reread = f"grep {spec.env_var} {path}"

    console.say(f"Stored your {spec.name} key in {where}.")
    console.say(f"Fingerprint {fingerprint(key)}. Read it back yourself with:  {reread}")
    console.say()

    # Relative to the directory this was run from, like every other round. A
    # measurement belongs to the project it was made for, and so does the
    # receipt for the call that proved the key could pay for one.
    return (check or check_call)(console, spec, key, ledger_dir=cwd / DEFAULT_LEDGER)


# -- init -------------------------------------------------------------------


def storage_menu(cwd: Path, home: Path) -> list[tuple[str, str]]:
    """The places a key can be put, described by where the file will land.

    The keychain is offered only where it has been exercised. An option that
    might silently not store anything is worse than one fewer option.
    """
    local, home_file = env_file_candidates(cwd, home)
    menu = []
    if keychain_supported():
        menu.append(("keychain", f"the OS keychain (service {KEYCHAIN_SERVICE}), not a file and not in the repo"))
    menu.append(("local", f"{local}, read only in this directory"))
    menu.append(("home", f"{home_file}, read from anywhere"))
    return menu


def init(
    console: Console,
    *,
    ask: Callable[[str], str],
    secret: Callable[[str], str],
    cwd: Path,
    home: Path,
    provider: str = "perplexity",
    from_env: bool = False,
    from_file: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    """Walk one person through storing one key, and confirm where it went.

    **There has to be a way in that does not need a terminal.** The prompt this
    used to insist on cannot hide what is typed unless it owns a tty, and the
    places people actually run setup from now include editors, agent shells and
    CI, none of which give it one. Asking anyway ended in a traceback with the
    key half typed, which is the worst of both: nothing stored, and a secret
    possibly echoed on its way to failing.

    So the secret can arrive from the environment or from a file instead, and
    the interactive path is what happens when a tty is there to make it safe.
    Neither of the other two puts the key in shell history, which is the thing
    the hidden prompt was protecting against in the first place.
    """
    spec = spec_for(provider)
    console.say(f"lulu init: setting up {spec.name}")
    console.say()

    key = ""
    if from_file is not None:
        try:
            key = from_file.read_text(encoding="utf-8").strip()
        except OSError as e:
            console.warn(f"Could not read {from_file}: {e}")
            return 1
        if not key:
            console.warn(f"{from_file} is empty, so nothing was stored.")
            return 1
        console.say(f"Read the key from {from_file}. Delete that file once this finishes.")
    elif from_env:
        source = os.environ if env is None else env
        for name in spec.env_names:
            if source.get(name, "").strip():
                key = source[name].strip()
                console.say(f"Read the key from the environment variable {name}.")
                break
        if not key:
            console.warn(
                f"None of {', '.join(spec.env_names)} is set, so there was nothing to read."
            )
            return 1
    else:
        console.say(f"1. Open {spec.key_page}")
        console.say("2. Sign in, open the API Keys tab, and create a key.")
        console.say("3. The key is shown once. Copy it, then paste it below.")
        console.say()
        console.say(f"   Keys for {spec.name} start with {spec.key_prefix!r} ({spec.key_prefix_source}).")
        console.say("   Nothing you type is echoed, logged, or sent anywhere except to the provider.")
        console.say()
        try:
            key = secret(f"Paste your {spec.name} API key: ").strip()
        except (EOFError, OSError):
            # No tty, so the prompt could neither read the key nor promise to
            # hide it. Say which of the other two doors to use rather than
            # leaving a stack trace where the instructions should be.
            console.warn("This shell has no terminal, so a hidden prompt is not possible here.")
            console.warn("")
            console.warn("Two ways in that do not echo the key and do not put it in shell history:")
            console.warn(f"  1. Run the same command in a real terminal window.")
            console.warn(f"  2. Put the key in a file, then run:")
            console.warn(f"       lulu init --provider {spec.name} --from-file /path/to/keyfile")
            console.warn(f"     and delete the file afterwards.")
            console.warn("")
            console.warn(f"  Already exported {spec.env_var}?  lulu init --provider {spec.name} --from-env")
            return 1
    if not key:
        console.warn("No key entered, so nothing was stored.")
        return 1

    problems = inspect_key(spec, key)
    if problems:
        console.say()
        console.say("Before storing it, two things look wrong:" if len(problems) > 1 else "One thing looks wrong:")
        for problem in problems:
            console.say(f"  - {problem}")
        console.say()
        if ask("Store it anyway? [y/N]: ").strip().lower() not in ("y", "yes"):
            console.say("Nothing was stored.")
            return 1

    menu = storage_menu(cwd, home)
    console.say()
    console.say("Where should it be kept?")
    for i, (_, description) in enumerate(menu, start=1):
        console.say(f"  {i}. {description}")
    console.say()
    choice = ask(f"Choose 1-{len(menu)} [1]: ").strip() or "1"
    if not choice.isdigit() or not 1 <= int(choice) <= len(menu):
        console.warn(f"{choice!r} is not one of the options, so nothing was stored.")
        return 1
    kind = menu[int(choice) - 1][0]

    local_file, home_file = env_file_candidates(cwd, home)
    if kind == "keychain":
        try:
            keychain_write(KEYCHAIN_SERVICE, spec.name, key)
        except (KeychainRefused, ValueError) as e:
            # No silent fallback here, unlike `setup`. The person picked this
            # option off a menu, so quietly writing the key to a file they did
            # not choose would answer a question they had already answered.
            console.warn(f"The keychain refused it: {redact(str(e), key)}")
            console.warn("Run lulu init again and pick a file, or lulu setup, which falls back itself.")
            return 1
        where = f"the OS keychain, service {KEYCHAIN_SERVICE}, account {spec.name}"
        reread = f"security find-generic-password -s {KEYCHAIN_SERVICE} -a {spec.name} -w"
    else:
        path = write_env_file(local_file if kind == "local" else home_file, spec.env_var, key)
        where = f"{path} (permissions 600, owner only)"
        reread = f"grep {spec.env_var} {path}"
        if kind == "local":
            added = ensure_gitignored(cwd)
            if added:
                console.say(f"Added {', '.join(added)} to .gitignore so the key cannot be committed.")

    console.say()
    console.say(f"Stored in {where}.")
    console.say(f"Fingerprint: {fingerprint(key)}")
    console.say(f"Read it back yourself with: {reread}")
    console.say()
    console.say("Now run:  lulu doctor")
    return 0


# -- doctor -----------------------------------------------------------------


def report_lookup(console: Console, spec: ProviderSpec, found: Resolution) -> None:
    console.say(f"Looking for a {spec.name} key, in order:")
    for line in found.explain():
        console.say(f"  {line}")
    console.say()
    if found.ok:
        console.say(f"Using the key from {found.source}.")
        console.say(f"Fingerprint: {fingerprint(found.key)}")
    else:
        console.say("No key was found in any of those places.")
        console.say(f"Get one at {spec.key_page}, then run:  lulu init")


def record_check_call(
    ledger_dir: Path,
    spec: ProviderSpec,
    answer: Answer,
    *,
    clock: Callable[[], str] = utc_now,
) -> Path:
    """Write the call that was just billed, and hand back where it went.

    A call that cost money and is not in the ledger is the one kind of
    unrecorded spend this library exists to argue against, and until now the
    two commands that bill one wrote nothing: `lulu usage` could not see money
    that had actually been spent, and `lulu plan --pilot` had no measured token
    rate to size a round from.

    It is written to its own snapshot, under its own subject, because a
    diagnostic is not a measurement. It asks about the account rather than
    about a brand, and it is asked once; pooled into a round it would enter the
    sample as a question where every tracked name went unmentioned. The
    separation lives in the file name and in the record's own prompt id rather
    than in a convention, and `replay` refuses to turn this snapshot into runs
    at all.

    A failed call is written too, with its status and the provider's reason.
    The failures are the interesting half here: an account that cannot spend is
    the state this command exists to find, and a diagnostic that only records
    its successes is a diagnostic that flatters itself.

    Only what the provider reported goes in, including the count of searches it
    ran, which schema v3 hashes and which is the number a per-search fee
    multiplies. This is the call that proved that count arrives, so it is also
    the call that has to record it: without it `lulu usage` prices this round
    at one fee and the account is billed for as many searches as the model
    chose to make.

    One call is still a round, so it is closed like one. The seal states that
    the round made one call and how it came out, which is what makes a
    diagnostic that was cut down to nothing distinguishable from a diagnostic
    that failed to write.
    """
    store = Ledger(ledger_dir)
    snapshot_id = store.next_snapshot_id(DIAGNOSTIC_SUBJECT, spec.name, answer.surface)
    store.append(
        snapshot_id,
        Record(
            snapshot_id=snapshot_id,
            seq=0,  # the ledger assigns the real one; it owns the order
            prompt_id=DIAGNOSTIC_SUBJECT,
            repeat=0,
            engine=spec.name,
            surface=answer.surface,
            # What answered, not what was asked for. A provider that quietly
            # served another model billed at that model's rate, and this is the
            # only record of which one it was.
            model=answer.model,
            asked_at=clock(),
            status=answer.status,
            latency_ms=answer.latency_ms,
            answer_text=answer.text,
            # No brand list was supplied to a diagnostic, so there is nothing
            # detected here. An empty tuple is the honest value: nothing was
            # looked for, rather than looked for and not found.
            brands=(),
            citations=answer.citations,
            provider=spec.name,
            error=answer.error,
            input_tokens=answer.usage.input_tokens,
            output_tokens=answer.usage.output_tokens,
            search_context=answer.usage.search_context,
            reported_cost_usd=answer.usage.cost_usd,
            searches=answer.usage.searches,
        ),
    )
    store.seal(
        snapshot_id,
        asked=1,
        ok=1 if answer.ok else 0,
        errors=0 if answer.ok else 1,
        at=clock(),
    )
    return store.path_of(snapshot_id)


def check_call(
    console: Console, spec: ProviderSpec, key: str, *, ledger_dir: Path, model: str | None = None
) -> int:
    """Spend the smallest possible amount to find out whether the key works.

    `ledger_dir` has no default. This function is the only place in the library
    that bills a call outside a collected round, and a default here would let a
    caller spend money without having decided where the evidence of it lands.
    """
    model = model or spec.check_model
    price = price_for(spec.name, model)
    if price is None:
        console.say(f"No published price on file for {spec.name}/{model}, so the cost of this call is unknown.")
    else:
        console.say(f"One {model} call is billed at {price.provenance()}:")
        console.say(
            f"  tokens ${price.input_per_mtok_usd:g} in / ${price.output_per_mtok_usd:g} out per million, "
            f"plus a fee of {price.fee_text}."
        )
    console.say(f"Asking {spec.name} one question that needs a search now.")
    console.say()

    answer = provider_for(spec.name, key, model=model).ask(CHECK_PROMPT)

    # Written before anything is printed. The money is spent the moment the
    # call comes back, so the record is made before any work that could fail
    # between spending it and writing it down.
    path = record_check_call(ledger_dir, spec, answer)

    if not answer.ok:
        console.say(f"The call failed after {answer.latency_ms} ms.")
        console.say(f"  {answer.error}")
        console.say(f"  recorded as an error in {path}")
        console.say()
        for line in diagnose(spec, answer.error):
            console.say(f"  {line}")
        return 1

    console.say(f"It worked, in {answer.latency_ms} ms.")
    console.say(f"  model as reported by the response: {answer.model}")
    console.say(f"  reply: {answer.text.strip()[:120]}")

    # The two failures a keys-only check would have called a success. Both are
    # the product's own premise not holding on this account, so they are stated
    # here rather than discovered on the first round that cost real money.
    if answer.usage.searches is not None:
        console.say(f"  searches it ran: {answer.usage.searches}")
    if answer.citations:
        console.say(f"  sources it returned: {len(answer.citations)}, first is {answer.citations[0]}")
    else:
        console.warn("  NO SOURCES. The call succeeded and came back with nothing to cite.")
        console.warn("  This product measures which pages an answer travels with, so a round")
        console.warn("  collected in this state would record every question as having none.")

    counted = answer.usage.input_tokens is not None and answer.usage.output_tokens is not None
    if counted:
        console.say(f"  tokens: {answer.usage.input_tokens} in, {answer.usage.output_tokens} out")
    else:
        console.say("  tokens: the response did not report them")

    cost: Cost | None
    if answer.usage.cost_usd is not None:
        cost = reported(answer.usage.cost_usd)
    elif price is None:
        cost = None
    elif counted:
        cost = estimate(
            price,
            input_tokens=answer.usage.input_tokens,
            output_tokens=answer.usage.output_tokens,
            # What it actually cost, from what the provider says it did. On a
            # per-search fee the call count is not the fee count, and quoting
            # one call here would understate the bill by however many times the
            # model chose to look.
            fee_units=answer.usage.searches if answer.usage.searches is not None else 1,
        )
    else:
        # No metered figure and no token counts. The request fee is still known
        # and is the larger term, so it is reported as the floor it is rather
        # than padded out with zero tokens and called an estimate.
        cost = fees(price)

    if cost is None:
        console.say("  cost: unknown, because no price for this model has been read from the provider")
    else:
        console.say(f"  cost of this call: {cost.as_text()}")
    # Last, and on every path that got an answer. A command that writes a file
    # into whatever directory it was run from has to say so, and the line that
    # says it must not sit behind a branch that returned early.
    console.say(f"  recorded in {path}")
    return 0


def diagnose(spec: ProviderSpec, error: str) -> list[str]:
    """Turn a provider error into the thing to go and do about it.

    A status code is not a diagnosis. Each branch below names the state the
    account is actually in and where to change it, because that is the gap
    between a person who fixes this in a minute and one who gives up.
    """
    lowered = error.lower()
    if "http 401" in lowered or "invalid api key" in lowered:
        return [
            "The endpoint answered, so the network is fine. It rejected the key.",
            "That is one of three things: the key was revoked, it was copied incompletely,",
            f"or it belongs to another account. Check the key list at {spec.key_page}",
            "and create a fresh one, then run: lulu init",
        ]
    if "http 402" in lowered or "insufficient" in lowered or "credit" in lowered:
        return [
            "The key is valid but the account has no credit, so no call can be billed.",
            f"Add credit at {spec.billing_page} and run this again.",
        ]
    if "http 429" in lowered:
        return [
            "The key is valid and the account is billable. You are being rate limited.",
            "Wait a minute and run this again; nothing is wrong with the setup.",
        ]
    if "http 404" in lowered:
        return [
            "The key was never checked: that endpoint does not exist.",
            "The provider has moved it. This is our bug, not your setup.",
        ]
    if "timeout" in lowered or "urlerror" in lowered or "gaierror" in lowered:
        return [
            "Nothing answered, so the key was never tested.",
            "This is a network path problem: no route, DNS, or a proxy in the way.",
        ]
    return ["The provider's own words are above. It is not a known failure, so nothing is being guessed here."]


def doctor(
    console: Console,
    *,
    cwd: Path,
    home: Path,
    provider: str = "perplexity",
    offline: bool = False,
    env: Mapping[str, str] | None = None,
    keychain: Callable[[str, str], str | None] | None = None,
) -> int:
    """One screen that says why it does not work, or proves that it does.

    `env` and `keychain` default to the real ones and exist so a test can pin
    the machine's own state out of the way. A diagnostic whose result depends
    on what happens to be exported in the shell running the tests would be
    telling us about the shell.
    """
    spec = spec_for(provider)
    console.say(f"lulu doctor: {spec.name}")
    console.say()
    found = resolve(spec, cwd=cwd, home=home, env=env, keychain=keychain)
    report_lookup(console, spec, found)
    if not found.ok:
        return 1

    problems = inspect_key(spec, found.key)
    if problems:
        console.say()
        console.say("The key is stored, but as a string it looks wrong:")
        for problem in problems:
            console.say(f"  - {problem}")

    console.say()
    if offline:
        console.say("Stopping here: --offline was given, so no call was made and nothing was spent.")
        return 0
    return check_call(console, spec, found.key, ledger_dir=cwd / DEFAULT_LEDGER)


# -- collect ----------------------------------------------------------------

#: Returned when the ceiling stopped the round before it had asked everything.
#: Not zero and not an error. The file on disk is a real round, shorter than
#: the design that bought it, so every interval computed from it is wider than
#: that design asked for; a caller that read a short round as a completed one
#: would publish the wider interval as the planned one. The screen says the
#: same thing in words, because a code is read by a script and a person needs
#: to be told that a shorter round is not a failed one.
ROUND_CUT_SHORT = 4


def collect(
    console: Console,
    *,
    subject_path: Path,
    ledger_dir: Path,
    k: int,
    budget_usd: float,
    cwd: Path,
    home: Path,
    provider: str = "anthropic",
    model: str | None = None,
    max_searches: int = DEFAULT_MAX_SEARCHES,
    can_search: bool = True,
    env: Mapping[str, str] | None = None,
    keychain: Callable[[str, str], str | None] | None = None,
    build_provider: Callable[[], Provider] | None = None,
    clock: Callable[[], str] = utc_now,
) -> int:
    """Ask one subject's questions k times each, and write the round down.

    This is the only command that spends money on purpose and at scale, so
    everything that could stop it stops it before the first call: an unreadable
    subject file, a model with no published price, a missing key, a ceiling of
    nothing. What is left after those is a round, and the worst case it can
    cost is printed before it starts rather than reported after it ends.

    **The ceiling is not optional and is not defaulted.** A number chosen here
    would be a number nobody decided, spent from a prepaid account against a
    price this file did not set. It is constructed from the published price of
    the model that will actually answer, so the guard and the invoice are
    reading the same table.

    **A model with no price on file is refused rather than collected.** Running
    unpriced would mean a guard that cannot count, which is the same as no
    guard at all, and the round would only find out what it cost when the
    account stopped answering.

    **Nothing is asked.** Every question in a step is a place to get stuck, and
    this repo has already deleted a wizard for that reason. What the person
    running this has to decide, they decide on the command line, once.

    `build_provider` and `clock` are injected so the whole command can be
    driven end to end against the deterministic stub, with no key spent and no
    socket opened. The key is still resolved on that path, because never
    printing it is a promise this command has to keep whether or not it calls
    anything.
    """
    spec = spec_for(provider)
    subject = load_subject(subject_path)
    model = model or spec.check_model
    price = price_for(provider, model)
    if price is None:
        raise ValueError(
            f"no published price on file for {provider}/{model}, so this round would run "
            "unpriced: the ceiling could not be enforced and the spend could not be checked "
            "afterwards. price the model in prices.py, or name one that is already there"
        )

    console.say(f"lulu collect: {subject.name} on {provider}/{model}")
    console.say()
    console.say(f"  subject   {subject.path}")
    console.say(f"  tracking  {_names(subject)}")
    console.say(
        f"  asking    {counted(len(subject.prompts), 'prompt')}, "
        f"{counted(k, 'time')} each"
    )
    if can_search:
        console.say(
            f"  arm       with the search tool, capped at "
            f"{counted(max_searches, 'search', 'searches')} a call"
        )
    else:
        console.say(
            f"  arm       with no search tool attached, recorded as surface {UNSEARCHED_SURFACE}"
        )
    if subject.ambiguous_name:
        console.say(
            f"  note      the file declares {subject.name!r} an ambiguous name: a bare mention"
        )
        console.say("            of it counts here, including one that meant somebody else.")
        console.say("            the forms above are the whole of what counts, because")
        console.say("            detection matches declared literals and infers nothing.")

    found = resolve(spec, cwd=cwd, home=home, env=env, keychain=keychain)
    if not found.ok:
        console.say()
        report_lookup(console, spec, found)
        return 1
    console.say(f"  key       {found.source}, fingerprint {fingerprint(found.key)}")

    # Built before the ceiling is printed rather than after. An engine that
    # cannot collect the arm it was asked for is refused here, so nobody reads
    # a price for a round this build was never going to be able to make.
    engine = build_provider() if build_provider else provider_for(
        provider, found.key, model=model, max_searches=max_searches, can_search=can_search
    )

    budget = Budget(
        price=price,
        limit_usd=budget_usd,
        max_searches=max_searches,
        can_search=can_search,
        max_output_tokens=engine.max_output_tokens,
    )
    planned = len(subject.prompts) * k
    ceiling = budget.next_call_ceiling_usd()
    console.say()
    console.say("BEFORE ANYTHING IS SPENT")
    console.say(
        f"  {counted(planned, 'call')} planned: "
        f"{counted(len(subject.prompts), 'prompt')}, {counted(k, 'time')} each"
    )
    console.say(f"  ${ceiling:.4f} is the most one of them can cost: an opening guess of")
    console.say(
        f"    {UNMEASURED_INPUT_TOKENS} in tokens against a cap of {engine.max_output_tokens} "
        f"out, {_fee_sentence(price, max_searches, can_search)}"
    )
    console.say(f"  ${planned * ceiling:.4f} is the most the whole round can cost at that price")
    affordable = int(budget_usd // ceiling)
    if affordable >= planned:
        console.say(f"  ${budget_usd:.2f} is your ceiling, and it covers all {planned}")
    else:
        console.say(f"  ${budget_usd:.2f} is your ceiling, and it covers {affordable} of them.")
        console.say("    the round stops there unless the calls come back cheaper than the")
        console.say("    guess, which this round replaces with its own measured rate as soon")
        console.say("    as one call has been metered")
    console.say(f"  priced from {price.provenance()}")

    console.say()
    console.say("ASKING")
    console.say("  nothing is printed until the round closes. every ask is written to the")
    console.say("  ledger as it comes back, so a round that dies halfway keeps what it had.")
    ledger = Ledger(ledger_dir)
    result = run_round(
        ledger=ledger,
        provider=engine,
        prompts=subject.prompts,
        brands=subject.brands,
        k=k,
        subject=subject.id,
        clock=clock,
        budget=budget,
    )

    console.say()
    console.say("COLLECTED")
    console.say(f"  snapshot  {result.snapshot_id}")
    console.say(f"  written   {ledger.path_of(result.snapshot_id)}")
    console.say(f"  {result.as_text()}")
    if result.errors:
        console.say(
            "  every ask that failed is in the file with the provider's own reason, and none "
            "was retried, because retrying until success reports the survivors"
        )
    for line in budget.as_text().splitlines():
        console.say(f"  {line}")
    if result.stopped_for_budget:
        console.say()
        console.say(
            f"  the ceiling stopped this round: {result.unasked} of "
            f"{counted(result.planned, 'ask')} were never made."
        )
        console.say(
            "  that is a shorter round rather than a failed one. what it costs is that every"
        )
        console.say(
            "  interval computed from it is wider than the design that bought it asked for,"
        )
        console.say("  and the count above is the only place that fact is written down.")

    console.say()
    console.say(f"  lulu verify --ledger {ledger_dir} --snapshot {result.snapshot_id}")
    console.say(f"  lulu usage --ledger {ledger_dir} --snapshot {result.snapshot_id}")
    return ROUND_CUT_SHORT if result.stopped_for_budget else 0


#: Returned when a draft produced a candidate pool and stopped before the round
#: that would have measured it. A distinct code because the file on disk is
#: real and unmeasured, which is neither a success nor a failure and would be
#: read as one of the two under any code that already exists.
DRAFT_UNMEASURED = 5


def _no_rivals_refusal(subject_name: str) -> str:
    return (
        f"no rival name was declared, so the only name this round could screen on is "
        f"{subject_name!r}. Screening a question set on the subject's own mentions keeps the "
        "questions it scored well on and drops the rest, which raises the published number by "
        "deleting the evidence against it. That is the inflation this repo exists to name, so "
        "the round is refused rather than run with the one name available. Declare who the "
        "customer competes with, with --rivals, and the gate measures them instead"
    )


def draft(
    console: Console,
    *,
    site: str,
    out: Path,
    floor: float,
    budget_usd: float,
    cwd: Path,
    home: Path,
    ledger_dir: Path,
    rivals: Sequence[str] = (),
    provider: str = "anthropic",
    model: str | None = None,
    max_searches: int = DEFAULT_MAX_SEARCHES,
    max_pages: int = DEFAULT_MAX_PAGES,
    page_chars: int = DEFAULT_PAGE_CHARS,
    wanted: int = DEFAULT_WANTED,
    harvest_only: bool = False,
    dry_run: bool = False,
    fetch: Callable[[str], tuple[int, str]] | None = None,
    env: Mapping[str, str] | None = None,
    keychain: Callable[[str, str], str | None] | None = None,
    build_provider: Callable[[], Provider] | None = None,
    clock: Callable[[], str] = utc_now,
) -> int:
    """Turn a domain into a measured question set, asking the customer nothing else.

    The acceptance gate for this whole path is that the person running it types
    one url. Everything a question needs comes from the site itself, and every
    question that does not survive is written down with the gate that stopped
    it, because a set that arrived with forty candidates and kept nine is a
    different object from one that only ever had nine.

    **It costs money in two places and both are priced before either happens.**
    One call proposes candidates, and one round asks the survivors for real.
    The second is the expensive one and it is also the pilot: the draws that
    decide which questions survive are the same draws the variance split is
    read off, so the number nobody in this category publishes comes out of a
    round that was already being paid for.

    **`k` is derived from the floor, never chosen here.** A question that names
    a rival in every one of its draws still has to clear the floor on the lower
    bound of that clean sweep before the sweep means anything, and how many
    draws that takes is arithmetic on the floor the caller set.

    Three stopping points, each cheaper than the next: `--harvest-only` reads
    the site and spends nothing, `--dry-run` adds the proposal call and the free
    gates, and the full command adds the measured round.
    """
    if not 0.0 <= floor < 1.0:
        raise ValueError(f"floor must be in [0, 1), got {floor}")

    corpus = harvest(site, fetch=fetch or http_get, max_pages=max_pages)

    console.say(f"lulu draft: {site}")
    console.say()
    console.say(f"  subject   {corpus.subject_name}, from {corpus.subject_name_source}")
    console.say(f"  read      {counted(len(corpus.pages), 'page')}")
    for page in corpus.pages:
        console.say(f"              {page.url}")
    if corpus.unreachable:
        console.say(f"  missing   {counted(len(corpus.unreachable), 'page')} could not be read")
        for miss in corpus.unreachable:
            console.say(f"              {miss.url} ({miss.status}, {miss.reason})")
    if corpus.disallowed:
        console.say(
            f"  refused   {counted(len(corpus.disallowed), 'path')} robots.txt keeps this "
            "collector out of"
        )
    if corpus.not_documents:
        console.say(
            f"  skipped   {counted(len(corpus.not_documents), 'link')} with nothing to quote"
        )
        for skipped in corpus.not_documents:
            console.say(f"              {skipped.url} ({skipped.reason})")
    if corpus.duplicates:
        console.say(
            f"  same page {counted(len(corpus.duplicates), 'url')} the site serves one page under"
        )
        for same in corpus.duplicates:
            console.say(f"              {same.url} is {same.same_as} ({same.reason})")
    console.say(f"  digest    {corpus.digest[:16]}")

    if corpus.is_empty:
        console.say()
        console.say(
            "  nothing was read, so there is nothing to ground a question in. the lines above"
        )
        console.say("  say which pages were asked for and what came back.")
        return 1

    if harvest_only:
        console.say()
        console.say("  stopped at the corpus. no model was called and nothing was spent.")
        return 0

    # The count is derived here so it can be printed with its arithmetic, and
    # so an unreachable floor is refused before a key is even looked for.
    k = minimum_draws(floor)

    spec = spec_for(provider)
    model = model or spec.check_model
    price = price_for(provider, model)
    if price is None:
        raise ValueError(
            f"no published price on file for {provider}/{model}, so this draft would run "
            "unpriced: the ceiling could not be enforced and the spend could not be checked "
            "afterwards. price the model in prices.py, or name one that is already there"
        )

    found = resolve(spec, cwd=cwd, home=home, env=env, keychain=keychain)
    if not found.ok:
        console.say()
        report_lookup(console, spec, found)
        return 1
    console.say(f"  key       {found.source}, fingerprint {fingerprint(found.key)}")

    engine = build_provider() if build_provider else provider_for(
        provider, found.key, model=model, max_searches=max_searches
    )

    budget = Budget(
        price=price,
        limit_usd=budget_usd,
        max_searches=max_searches,
        max_output_tokens=engine.max_output_tokens,
    )
    # Two shapes, and one number for both was the defect. The proposing call
    # sends the site and asks for a list; a draw sends one question. Pricing
    # the round at the average of those describes neither call.
    call = call_for(corpus, provider=engine, wanted=wanted, page_chars=page_chars)
    proposing = budget.next_call_ceiling_usd(
        input_tokens=call.input_tokens,
        output_tokens=call.output_tokens,
        searches=call.searches,
    )
    per_draw = budget.next_call_ceiling_usd()

    console.say()
    console.say("BEFORE ANYTHING IS SPENT")
    console.say(f"  {wanted} candidates asked for in one call")
    console.say(
        f"  {counted(k, 'draw')} each afterwards, derived from a floor of {floor:.2f}: "
        f"a clean sweep of {k}/{k} is the shortest one whose lower bound clears it"
    )
    console.say(
        f"  ${proposing:.4f} is the most the proposing call can cost: the site as it will be "
        f"sent is {call.input_tokens} tokens, against a cap of {call.output_tokens} out"
        + (", and it is sent with no search tool" if call.searches == 0 else "")
    )
    console.say(
        f"  ${per_draw:.4f} is the most one draw can cost, against a cap of "
        f"{budget.max_output_tokens} out"
    )
    console.say(
        f"  ${proposing + wanted * k * per_draw:.4f} is the most this can cost if every candidate "
        "survives the free gates"
    )
    console.say(f"  ${budget_usd:.2f} is your ceiling, priced from {price.provenance()}")
    if not rivals:
        console.say()
        console.say("  note      " + _no_rivals_refusal(corpus.subject_name))

    console.say()
    console.say("PROPOSING")
    proposed = propose(
        corpus, provider=engine, wanted=wanted, page_chars=page_chars, budget=budget
    )
    console.say(f"  {proposed.as_text()}")
    if not proposed.asked or proposed.answer is None or not proposed.answer.ok:
        console.say("  nothing was proposed, so there is nothing to screen.")
        return 1

    tracked = (Brand(name=corpus.subject_name),) + tuple(Brand(name=name) for name in rivals)
    candidates = tuple(
        Candidate(id=f"c{i}", text=p.text, source=p.source, evidence=p.evidence)
        for i, p in enumerate(proposed.proposals, start=1)
    )
    result = screen(
        candidates,
        pages=pages_for_screening(corpus),
        detect_names=lambda text: detect(text, tracked),
    )

    console.say()
    console.say("FREE GATES")
    for gate, count in result.counts.items():
        console.say(f"  {gate:<10} {count} dropped")
    console.say(f"  {len(result.kept)} of {len(candidates)} survived")

    kept = stable_ids(result.kept, _existing_ids(out))
    draft_path = out.with_suffix(".draft.json")

    screened: tuple = ()
    split = None
    snapshot_id = ""
    cut_short = False

    if dry_run:
        console.say()
        console.say(
            f"  dry run, so the {counted(len(kept) * k, 'draw')} that would decide these were "
            "not made and nothing above was measured."
        )
    elif not rivals:
        console.say()
        console.say("  " + _no_rivals_refusal(corpus.subject_name))
    elif not kept:
        console.say()
        console.say("  no candidate survived the free gates, so there is nothing to measure.")
    else:
        console.say()
        console.say("ASKING")
        console.say(f"  {counted(len(kept) * k, 'draw')}, and every one is written to the ledger")
        ledger = Ledger(ledger_dir)
        round_result = run_round(
            ledger=ledger,
            provider=engine,
            prompts=[Prompt(id=c.id, text=c.text) for c in kept],
            brands=tracked,
            k=k,
            subject=_slug(corpus.subject_name),
            clock=clock,
            budget=budget,
        )
        snapshot_id = round_result.snapshot_id
        cut_short = round_result.stopped_for_budget
        console.say(f"  {round_result.as_text()}")

        observations = _rival_draws(replay(ledger, snapshot_id), kept, rivals)
        screened = screen_by_discrimination(observations, floor=floor)
        split = pool_variance(observations)

        console.say()
        console.say("MEASURED")
        for one in screened:
            console.say(f"  {one.as_text()}")
        console.say()
        console.say(
            f"  {split.noise_floor * 100:.1f} points is the noise floor of this pool, which is "
            "how far a score can move without anything about the brand changing"
        )
        console.say(
            "  it costs nothing extra: the draws that decided the questions are the draws it "
            "was read off"
        )

        undeclared = _undeclared_names(ledger, snapshot_id, rivals)
        if undeclared:
            console.say()
            console.say("NAMED AND NOT DECLARED")
            for one in undeclared[:UNDECLARED_SHOWN]:
                console.say(f"  {one.as_text()}")
            if len(undeclared) > UNDECLARED_SHOWN:
                console.say(
                    f"  {UNDECLARED_SHOWN} of {len(undeclared)} such names, the ones in the most "
                    f"questions; `lulu rivals --snapshot {snapshot_id}` prints the rest"
                )
            console.say()
            console.say(
                "  a question is barren about the list it was given, so a name the answers "
                "reached for and the list never mentioned is counted as nobody"
            )

    carried = tuple(one.candidate for one in screened if one.verdict == CARRIES) if screened else kept
    _write_subject_file(out, corpus, rivals, carried)
    _write_draft_ledger(draft_path, corpus, proposed, result, screened, split, snapshot_id, rivals)

    console.say()
    console.say("WRITTEN")
    console.say(f"  {out}")
    console.say(f"  {draft_path}, with every candidate that died and what stopped it")
    for line in budget.as_text().splitlines():
        console.say(f"  {line}")
    if not screened:
        console.say()
        console.say(
            "  the questions in that file passed the free gates and were never measured, so "
            "nothing yet says any of them discriminates."
        )
        return DRAFT_UNMEASURED
    return ROUND_CUT_SHORT if cut_short else 0


def _slug(name: str) -> str:
    """A subject id from a name, for the snapshot the screening round writes."""
    kept = "".join(ch if ch.isalnum() else "-" for ch in name.casefold())
    return "-".join(part for part in kept.split("-") if part) or "subject"


def _existing_ids(out: Path) -> dict[str, str]:
    """Question text to the id it already holds, from a file being rewritten.

    An id is the key every comparison groups by, so a second draft over the
    same subject must not renumber a question whose text did not change. A
    file that does not exist yet contributes nothing rather than raising.
    """
    if not out.exists():
        return {}
    try:
        data = json.loads(out.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {}
    from .mirror.screen import normalise as screen_normalise

    previous: dict[str, str] = {}
    for entry in data.get("prompts", []):
        if isinstance(entry, dict) and entry.get("id") and entry.get("text"):
            previous[screen_normalise(str(entry["text"]))] = str(entry["id"])
    return previous


#: Undeclared names the draft prints before it stops counting them out. The
#: whole list is what `lulu rivals` is for; this is the part that fits under a
#: verdict without pushing it off the screen.
UNDECLARED_SHOWN = 12


def _undeclared_names(store: Ledger, snapshot_id: str, rivals: Sequence[str]):
    """Names the answers reached for that the declared list never mentioned.

    Read off the draws that were already bought, so it costs nothing and is
    available in the same round that produced the verdicts. It exists because
    of what those verdicts do when the list is wrong: a question where none of
    the declared names appears comes back barren, which reads as a question
    nobody competes on, when it can equally be a question everybody competes on
    under names nobody wrote down.

    That is not a hypothetical. The list that produced the first paid screening
    round was read off the arm that answers from its own weights, the round was
    collected on the arm that searches, and the second arm reaches for a
    different set of companies than the first. Eleven of twenty questions came
    back barren, and the answers behind them were full of names.

    Matched by the same fold `detect` matches on, and on the whole name, so a
    list carrying `Bloomberg Terminal` against answers that write `Bloomberg`
    is reported here rather than counted as agreement.
    """
    declared = {name.casefold() for name in rivals}
    # Read off the records rather than off the replayed runs, because a run
    # carries the names somebody declared and went looking for, and the list
    # worth having here is the one nobody declared. The words are only on the
    # record.
    replies = tuple(
        Reply(prompt_id=rec.prompt_id, draw=rec.repeat, text=rec.answer_text)
        for rec in store.read(snapshot_id)
        if rec.prompt_id and rec.status == "ok" and rec.answer_text
    )
    return tuple(one for one in names_in(replies) if one.name.casefold() not in declared)


def _rival_draws(
    played: Replay, kept: Sequence[Candidate], rivals: Sequence[str]
) -> tuple[tuple[Candidate, tuple[float, ...]], ...]:
    """One 1/0 per draw, marking whether that answer named any rival.

    Rivals rather than the subject, which is the whole of the measurement gate.
    A question is kept for moving somebody else's odds of being named, never
    for the subject's own rate, because a set screened on the subject's rate is
    a set with its own counter-evidence removed.
    """
    wanted = {name.casefold() for name in rivals}
    per_prompt: dict[str, list[float]] = {c.id: [] for c in kept}
    for run in played.runs:
        if run.prompt_id in per_prompt:
            named = {b.casefold() for b in run.brands}
            per_prompt[run.prompt_id].append(1.0 if named & wanted else 0.0)
    return tuple(
        (candidate, tuple(per_prompt[candidate.id]))
        for candidate in kept
        if per_prompt[candidate.id]
    )


def _write_subject_file(
    out: Path, corpus, rivals: Sequence[str], prompts: Sequence[Candidate]
) -> None:
    """The subject file, carrying every question's page and quote.

    Written with `source` and `evidence` on each prompt, which is what lets a
    later reader check a question rather than take it. A build older than those
    keys refuses this file outright instead of reading it partially, and that
    refusal is the point.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "subject": {
            "id": _slug(corpus.subject_name),
            "name": corpus.subject_name,
            "domain": corpus.base_url,
        },
        "competitors": [
            {"id": f"rival{i}", "name": name} for i, name in enumerate(rivals, start=1)
        ],
        "prompts": [
            {"id": c.id, "text": c.text, "source": c.source, "evidence": c.evidence}
            for c in prompts
        ],
    }
    out.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_draft_ledger(
    path: Path,
    corpus,
    proposed,
    result,
    screened: Sequence,
    split,
    snapshot_id: str,
    rivals: Sequence[str] = (),
) -> None:
    """Every candidate that died, and what killed it.

    Kept beside the subject file rather than inside it, because the subject
    file is an input to a paid round and this is a record of one draft. A
    reader asking why a set has nine questions is asking about this file.
    """
    body = {
        "site": corpus.base_url,
        # The list every verdict below is relative to. A draft that recorded
        # the verdicts and not the list they were measured against would leave
        # `barren` reading as a fact about a market rather than about thirteen
        # names somebody typed.
        "rivals": list(rivals),
        "corpus_digest": corpus.digest,
        "pages_read": [page.url for page in corpus.pages],
        "unreachable": [
            {"url": m.url, "status": m.status, "reason": m.reason} for m in corpus.unreachable
        ],
        "not_documents": [
            {"url": n.url, "reason": n.reason} for n in corpus.not_documents
        ],
        "duplicates": [
            {"url": d.url, "same_as": d.same_as, "reason": d.reason} for d in corpus.duplicates
        ],
        "proposed": len(proposed.proposals),
        "unreadable_entries": [
            {"raw": m.raw, "reason": m.reason} for m in proposed.malformed
        ],
        "rejected": [
            {
                "id": r.candidate.id,
                "text": r.candidate.text,
                "source": r.candidate.source,
                "evidence": r.candidate.evidence,
                "gate": r.gate,
                "reason": r.reason,
            }
            for r in result.rejected
        ],
        "screening_snapshot": snapshot_id,
        "measured": [
            {
                "id": one.candidate.id,
                # The words, beside the verdict on them. Without these a draft
                # reads `p7 barren` and nothing anywhere says what p7 asked: a
                # ledger line carries a prompt's id and not its sentence, and
                # the subject file keeps only the questions that survived. The
                # first paid screening round found eleven of twenty questions
                # naming nobody at all and could not show a reader one of them.
                "text": one.candidate.text,
                "source": one.candidate.source,
                "evidence": one.candidate.evidence,
                "verdict": one.verdict,
                "rival_hits": one.rival_hits,
                "draws": one.draws,
                "floor": one.floor,
                "interval": [one.interval.low, one.interval.high],
            }
            for one in screened
        ],
        "noise_floor": None if split is None else split.noise_floor,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _names(subject: Subject) -> str:
    """Every tracked name and every form of it, said in full.

    Printed rather than counted. What counts as a mention is a declaration in a
    file and nothing else, and this is the last screen before money is spent
    against it, so it is where a missing alias or a name nobody meant to track
    is still cheap to notice.
    """
    listed = []
    for brand in subject.brands:
        aliases = f" (also {', '.join(brand.aliases)})" if brand.aliases else ""
        listed.append(f"{brand.name}{aliases}")
    if len(listed) == 1:
        return f"{listed[0]}, and nobody else"
    return "; ".join(listed)


def _fee_sentence(price: Price, max_searches: int, can_search: bool) -> str:
    """How the fee half of that ceiling was arrived at, in words.

    The fee is the term a reader cannot check from the token counts, and on a
    search-grounded model it is the term that moves the figure most, so the
    number of fees assumed is said out loud rather than folded into a total.
    """
    if not price.has_fee:
        return "and no fee, because this model publishes none"
    if price.fee_unit != FEE_PER_SEARCH:
        return f"plus one fee at {price.fee_text}"
    if not can_search:
        return "and no search fee: this arm has no tool to run one with"
    return f"plus up to {counted(max_searches, 'search', 'searches')} at {price.fee_text}"


# -- usage ------------------------------------------------------------------


def usage(
    console: Console,
    *,
    ledger_dir: Path,
    snapshot: str | None = None,
) -> int:
    """What the rounds on disk cost, from what the provider said about them.

    Takes no model. Each record names the model that answered it, and that is
    the only model that was billed, so the rate is read per record rather than
    chosen once by whoever runs the command. A flag here would let a round
    collected on one model be priced at another's rate without anything on
    screen disagreeing.

    The chain is checked before a single figure is printed. An invoice computed
    from a file that does not verify is not a cheaper invoice, it is an unknown
    one, and printing it under a heading that says COST would be the exact
    move this library exists to argue against.
    """
    store = Ledger(ledger_dir)
    wanted = [snapshot] if snapshot else store.snapshots()
    if not wanted:
        console.say(f"No rounds recorded in {ledger_dir}.")
        console.say("Nothing has been asked yet, so nothing has been spent.")
        return 0

    console.say(f"lulu usage: {ledger_dir}")

    failed_chain = False
    for snapshot_id in wanted:
        console.say()
        console.say(snapshot_id)
        problems = store.verify(snapshot_id)
        if problems:
            failed_chain = True
            console.say(
                f"  CHAIN BROKEN, {counted(len(problems), 'problem')}. "
                "No cost is computed from it."
            )
            for line in problems[:5]:
                console.say(f"    {line}")
            if len(problems) > 5:
                console.say(f"    ... and {len(problems) - 5} more")
            continue
        console.say("  chain intact")
        console.say()
        for line in spend_of(store.read(snapshot_id)).as_text().splitlines():
            console.say(f"  {line}" if line else "")

    return 1 if failed_chain else 0


# -- verify -----------------------------------------------------------------

#: What a round with no closing record says about its own length, which is
#: nothing. One wording, because two surfaces now print it and a file described
#: as unsealed on one screen and something else on another is two claims.
UNSEALED = "length never sealed"


def seal_text(seal: Record) -> str:
    """What a round's own closing record says the round did.

    Beside `UNSEALED` and for the same reason. `lulu verify` says this on the
    round's line and a printed report says it in its evidence, and the counts
    are the ones the round wrote down rather than a count of the file: a seal
    read off the file would agree with a file somebody had just shortened.
    """
    return (
        f"{counted(seal.round_asked, 'call')} sealed, "
        f"{seal.round_ok} answered, {seal.round_errors} failed"
    )


def verify(console: Console, *, ledger_dir: Path, snapshot: str | None = None) -> int:
    """Re-derive every chain on disk and say what that does and does not prove.

    The library tells a customer that every number it prints is reproducible
    from the ledger. Until this command existed that was true and unusable: the
    check lived in the test suite, where only we could run it. A guarantee the
    person relying on it cannot exercise is a claim, not a guarantee.

    What is printed at the end is the limit of the check, not a summary of how
    well it went. A verifier that reports "intact" without saying what intact
    covers is the sort of confident output this repo exists to argue with.

    The limit moved and the screen has to move with it. A round that sealed its
    own length is now checked against it, so the closing paragraph about a cut
    tail is printed for the rounds it is still true of and for no others: a
    caveat repeated after it stops applying teaches a reader to skip the
    paragraph where the real one will be.
    """
    store = Ledger(ledger_dir)
    wanted = [snapshot] if snapshot else store.snapshots()
    console.say(f"lulu verify: {ledger_dir}")
    console.say()
    if not wanted:
        console.say("No rounds recorded here, so there is nothing to check.")
        return 0

    broken = 0
    unsealed = 0
    for snapshot_id in wanted:
        problems = store.verify(snapshot_id)
        if problems:
            broken += 1
            console.say(f"  BROKEN   {snapshot_id}   {counted(len(problems), 'problem')}")
            for line in problems:
                console.say(f"           {line}")
            continue
        seal = store.seal_of(snapshot_id)
        if seal is None:
            # Intact and shorter than the check reaches. Said on the round's
            # own line rather than in a footnote, because this is the one state
            # where "intact" means less than a reader would take it to mean.
            unsealed += 1
            console.say(
                f"  intact   {snapshot_id}   "
                f"{counted(store.count(snapshot_id), 'record')}, {UNSEALED}"
            )
            continue
        console.say(f"  intact   {snapshot_id}   {seal_text(seal)}")

    console.say()
    console.say(
        f"{len(wanted) - broken} of {counted(len(wanted), 'round')} re-derive from their "
        "own contents."
    )
    console.say()
    console.say("What that covers: every record present was checked against its own hash and")
    console.say("against the one before it, so altering an answer costs a rewrite of every")
    console.say("record after it. A sealed round is also checked against its own length: it")
    console.say("ends with a record saying how many calls it made, so records removed from the")
    console.say("end are reported rather than silently lost.")
    if unsealed:
        rounds = counted(unsealed, "round")
        console.say()
        console.say(f"What it does not cover: the {rounds} above whose length was never sealed.")
        console.say("Collected before a round closed itself, so nothing in there says how long it")
        console.say("was meant to be and a cut tail leaves no trace. Keep your own count of what")
        console.say("you asked for those.")
    return 1 if broken else 0


# -- plan -------------------------------------------------------------------

#: ICCs the no-pilot bracket is evaluated at. Not a guess at the answer: the
#: point of showing several is that the answer moves by more than an order of
#: magnitude across them, which is the argument for measuring it.
BRACKET_ICCS = (0.0, 0.02, 0.05, 0.10, 0.25)


def plan(
    console: Console,
    *,
    prompts: int,
    half_width: float,
    brands: int = 1,
    confidence: float = 0.95,
    rate: float = 0.5,
    days: int = 30,
    scans_per_day: int = 1,
    family: bool = True,
    pilot: str | None = None,
    brand: str | None = None,
    ledger_dir: Path | None = None,
    provider: str = "perplexity",
    model: str | None = None,
    searches_per_call: int = SEARCHES_PER_CALL,
) -> int:
    """Size a measurement, and price both what it needs and what it replaces."""
    z = critical_value(confidence, brands, family=family)
    model = model or check_model_for(provider)
    price = price_for(provider, model)

    console.say("lulu plan")
    console.say()
    console.say("DESIGN")
    console.say(f"  {counted(prompts, 'prompt')}, {counted(brands, 'brand')} tracked")
    console.say(f"  target +/-{half_width * 100:.1f} points at {int(confidence * 100)}% confidence")
    console.say(
        f"  z={z:.4f} "
        + (
            f"(held across all {brands} brands at once)"
            if family and brands > 1
            else "(one brand at a time)"
        )
    )
    console.say("  tracking more brands does not cost more calls: every brand is read out of")
    console.say("  the same answers. What more brands cost is a wider critical value.")

    measured = _pilot_split(console, pilot, brand, ledger_dir)
    console.say()

    #: Every design this prompt count can actually buy, cheapest first. Kept so
    #: the price section quotes the range rather than one end of it.
    affordable: list[Design] = []

    if measured is None:
        variance = total_variance(rate)
        console.say("VARIANCE, assumed")
        console.say(
            f"  for a yes-or-no outcome the total per-draw variance is p(1-p), which at "
            f"p={rate:g} is {variance:.4f}."
        )
        console.say("  that much is arithmetic. how it splits between the model answering")
        console.say("  differently and the questions you chose is not, and the split is what")
        console.say("  decides whether repeats or prompts buy your precision.")
        ceiling = reachable_icc(prompts, half_width, z, variance)
        console.say()
        if math.isfinite(ceiling):
            console.say(f"  above icc {ceiling:.4f} no number of repeats reaches this target with")
            console.say(
                f"  {counted(prompts, 'prompt')}. "
                f"{counted(prompts_for_worst_case(half_width, z, variance), 'prompt')} "
                "would reach it at any icc."
            )
        else:
            # p(1-p) is zero only at p=0 and p=1, where a draw has no variance
            # and every design meets every target. Printing the ceiling as
            # "inf" would read as a very large icc a design could still fall
            # under, and the worst-case prompt count as "0 prompts", which
            # reads as a measurement that costs nothing.
            console.say(f"  at p={rate:g} a draw carries no variance at all, so every split reaches")
            console.say("  this target at the minimum design. that is arithmetic about a rate you")
            console.say("  supplied, not a finding, and a rate of exactly 0 or 1 is the one input")
            console.say("  here that no number of calls can confirm.")
        console.say()
        console.say("WHAT ONE INTERVAL COSTS, across the range the split could take")
        for icc in BRACKET_ICCS:
            design = draws_needed(prompts, half_width, z, variance, icc)
            console.say(f"  {design.as_text()}")
            if design.reachable:
                affordable.append(design)
        console.say()
        console.say("  that spread is the output. it is also the argument for measuring the")
        console.say("  split rather than assuming it: one round of this size settles it, and")
        console.say("  every number above it is then replaced by one.")
    else:
        variance, icc = measured
        ceiling = reachable_icc(prompts, half_width, z, variance)
        console.say("VARIANCE, measured from the pilot")
        console.say(f"  total per-draw variance {variance:.4f}, icc {icc:.4f}")
        console.say()
        console.say("WHAT ONE INTERVAL COSTS")
        design = draws_needed(prompts, half_width, z, variance, icc)
        console.say(f"  {design.as_text()}")
        if design.reachable:
            affordable.append(design)
        else:
            console.say(
                f"  {counted(prompts_for_worst_case(half_width, z, variance), 'prompt')} "
                "would reach it even if repeats bought nothing."
            )

    designed = affordable[0].calls if affordable else None

    console.say()
    console.say("DETECTING A MOVE OF THAT SIZE")
    console.say("  two rounds compared carry both rounds' error, so each one needs to be")
    console.say(f"  +/-{half_width / math.sqrt(2) * 100:.1f} points to call a {half_width * 100:.1f} point move real.")
    tighter_icc = measured[1] if measured else 0.0
    tighter = draws_needed(prompts, half_width / math.sqrt(2), z, variance, tighter_icc)
    if measured is None:
        console.say("  quoted at icc 0, the most optimistic end of the bracket above. any")
        console.say("  higher split costs more, and past the ceiling it cannot be bought.")
    if tighter.reachable:
        console.say(
            f"  {counted(tighter.calls, 'call')} per round, {tighter.calls * 2} for the pair."
        )
    else:
        console.say(f"  unreachable at {counted(prompts, 'prompt')}: {tighter.reason}")

    console.say()
    console.say("ASKING EVERY DAY INSTEAD")
    daily = prompts * days * scans_per_day
    for line in Comparison(
        designed_calls=designed,
        daily_calls=daily,
        days=days,
        scans_per_day=scans_per_day,
        n_prompts=prompts,
    ).as_text().splitlines():
        console.say(f"  {line}" if line else "")

    console.say()
    console.say("PRICE")
    tokens = _pilot_tokens(pilot, ledger_dir)
    console.say(f"  {provider}/{model}, {price.fee_text}." if price else f"  {provider}/{model}, no published price on file.")
    if tokens is None:
        console.say("  no call has been metered, so only the fee is counted. these are")
        console.say("  floors, not totals.")
    else:
        console.say(f"  priced from a measured {tokens[0]} in / {tokens[1]} out tokens per call.")
    per_call_fees = 1
    if price is not None and price.fee_unit == FEE_PER_SEARCH:
        per_call_fees = searches_per_call
        console.say(
            f"  this fee is charged per search, and a call is capped at {searches_per_call}, so the"
        )
        console.say("  figures below are ceilings. a call that searched once pays one fee.")

    # Both ends of the reachable range, each carrying the icc it was quoted at.
    # Printing only the cheapest end is the most optimistic number on the page,
    # and printing it unlabelled beside a section that does label its own
    # assumption invites it to be read as the price rather than as one end of a
    # spread the whole command exists to show.
    rows: list[tuple[str, int | None]] = []
    if not affordable:
        rows.append(("one interval", None))
    else:
        ends = affordable if len(affordable) == 1 else [affordable[0], affordable[-1]]
        rows.extend((f"one interval, icc {d.icc:.2f}", d.calls) for d in ends)
    rows.append(("a daily schedule", daily))

    for label, calls in rows:
        if calls is None:
            console.say(f"  {label:<24} not reachable at this prompt count")
            continue
        cost = price_of(price, calls, tokens, fee_units=calls * per_call_fees)
        console.say(
            f"  {label:<24} {counted(calls, 'call')}   "
            + (cost.as_text() if cost else "no published price on file")
        )

    if math.isfinite(ceiling):
        console.say()
        console.say(f"  above icc {ceiling:.4f} this design has no price at any budget: with")
        console.say(
            f"  {counted(prompts, 'prompt')} the prompt set alone carries more error than the"
        )
        console.say("  target, so no number of repeats closes it and no amount of money buys it.")
    return 0


# -- size -------------------------------------------------------------------


def _engine_spec(token: str) -> tuple[str, str]:
    """`perplexity` or `perplexity:sonar` into a provider and a model.

    An unknown provider is refused here rather than priced as unlisted, because
    the two failures read the same on screen and mean opposite things: one is a
    typo the buyer can fix, the other is a model this build can call but has no
    published price for.
    """
    provider, _, model = token.partition(":")
    provider = provider.strip()
    spec_for(provider)
    return provider, (model.strip() or check_model_for(provider))


def size(
    console: Console,
    *,
    prompts: int,
    runs: int,
    engines: Sequence[str],
    brands: int = 1,
    confidence: float = 0.95,
    rate: float = 0.5,
    family: bool = True,
    pilot: str | None = None,
    brand: str | None = None,
    ledger_dir: Path | None = None,
    searches_per_call: int = SEARCHES_PER_CALL,
) -> int:
    """Price a design the buyer stated, and say what precision it buys.

    `plan` answers "what do I need". This answers "what does what I set cost",
    which is the question that matters when the key is the buyer's: the spend
    lands on their card, so the bill has to be answerable before it is made
    rather than explained after.
    """
    # Checked before a single line is printed. Sizing an impossible design far
    # enough to show a bill and only then refusing it puts a price for
    # something unbuyable on the buyer's screen, which is the one failure this
    # command cannot afford.
    if prompts < 1:
        raise ValueError(f"a design needs at least one prompt, got {prompts}")
    if runs < 1:
        raise ValueError(f"a design needs at least one run per prompt, got {runs}")
    if not engines:
        raise ValueError("a design needs at least one engine")

    z = critical_value(confidence, brands, family=family)
    chosen = [_engine_spec(token) for token in engines]

    console.say("lulu size")
    console.say()
    console.say("DESIGN YOU SET")
    console.say(
        f"  {counted(prompts, 'prompt')}, asked {counted(runs, 'time', 'times')} each, "
        f"on {counted(len(chosen), 'engine')}"
    )
    console.say(f"  {counted(brands, 'brand')} tracked, read out of the same answers")
    console.say(f"  {int(confidence * 100)}% confidence, z={z:.4f}")

    measured = _pilot_split(console, pilot, brand, ledger_dir)
    tokens = _pilot_tokens(pilot, ledger_dir)
    console.say()

    engine_rows: list[Engine] = []
    for provider, model in chosen:
        price = price_for(provider, model)
        calls = prompts * runs
        per_call_fees = (
            searches_per_call if price is not None and price.fee_unit == FEE_PER_SEARCH else 1
        )
        engine_rows.append(
            Engine(
                provider=provider,
                model=model,
                calls=calls,
                cost=price_of(price, calls, tokens, fee_units=calls * per_call_fees),
            )
        )

    if measured is None:
        variance, icc = total_variance(rate), None
    else:
        variance, icc = measured

    design = SetDesign(
        n_prompts=prompts,
        k_runs=runs,
        engines=tuple(engine_rows),
        z=z,
        variance=variance,
    )

    console.say("WHAT IT COSTS")
    for engine in design.engines:
        console.say(f"  {engine.as_text()}")
    total = design.total_cost()
    console.say(
        f"  total   {counted(design.total_calls, 'call')}   "
        + (total.as_text() if total else "not totalled: an engine here has no published price")
    )
    if tokens is None:
        console.say("  no call has been metered, so only the fee is counted. these are floors.")
    else:
        console.say(f"  priced from a measured {tokens[0]} in / {tokens[1]} out tokens per call.")
    console.say("  the key is yours, so this lands on your account and not ours.")

    console.say()
    console.say("WHAT IT BUYS")
    if not design.decomposable:
        console.say(
            f"  nothing that carries an interval. at {counted(runs, 'run')} per prompt the"
        )
        console.say("  model's rerun noise and the prompt-to-prompt spread are the same")
        console.say("  quantity, so the split cannot be identified and no honest interval")
        console.say("  comes off this round. it returns a reading, and a reading is not a")
        console.say(f"  measurement. {counted(MIN_DRAWS, 'run')} per prompt is the floor.")
    elif measured is None:
        console.say(f"  per engine, and only per engine, at p={rate:g}:")
        for icc in BRACKET_ICCS:
            console.say(
                f"    icc {icc:.2f}   +/-{design.half_width(icc) * 100:.1f} points"
            )
        console.say("  the split is assumed, not measured, and it is the whole spread above.")
        console.say("  one round of this size settles it and replaces every line here.")
    else:
        console.say(
            f"  per engine, at the pilot's measured icc {icc:.4f}: "
            f"+/-{design.half_width(icc) * 100:.1f} points"
        )

    console.say()
    console.say("  a second engine does not narrow the first. engine answers are never")
    console.say("  pooled into one proportion, so what more engines buy is coverage across")
    console.say("  systems, and each one carries its own interval and its own bill.")
    return 0


def _pilot_split(
    console: Console, pilot: str | None, brand: str | None, ledger_dir: Path | None
) -> tuple[float, float] | None:
    """Total variance and ICC read from a round that actually happened.

    Returns None for a diagnostic round rather than refusing the whole command.
    A check call is a real billed call and settles what a call costs, which is
    half of what a plan needs; it is one draw with no brand list, which is none
    of the other half. So the price below is measured and the split stays
    labelled as assumed, and the screen says which is which. Quietly reporting
    a split "measured" from a single diagnostic answer would be the flattering
    version of the same arithmetic.
    """
    if pilot is None:
        return None
    if ledger_dir is None:
        raise ValueError("a pilot needs --ledger so the round it names can be read")
    store = Ledger(ledger_dir)
    # Before either branch. A design sized from a round that does not re-derive
    # is a design with nothing behind it, whichever half of the round is used.
    problems = store.verify(pilot)
    if problems:
        raise ValueError(
            f"{pilot} does not verify ({counted(len(problems), 'problem')}), so nothing is "
            "planned from it"
        )
    if is_diagnostic(pilot):
        console.say()
        console.say(f"  note: {pilot} is a diagnostic round, so it")
        console.say("  measures what a call costs and not how the variance splits: it was asked")
        console.say("  once, with no brand list. the bracket below is still assumed.")
        return None
    if brand is None:
        raise ValueError("a pilot needs --brand and --ledger so its answers can be scored")
    played = replay(store, pilot)
    clusters = [list(sample.detections(brand)) for sample in group_runs(played.runs)]
    split = decompose(clusters)
    if played.dropped:
        console.say()
        console.say(
            f"  note: {played.dropped} of {counted(played.total, 'pilot ask')} failed and are "
            "excluded; a failed ask is missing data, not an observed absence"
        )
    return variance_of(split), icc_of(split)


def _pilot_tokens(pilot: str | None, ledger_dir: Path | None) -> tuple[int, int] | None:
    if pilot is None or ledger_dir is None:
        return None
    return token_rate(list(Ledger(ledger_dir).read(pilot)))


# -- ablate -----------------------------------------------------------------

#: `ablate` reports through its exit code, because it is a gate and a gate is
#: usually read by something other than a person. `undecided` is deliberately
#: not 0: a design that could not tell has not passed, and a script that treats
#: "cannot tell" as "fine" is the failure this whole command exists to prevent.
ABLATE_EXIT = {STANDS_IN: 0, DIFFERS: 1, UNDECIDED: 4}

#: Returned by both gate and contrast when a chain does not re-derive. A broken
#: evidence file is not a verdict of any kind, so it never shares a code with
#: one.
CHAIN_BROKEN = 3


class BrokenChain(Exception):
    """One snapshot did not re-derive, so no number is computed from it."""


def _verified(store: Ledger, console: Console, role: str, snapshot_id: str):
    """Re-derive one round's chain, then replay it, announcing both.

    Shared by the two commands that read rounds off disk to compare them.
    Copying this would eventually give the same broken file two different
    treatments depending on which command opened it.

    The engine check is here for the same reason: it is the one door every
    round of every comparison below comes through, so a round nothing here can
    pair is refused once, in front of the person who asked for the comparison,
    rather than in whichever of the two commands happened to open it.
    """
    problems = store.verify(snapshot_id)
    if problems:
        console.say(f"  {snapshot_id}: CHAIN BROKEN, {counted(len(problems), 'problem')}.")
        console.say("  no verdict is computed from a round that does not re-derive.")
        raise BrokenChain(snapshot_id)
    played = replay(store, snapshot_id)
    console.say(f"  {role:<8} {snapshot_id}")
    console.say(f"           {played.as_text()}")
    _one_engine(played, snapshot_id)
    return played


def _one_engine(played, snapshot_id: str) -> None:
    """Refuse a round whose answers did not all come from one engine.

    A round is one engine and one surface. `collect.session.run_round` asks
    through a single provider and writes that provider's name on every record,
    and the engine is part of the snapshot's own file name, so a file holding
    two of them was not written by one round.

    It is refused rather than keyed around because there is no reading of it
    that is about a brand. Keyed by the prompt alone, one engine's answers
    replace the other's and the round is scored on whichever was written last.
    Keyed by the sample, the pairing below either drops every prompt the two
    engines do not share or matches a question asked of one provider against
    the same question asked of another. Both produce a number about the
    collector, and the first produces it silently.
    """
    if len(played.engines) > 1:
        raise ValueError(
            f"{snapshot_id} carries answers from more than one engine "
            f"({', '.join(played.engines)}), and a round is one engine and one surface. "
            "nothing here can pair two providers' answers to the same question, so this "
            "round is refused rather than scored on whichever engine was written last"
        )


def _detections(played, brand: str) -> dict[tuple[str, str], tuple[int, ...]]:
    """Per-run detections of one brand, keyed by the sample they came from.

    The key is the pair `(prompt_id, engine)`. That is the correct one because
    it is the identity the rest of the layer already uses: `group_runs` buckets
    by it, a `PromptSample` is defined as one prompt on one engine, and
    `Snapshot` refuses two samples that share it. This mapping is built out of
    exactly those samples, so keying it by the prompt alone was narrower than
    the thing it was built from, and a dict comprehension over a narrower key
    does not merge, it overwrites.

    With one engine in a round the two keyings agree, which is why this cost
    nothing until the build could call a second engine. With two, the samples
    for one prompt collapse onto one entry and one engine's answers leave the
    sample with nothing raised and nothing printed.

    The pair is what the comparisons downstream pair on, so it also stops a
    prompt asked of one engine being matched against the same prompt asked of
    another.
    """
    return {(s.prompt_id, s.engine): s.detections(brand) for s in group_runs(played.runs)}


def ablate(
    console: Console,
    *,
    ledger_dir: Path,
    live: str,
    replica: str,
    brand: str,
    margin: float,
    confidence: float = 0.95,
    brands: int = 1,
    family: bool = True,
) -> int:
    """Ask whether a replica round may stand in for a live one, and say why not.

    This is the gate the causal half of the product rests on, so it runs before
    anything is concluded rather than after. It reports three outcomes and the
    third one, "this design cannot tell", is a real answer with a call count
    attached rather than a failure to produce one.
    """
    store = Ledger(ledger_dir)
    console.say(f"lulu ablate: {ledger_dir}")
    console.say()

    try:
        sides = {
            role: _verified(store, console, role, snapshot_id)
            for role, snapshot_id in (("live", live), ("replica", replica))
        }
    except BrokenChain:
        return CHAIN_BROKEN

    console.say()
    lab = sides["replica"]
    if not any(is_replica_surface(s) for s in lab.surfaces):
        raise ValueError(
            f"{replica} was collected on {', '.join(lab.surfaces)}, not on the replica "
            "surface; this gate asks whether a laboratory round tracks a live one, and "
            "comparing two live rounds is a different question with a different answer"
        )
    if any(is_replica_surface(s) for s in sides["live"].surfaces):
        raise ValueError(
            f"{live} is itself a replica round, so there is no live surface here to be "
            "tracked and passing this gate would prove only that the instrument repeats"
        )

    # Only the model version is treated as a confound. The surfaces differ by
    # construction here, which is the comparison rather than a flaw in it, and
    # listing it would void every verdict this command can ever reach.
    confounds = model_confounds(
        Snapshot(label="live", samples=group_runs(sides["live"].runs)),
        Snapshot(label="replica", samples=group_runs(lab.runs)),
    )

    verdict = replica_gate(
        _detections(sides["live"], brand),
        _detections(lab, brand),
        margin=margin,
        confidence=confidence,
        brands=brands,
        family=family,
        confounded_by=tuple(f"{e} (model version)" for e in confounds),
    )
    console.say()
    for line in verdict.as_text().splitlines():
        console.say(f"  {line}" if line else "")
    console.say()
    if verdict.passed:
        console.say("  a lift measured on this replica may be read as a lift, at that margin.")
    else:
        console.say("  nothing causal is read off this replica until that changes.")
    return ABLATE_EXIT[verdict.verdict]


# -- lift -------------------------------------------------------------------

#: What this round could say about the source that was removed. `negligible` is
#: not an error and not a pass: it is a decision, and the decision is that the
#: source is not worth chasing. `no_contrast` is separated from it because two
#: arms that never differed look identical to arithmetic and mean something
#: entirely different.
LIFT_EXIT = {MOVES: 0, NEGLIGIBLE: 1, EFFECT_UNDECIDED: 4, NO_CONTRAST: 5}

#: Returned whatever the arithmetic said, when the result may not be called a
#: lift. A caller branching on 0 is asking about a customer's surface, and
#: without a gate that passed there is no answer to that question on this
#: screen, only a true statement about a laboratory.
NOT_TRANSPORTABLE = 6


def _arm_surface(played, snapshot_id: str, expected: str, role: str) -> None:
    """Refuse an arm whose recorded treatment is not the one being claimed.

    The ledger stores the digest of the material an arm was shown, so the list
    given on the command line is checked against the evidence rather than
    believed. Without this the treatment of an ablation would be an assertion
    typed next to the result it produces.
    """
    surfaces = played.surfaces
    if surfaces == (REPLICA_SURFACE,):
        raise ValueError(
            f"{snapshot_id} was written before rounds recorded which sources they were "
            "asked under, so nothing on disk says this is the "
            f"{role} arm. it can be read, it cannot be verified, and a contrast whose "
            "treatment rests on the command line is not evidence"
        )
    if surfaces != (expected,):
        found = ", ".join(surfaces) or "nothing"
        raise ValueError(
            f"{snapshot_id} was collected under {found}, and the {role} arm of this "
            f"ablation is {expected}. either the source list passed here is not the one "
            "that round was asked under, or the two arms have been swapped"
        )


def lift(
    console: Console,
    *,
    ledger_dir: Path,
    held: str,
    dropped: str,
    brand: str,
    source: str,
    sources: Sequence[str],
    margin: float,
    live: str | None = None,
    gate_margin: float | None = None,
    confidence: float = 0.95,
    brands: int = 1,
    family: bool = True,
) -> int:
    """What one source was worth, between the arm that carried it and the arm that did not.

    `sources` is the full list the held arm was asked under and `source` is the
    one taken out of it. Both are checked against what the rounds recorded, so
    the treatment behind the number is read off the evidence rather than taken
    on trust.

    `live` is optional and its absence is loud. Supplied, the replica gate runs
    first and a passing verdict is what lets the difference be called a lift.
    Absent, the same difference is printed as what it is without one: a measured
    fact about two laboratory arms.
    """
    store = Ledger(ledger_dir)
    console.say(f"lulu lift: {ledger_dir}")
    console.say()

    remaining = without(sources, source)
    roles = [("held", held), ("dropped", dropped)]
    if live is not None:
        roles.insert(0, ("live", live))
    try:
        rounds = {
            role: _verified(store, console, role, snapshot_id) for role, snapshot_id in roles
        }
    except BrokenChain:
        return CHAIN_BROKEN

    _arm_surface(rounds["held"], held, replica_surface(sources), "held")
    _arm_surface(rounds["dropped"], dropped, replica_surface(remaining), "dropped")

    console.say()
    console.say(
        f"  source list  {counted(len(sources), 'page')}, in the order the model saw them"
    )
    for i, url in enumerate(sources, start=1):
        console.say(f"    [{i}] {url}{'   <- removed in the dropped arm' if url == source else ''}")

    gate = None
    if live is not None:
        if any(is_replica_surface(s) for s in rounds["live"].surfaces):
            raise ValueError(
                f"{live} is itself a replica round, so there is no live surface here for the "
                "gate to check and passing it would prove only that the instrument repeats"
            )
        gate_confounds = model_confounds(
            Snapshot(label="live", samples=group_runs(rounds["live"].runs)),
            Snapshot(label="held", samples=group_runs(rounds["held"].runs)),
        )
        gate = replica_gate(
            _detections(rounds["live"], brand),
            _detections(rounds["held"], brand),
            margin=margin if gate_margin is None else gate_margin,
            confidence=confidence,
            brands=brands,
            family=family,
            confounded_by=tuple(f"{e} (model version)" for e in gate_confounds),
        )
        console.say()
        for line in gate.as_text().splitlines():
            console.say(f"  {line}" if line else "")

    # The two arms differ in their source list by construction, which is the
    # comparison itself, so the surface is not read as a confound here. The
    # model version is: two arms answered by different builds of a model are a
    # contrast between two things at once.
    arm_confounds = model_confounds(
        Snapshot(label="held", samples=group_runs(rounds["held"].runs)),
        Snapshot(label="dropped", samples=group_runs(rounds["dropped"].runs)),
    )
    effect = source_effect(
        _detections(rounds["held"], brand),
        _detections(rounds["dropped"], brand),
        source=source,
        margin=margin,
        gate=gate,
        confidence=confidence,
        brands=brands,
        family=family,
        confounded_by=tuple(f"{e} (model version)" for e in arm_confounds),
    )
    console.say()
    for line in effect.as_text().splitlines():
        console.say(f"  {line}" if line else "")
    console.say()
    if not effect.is_lift:
        console.say(
            "  this round measured a laboratory, and no number here is a claim about "
            "what a customer sees."
        )
        return NOT_TRANSPORTABLE
    return LIFT_EXIT[effect.verdict]


# -- report -----------------------------------------------------------------

#: Returned when the round re-derived, the arithmetic ran, and there is still no
#: rate to print because every question in the subject file names the brand. Its
#: own code, beside the undecided verdict of `ablate` rather than beside a
#: refusal: nothing is wrong with the round and nothing is wrong with the
#: command line, and a script reading this as a failure would go looking for a
#: fault that is not there.
NOTHING_TO_SCORE = 4

#: The typesetter this command shells out to. Named once, because it is printed
#: when it is missing and a message that says a different binary from the one
#: that was looked for sends somebody to install the wrong thing.
TEX_ENGINE = "tectonic"

#: No typesetter on this machine. Deliberately outside the range the refusals
#: use: 4, 5 and 6 all mean the measurement would not stand up, and a script
#: that read "nothing here can make a PDF" as one of those would go looking at
#: the round. The document was written either way, and the arithmetic behind it
#: is the same arithmetic that just printed to the terminal.
NO_TEX_ENGINE = 7

#: A typesetter was found and did not produce a PDF. Its own code, because the
#: remedy is not the remedy for the one above: something is wrong with the run
#: rather than with the machine, and the engine's last words are printed.
TEX_ENGINE_FAILED = 8


def report(
    console: Console,
    *,
    ledger_dir: Path,
    snapshot: str,
    subject_path: Path,
    brand: str,
    tex_path: Path | None = None,
    pdf_path: Path | None = None,
    which: Callable[[str], str | None] | None = None,
    run: Callable[..., subprocess.CompletedProcess] | None = None,
) -> int:
    """Print what one recorded round measured about one brand.

    `lulu collect` writes a round down, and until this command existed nothing
    printed what it came to. Every figure this repo has quoted about its own
    first round was produced by calling `mirror` by hand, which is a tool that
    cannot show its own answer.

    **The subject file is read rather than a list of ids being typed here.**
    Which questions name the brand is derivable from the file that states the
    questions, so a flag carrying that list would move a rule that cannot be got
    wrong onto whoever remembers to pass it.

    The chain is re-derived before anything is computed, through the same check
    `lulu verify` runs rather than a second copy of it. A number derived from a
    round that does not re-derive is not a number.

    **The terminal is still the default and still the whole of it.** `tex_path`
    and `pdf_path` add a file each; neither changes a line of what is printed,
    because a report somebody has been reading for weeks should not move because
    a colleague wanted a PDF of it.

    `which` and `run` are injected for the reason every stream in this file is:
    both arms are exercised in a suite that has no typesetter installed and
    never runs one. They default to nothing rather than to the library
    functions, because a default evaluated in the signature is bound once and
    a suite that replaced it afterwards would be testing a path this command
    does not take.
    """
    store = Ledger(ledger_dir)
    subject = load_subject(subject_path)
    self_naming = subject.self_naming(brand)

    console.say(f"lulu report: {ledger_dir}")
    console.say()
    try:
        played = _verified(store, console, "round", snapshot)
    except BrokenChain:
        return CHAIN_BROKEN

    console.say()
    try:
        scored = brand_report(
            Snapshot(label=snapshot, samples=group_runs(played.runs)),
            brand,
            self_naming=self_naming,
        )
    except NothingLeftToScore as e:
        console.say(f"  {e}")
        return NOTHING_TO_SCORE

    records = list(store.read(snapshot))
    panel = Panel(
        report=scored,
        dropped_runs=played.dropped,
        surfaces=played.surfaces,
        questions=questions_of(subject, played, records, self_naming),
    )
    for line in panel.as_text().splitlines():
        console.say(f"  {line}" if line else "")

    if tex_path is None and pdf_path is None:
        return 0
    written = tex_path if tex_path is not None else pdf_path.with_suffix(".tex")
    if not written.parent.is_dir():
        raise ValueError(
            f"{written.parent} is not a directory, so {written} cannot be written there"
        )
    written.write_text(tex_document(panel, evidence_of(records, played)), encoding="utf-8")
    console.say()
    console.say(f"  wrote {written}")
    if pdf_path is None:
        return 0
    return typeset(console, tex=written, pdf=pdf_path, which=which, run=run)


#: A draft ledger that is not one, or one this build cannot read. Its own code
#: rather than the argument error it would otherwise share: the file exists and
#: was opened, and the remedy is a different file rather than a different flag.
NOT_A_DRAFT = 9


def screened(
    console: Console,
    *,
    draft_path: Path,
    ledger_dir: Path,
    tex_path: Path | None = None,
    pdf_path: Path | None = None,
    which: Callable[[str], str | None] | None = None,
    run: Callable[..., subprocess.CompletedProcess] | None = None,
) -> int:
    """Read a finished screening round back, and say what it found.

    `lulu draft` prints this once while it is spending, and afterwards the round
    is a scroll of terminal output and two files of JSON. That is enough to run
    the next command and not enough to hand to anybody, which left the strongest
    finding this library has produced with nowhere to be read: a round where
    most questions come back naming nobody at all says something larger about a
    market than any percentage would, and it was living in a scrollback.

    Nothing is spent and nothing is asked. Every figure comes out of the draft
    ledger and the round it names, so the same two files give the same document
    forever, including to whoever is checking whether it was true.
    """
    try:
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        panel = _screen_panel(draft, ledger_dir)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        console.warn(f"{draft_path} is not a draft ledger this build can read: {e}")
        return NOT_A_DRAFT

    console.say(f"lulu screened: {draft_path}")
    console.say()
    for line in panel.as_text().splitlines():
        console.say(f"  {line}" if line else "")

    if tex_path is None and pdf_path is None:
        return 0
    written = tex_path if tex_path is not None else pdf_path.with_suffix(".tex")
    if not written.parent.is_dir():
        raise ValueError(
            f"{written.parent} is not a directory, so {written} cannot be written there"
        )
    written.write_text(tex_screening(panel), encoding="utf-8")
    console.say()
    console.say(f"  wrote {written}")
    if pdf_path is None:
        return 0
    return typeset(console, tex=written, pdf=pdf_path, which=which, run=run)


def _screen_panel(draft: dict, ledger_dir: Path) -> ScreenPanel:
    """The draft ledger as the surface prints it, with the names joined back on.

    The names come off the round rather than out of the draft file, because the
    draft records which declared rivals were hit and the interesting list is the
    one nobody declared. A round that cannot be opened leaves that section out
    and says why, rather than printing an empty table that reads as an answer.
    """
    snapshot = str(draft.get("screening_snapshot") or "")
    named: tuple = ()
    named_from = ""
    if not snapshot:
        named_from = "no draws were bought, so nothing was named"
    else:
        try:
            store = Ledger(ledger_dir)
            replies = tuple(
                Reply(prompt_id=rec.prompt_id, draw=rec.repeat, text=rec.answer_text)
                for rec in store.read(snapshot)
                if rec.prompt_id and rec.status == "ok" and rec.answer_text
            )
            named = names_in(replies)
            if not replies:
                # An empty read is not an exception here: a directory with no
                # such round in it answers with nothing. Printing an empty
                # table under a heading would read as a round that named
                # nobody, which is the opposite of a round nobody could open.
                named_from = f"{snapshot} holds no readable answer in {ledger_dir}"
        except (OSError, LedgerFormatError, ValueError) as e:
            named_from = f"{snapshot} could not be read from {ledger_dir}: {e}"

    return ScreenPanel(
        site=str(draft["site"]),
        snapshot=snapshot,
        corpus_digest=str(draft.get("corpus_digest", "")),
        pages_read=len(draft.get("pages_read", ())),
        proposed=int(draft["proposed"]),
        unreadable=len(draft.get("unreadable_entries", ())),
        dropped=tuple((str(r["gate"]), str(r["id"])) for r in draft.get("rejected", ())),
        screened=tuple(
            Screened(
                id=str(one["id"]),
                # Read with a default so a draft written before the words were
                # kept still opens, and it says so on the line rather than
                # printing a blank where a sentence belongs.
                text=str(one.get("text") or "(not recorded by the build that wrote this draft)"),
                verdict=str(one["verdict"]),
                rival_hits=int(one["rival_hits"]),
                draws=int(one["draws"]),
                floor=float(one["floor"]),
                low=float(one["interval"][0]),
                high=float(one["interval"][1]),
            )
            for one in draft.get("measured", ())
        ),
        noise_floor=None if draft.get("noise_floor") is None else float(draft["noise_floor"]),
        named=named,
        named_from=named_from,
        declared=tuple(str(r) for r in draft.get("rivals", ())),
    )


def rivals(console: Console, *, ledger_dir: Path, snapshot: str, least: int = 1) -> int:
    """Print every name a recorded round reached for, and where it reached for it.

    The questions in a screening round carry no company in them, so the names
    in the answers are the model's own. Reading them back is how a customer
    finds out who it is up against inside an answer, and until this command
    existed that reading was done once, by hand, in a script that was thrown
    away afterwards. A finding nobody can re-derive is an anecdote.

    Nothing is spent here and nothing is asked. The round has already been
    paid for, the answers are already on disk, and this is arithmetic over
    them: the same file gives the same table forever, including to whoever is
    checking whether the table was true.

    `least` is a floor on how many questions a name has to turn up in, and it
    defaults to letting everything through. A name in one question is a real
    observation about that question, and this command does not get to decide
    which observations a reader is allowed to see.
    """
    store = Ledger(ledger_dir)
    console.say(f"lulu rivals: {ledger_dir}")
    console.say()
    try:
        _verified(store, console, "round", snapshot)
    except BrokenChain:
        return CHAIN_BROKEN

    replies = tuple(
        Reply(prompt_id=rec.prompt_id, draw=rec.repeat, text=rec.answer_text)
        for rec in store.read(snapshot)
        if rec.prompt_id and rec.status == "ok" and rec.answer_text
    )
    found = [one for one in names_in(replies) if one.in_questions >= least]

    console.say()
    console.say("NAMED")
    for one in found:
        console.say(f"  {one.as_text()}")
    console.say()
    console.say(
        f"  {counted(len(found), 'name')} across {counted(len(replies), 'answer')}, and every one "
        "of them appears in a recorded answer character for character"
    )
    console.say(
        "  a name here is a name the model wrote, not a rival. which of them compete with the "
        "customer is the one judgement this cannot make from the answers"
    )
    return 0 if found else NOTHING_TO_SCORE


def questions_of(
    subject: Subject,
    played: Replay,
    records: Sequence[Record],
    self_naming: Sequence[str],
) -> tuple[Question, ...]:
    """Every question the subject file states, with what the round did with it.

    Assembled here for the reason `evidence_of` is: it reads a file, and the
    surface that prints it is not allowed to know that a file exists. The text
    of a question is in the subject file and nowhere else, since a `Record`
    carries the prompt's id and not its words, so the two sides are joined on
    the id that is the prompt's permanent identity.

    A question the round never reached is listed with nothing against it. That
    is the case a budget ceiling produces, and the round is shorter than the
    design that bought it whether or not anybody says so on the page.

    **A round that asked something the file does not state is refused.** The
    questions on the report are read off the subject file, so a file edited
    since the round was collected would print a list of questions that are not
    the ones that were asked, and the rule that leaves out a question naming the
    brand would be applied to whichever ids happened to survive the edit. This
    is the same door that already refuses a brand the file does not track.
    """
    asked: dict[str, int] = {}
    for rec in records:
        if rec.is_seal:
            continue
        asked[rec.prompt_id] = asked.get(rec.prompt_id, 0) + 1
    usable: dict[str, int] = {}
    for run in played.runs:
        usable[run.prompt_id] = usable.get(run.prompt_id, 0) + 1

    unstated = sorted(set(asked) - {prompt.id for prompt in subject.prompts})
    if unstated:
        raise ValueError(
            f"{subject.path} does not state {', '.join(unstated)}, which this round asked. "
            "a report reads its questions and its exclusions off the subject file, so a file "
            "that has moved since the round was collected describes a different round"
        )
    return tuple(
        Question(
            id=prompt.id,
            text=prompt.text,
            asked=asked.get(prompt.id, 0),
            usable=usable.get(prompt.id, 0),
            excluded=prompt.id in self_naming,
        )
        for prompt in subject.prompts
    )


def evidence_of(records: Sequence[Record], played: Replay) -> Evidence:
    """The facts about the file a printed report is checked against.

    Read by the caller rather than in the renderer, which is not allowed to
    know that a file exists. The round has already re-derived by the time this
    runs, so what is written down is what the chain was checked as, and the
    hash on the last record is the hash a reader recomputes to check it again.

    The dates come off the asks and not off the seal. A round is closed once
    and asked over however long it took, so the closing timestamp is when the
    collector stopped rather than when the answers were collected.
    """
    last = records[-1]
    return Evidence(
        records=len(records),
        seal=seal_text(last) if last.is_seal else UNSEALED,
        final_hash=last.hash,
        models=played.models,
        surfaces=played.surfaces,
        dates=tuple(sorted({rec.asked_at[:10] for rec in records if not rec.is_seal})),
        cost=spend_of(records).total_lines(),
    )


def typeset(
    console: Console,
    *,
    tex: Path,
    pdf: Path,
    which: Callable[[str], str | None] | None = None,
    run: Callable[..., subprocess.CompletedProcess] | None = None,
) -> int:
    """Run the typesetter over a document that has already been written.

    This is the only part of printing a report that is not a pure function of
    the round, which is why it is here and not beside the renderer: producing
    the string reaches nothing, and spawning a process reaches a machine.

    The document is written before this is called and stays written whatever
    happens next. A command that deleted its own output on a failed compile
    would leave somebody with no PDF, no `.tex` and nothing to send to whoever
    could tell them why.

    The engine builds in a temporary directory and the result is moved onto the
    path that was asked for. Working in the destination would leave whatever
    the engine keeps beside the PDF in a directory somebody chose for one file,
    and it would name the output after the document rather than after the
    request.
    """
    binary = (which or shutil.which)(TEX_ENGINE)
    if binary is None:
        console.warn(f"  no {TEX_ENGINE} on PATH, so nothing typeset the document.")
        console.warn(f"  {tex} is written and is what an engine would be given.")
        return NO_TEX_ENGINE
    with tempfile.TemporaryDirectory() as build:
        done = (run or subprocess.run)(
            [binary, "--chatter", "minimal", "--outdir", build, str(tex)],
            capture_output=True,
            text=True,
        )
        if done.returncode != 0:
            console.warn(f"  {TEX_ENGINE} exited {done.returncode} and produced no PDF.")
            for line in (done.stderr or done.stdout).strip().splitlines()[-10:]:
                console.warn(f"    {line}")
            return TEX_ENGINE_FAILED
        shutil.move(str(Path(build) / f"{tex.stem}.pdf"), pdf)
    console.say(f"  wrote {pdf}")
    return 0


# -- entry point ------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lulu",
        description="Measure how an answer engine talks about a brand, with the uncertainty attached.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_setup = sub.add_parser(
        "setup", help="store an API key and prove it works, in one command with no questions"
    )
    p_setup.add_argument(
        "--provider",
        default=None,
        help="only needed when the key does not start the way its engine's keys do",
    )

    p_init = sub.add_parser("init", help="the older wizard, which asks where to store the key")
    p_init.add_argument("--provider", default="perplexity", help="which engine the key is for")
    p_init.add_argument(
        "--from-file",
        default=None,
        metavar="PATH",
        help="read the key from this file instead of prompting; delete the file afterwards",
    )
    p_init.add_argument(
        "--from-env",
        action="store_true",
        help="read the key from the provider's environment variable instead of prompting",
    )

    p_doctor = sub.add_parser("doctor", help="find the key, test it, and price the call")
    p_doctor.add_argument("--provider", default="perplexity", help="which engine to check")
    p_doctor.add_argument(
        "--offline",
        action="store_true",
        help="do everything except the test call, so nothing is spent",
    )

    p_collect = sub.add_parser(
        "collect", help="ask one subject's questions k times each and write the round down"
    )
    p_collect.add_argument(
        "--subject",
        required=True,
        metavar="PATH",
        help="the subject file: the names this round tracks and the questions it asks",
    )
    # No default. k decides whether the round can carry an interval at all, and
    # a number chosen here would be one nobody decided, spent for.
    p_collect.add_argument(
        "--k", type=int, required=True, help="how many times each prompt is asked; at least 2"
    )
    # Required for the same reason, and a harder one: this is the command that
    # spends real money on a prepaid account, and a default ceiling is a
    # default amount of somebody else's money.
    p_collect.add_argument(
        "--budget",
        type=float,
        required=True,
        metavar="USD",
        help="hard ceiling for this round in dollars; a round with no ceiling is refused",
    )
    p_collect.add_argument("--ledger", default=DEFAULT_LEDGER, help="directory the round is written to")
    p_collect.add_argument("--provider", default="anthropic", help="which engine answers")
    p_collect.add_argument(
        "--model", default=None, help="model to ask; the provider's check model by default"
    )
    p_collect.add_argument(
        "--max-searches",
        type=int,
        default=DEFAULT_MAX_SEARCHES,
        help="searches one call may run, on an engine billed per search",
    )
    p_collect.add_argument(
        "--no-search",
        action="store_true",
        help=(
            "collect the arm with no search tool attached, which is recorded under its own "
            f"surface ({UNSEARCHED_SURFACE}) so it can never be pooled with the searched one"
        ),
    )

    p_draft = sub.add_parser(
        "draft", help="turn one domain into a measured question set, asking nothing else"
    )
    p_draft.add_argument("--site", required=True, help="the customer's site, and the only thing they type")
    p_draft.add_argument(
        "--out", required=True, metavar="PATH", help="where the subject file is written"
    )
    # Required, and with no default, for the same reason `replica_gate` takes a
    # margin: the floor is what the verdicts mean. A number chosen here would
    # decide which questions survive on behalf of somebody who never saw it.
    p_draft.add_argument(
        "--floor",
        type=float,
        required=True,
        help="rate a question has to beat on rivals to be kept; also sets how many draws it takes",
    )
    p_draft.add_argument(
        "--budget",
        type=float,
        required=True,
        metavar="USD",
        help="hard ceiling in dollars; a draft with no ceiling is refused",
    )
    p_draft.add_argument(
        "--rivals",
        default="",
        help="comma separated names the questions are screened on; without them the paid round is refused",
    )
    p_draft.add_argument("--ledger", default=DEFAULT_LEDGER, help="directory the screening round is written to")
    p_draft.add_argument("--provider", default="anthropic", help="which engine answers")
    p_draft.add_argument("--model", default=None, help="model to ask; the provider's check model by default")
    p_draft.add_argument(
        "--max-searches", type=int, default=DEFAULT_MAX_SEARCHES, help="searches one call may run"
    )
    p_draft.add_argument(
        "--pages", type=int, default=DEFAULT_MAX_PAGES, help="how many of the site's pages are read"
    )
    p_draft.add_argument(
        "--candidates", type=int, default=DEFAULT_WANTED, help="questions asked for in one call"
    )
    p_draft.add_argument(
        "--harvest-only", action="store_true", help="read the site and stop; no model, no spend"
    )
    p_draft.add_argument(
        "--dry-run",
        action="store_true",
        help="corpus, one proposal call and the free gates; stops before the draws that measure",
    )

    # No --model and no --provider. Both are read from each record, which names
    # the model that was actually billed; a flag would let one round be priced
    # at another model's rate with nothing on screen to say so.
    p_usage = sub.add_parser("usage", help="what the recorded rounds cost, from the provider's own figures")
    p_usage.add_argument("--ledger", default=DEFAULT_LEDGER, help="directory the rounds were written to")
    p_usage.add_argument("--snapshot", default=None, help="one round; every round by default")

    p_ablate = sub.add_parser(
        "ablate", help="whether a replica round may stand in for a live one, and why not"
    )
    p_ablate.add_argument("--live", required=True, help="a round collected from the engine itself")
    p_ablate.add_argument("--replica", required=True, help="a round collected with the sources supplied")
    p_ablate.add_argument("--brand", required=True, help="which brand the two rounds are scored for")
    p_ablate.add_argument(
        "--margin",
        type=float,
        default=5.0,
        help="how many points the two may differ by and still count as the same, e.g. 5",
    )
    p_ablate.add_argument("--confidence", type=float, default=0.95)
    p_ablate.add_argument("--brands", type=int, default=1, help="how many brands are held at once")
    p_ablate.add_argument("--per-brand", action="store_true")
    p_ablate.add_argument("--ledger", default=DEFAULT_LEDGER, help="directory the rounds live in")

    p_lift = sub.add_parser(
        "lift", help="what one source was worth, between the arm that carried it and the arm that did not"
    )
    p_lift.add_argument("--held", required=True, help="the replica round asked with the full list")
    p_lift.add_argument("--dropped", required=True, help="the replica round asked without one source")
    p_lift.add_argument("--brand", required=True, help="which brand the two arms are scored for")
    p_lift.add_argument(
        "--source", required=True, help="the one page removed from the list in the dropped arm"
    )
    p_lift.add_argument(
        "--sources",
        action="append",
        required=True,
        metavar="URL",
        help="one page of the full list, repeated once per page, in the order the model saw them",
    )
    p_lift.add_argument(
        "--live",
        default=None,
        help="a live round; supplying it runs the gate, and only a gate that passes allows the word lift",
    )
    p_lift.add_argument(
        "--margin",
        type=float,
        default=5.0,
        help="how many points a source may be worth and still count as not worth chasing",
    )
    p_lift.add_argument(
        "--gate-margin",
        type=float,
        default=None,
        help="margin the replica gate is held to; the same as --margin unless given",
    )
    p_lift.add_argument("--confidence", type=float, default=0.95)
    p_lift.add_argument("--brands", type=int, default=1, help="how many brands are held at once")
    p_lift.add_argument("--per-brand", action="store_true")
    p_lift.add_argument("--ledger", default=DEFAULT_LEDGER, help="directory the rounds live in")

    p_screened = sub.add_parser(
        "screened", help="read a finished screening round back, and what it found"
    )
    p_screened.add_argument(
        "--draft", required=True, metavar="PATH", help="the .draft.json a draft wrote"
    )
    p_screened.add_argument(
        "--ledger", default=DEFAULT_LEDGER, help="directory the screening round lives in"
    )
    p_screened.add_argument("--tex", default=None, metavar="PATH", help="write the document here")
    p_screened.add_argument(
        "--pdf", default=None, metavar="PATH", help="write the document and typeset it here"
    )

    p_rivals = sub.add_parser(
        "rivals", help="every name a recorded round reached for, and in which questions"
    )
    p_rivals.add_argument("--snapshot", required=True, help="the round to read")
    p_rivals.add_argument("--ledger", default=DEFAULT_LEDGER, help="directory the round lives in")
    p_rivals.add_argument(
        "--least",
        type=int,
        default=1,
        metavar="N",
        help="only names that turned up in at least N of the questions",
    )

    p_report = sub.add_parser("report", help="what one recorded round measured about one brand")
    p_report.add_argument("--snapshot", required=True, help="the round to read")
    # Required, and not a list of prompt ids. The file that stated the questions
    # is what says which of them name the brand, so the rule is derived here
    # rather than typed here.
    p_report.add_argument(
        "--subject",
        required=True,
        metavar="PATH",
        help="the subject file this round was collected from, which states the questions",
    )
    p_report.add_argument("--brand", required=True, help="which tracked name the round is scored for")
    p_report.add_argument("--ledger", default=DEFAULT_LEDGER, help="directory the round lives in")
    # Both are additions to the screen rather than replacements of it. Neither
    # has a default: a command that wrote a file nobody asked for would put a
    # customer's round somewhere they did not choose.
    p_report.add_argument(
        "--tex",
        default=None,
        metavar="PATH",
        help="also write the report as a standalone LaTeX document; needs no TeX installed",
    )
    p_report.add_argument(
        "--pdf",
        default=None,
        metavar="PATH",
        help=f"also typeset that document to a PDF, through {TEX_ENGINE}",
    )

    p_verify = sub.add_parser("verify", help="re-derive every chain on disk and report what moved")
    p_verify.add_argument("--ledger", default=DEFAULT_LEDGER, help="directory the rounds were written to")
    p_verify.add_argument("--snapshot", default=None, help="one round; every round by default")

    p_plan = sub.add_parser("plan", help="how many calls a target precision needs, and what it costs")
    p_plan.add_argument("--prompts", type=int, required=True, help="how many tracked questions")
    p_plan.add_argument("--brands", type=int, default=1, help="how many brands are read from the same answers")
    p_plan.add_argument(
        "--half-width",
        type=float,
        default=5.0,
        help="target precision in percentage points, e.g. 5 for +/-5 points",
    )
    p_plan.add_argument("--confidence", type=float, default=0.95)
    p_plan.add_argument(
        "--rate",
        type=float,
        default=0.5,
        help="expected appearance rate; 0.5 is the worst case and the default",
    )
    p_plan.add_argument("--days", type=int, default=30, help="window the daily comparison covers")
    p_plan.add_argument("--scans-per-day", type=int, default=1)
    p_plan.add_argument(
        "--per-brand",
        action="store_true",
        help="size one brand at a time instead of holding every brand at once",
    )
    p_plan.add_argument("--pilot", default=None, help="a recorded round to measure the split from")
    p_plan.add_argument("--brand", default=None, help="which brand the pilot is scored for")
    p_plan.add_argument("--ledger", default=DEFAULT_LEDGER, help="where the pilot round lives")
    p_plan.add_argument("--provider", default="perplexity", help="which engine's price table to use")
    p_plan.add_argument(
        "--searches-per-call",
        type=int,
        default=SEARCHES_PER_CALL,
        help="searches one call may run, for engines billed per search rather than per call",
    )
    p_plan.add_argument("--model", default=None, help="model to price; the provider's check model by default")

    p_size = sub.add_parser(
        "size", help="what a design you set costs, and what precision it buys"
    )
    p_size.add_argument("--prompts", type=int, required=True, help="how many tracked questions")
    p_size.add_argument("--runs", type=int, required=True, help="how many times each prompt is asked")
    p_size.add_argument(
        "--engines",
        default="perplexity",
        help="comma separated, provider or provider:model, e.g. perplexity,anthropic",
    )
    p_size.add_argument("--brands", type=int, default=1, help="how many brands are read from the same answers")
    p_size.add_argument("--confidence", type=float, default=0.95)
    p_size.add_argument(
        "--rate",
        type=float,
        default=0.5,
        help="expected appearance rate; 0.5 is the worst case and the default",
    )
    p_size.add_argument(
        "--per-brand",
        action="store_true",
        help="size one brand at a time instead of holding every brand at once",
    )
    p_size.add_argument("--pilot", default=None, help="a recorded round to measure the split from")
    p_size.add_argument("--brand", default=None, help="which brand the pilot is scored for")
    p_size.add_argument("--ledger", default=DEFAULT_LEDGER, help="where the pilot round lives")
    p_size.add_argument(
        "--searches-per-call",
        type=int,
        default=SEARCHES_PER_CALL,
        help="searches one call may run, for engines billed per search rather than per call",
    )
    return parser


def main(argv: Sequence[str] | None = None, *, console: Console | None = None) -> int:
    args = build_parser().parse_args(argv)
    console = console or Console(out=sys.stdout, err=sys.stderr)
    cwd, home = Path.cwd(), Path.home()

    try:
        if args.command == "setup":
            import getpass

            return setup(
                console,
                key=read_key(console, sys.stdin, getpass.getpass),
                cwd=cwd,
                home=home,
                provider=args.provider,
            )
        if args.command == "init":
            import getpass

            return init(
                console,
                ask=input,
                secret=getpass.getpass,
                cwd=cwd,
                home=home,
                provider=args.provider,
                from_env=args.from_env,
                from_file=Path(args.from_file) if args.from_file else None,
            )
        if args.command == "plan":
            return plan(
                console,
                prompts=args.prompts,
                half_width=args.half_width / 100.0,
                brands=args.brands,
                confidence=args.confidence,
                rate=args.rate,
                days=args.days,
                scans_per_day=args.scans_per_day,
                family=not args.per_brand,
                pilot=args.pilot,
                brand=args.brand,
                ledger_dir=Path(args.ledger),
                provider=args.provider,
                model=args.model,
                searches_per_call=args.searches_per_call,
            )
        if args.command == "size":
            return size(
                console,
                prompts=args.prompts,
                runs=args.runs,
                engines=[e for e in args.engines.split(",") if e.strip()],
                brands=args.brands,
                confidence=args.confidence,
                rate=args.rate,
                family=not args.per_brand,
                pilot=args.pilot,
                brand=args.brand,
                ledger_dir=Path(args.ledger),
                searches_per_call=args.searches_per_call,
            )
        if args.command == "ablate":
            return ablate(
                console,
                ledger_dir=Path(args.ledger),
                live=args.live,
                replica=args.replica,
                brand=args.brand,
                margin=args.margin / 100.0,
                confidence=args.confidence,
                brands=args.brands,
                family=not args.per_brand,
            )
        if args.command == "lift":
            return lift(
                console,
                ledger_dir=Path(args.ledger),
                held=args.held,
                dropped=args.dropped,
                brand=args.brand,
                source=args.source,
                sources=tuple(args.sources),
                margin=args.margin / 100.0,
                live=args.live,
                gate_margin=None if args.gate_margin is None else args.gate_margin / 100.0,
                confidence=args.confidence,
                brands=args.brands,
                family=not args.per_brand,
            )
        if args.command == "collect":
            return collect(
                console,
                subject_path=Path(args.subject),
                ledger_dir=Path(args.ledger),
                k=args.k,
                budget_usd=args.budget,
                cwd=cwd,
                home=home,
                provider=args.provider,
                model=args.model,
                max_searches=args.max_searches,
                can_search=not args.no_search,
            )
        if args.command == "draft":
            return draft(
                console,
                site=args.site,
                out=Path(args.out),
                floor=args.floor,
                budget_usd=args.budget,
                cwd=cwd,
                home=home,
                ledger_dir=Path(args.ledger),
                rivals=[r.strip() for r in args.rivals.split(",") if r.strip()],
                provider=args.provider,
                model=args.model,
                max_searches=args.max_searches,
                max_pages=args.pages,
                wanted=args.candidates,
                harvest_only=args.harvest_only,
                dry_run=args.dry_run,
            )
        if args.command == "screened":
            return screened(
                console,
                draft_path=Path(args.draft),
                ledger_dir=Path(args.ledger),
                tex_path=None if args.tex is None else Path(args.tex),
                pdf_path=None if args.pdf is None else Path(args.pdf),
            )
        if args.command == "rivals":
            return rivals(
                console,
                ledger_dir=Path(args.ledger),
                snapshot=args.snapshot,
                least=args.least,
            )
        if args.command == "report":
            return report(
                console,
                ledger_dir=Path(args.ledger),
                snapshot=args.snapshot,
                subject_path=Path(args.subject),
                brand=args.brand,
                tex_path=None if args.tex is None else Path(args.tex),
                pdf_path=None if args.pdf is None else Path(args.pdf),
            )
        if args.command == "verify":
            return verify(console, ledger_dir=Path(args.ledger), snapshot=args.snapshot)
        if args.command == "usage":
            return usage(console, ledger_dir=Path(args.ledger), snapshot=args.snapshot)
        return doctor(console, cwd=cwd, home=home, provider=args.provider, offline=args.offline)
    except LedgerFormatError as e:
        # Kept above the ValueError branch it inherits from. "This evidence
        # file cannot be read" and "you typed the argument wrong" are different
        # problems with different remedies, and they must not share an exit code.
        console.warn(f"The ledger could not be read: {e}")
        return 3
    except ValueError as e:
        console.warn(str(e))
        return 2
    except KeyboardInterrupt:
        console.warn("Stopped. Nothing was stored.")
        return 130
    except EOFError:
        # A shell with no input left. Reported rather than raised, because the
        # traceback would land where the next instruction should be.
        console.warn("The input ended before the command finished. Nothing was stored.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
