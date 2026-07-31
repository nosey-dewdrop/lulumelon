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
    return f"sha256:{digest} ({len(key)} characters)"


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


def keychain_available(system: str | None = None) -> bool:
    """True only where the read and write paths below are actually exercised.

    macOS for now. A Linux implementation lands with a Linux test rather than
    ahead of one, because an untested storage backend that silently fails to
    write is the worst possible outcome for a secret.
    """
    return (system or platform.system()) == "Darwin"


def keychain_read(service: str, account: str) -> str | None:
    """Read one generic password, or None when there is no such item.

    A non-zero exit is not an error here: "not found" is the normal case on a
    first run and has to be reportable as a step in the trail rather than as a
    crash.
    """
    if not keychain_available():
        return None
    try:
        done = subprocess.run(
            ["security", "find-generic-password", "-s", service, "-a", account, "-w"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    value = done.stdout.strip()
    return value or None


def keychain_write(service: str, account: str, key: str) -> None:
    """Store a key without ever putting it in a command line.

    `security` is driven through its interactive mode so the secret travels on
    stdin. Passed as an argument it would be visible in the process list to
    every other user on the machine for the lifetime of the call.
    """
    if not keychain_available():
        raise RuntimeError("no OS keychain on this platform; use the file option instead")
    if "\n" in key or "\r" in key:
        raise ValueError("a key containing a newline cannot be stored this way")
    command = f"add-generic-password -s {service} -a {account} -w {key} -U\n"
    done = subprocess.run(
        ["security", "-i"],
        input=command,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if done.returncode != 0:
        raise RuntimeError(redact((done.stderr or done.stdout).strip(), key) or "keychain write failed")


def keychain_delete(service: str, account: str) -> bool:
    """Remove a stored key. Returns whether there was one to remove."""
    if not keychain_available():
        return False
    done = subprocess.run(
        ["security", "delete-generic-password", "-s", service, "-a", account],
        capture_output=True,
        text=True,
        timeout=15,
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
        tail = f" — {self.note}" if self.note else ""
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
    if keychain_available(system):
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
        problems.append(f"the key is {len(stripped)} characters, shorter than any key this provider issues")
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
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    return path


def ensure_gitignored(repo_root: Path, patterns: Sequence[str] = (".env",)) -> list[str]:
    """Make sure a key file written into a repository cannot be committed.

    Returns what was added. Nothing is added when an existing rule already
    covers it; the check is textual and deliberately conservative, since the
    cost of a redundant line is a duplicate and the cost of a missed one is a
    key on GitHub.
    """
    gitignore = repo_root / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.is_file() else ""
    have = {line.strip() for line in existing.splitlines()}
    added = [p for p in patterns if p not in have and f"{p}*" not in have and f"/{p}" not in have]
    if not added:
        return []
    block = "" if existing.endswith("\n") or not existing else "\n"
    block += "\n# api keys never enter the repo\n" + "\n".join(added) + "\n"
    gitignore.write_text(existing + block, encoding="utf-8")
    return added
