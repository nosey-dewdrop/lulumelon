"""`lulu`: the commands that stand between a person and a defensible number.

Two are about getting started, two are about money and evidence, and one is
about whether the causal half of this product is real at all.

`lulu init` asks for a key, stores it, and says out loud where it stored it.
`lulu doctor` answers "why is it not working" in one screen: every place that
was looked at, what was wrong with the key as a string, whether the endpoint is
reachable at all, and what the one test call cost.
`lulu plan` sizes a round before it is bought, and says where no number of
repeats would be enough.
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
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence, TextIO

from .collect.ask import DEFAULT_MAX_SEARCHES, Answer, provider_for
from .collect.ledger import (
    DIAGNOSTIC_SUBJECT,
    Ledger,
    LedgerFormatError,
    Record,
    is_diagnostic,
)
from .collect.replay import replay
from .collect.replica import (
    REPLICA_SURFACE,
    is_replica_surface,
    replica_surface,
    without,
)
from .collect.session import utc_now
from .mirror.ablation import DIFFERS, STANDS_IN, UNDECIDED, replica_gate
from .mirror.compare import model_confounds
from .mirror.lift import MOVES, NEGLIGIBLE, NO_CONTRAST
from .mirror.lift import UNDECIDED as EFFECT_UNDECIDED
from .mirror.lift import source_effect
from .mirror.types import Snapshot, group_runs
from .mirror.variance import decompose
from .keys import (
    KEYCHAIN_SERVICE,
    PROVIDERS,
    ProviderSpec,
    Resolution,
    ensure_gitignored,
    env_file_candidates,
    fingerprint,
    inspect_key,
    keychain_available,
    keychain_write,
    redact,
    resolve,
    spec_for,
    write_env_file,
)
from .prices import FEE_PER_SEARCH, Cost, estimate, fees, price_for, reported
from .plan import (
    Comparison,
    Design,
    critical_value,
    draws_needed,
    icc_of,
    price_of,
    prompts_for_worst_case,
    reachable_icc,
    total_variance,
    variance_of,
)
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

    # No menu. The keychain where the machine has one, a file with owner-only
    # permissions where it does not, and the answer printed rather than asked.
    if keychain_available():
        try:
            keychain_write(KEYCHAIN_SERVICE, spec.name, key)
        except (RuntimeError, ValueError) as e:
            console.warn(f"The keychain refused it: {redact(str(e), key)}")
            return 1
        where = f"the OS keychain, service {KEYCHAIN_SERVICE}, account {spec.name}"
        reread = f"security find-generic-password -s {KEYCHAIN_SERVICE} -a {spec.name} -w"
    else:
        _, home_file = env_file_candidates(cwd, home)
        path = write_env_file(home_file, spec.env_var, key)
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
    if keychain_available():
        menu.append(("keychain", f"the OS keychain (service {KEYCHAIN_SERVICE}) — not a file, not in the repo"))
    menu.append(("local", f"{local} — read only in this directory"))
    menu.append(("home", f"{home_file} — read from anywhere"))
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
    console.say(f"lulu init — setting up {spec.name}")
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
        except (RuntimeError, ValueError) as e:
            console.warn(f"The keychain refused it: {redact(str(e), key)}")
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
    console.say(f"lulu doctor — {spec.name}")
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

    console.say(f"lulu usage — {ledger_dir}")

    failed_chain = False
    for snapshot_id in wanted:
        console.say()
        console.say(snapshot_id)
        problems = store.verify(snapshot_id)
        if problems:
            failed_chain = True
            console.say(f"  CHAIN BROKEN, {len(problems)} problems. No cost is computed from it.")
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
    console.say(f"lulu verify — {ledger_dir}")
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
            console.say(f"  BROKEN   {snapshot_id}   {len(problems)} problems")
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
                f"  intact   {snapshot_id}   {store.count(snapshot_id)} records, "
                "length never sealed"
            )
            continue
        console.say(
            f"  intact   {snapshot_id}   {seal.round_asked} calls sealed, "
            f"{seal.round_ok} answered, {seal.round_errors} failed"
        )

    console.say()
    console.say(f"{len(wanted) - broken} of {len(wanted)} rounds re-derive from their own contents.")
    console.say()
    console.say("What that covers: every record present was checked against its own hash and")
    console.say("against the one before it, so altering an answer costs a rewrite of every")
    console.say("record after it. A sealed round is also checked against its own length: it")
    console.say("ends with a record saying how many calls it made, so records removed from the")
    console.say("end are reported rather than silently lost.")
    if unsealed:
        rounds = "1 round" if unsealed == 1 else f"{unsealed} rounds"
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
    console.say(f"  {prompts} prompts, {brands} brand{'' if brands == 1 else 's'} tracked")
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
            console.say(f"  {prompts} prompts. {prompts_for_worst_case(half_width, z, variance)} prompts would reach it at any icc.")
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
                f"  {prompts_for_worst_case(half_width, z, variance)} prompts would reach it "
                "even if repeats bought nothing."
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
        console.say(f"  {tighter.calls} calls per round, {tighter.calls * 2} for the pair.")
    else:
        console.say(f"  unreachable at {prompts} prompts: {tighter.reason}")

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
        console.say(f"  {label:<24} {calls} calls   " + (cost.as_text() if cost else "no published price on file"))

    if math.isfinite(ceiling):
        console.say()
        console.say(f"  above icc {ceiling:.4f} this design has no price at any budget: with")
        console.say(f"  {prompts} prompts the prompt set alone carries more error than the")
        console.say("  target, so no number of repeats closes it and no amount of money buys it.")
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
            f"{pilot} does not verify ({len(problems)} problems), so nothing is planned from it"
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
            f"  note: {played.dropped} of {played.total} pilot asks failed and are excluded; "
            "a failed ask is missing data, not an observed absence"
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
    """
    problems = store.verify(snapshot_id)
    if problems:
        console.say(f"  {snapshot_id}: CHAIN BROKEN, {len(problems)} problems.")
        console.say("  no verdict is computed from a round that does not re-derive.")
        raise BrokenChain(snapshot_id)
    played = replay(store, snapshot_id)
    console.say(f"  {role:<8} {snapshot_id}")
    console.say(f"           {played.as_text()}")
    return played


def _detections(played, brand: str) -> dict[str, tuple[int, ...]]:
    return {s.prompt_id: s.detections(brand) for s in group_runs(played.runs)}


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
    console.say(f"lulu ablate — {ledger_dir}")
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
    console.say(f"lulu lift — {ledger_dir}")
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
    console.say(f"  source list  {len(sources)} pages, in the order the model saw them")
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
