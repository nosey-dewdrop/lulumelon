"""Where the key comes from, and what the user is told when it is not there.

This library asks the user to bring their own key. That decision is what makes
the measurement cheap, and it is also the single place where a person who wants
to use the tool can get stuck with nothing to read. A product that cannot be
started is not a product, so the key path is treated as part of the engine
rather than as documentation.

Three properties are enforced here, and each one exists because of a specific
way this goes wrong.

**Lookup is a recorded walk, not a boolean.** `resolve` returns every place it
looked in the order it looked, with the absolute path or service name it used,
whether or not it found anything. "No API key found" without that list leaves
the user guessing which of four files the tool actually reads, and guessing is
the failure this module exists to remove.

**The key never leaves this module as text.** It is held on a field with
`repr=False`, so a traceback or a printed dataclass cannot spill it, and
`redact` is applied to anything that came back from a provider before it is
shown or written down. Provider error bodies echo request material often
enough that scrubbing on the way in is cheaper than auditing every surface.

**A stored key is verified as a string before it is spent on a request.** A
trailing newline from a paste, a pair of shell quotes captured into the value,
or a key from a different provider all produce the same opaque 401. Those are
distinguishable locally, for free, so they are distinguished locally.

**Storage is attempted, never predicted.** Whether the machine has a keychain
and whether it will take a key right now are two questions, and answering them
with one boolean is how a Mac with no writable default keychain ended up
storing the key nowhere at all. `keychain_supported` answers the first;
`keychain_write` raising `KeychainRefused` answers the second. Every caller
therefore has a second place to put the key, and reaches it.
"""

from __future__ import annotations

import hashlib
import os
import platform
import re
import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .text import counted

#: The service name a key is filed under in the OS keychain. Fixed, because a
#: key stored under one name and read under another is indistinguishable from
#: no key at all.
KEYCHAIN_SERVICE = "lulumelon"

#: Everything the CLI writes when the user picks the file option lives here, so
#: there is one answer to "where did it put my key" that does not depend on the
#: directory the command was run from.
HOME_CONFIG_DIR = ".lulu"
HOME_CONFIG_FILE = "env"


@dataclass(frozen=True, slots=True)
class ProviderSpec:
    """One engine we can actually call, and everything needed to start it.

    Only providers with a working implementation in `collect.ask` appear in
    `PROVIDERS`. Offering to store a key for an engine that nothing can call
    would produce a setup that completes successfully and measures nothing.
    """

    name: str
    #: Read first, and the name the docs tell people to export.
    env_var: str
    #: Also accepted. Present because these names are already in circulation.
    env_aliases: tuple[str, ...]
    #: The page where a human obtains the key. Printed on failure.
    key_page: str
    #: The billing page, printed when the provider says the account is empty.
    billing_page: str
    #: Observed prefix of this provider's keys. Used only as a hint: a key that
    #: does not match is still tried, because a provider may change the format
    #: without telling anyone and refusing a valid key would be worse.
    key_prefix: str
    #: Where the prefix above was read, so the hint can be re-checked later.
    key_prefix_source: str
    #: The model a check call asks for. Per provider, because the cheapest
    #: search-grounded model on one price table is not a model name on another,
    #: and a default borrowed across providers is a 404 at the worst moment.
    check_model: str

    @property
    def env_names(self) -> tuple[str, ...]:
        return (self.env_var, *self.env_aliases)


PROVIDERS: dict[str, ProviderSpec] = {
    "perplexity": ProviderSpec(
        name="perplexity",
        env_var="PERPLEXITY_API_KEY",
        env_aliases=("LULU_PERPLEXITY_API_KEY",),
        key_page="https://console.perplexity.ai",
        billing_page="https://console.perplexity.ai",
        key_prefix="pplx-",
        # Perplexity's own documentation states no key format anywhere we could
        # find on 2026-07-31, so this is labelled as what it is. It gates
        # nothing and only explains a warning, and the wording is kept exact so
        # that nobody later mistakes it for something read off a first-party
        # page.
        key_prefix_source="a convention reported outside the provider, not stated in perplexity's docs as of 2026-07-31",
        check_model="sonar",
    ),
    "anthropic": ProviderSpec(
        name="anthropic",
        env_var="ANTHROPIC_API_KEY",
        env_aliases=("LULU_ANTHROPIC_API_KEY",),
        key_page="https://console.anthropic.com/settings/keys",
        billing_page="https://console.anthropic.com/settings/billing",
        key_prefix="sk-ant-",
        # First-party, unlike the other row: Anthropic's own documentation
        # prints keys of this shape in its examples. A subscription to the
        # assistant is not one of these; the API is billed separately and
        # issues its own key, which is the step people miss.
        key_prefix_source="the shape Anthropic's own docs print, read 2026-08-01",
        # The cheapest model that can run the search tool, for the same reason
        # as the other row: a check call exists to prove the key spends.
        check_model="claude-haiku-4-5",
    ),
}


def spec_for(provider: str) -> ProviderSpec:
    try:
        return PROVIDERS[provider]
    except KeyError:
        known = ", ".join(sorted(PROVIDERS))
        raise ValueError(f"unknown provider {provider!r}; this build can call: {known}") from None


# -- never say the secret out loud ------------------------------------------

#: Shapes that are a key regardless of which of our fields it arrived in. Used
#: as a second net under exact-match redaction: a provider that echoes part of
#: a request back in an error body would otherwise put it in the ledger.
_KEYLIKE = re.compile(r"\b(?:pplx|sk|sk-ant|sk-proj)-[A-Za-z0-9_\-]{12,}")

REDACTED = "[redacted key]"


def redact(text: str, *secrets: str) -> str:
    """Remove exact secrets, then anything else shaped like a key.

    Applied to provider error text before it is printed or stored. The exact
    pass catches our own key; the pattern pass catches a key we do not hold,
    which happens when an answer quotes a page that leaked one.
    """
    for secret in secrets:
        if secret and len(secret) >= 8:
            text = text.replace(secret, REDACTED)
    return _KEYLIKE.sub(REDACTED, text)


def fingerprint(key: str) -> str:
    """A stable label for a key that reveals none of it.

    Enough to answer "is this the same key I put in the keychain last week" by
    comparing two lines of output, which is the only question a user needs to
    ask about a key they cannot see.
    """
    if not key:
        return "none"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]
    return f"sha256:{digest} ({counted(len(key), 'character')})"


# -- reading a .env file ----------------------------------------------------


def parse_env(text: str) -> dict[str, str]:
    """Parse the subset of dotenv syntax a key file actually uses.

    Two deliberate narrownesses. A value runs to the end of the line and an
    unquoted `#` is part of it, because a secret may legally contain one and
    silently truncating a key produces a 401 that looks like a billing problem.
    Trailing whitespace is stripped, because a value pasted with a newline is
    the most common way a correct key is rejected.
    """
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        name, sep, value = line.partition("=")
        if not sep:
            continue
        name = name.strip()
        if not name:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[name] = value.strip()
    return out


def env_file_candidates(cwd: Path, home: Path) -> tuple[Path, ...]:
    """The files read, in order, always as absolute paths.

    Two of them and no walk up the tree. A search that climbs directories finds
    a key whose location the user cannot predict, and a measurement run against
    an unexpected account is worse than one that refuses to start.
    """
    return (cwd / ".env", home / HOME_CONFIG_DIR / HOME_CONFIG_FILE)


# -- reading the OS keychain ------------------------------------------------

#: How long `security` is given to accept a key. Generous, because the command
#: can be sitting behind an authorisation dialog nobody is looking at, and
#: finite, because a dialog nobody answers is precisely the state the file
#: fallback exists for.
KEYCHAIN_WRITE_TIMEOUT_SECONDS = 30

#: Reading is not allowed to hold a command up for as long as writing, because
#: it happens on every lookup rather than once at setup.
KEYCHAIN_READ_TIMEOUT_SECONDS = 15


class KeychainRefused(RuntimeError):
    """The keychain did not take the key, for a reason worth printing.

    Every way `security` can decline arrives as this one type, because the
    decision behind all of them is the same: stop asking the keychain and store
    the key somewhere the caller can name. A timeout, a missing binary and a
    non-zero exit are three subprocess facts and one product fact.

    Nothing is swallowed on the way. The message carries the reason, redacted,
    and the original exception is kept as `__cause__`, so naming the condition
    costs no detail. It is a `RuntimeError` because it describes the state of
    the machine rather than a bad argument, which is what `ValueError` is left
    to mean here: a key this transport cannot carry at all.
    """


def keychain_supported(system: str | None = None) -> bool:
    """Whether this build has a keychain implementation for this platform.

    It answers that question and it is named for that question. It was called
    `keychain_available`, which reads like "a keychain is available to store a
    key in", and that reading is what broke `lulu setup`: the command branched
    on it, took the keychain arm because the platform was macOS, and had no way
    back to the file arm when the write then failed. The key was stored
    nowhere and the reader got a stack trace.

    The two questions cannot share a boolean, because the second one has no
    honest answer short of asking. A keychain can be locked, deleted, or have
    its authorisation dialog cancelled between any probe and the write that
    follows, so a probe that says yes is a statement about the past. And the
    only probe that would exercise the write path is a write, which would leave
    a test item in a stranger's keychain every time they ran a command.

    So the split is: this decides whether the keychain is worth attempting, and
    `keychain_write` raising `KeychainRefused` is the answer to whether it
    could actually be stored. A refusal is an ordinary outcome with a fallback
    behind it rather than a failure of the command.

    macOS for now. A Linux implementation lands with a Linux test rather than
    ahead of one, because an untested storage backend that silently fails to
    write is the worst possible outcome for a secret.
    """
    return (system or platform.system()) == "Darwin"


def _in_keychain(keychain: Path | str | None) -> list[str]:
    """The trailing keychain argument `security` takes, or nothing at all.

    Nothing means the machine's default keychain, which is what every caller in
    this package wants and what the user's other tools already read. A path is
    passed only by a caller that made a keychain of its own, so that exercising
    the real `security` binary does not mean writing into somebody's login
    keychain, which is what the round trip test used to do on every run.

    For the two calls that go through argv, where the list is the argument
    boundary and no quoting exists or is needed. `keychain_write` drives the
    interactive parser instead and has to quote the path itself.
    """
    return [] if keychain is None else [str(keychain)]


def keychain_read(service: str, account: str, keychain: Path | str | None = None) -> str | None:
    """Read one generic password, or None when there is no such item.

    A non-zero exit is not an error here: "not found" is the normal case on a
    first run and has to be reportable as a step in the trail rather than as a
    crash.
    """
    if not keychain_supported():
        return None
    try:
        done = subprocess.run(
            ["security", "find-generic-password", "-s", service, "-a", account, "-w"]
            + _in_keychain(keychain),
            capture_output=True,
            text=True,
            timeout=KEYCHAIN_READ_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    value = done.stdout.strip()
    return value or None


def keychain_write(
    service: str, account: str, key: str, keychain: Path | str | None = None
) -> None:
    """Store a key without ever putting it in a command line.

    `security` is driven through its interactive mode so the secret travels on
    stdin. Passed as an argument it would be visible in the process list to
    every other user on the machine for the lifetime of the call.

    `keychain` names the file to write into and defaults to the machine's
    default one. It is quoted, and only it: the interactive parser splits on
    whitespace, a home directory with a space in its name is ordinary, and a
    keychain path is the one argument here this package generates rather than
    fixes. The key stays unquoted because a quote character inside a key would
    then be the thing that broke it.

    Raises `KeychainRefused` for every way the keychain can decline, including
    the timeout, and `ValueError` for a key this transport cannot carry.
    """
    if not keychain_supported():
        raise KeychainRefused("this platform has no keychain that lulu knows how to write to")
    if "\n" in key or "\r" in key:
        raise ValueError("a key containing a newline cannot be stored this way")
    target = "" if keychain is None else f' "{keychain}"'
    command = f"add-generic-password -s {service} -a {account} -w {key} -U{target}\n"
    try:
        done = subprocess.run(
            ["security", "-i"],
            input=command,
            capture_output=True,
            text=True,
            timeout=KEYCHAIN_WRITE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as e:
        raise KeychainRefused(
            f"it did not answer within {counted(KEYCHAIN_WRITE_TIMEOUT_SECONDS, 'second')}, "
            "which is how a locked or missing default keychain looks from here"
        ) from e
    except OSError as e:
        raise KeychainRefused(f"the security command could not be run: {e.strerror}") from e
    if done.returncode != 0:
        reason = redact((done.stderr or done.stdout).strip(), key)
        raise KeychainRefused(reason or "it exited without saying why")


def keychain_delete(service: str, account: str, keychain: Path | str | None = None) -> bool:
    """Remove a stored key. Returns whether there was one to remove."""
    if not keychain_supported():
        return False
    done = subprocess.run(
        ["security", "delete-generic-password", "-s", service, "-a", account]
        + _in_keychain(keychain),
        capture_output=True,
        text=True,
        timeout=KEYCHAIN_READ_TIMEOUT_SECONDS,
    )
    return done.returncode == 0


# -- the walk ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Probe:
    """One place that was looked at, and what was there.

    `where` is written to be pasted into a shell or opened in an editor: an
    absolute path, or the exact service and account pair. A trail of vague
    descriptions is the same as no trail.
    """

    where: str
    found: bool
    note: str = ""

    def line(self) -> str:
        mark = "found" if self.found else "empty"
        tail = f", {self.note}" if self.note else ""
        return f"[{mark}] {self.where}{tail}"


@dataclass(frozen=True, slots=True)
class Resolution:
    """The outcome of the walk, with the key held where repr cannot reach it."""

    provider: str
    trail: tuple[Probe, ...]
    source: str = ""
    key: str = field(default="", repr=False)

    @property
    def ok(self) -> bool:
        return bool(self.key)

    def explain(self) -> list[str]:
        """The trail as printable lines. Contains no part of the key."""
        return [p.line() for p in self.trail]


def resolve(
    spec: ProviderSpec,
    *,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
    home: Path | None = None,
    keychain: Callable[[str, str], str | None] | None = None,
    system: str | None = None,
) -> Resolution:
    """Look for the key in a fixed order and record every step.

    Environment first, because a key exported for one command is meant to win
    over a stored one; the keychain next, because it is the storage the OS
    protects; the files last. Every argument is injectable so the order can be
    tested without touching the machine's real keychain.
    """
    env = os.environ if env is None else env
    cwd = Path.cwd() if cwd is None else cwd
    home = Path.home() if home is None else home
    keychain = keychain_read if keychain is None else keychain

    trail: list[Probe] = []

    for name in spec.env_names:
        value = (env.get(name) or "").strip()
        trail.append(Probe(where=f"environment variable {name}", found=bool(value)))
        if value:
            return Resolution(spec.name, tuple(trail), source=f"environment variable {name}", key=value)

    where_chain = f"OS keychain (service {KEYCHAIN_SERVICE}, account {spec.name})"
    if keychain_supported(system):
        stored = keychain(KEYCHAIN_SERVICE, spec.name)
        stored = (stored or "").strip()
        trail.append(Probe(where=where_chain, found=bool(stored)))
        if stored:
            return Resolution(spec.name, tuple(trail), source=where_chain, key=stored)
    else:
        trail.append(Probe(where=where_chain, found=False, note="not available on this platform"))

    for path in env_file_candidates(cwd, home):
        if not path.is_file():
            trail.append(Probe(where=str(path), found=False, note="no such file"))
            continue
        try:
            values = parse_env(path.read_text(encoding="utf-8"))
        except OSError as e:
            trail.append(Probe(where=str(path), found=False, note=f"unreadable: {e.strerror}"))
            continue
        for name in spec.env_names:
            value = (values.get(name) or "").strip()
            if value:
                where = f"{path} ({name})"
                trail.append(Probe(where=where, found=True))
                return Resolution(spec.name, tuple(trail), source=where, key=value)
        present = ", ".join(sorted(values)) or "nothing"
        trail.append(Probe(where=str(path), found=False, note=f"read, but holds {present}"))

    return Resolution(spec.name, tuple(trail))


# -- is this string even a key ----------------------------------------------


def inspect_key(spec: ProviderSpec, key: str) -> list[str]:
    """Everything wrong with a key that can be known without spending money.

    Returns human sentences, empty when nothing is suspect. These conditions
    all produce the same 401 from the provider, so naming them here is the
    difference between a two minute fix and an afternoon.
    """
    problems: list[str] = []
    if not key:
        return ["the key is empty"]
    if key != key.strip():
        problems.append("the key has whitespace around it; the paste probably included a newline")
    stripped = key.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in "\"'":
        problems.append("the key is wrapped in quotes; store the value without them")
    if any(c.isspace() for c in stripped):
        problems.append("the key contains a space, so part of a line was captured with it")
    if spec.key_prefix and not stripped.startswith(spec.key_prefix):
        problems.append(
            f"the key does not start with {spec.key_prefix!r}, which is what {spec.name} keys "
            f"look like ({spec.key_prefix_source}); it may belong to another provider"
        )
    if len(stripped) < 20:
        problems.append(
            f"the key is {counted(len(stripped), 'character')}, shorter than any key this "
            "provider issues"
        )
    return problems


# -- writing a key down -----------------------------------------------------


def write_env_file(path: Path, name: str, key: str) -> Path:
    """Set one variable in a key file, creating it 0600 and leaving the rest.

    Rewrites the matching line in place rather than appending, so a second run
    of the wizard does not leave two values for the same variable with the dead
    one shadowing the live one depending on the reader.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    replacement = f"{name}={key}"
    out: list[str] = []
    replaced = False
    for line in lines:
        head = line.strip()
        if head.startswith("export "):
            head = head[len("export ") :].lstrip()
        if head.partition("=")[0].strip() == name:
            if not replaced:
                out.append(replacement)
                replaced = True
            continue
        out.append(line)
    if not replaced:
        out.append(replacement)

    # Created at 0600 rather than corrected to it. `write_text` opens with the
    # process umask, which on a default machine is 0644, so the key existed
    # world readable for as long as the chmod took to run. That window is short
    # and it is not zero, and the file it applies to is the one thing in this
    # repository that must never be read by another account.
    #
    # `O_TRUNC` rather than `O_EXCL`, because rewriting a key file is the
    # documented behaviour of this function and refusing an existing one would
    # make the second run of the wizard fail. The mode argument only applies
    # when the file is created, so the chmod stays for the file that was
    # already there with the wrong one.
    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(handle, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    return path


#: What must not reach a repository, in the form git reads as "anywhere".
#:
#: A round is the customer's own record and the default write path is
#: `./ledger`, so a rule pinned to the root leaves every round collected from a
#: subdirectory unprotected. `ledger/` without the leading slash matches at any
#: depth, which is the difference between a rule and a rule that held on the
#: one day somebody ran the command from somewhere else.
KEPT_OUT = (".env", "ledger/")


def _covered(pattern: str, have: set[str]) -> bool:
    """Whether a rule already in the file makes this one redundant.

    Read the way git reads a pattern rather than the way it looks. A rule with
    no slash in it applies at every depth, so `.env*` covers `.env` wherever it
    is written. A rule with one does not: `/ledger/` is the root and nothing
    under it, and `ledger/*` is anchored to the file it is written in, so
    neither of them covers a round collected two directories down.

    An earlier version of this treated `/ledger/` as covering `ledger/`, which
    is how a repository ended up protecting exactly one of the places its own
    command writes to.
    """
    if pattern in have:
        return True
    return not pattern.endswith("/") and f"{pattern}*" in have


def ensure_gitignored(repo_root: Path, patterns: Sequence[str] = KEPT_OUT) -> list[str]:
    """Make sure a key file or a collected round cannot be committed.

    Returns what was added. Nothing is added when an existing rule already
    covers it; the check is textual and deliberately conservative, since the
    cost of a redundant line is a duplicate and the cost of a missed one is a
    key on GitHub, or somebody else's measured round.
    """
    gitignore = repo_root / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.is_file() else ""
    have = {line.strip() for line in existing.splitlines()}
    added = [p for p in patterns if not _covered(p, have)]
    if not added:
        return []
    block = "" if existing.endswith("\n") or not existing else "\n"
    block += "\n# keys and collected rounds never enter the repo\n" + "\n".join(added) + "\n"
    gitignore.write_text(existing + block, encoding="utf-8")
    return added
