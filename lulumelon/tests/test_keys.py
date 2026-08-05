"""The key path has to be inspectable, and the key itself must never surface."""

from __future__ import annotations

import contextlib
import secrets
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from lulumelon.keys import (
    KEYCHAIN_SERVICE,
    KEYCHAIN_WRITE_TIMEOUT_SECONDS,
    REDACTED,
    KeychainRefused,
    Resolution,
    ensure_gitignored,
    env_file_candidates,
    fingerprint,
    inspect_key,
    keychain_delete,
    keychain_read,
    keychain_supported,
    keychain_write,
    parse_env,
    redact,
    resolve,
    spec_for,
    write_env_file,
)

PPLX = spec_for("perplexity")
KEY = "pplx-" + "a1b2c3d4e5" * 4

#: What the round trip files its fake key under. Named so that a stray item
#: left on a machine can be found and removed by hand, and so the acceptance
#: check for "the user's own keychain is clean" has one string to look for.
PYTEST_SERVICE = "lulumelon-pytest"
PYTEST_ACCOUNT = "roundtrip"


def no_keychain(service: str, account: str) -> str | None:
    return None


def stocked_keychain(value: str):
    def read(service: str, account: str) -> str | None:
        assert service == KEYCHAIN_SERVICE
        assert account == "perplexity"
        return value

    return read


def test_unknown_provider_names_the_ones_that_work():
    with pytest.raises(ValueError, match="perplexity"):
        spec_for("gemini")


# -- order ------------------------------------------------------------------


def test_environment_wins_over_everything_else(tmp_path: Path):
    (tmp_path / ".env").write_text("PERPLEXITY_API_KEY=pplx-from-the-file\n", encoding="utf-8")
    got = resolve(
        PPLX,
        env={"PERPLEXITY_API_KEY": KEY},
        cwd=tmp_path,
        home=tmp_path / "home",
        keychain=stocked_keychain("pplx-from-the-keychain"),
        system="Darwin",
    )
    assert got.key == KEY
    assert got.source == "environment variable PERPLEXITY_API_KEY"


def test_keychain_wins_over_the_files(tmp_path: Path):
    (tmp_path / ".env").write_text("PERPLEXITY_API_KEY=pplx-from-the-file\n", encoding="utf-8")
    got = resolve(
        PPLX,
        env={},
        cwd=tmp_path,
        home=tmp_path / "home",
        keychain=stocked_keychain(KEY),
        system="Darwin",
    )
    assert got.key == KEY
    assert got.source.startswith("OS keychain")


def test_working_directory_file_wins_over_the_home_file(tmp_path: Path):
    home = tmp_path / "home"
    (home / ".lulu").mkdir(parents=True)
    (home / ".lulu" / "env").write_text("PERPLEXITY_API_KEY=pplx-from-home\n", encoding="utf-8")
    (tmp_path / ".env").write_text(f"PERPLEXITY_API_KEY={KEY}\n", encoding="utf-8")
    got = resolve(PPLX, env={}, cwd=tmp_path, home=home, keychain=no_keychain, system="Darwin")
    assert got.key == KEY
    assert got.source == f"{tmp_path / '.env'} (PERPLEXITY_API_KEY)"


def test_the_home_file_is_read_when_the_local_one_is_absent(tmp_path: Path):
    home = tmp_path / "home"
    (home / ".lulu").mkdir(parents=True)
    (home / ".lulu" / "env").write_text(f"PERPLEXITY_API_KEY={KEY}\n", encoding="utf-8")
    got = resolve(PPLX, env={}, cwd=tmp_path, home=home, keychain=no_keychain, system="Darwin")
    assert got.key == KEY


def test_the_alias_variable_is_accepted(tmp_path: Path):
    got = resolve(
        PPLX,
        env={"LULU_PERPLEXITY_API_KEY": KEY},
        cwd=tmp_path,
        home=tmp_path,
        keychain=no_keychain,
        system="Darwin",
    )
    assert got.key == KEY
    assert "LULU_PERPLEXITY_API_KEY" in got.source


def test_a_pasted_newline_does_not_travel_with_the_key(tmp_path: Path):
    got = resolve(
        PPLX,
        env={"PERPLEXITY_API_KEY": f"  {KEY}\n"},
        cwd=tmp_path,
        home=tmp_path,
        keychain=no_keychain,
        system="Darwin",
    )
    assert got.key == KEY


# -- the trail --------------------------------------------------------------


def test_failure_names_every_place_that_was_looked_at(tmp_path: Path):
    home = tmp_path / "home"
    got = resolve(PPLX, env={}, cwd=tmp_path, home=home, keychain=no_keychain, system="Darwin")
    assert not got.ok
    lines = got.explain()
    assert len(lines) == len(PPLX.env_names) + 1 + len(env_file_candidates(tmp_path, home))
    joined = "\n".join(lines)
    for name in PPLX.env_names:
        assert name in joined
    assert KEYCHAIN_SERVICE in joined
    for path in env_file_candidates(tmp_path, home):
        assert str(path) in joined
    assert all(line.startswith("[empty]") for line in lines)


def test_the_trail_uses_absolute_paths(tmp_path: Path):
    got = resolve(PPLX, env={}, cwd=tmp_path, home=tmp_path, keychain=no_keychain, system="Darwin")
    for path in env_file_candidates(tmp_path, tmp_path):
        assert path.is_absolute()
        assert str(path) in "\n".join(got.explain())


def test_a_file_that_holds_other_variables_says_what_it_holds(tmp_path: Path):
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-something\n", encoding="utf-8")
    got = resolve(PPLX, env={}, cwd=tmp_path, home=tmp_path / "h", keychain=no_keychain, system="Darwin")
    trail = "\n".join(got.explain())
    assert "holds OPENAI_API_KEY" in trail


def test_a_platform_without_a_keychain_says_so_instead_of_skipping(tmp_path: Path):
    got = resolve(PPLX, env={}, cwd=tmp_path, home=tmp_path, keychain=no_keychain, system="Linux")
    keychain_lines = [line for line in got.explain() if KEYCHAIN_SERVICE in line]
    assert keychain_lines == [
        f"[empty] OS keychain (service {KEYCHAIN_SERVICE}, account perplexity), not available on this platform"
    ]


# -- the key never surfaces -------------------------------------------------


def test_the_resolution_does_not_print_the_key():
    got = Resolution("perplexity", (), source="test", key=KEY)
    assert KEY not in repr(got)
    assert KEY not in str(got)


def test_the_trail_does_not_print_the_key(tmp_path: Path):
    (tmp_path / ".env").write_text(f"PERPLEXITY_API_KEY={KEY}\n", encoding="utf-8")
    got = resolve(PPLX, env={}, cwd=tmp_path, home=tmp_path / "h", keychain=no_keychain, system="Darwin")
    assert got.ok
    assert KEY not in "\n".join(got.explain())
    assert KEY not in repr(got)


def test_fingerprint_identifies_a_key_without_showing_it():
    label = fingerprint(KEY)
    assert KEY not in label
    assert str(len(KEY)) in label
    assert label == fingerprint(KEY)
    assert label != fingerprint(KEY + "x")
    assert fingerprint("") == "none"


def test_redaction_removes_the_exact_secret():
    text = f"http 401: bad key {KEY} for account"
    assert KEY not in redact(text, KEY)
    assert REDACTED in redact(text, KEY)


def test_redaction_removes_a_key_we_do_not_hold():
    text = "the page listed sk-ant-api03-QQQQQQQQQQQQQQQQ and moved on"
    out = redact(text)
    assert "sk-ant-api03-QQQQQQQQQQQQQQQQ" not in out
    assert REDACTED in out


def test_redaction_leaves_ordinary_text_alone():
    text = "http 429: too many requests, retry after 12s"
    assert redact(text, "") == text
    assert redact(text, "short") == text


# -- what is wrong with this string -----------------------------------------


def test_a_good_key_has_nothing_wrong_with_it():
    assert inspect_key(PPLX, KEY) == []


def test_the_empty_key_is_reported_once():
    assert inspect_key(PPLX, "") == ["the key is empty"]


def test_quotes_and_spaces_and_the_wrong_provider_are_each_named():
    quoted = inspect_key(PPLX, f'"{KEY}"')
    assert any("quotes" in p for p in quoted)

    spaced = inspect_key(PPLX, f"{KEY} extra")
    assert any("space" in p for p in spaced)

    foreign = inspect_key(PPLX, "sk-" + "z" * 40)
    assert any("pplx-" in p for p in foreign)

    short = inspect_key(PPLX, "pplx-abc")
    assert any("shorter" in p for p in short)


def test_trailing_whitespace_is_named_rather_than_silently_accepted():
    problems = inspect_key(PPLX, KEY + "\n")
    assert any("whitespace" in p for p in problems)


# -- parsing ----------------------------------------------------------------


def test_parse_env_handles_export_quotes_and_blank_lines():
    text = """
# a comment
export PERPLEXITY_API_KEY="pplx-quoted"
EMPTY=
OTHER = spaced
not a variable line
"""
    got = parse_env(text)
    assert got["PERPLEXITY_API_KEY"] == "pplx-quoted"
    assert got["EMPTY"] == ""
    assert got["OTHER"] == "spaced"
    assert "not a variable line" not in got


def test_parse_env_keeps_a_hash_inside_a_value():
    assert parse_env("K=pplx-aa#bb")["K"] == "pplx-aa#bb"


def test_parse_env_strips_a_trailing_newline_from_a_paste():
    assert parse_env("K=pplx-value   \n")["K"] == "pplx-value"


# -- writing ----------------------------------------------------------------


def test_write_env_file_creates_it_readable_only_by_its_owner(tmp_path: Path):
    path = write_env_file(tmp_path / "sub" / ".env", "PERPLEXITY_API_KEY", KEY)
    assert path.is_file()
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600
    assert parse_env(path.read_text(encoding="utf-8"))["PERPLEXITY_API_KEY"] == KEY


def test_writing_twice_leaves_one_value_not_two(tmp_path: Path):
    path = tmp_path / ".env"
    write_env_file(path, "PERPLEXITY_API_KEY", "pplx-old")
    write_env_file(path, "PERPLEXITY_API_KEY", KEY)
    body = path.read_text(encoding="utf-8")
    assert body.count("PERPLEXITY_API_KEY") == 1
    assert parse_env(body)["PERPLEXITY_API_KEY"] == KEY


def test_writing_keeps_the_other_lines(tmp_path: Path):
    path = tmp_path / ".env"
    path.write_text("# mine\nOTHER=1\nexport PERPLEXITY_API_KEY=pplx-old\n", encoding="utf-8")
    write_env_file(path, "PERPLEXITY_API_KEY", KEY)
    body = path.read_text(encoding="utf-8")
    assert "# mine" in body
    assert parse_env(body) == {"OTHER": "1", "PERPLEXITY_API_KEY": KEY}


# -- the real keychain ------------------------------------------------------


def _security(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["security", *args], capture_output=True, text=True, timeout=30)


@contextlib.contextmanager
def temporary_keychain():
    """A keychain of this suite's own, made and destroyed around one test.

    It exists so the round trip below can drive the real `security` binary
    without writing into the keychain the person running the suite keeps their
    own passwords in. That is not hypothetical. Every `pytest` run on this
    repository put an item in the runner's login keychain, and on a machine
    with no default keychain it put an authorisation dialog on their screen and
    then failed.

    Three properties, each of them a way this could otherwise still change a
    machine that only ran the tests.

    **It never becomes the default and never joins the search list.** Neither
    `security default-keychain -s` nor `security list-keychains -s` is called
    here, and neither may be added: a crash between setting one and restoring
    it would leave a stranger's Mac pointed at a keychain this suite then
    deletes. A keychain named as an argument needs no such registration, which
    is what makes the honest version of this also the simple one.

    **It is removed whatever the test does**, from a `finally`, along with the
    directory holding it.

    **If it cannot be made, the test skips and says so.** There is no fallback
    to the default keychain, because a round trip that quietly ran against the
    real one is the exact failure this helper was written to remove.
    """
    if not keychain_supported():
        pytest.skip("no OS keychain on this platform")
    directory = Path(tempfile.mkdtemp(prefix="lulumelon-keychain-"))
    path = directory / "lulumelon-pytest.keychain"
    # Not protecting anything: this keychain holds one fake key for the length
    # of one test and is deleted with the file. It is random rather than fixed
    # only so that no real keychain anywhere shares a password with a literal
    # committed to a public repository.
    password = secrets.token_hex(16)
    try:
        made = _security("create-keychain", "-p", password, str(path))
    except (OSError, subprocess.SubprocessError) as e:
        shutil.rmtree(directory, ignore_errors=True)
        pytest.skip(f"a temporary keychain could not be created: {e}")
    if made.returncode != 0:
        shutil.rmtree(directory, ignore_errors=True)
        pytest.skip(
            "a temporary keychain could not be created, so this test will not fall back on "
            f"the real one: {(made.stderr or made.stdout).strip()}"
        )
    try:
        yield path
    finally:
        _security("delete-keychain", str(path))
        shutil.rmtree(directory, ignore_errors=True)


def test_a_key_survives_a_round_trip_through_the_real_keychain():
    """The storage backend is exercised for real, in a keychain of its own.

    Mocking this would test the mock. A key written but not readable is the one
    failure mode that makes the whole setup path silently useless, and it can
    only be seen by talking to the actual keychain.

    What changed is which keychain. It used to write into whichever one the
    machine calls default, which on anybody's Mac is the login keychain holding
    their own passwords, so running the suite modified the machine that ran it.
    `security` takes a keychain file as an argument, so the storage functions
    take one too and this test brings its own.
    """
    with temporary_keychain() as keychain:
        keychain_write(PYTEST_SERVICE, PYTEST_ACCOUNT, KEY, keychain)
        assert keychain_read(PYTEST_SERVICE, PYTEST_ACCOUNT, keychain) == KEY

        keychain_write(PYTEST_SERVICE, PYTEST_ACCOUNT, KEY + "-second", keychain)
        assert keychain_read(PYTEST_SERVICE, PYTEST_ACCOUNT, keychain) == KEY + "-second"

        assert keychain_delete(PYTEST_SERVICE, PYTEST_ACCOUNT, keychain)
        assert keychain_read(PYTEST_SERVICE, PYTEST_ACCOUNT, keychain) is None


def test_the_round_trip_leaves_the_default_keychain_untouched():
    """The property without which the round trip above is not worth running.

    Written to the temporary keychain, then read back with no keychain named,
    which is the default one. Finding nothing is the assertion that the old
    version of this file could never have made.
    """
    with temporary_keychain() as keychain:
        keychain_write(PYTEST_SERVICE, PYTEST_ACCOUNT, KEY, keychain)
        assert keychain_read(PYTEST_SERVICE, PYTEST_ACCOUNT) is None, (
            f"an item for service {PYTEST_SERVICE} is in the default keychain. An older "
            "version of this suite put it there. Remove it with: security "
            f"delete-generic-password -s {PYTEST_SERVICE} -a {PYTEST_ACCOUNT}"
        )


def test_the_temporary_keychain_is_never_made_the_default_one():
    """Not even for the length of the test, because a crash does not restore.

    Read back from `security` itself rather than from a promise in a comment,
    since the damage this prevents lands on a machine that merely ran the
    tests once.
    """
    if not keychain_supported():
        pytest.skip("no OS keychain on this platform")
    before = _security("default-keychain").stdout
    with temporary_keychain() as keychain:
        assert _security("default-keychain").stdout == before
        assert str(keychain) not in _security("list-keychains").stdout
    assert _security("default-keychain").stdout == before


def test_the_temporary_keychain_is_removed_even_when_the_test_using_it_fails():
    """Cleanup on the failing path, which is the path that leaves debris."""

    class Failed(RuntimeError):
        pass

    made: list[Path] = []
    with pytest.raises(Failed):
        with temporary_keychain() as keychain:
            made.append(keychain)
            keychain_write(PYTEST_SERVICE, PYTEST_ACCOUNT, KEY, keychain)
            raise Failed("as a test would")

    assert made, "the helper skipped rather than yielding, so nothing was proved"
    assert not made[0].exists()
    assert not made[0].parent.exists()


def test_the_keychain_write_does_not_put_the_key_on_a_command_line(monkeypatch):
    """Read the argv the helper would use, and prove the secret is not in it.

    Anything passed as an argument is visible in `ps` to every other user on
    the machine while the call runs. The keychain file is not a secret and is
    quoted onto the interactive line, where nothing outside this process can
    read it.

    The platform is held open the way the neighbouring tests hold it, because
    the argv being read here is the argv this package builds anywhere. Without
    that line the write refuses before the spy sees anything, and the claim
    about where a secret travels is only ever checked on one operating system.
    """
    monkeypatch.setattr("lulumelon.keys.keychain_supported", lambda *a: True)
    seen: list[list[str]] = []

    def spy(args, **kwargs):
        seen.append(list(args))
        assert KEY in kwargs.get("input", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    with mock.patch.object(subprocess, "run", spy):
        keychain_write(PYTEST_SERVICE, "argv", KEY)
        keychain_write(PYTEST_SERVICE, "argv", KEY, "/tmp/a keychain with spaces.keychain")

    assert seen == [["security", "-i"], ["security", "-i"]]


def test_a_named_keychain_reaches_security_quoted_and_the_default_one_is_unnamed(monkeypatch):
    """A home directory with a space in it is ordinary, and would split.

    The interactive parser tokenises on whitespace, so the one argument this
    package generates rather than fixes is the one that gets quotes.
    """
    monkeypatch.setattr("lulumelon.keys.keychain_supported", lambda *a: True)
    written: list[str] = []

    def spy(args, **kwargs):
        written.append(kwargs.get("input", ""))
        return subprocess.CompletedProcess(args, 0, "", "")

    with mock.patch.object(subprocess, "run", spy):
        keychain_write(PYTEST_SERVICE, "quoting", KEY)
        keychain_write(PYTEST_SERVICE, "quoting", KEY, "/Users/a b/c.keychain")

    assert written[0].rstrip("\n").endswith("-U")
    assert written[1].rstrip("\n").endswith('-U "/Users/a b/c.keychain"')


# -- a keychain that will not take it ---------------------------------------


def test_a_keychain_that_never_answers_is_a_refusal_and_not_a_raw_timeout(monkeypatch):
    """The thirty seconds of silence that ended in a stack trace.

    `security -i` sat behind an authorisation dialog and `TimeoutExpired` came
    out of here. It is a `SubprocessError`, not a `RuntimeError`, so callers
    catching the documented pair missed it entirely and printed a traceback to
    somebody who was trying to store a key. Naming it keeps the cause.
    """
    monkeypatch.setattr("lulumelon.keys.keychain_supported", lambda *a: True)

    def hangs(args, **kwargs):
        raise subprocess.TimeoutExpired(list(args), kwargs["timeout"])

    with mock.patch.object(subprocess, "run", hangs):
        with pytest.raises(KeychainRefused) as raised:
            keychain_write(PYTEST_SERVICE, "timeout", KEY)

    assert isinstance(raised.value, RuntimeError), "the type callers already catch"
    assert isinstance(raised.value.__cause__, subprocess.TimeoutExpired), "the cause is kept"
    assert str(KEYCHAIN_WRITE_TIMEOUT_SECONDS) in str(raised.value)
    assert KEY not in str(raised.value)


def test_a_keychain_that_says_no_repeats_its_reason_without_the_key(monkeypatch):
    """The words `security` used, which name the state, minus the secret."""
    monkeypatch.setattr("lulumelon.keys.keychain_supported", lambda *a: True)
    said = f"security: no keychain could be found to store the item, while sending {KEY}"

    def refuses(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, "", said)

    with mock.patch.object(subprocess, "run", refuses):
        with pytest.raises(KeychainRefused) as raised:
            keychain_write(PYTEST_SERVICE, "refused", KEY)

    assert "no keychain could be found" in str(raised.value)
    assert KEY not in str(raised.value)
    assert REDACTED in str(raised.value)


def test_a_security_binary_that_is_not_there_is_also_a_refusal(monkeypatch):
    """A Mac is not a guarantee that the tool is on the path."""
    monkeypatch.setattr("lulumelon.keys.keychain_supported", lambda *a: True)

    def missing(args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory")

    with mock.patch.object(subprocess, "run", missing):
        with pytest.raises(KeychainRefused, match="could not be run"):
            keychain_write(PYTEST_SERVICE, "missing", KEY)


def test_a_platform_with_no_keychain_refuses_before_running_anything(monkeypatch):
    """No subprocess at all, so a Linux box cannot be told to shell out."""
    monkeypatch.setattr("lulumelon.keys.keychain_supported", lambda *a: False)

    def never(args, **kwargs):
        raise AssertionError("security was run on a platform with no keychain")

    with mock.patch.object(subprocess, "run", never):
        with pytest.raises(KeychainRefused, match="no keychain"):
            keychain_write(PYTEST_SERVICE, "linux", KEY)
        assert keychain_read(PYTEST_SERVICE, "linux") is None
        assert keychain_delete(PYTEST_SERVICE, "linux") is False


def test_a_key_with_a_newline_is_a_bad_argument_rather_than_a_refusal(monkeypatch):
    """The one failure with no fallback behind it, so it keeps its own type.

    A refusal means try somewhere else. This means the string itself cannot be
    stored, and the file path could not hold it either, so `setup` has to stop
    rather than fall through.
    """
    monkeypatch.setattr("lulumelon.keys.keychain_supported", lambda *a: True)
    with pytest.raises(ValueError, match="newline"):
        keychain_write(PYTEST_SERVICE, "newline", KEY + "\ninjected")


def test_the_key_file_is_created_at_0600_rather_than_corrected_to_it(tmp_path: Path):
    """A window with a key in it is a window, however short.

    `write_text` opens with the process umask, which on a default machine is
    0644, so the file existed world readable until the chmod on the next line
    ran. The mode travels with the creation now, and the chmod stays for a file
    that was already there with the wrong one.
    """
    source = (Path(__file__).resolve().parents[1] / "keys.py").read_text(encoding="utf-8")
    body = source.split("def write_env_file")[1].split("\ndef ")[0]
    assert "os.open(" in body and "S_IRUSR | stat.S_IWUSR)" in body
    assert "path.write_text(" not in body, "the umask decides the mode of anything written that way"

    written = write_env_file(tmp_path / ".env", "ANTHROPIC_API_KEY", KEY)
    assert stat.S_IMODE(written.stat().st_mode) == 0o600
    assert written.read_text(encoding="utf-8") == f"ANTHROPIC_API_KEY={KEY}\n"


def test_a_key_file_that_was_already_wide_open_is_closed(tmp_path: Path):
    path = tmp_path / ".env"
    path.write_text("OTHER=1\n", encoding="utf-8")
    path.chmod(0o644)

    write_env_file(path, "ANTHROPIC_API_KEY", KEY)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert "OTHER=1" in path.read_text(encoding="utf-8"), "the rest of the file is left alone"


def test_a_key_file_in_a_repository_gets_ignored(tmp_path: Path):
    assert ensure_gitignored(tmp_path) == [".env", "ledger/"]
    written = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in written


def test_a_round_collected_anywhere_in_a_repository_gets_ignored(tmp_path: Path):
    """A round is the customer's own record, and it is not always at the root.

    The rule this repository carried was `/ledger/`, which is the root and
    nothing else, so a round collected from a subdirectory was one `git add -A`
    away from being published by whoever ran it.
    """
    (tmp_path / ".gitignore").write_text("node_modules\n.env*\n/ledger/\n", encoding="utf-8")

    assert ensure_gitignored(tmp_path) == ["ledger/"]
    written = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert "\nledger/\n" in written, "at any depth, beside the rule for the root"


def test_an_existing_rule_is_not_duplicated(tmp_path: Path):
    (tmp_path / ".gitignore").write_text("node_modules\n.env*\nledger/\n", encoding="utf-8")
    assert ensure_gitignored(tmp_path) == []
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8").count(".env") == 1
