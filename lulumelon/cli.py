"""`lulu`: the two commands that stand between a new user and a measurement.

A bring-your-own-key tool has exactly one hard step, and it happens before any
of the engineering matters: putting a key somewhere the tool will find it. That
step is treated here as a feature with tests, not as a paragraph in a README.

`lulu init` asks, stores, and then says out loud where it stored it.
`lulu doctor` answers "why is it not working" in one screen: every place that
was looked at, what was wrong with the key as a string, whether the endpoint is
reachable at all, and what the one test call cost.

Both are written so nothing is guessed. Where the code cannot know something it
says so: an unknown price is "no published price on file", not a plausible
number, and a rejected key names the two things that produce that rejection
rather than printing a status code.

Every stream and every prompt is injected, so the whole interaction is exercised
in tests without a terminal and without a key.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence, TextIO

from .collect.ask import PerplexityProvider
from .collect.ledger import Ledger, LedgerFormatError
from .keys import (
    KEYCHAIN_SERVICE,
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
from .prices import estimate, price_for, reported, request_fees
from .usage import spend_of

#: Where rounds are written unless a caller says otherwise. Relative on
#: purpose: a measurement belongs to the project it was made for.
DEFAULT_LEDGER = "./ledger"

#: The model a check call uses. The cheapest search-grounded model on the price
#: table, because the point of the call is to prove the key spends, not to get
#: a good answer.
CHECK_MODEL = "sonar"

#: Short and dull on purpose: a check call is billed like any other, so it asks
#: for as few output tokens as a question can.
CHECK_PROMPT = "Reply with the single word: ok"


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
) -> int:
    """Walk one person through storing one key, and confirm where it went."""
    spec = spec_for(provider)
    console.say(f"lulu init — setting up {spec.name}")
    console.say()
    console.say(f"1. Open {spec.key_page}")
    console.say("2. Sign in, open the API Keys tab, and create a key.")
    console.say("3. The key is shown once. Copy it, then paste it below.")
    console.say()
    console.say(f"   A {spec.name} key starts with {spec.key_prefix!r} ({spec.key_prefix_source}).")
    console.say("   Nothing you type is echoed, logged, or sent anywhere except to the provider.")
    console.say()

    key = secret(f"Paste your {spec.name} API key: ").strip()
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


def check_call(console: Console, spec: ProviderSpec, key: str, *, model: str = CHECK_MODEL) -> int:
    """Spend the smallest possible amount to find out whether the key works."""
    price = price_for(spec.name, model)
    if price is None:
        console.say(f"No published price on file for {spec.name}/{model}, so the cost of this call is unknown.")
    else:
        console.say(f"One {model} call is billed at {price.provenance()}:")
        console.say(
            f"  tokens ${price.input_per_mtok_usd:g} in / ${price.output_per_mtok_usd:g} out per million, "
            f"plus a request fee of ${price.request_fee_per_k_low_usd:g} to "
            f"${price.request_fee_per_k_high_usd:g} per thousand requests."
        )
    console.say(f"Asking {spec.name} one question now.")
    console.say()

    provider = PerplexityProvider(api_key=key, model=model)
    answer = provider.ask(CHECK_PROMPT)

    if not answer.ok:
        console.say(f"The call failed after {answer.latency_ms} ms.")
        console.say(f"  {answer.error}")
        console.say()
        for line in diagnose(spec, answer.error):
            console.say(f"  {line}")
        return 1

    console.say(f"It worked, in {answer.latency_ms} ms.")
    console.say(f"  model as reported by the response: {answer.model}")
    console.say(f"  reply: {answer.text.strip()[:120]}")
    counted = answer.usage.input_tokens is not None and answer.usage.output_tokens is not None
    if counted:
        console.say(f"  tokens: {answer.usage.input_tokens} in, {answer.usage.output_tokens} out")
    else:
        console.say("  tokens: the response did not report them")

    if answer.usage.cost_usd is not None:
        cost = reported(answer.usage.cost_usd)
    elif price is None:
        console.say("  cost: unknown, because no price for this model has been read from the provider")
        return 0
    elif counted:
        cost = estimate(price, input_tokens=answer.usage.input_tokens, output_tokens=answer.usage.output_tokens)
    else:
        # No metered figure and no token counts. The request fee is still known
        # and is the larger term, so it is reported as the floor it is rather
        # than padded out with zero tokens and called an estimate.
        cost = request_fees(price)
    console.say(f"  cost of this call: {cost.as_text()}")
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
    return check_call(console, spec, found.key)


# -- usage ------------------------------------------------------------------


def usage(
    console: Console,
    *,
    ledger_dir: Path,
    snapshot: str | None = None,
    provider: str = "perplexity",
    model: str = CHECK_MODEL,
) -> int:
    """What the rounds on disk cost, from what the provider said about them.

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

    price = price_for(provider, model)
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
        for line in spend_of(store.read(snapshot_id), price).as_text().splitlines():
            console.say(f"  {line}" if line else "")

    return 1 if failed_chain else 0


# -- entry point ------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lulu",
        description="Measure how an answer engine talks about a brand, with the uncertainty attached.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="store an API key and say where it was stored")
    p_init.add_argument("--provider", default="perplexity", help="which engine the key is for")

    p_doctor = sub.add_parser("doctor", help="find the key, test it, and price the call")
    p_doctor.add_argument("--provider", default="perplexity", help="which engine to check")
    p_doctor.add_argument(
        "--offline",
        action="store_true",
        help="do everything except the test call, so nothing is spent",
    )

    p_usage = sub.add_parser("usage", help="what the recorded rounds cost, from the provider's own figures")
    p_usage.add_argument("--ledger", default=DEFAULT_LEDGER, help="directory the rounds were written to")
    p_usage.add_argument("--snapshot", default=None, help="one round; every round by default")
    p_usage.add_argument("--provider", default="perplexity", help="which engine's price table to use")
    p_usage.add_argument("--model", default=CHECK_MODEL, help="which model's published rates to use")
    return parser


def main(argv: Sequence[str] | None = None, *, console: Console | None = None) -> int:
    args = build_parser().parse_args(argv)
    console = console or Console(out=sys.stdout, err=sys.stderr)
    cwd, home = Path.cwd(), Path.home()

    try:
        if args.command == "init":
            import getpass

            return init(
                console,
                ask=input,
                secret=getpass.getpass,
                cwd=cwd,
                home=home,
                provider=args.provider,
            )
        if args.command == "usage":
            return usage(
                console,
                ledger_dir=Path(args.ledger),
                snapshot=args.snapshot,
                provider=args.provider,
                model=args.model,
            )
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


if __name__ == "__main__":
    raise SystemExit(main())
