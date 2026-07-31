"""The key path has to be inspectable, and the key itself must never surface."""

from __future__ import annotations

import stat
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from lulumelon.keys import (
    KEYCHAIN_SERVICE,
    REDACTED,
    Resolution,
    ensure_gitignored,
    env_file_candidates,
    fingerprint,
    inspect_key,
    keychain_available,
    keychain_delete,
    keychain_read,
    keychain_write,
    parse_env,
    redact,
    resolve,
    spec_for,
    write_env_file,
)

PPLX = spec_for("perplexity")
KEY = "pplx-" + "a1b2c3d4e5" * 4


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
        f"[empty] OS keychain (service {KEYCHAIN_SERVICE}, account perplexity) — not available on this platform"
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


@pytest.mark.skipif(not keychain_available(), reason="no OS keychain on this platform")
def test_a_key_survives_a_round_trip_through_the_real_keychain():
    """The storage backend is exercised for real, under its own service name.

    Mocking this would test the mock. A key written but not readable is the one
    failure mode that makes the whole setup path silently useless, and it can
    only be seen by talking to the actual keychain.
    """
    service = "lulumelon-pytest"
    account = "roundtrip"
    try:
        keychain_write(service, account, KEY)
        assert keychain_read(service, account) == KEY
        keychain_write(service, account, KEY + "-second")
        assert keychain_read(service, account) == KEY + "-second"
    finally:
        keychain_delete(service, account)
    assert keychain_read(service, account) is None


@pytest.mark.skipif(not keychain_available(), reason="no OS keychain on this platform")
def test_the_keychain_write_does_not_put_the_key_on_a_command_line():
    """Read the argv the helper would use, and prove the secret is not in it.

    Anything passed as an argument is visible in `ps` to every other user on
    the machine while the call runs.
    """
    seen: list[list[str]] = []

    def spy(args, **kwargs):
        seen.append(list(args))
        assert KEY in kwargs.get("input", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    with mock.patch.object(subprocess, "run", spy):
        keychain_write("lulumelon-pytest", "argv", KEY)

    assert seen == [["security", "-i"]]


def test_a_key_file_in_a_repository_gets_ignored(tmp_path: Path):
    assert ensure_gitignored(tmp_path) == [".env"]
    assert ".env" in (tmp_path / ".gitignore").read_text(encoding="utf-8")


def test_an_existing_rule_is_not_duplicated(tmp_path: Path):
    (tmp_path / ".gitignore").write_text("node_modules\n.env*\n", encoding="utf-8")
    assert ensure_gitignored(tmp_path) == []
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8").count(".env") == 1
