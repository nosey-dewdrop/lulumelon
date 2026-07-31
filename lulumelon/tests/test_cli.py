"""The setup path is a feature: every branch of it is driven here, without a key."""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from lulumelon import cli
from lulumelon.cli import Console, doctor, init
from lulumelon.keys import parse_env, spec_for

KEY = "pplx-" + "a1b2c3d4e5" * 4
PPLX = spec_for("perplexity")


class Recorder:
    """A console whose whole output is one searchable string."""

    def __init__(self) -> None:
        self.out = io.StringIO()
        self.err = io.StringIO()
        self.console = Console(out=self.out, err=self.err)

    @property
    def text(self) -> str:
        return self.out.getvalue() + self.err.getvalue()


def scripted(*answers: str):
    """Feed prepared answers to the wizard, and fail if it asks one too many."""
    queue = list(answers)

    def ask(prompt: str) -> str:
        assert queue, f"the wizard asked something unscripted: {prompt!r}"
        return queue.pop(0)

    return ask


def no_keychain(monkeypatch):
    monkeypatch.setattr(cli, "keychain_available", lambda *a: False)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def answering(payload: dict):
    def urlopen(req, timeout=None):
        return FakeResponse(json.dumps(payload).encode("utf-8"))

    return urlopen


def http_error(code: int, body: str):
    def urlopen(req, timeout=None):
        raise urllib.error.HTTPError(
            "https://api.perplexity.ai", code, "err", {}, io.BytesIO(body.encode("utf-8"))
        )

    return urlopen


# -- init -------------------------------------------------------------------


def test_init_writes_the_key_to_the_local_file_and_says_where(tmp_path: Path, monkeypatch):
    no_keychain(monkeypatch)
    rec = Recorder()
    code = init(
        rec.console,
        ask=scripted("1"),
        secret=lambda prompt: KEY,
        cwd=tmp_path,
        home=tmp_path / "home",
    )
    assert code == 0
    written = tmp_path / ".env"
    assert parse_env(written.read_text(encoding="utf-8"))["PERPLEXITY_API_KEY"] == KEY
    assert str(written) in rec.text


def test_init_never_shows_the_key_it_just_stored(tmp_path: Path, monkeypatch):
    no_keychain(monkeypatch)
    rec = Recorder()
    init(rec.console, ask=scripted("1"), secret=lambda p: KEY, cwd=tmp_path, home=tmp_path / "h")
    assert KEY not in rec.text
    assert "sha256:" in rec.text


def test_init_tells_the_user_where_to_get_a_key_before_asking_for_one(tmp_path: Path, monkeypatch):
    no_keychain(monkeypatch)
    rec = Recorder()
    init(rec.console, ask=scripted("1"), secret=lambda p: KEY, cwd=tmp_path, home=tmp_path / "h")
    text = rec.text
    assert PPLX.key_page in text
    assert text.index(PPLX.key_page) < text.index("Stored in")
    assert "API Keys tab" in text


def test_init_protects_a_key_written_into_a_repository(tmp_path: Path, monkeypatch):
    no_keychain(monkeypatch)
    rec = Recorder()
    init(rec.console, ask=scripted("1"), secret=lambda p: KEY, cwd=tmp_path, home=tmp_path / "h")
    assert ".env" in (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert ".gitignore" in rec.text


def test_init_can_put_the_key_somewhere_every_directory_can_read(tmp_path: Path, monkeypatch):
    no_keychain(monkeypatch)
    home = tmp_path / "home"
    rec = Recorder()
    init(rec.console, ask=scripted("2"), secret=lambda p: KEY, cwd=tmp_path, home=home)
    stored = home / ".lulu" / "env"
    assert parse_env(stored.read_text(encoding="utf-8"))["PERPLEXITY_API_KEY"] == KEY


def test_init_stores_nothing_when_no_key_is_pasted(tmp_path: Path, monkeypatch):
    no_keychain(monkeypatch)
    rec = Recorder()
    assert init(rec.console, ask=scripted(), secret=lambda p: "  ", cwd=tmp_path, home=tmp_path) == 1
    assert not (tmp_path / ".env").exists()
    assert "nothing was stored" in rec.text.lower()


def test_init_questions_a_suspect_key_and_obeys_the_answer(tmp_path: Path, monkeypatch):
    no_keychain(monkeypatch)
    rec = Recorder()
    code = init(rec.console, ask=scripted("n"), secret=lambda p: "sk-" + "z" * 40, cwd=tmp_path, home=tmp_path)
    assert code == 1
    assert "pplx-" in rec.text
    assert not (tmp_path / ".env").exists()

    rec = Recorder()
    code = init(rec.console, ask=scripted("y", "1"), secret=lambda p: "sk-" + "z" * 40, cwd=tmp_path, home=tmp_path)
    assert code == 0
    assert (tmp_path / ".env").is_file()


def test_init_refuses_a_choice_that_is_not_on_the_menu(tmp_path: Path, monkeypatch):
    no_keychain(monkeypatch)
    rec = Recorder()
    assert init(rec.console, ask=scripted("9"), secret=lambda p: KEY, cwd=tmp_path, home=tmp_path) == 1
    assert not (tmp_path / ".env").exists()


def test_the_keychain_option_is_offered_only_where_it_works(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cli, "keychain_available", lambda *a: True)
    assert cli.storage_menu(tmp_path, tmp_path)[0][0] == "keychain"
    monkeypatch.setattr(cli, "keychain_available", lambda *a: False)
    assert [kind for kind, _ in cli.storage_menu(tmp_path, tmp_path)] == ["local", "home"]


# -- doctor -----------------------------------------------------------------


def run_doctor(rec: Recorder, tmp_path: Path, **kw) -> int:
    """Always with the machine's own environment and keychain pinned out."""
    kw.setdefault("home", tmp_path / "h")
    return doctor(rec.console, cwd=tmp_path, env={}, keychain=lambda s, a: None, **kw)


def test_doctor_lists_every_place_it_looked_when_it_finds_nothing(tmp_path: Path):
    rec = Recorder()
    assert run_doctor(rec, tmp_path) == 1
    text = rec.text
    assert "PERPLEXITY_API_KEY" in text
    assert str(tmp_path / ".env") in text
    assert "lulu init" in text
    assert PPLX.key_page in text


def test_doctor_spends_nothing_when_told_not_to(tmp_path: Path, monkeypatch):
    (tmp_path / ".env").write_text(f"PERPLEXITY_API_KEY={KEY}\n", encoding="utf-8")
    monkeypatch.setattr(urllib.request, "urlopen", _forbidden)
    rec = Recorder()
    assert run_doctor(rec, tmp_path, offline=True) == 0
    assert "nothing was spent" in rec.text


def _forbidden(req, timeout=None):
    raise AssertionError("the offline path must not touch the network")


def test_doctor_reports_the_provider_stated_cost_when_there_is_one(tmp_path: Path, monkeypatch):
    (tmp_path / ".env").write_text(f"PERPLEXITY_API_KEY={KEY}\n", encoding="utf-8")
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        answering(
            {
                "model": "sonar",
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 3, "cost": {"total_cost": 0.0061}},
            }
        ),
    )
    rec = Recorder()
    assert run_doctor(rec, tmp_path) == 0
    assert "$0.006100 (reported by the provider)" in rec.text
    assert "12 in, 3 out" in rec.text


def test_doctor_prices_from_the_published_table_when_the_provider_is_silent(tmp_path: Path, monkeypatch):
    (tmp_path / ".env").write_text(f"PERPLEXITY_API_KEY={KEY}\n", encoding="utf-8")
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        answering(
            {
                "model": "sonar",
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 1000, "completion_tokens": 1000},
            }
        ),
    )
    rec = Recorder()
    assert run_doctor(rec, tmp_path) == 0
    text = rec.text
    assert "to $" in text
    assert "docs.perplexity.ai/getting-started/pricing" in text
    assert "read 2026-07-31" in text


def test_doctor_survives_a_response_that_reports_no_usage_at_all(tmp_path: Path, monkeypatch):
    """The first-run experience of a user whose provider renamed a field.

    There is nothing to add the token term from, so the fee is reported as the
    floor it is. Padding it out with zero tokens would print a number that
    reads like an invoice and is missing a term.
    """
    (tmp_path / ".env").write_text(f"PERPLEXITY_API_KEY={KEY}\n", encoding="utf-8")
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        answering({"model": "sonar", "choices": [{"message": {"content": "ok"}}]}),
    )
    rec = Recorder()
    assert run_doctor(rec, tmp_path) == 0
    assert "did not report them" in rec.text
    assert "no call metered yet" in rec.text


def test_doctor_turns_a_rejected_key_into_something_to_do(tmp_path: Path, monkeypatch):
    (tmp_path / ".env").write_text(f"PERPLEXITY_API_KEY={KEY}\n", encoding="utf-8")
    body = json.dumps({"error": {"message": "Invalid API key provided.", "code": 401}})
    monkeypatch.setattr(urllib.request, "urlopen", http_error(401, body))
    rec = Recorder()
    assert run_doctor(rec, tmp_path) == 1
    text = rec.text
    assert "rejected the key" in text
    assert PPLX.key_page in text
    assert KEY not in text


def test_doctor_separates_an_empty_account_from_a_bad_key(tmp_path: Path, monkeypatch):
    (tmp_path / ".env").write_text(f"PERPLEXITY_API_KEY={KEY}\n", encoding="utf-8")
    monkeypatch.setattr(urllib.request, "urlopen", http_error(402, "insufficient credit on this account"))
    rec = Recorder()
    assert run_doctor(rec, tmp_path) == 1
    assert "no credit" in rec.text
    assert PPLX.billing_page in rec.text


def test_doctor_says_when_the_key_was_never_tested_at_all(tmp_path: Path, monkeypatch):
    (tmp_path / ".env").write_text(f"PERPLEXITY_API_KEY={KEY}\n", encoding="utf-8")

    def timing_out(req, timeout=None):
        raise TimeoutError("timed out")

    monkeypatch.setattr(urllib.request, "urlopen", timing_out)
    rec = Recorder()
    assert run_doctor(rec, tmp_path) == 1
    assert "the key was never tested" in rec.text
    assert "network path problem" in rec.text


def test_doctor_names_a_moved_endpoint_as_our_bug(tmp_path: Path, monkeypatch):
    (tmp_path / ".env").write_text(f"PERPLEXITY_API_KEY={KEY}\n", encoding="utf-8")
    monkeypatch.setattr(urllib.request, "urlopen", http_error(404, "not found"))
    rec = Recorder()
    assert run_doctor(rec, tmp_path) == 1
    assert "our bug" in rec.text


def test_doctor_says_which_place_the_key_came_from(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    (home / ".lulu").mkdir(parents=True)
    (home / ".lulu" / "env").write_text(f"PERPLEXITY_API_KEY={KEY}\n", encoding="utf-8")
    rec = Recorder()
    run_doctor(rec, tmp_path, home=home, offline=True)
    assert str(home / ".lulu" / "env") in rec.text
    assert KEY not in rec.text


def test_doctor_flags_a_stored_key_that_is_malformed(tmp_path: Path, monkeypatch):
    (tmp_path / ".env").write_text('PERPLEXITY_API_KEY=sk-zzzzzzzzzzzzzzzzzzzzzzzzz\n', encoding="utf-8")
    rec = Recorder()
    run_doctor(rec, tmp_path, offline=True)
    assert "looks wrong" in rec.text
    assert "pplx-" in rec.text


# -- entry point ------------------------------------------------------------


def test_an_unknown_provider_is_refused_by_name():
    rec = Recorder()
    assert cli.main(["doctor", "--provider", "gemini"], console=rec.console) == 2
    assert "perplexity" in rec.text


def test_the_commands_are_reachable_from_the_parser():
    parser = cli.build_parser()
    assert parser.parse_args(["init"]).command == "init"
    assert parser.parse_args(["doctor", "--offline"]).offline is True
    with pytest.raises(SystemExit):
        parser.parse_args([])
