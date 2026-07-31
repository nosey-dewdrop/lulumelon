"""Getting started, tested as the ways it strands somebody on the first step.

The acceptance criterion for this half of the product is that a person who has
never used it stores a key in one sitting. It failed that on a real machine the
first time it was tried, in the least recoverable way available: a stack trace,
printed under a half-typed secret, in a shell where the hidden prompt could not
hide anything anyway.

So the entry paths are tested here as behaviour rather than as plumbing. A
setup command that cannot be run from the place people run setup from is not a
documentation problem.
"""

from __future__ import annotations

import io
import json
import urllib.request
from pathlib import Path

import pytest

from lulumelon.cli import Console, check_call, init
from lulumelon.keys import KEYCHAIN_SERVICE, spec_for

ANTHROPIC = spec_for("anthropic")
KEY = "sk-ant-" + "a1b2c3d4e5" * 4


class Recorder:
    def __init__(self) -> None:
        self.out, self.err = io.StringIO(), io.StringIO()
        self.console = Console(out=self.out, err=self.err)

    @property
    def text(self) -> str:
        return self.out.getvalue() + self.err.getvalue()


def refuses(prompt: str) -> str:
    """A `getpass` with no terminal under it, which is what actually happens."""
    raise EOFError


def answers(*replies: str):
    queue = list(replies)
    return lambda prompt: queue.pop(0)


# -- the shell with no terminal ---------------------------------------------


def test_a_shell_with_no_terminal_gets_instructions_not_a_traceback(tmp_path: Path):
    rec = Recorder()
    code = init(
        rec.console,
        ask=answers(),
        secret=refuses,
        cwd=tmp_path,
        home=tmp_path,
        provider="anthropic",
    )
    assert code == 1
    text = rec.text
    assert "no terminal" in text
    assert "--from-file" in text
    assert "--from-env" in text
    assert "Traceback" not in text


def test_a_key_can_arrive_from_a_file_the_user_deletes(tmp_path: Path, monkeypatch):
    keyfile = tmp_path / "key.txt"
    keyfile.write_text(KEY + "\n", encoding="utf-8")
    monkeypatch.setattr("lulumelon.cli.keychain_available", lambda *a: False)

    rec = Recorder()
    code = init(
        rec.console,
        ask=answers("1"),  # the local .env option, keychain being unavailable
        secret=refuses,
        cwd=tmp_path,
        home=tmp_path,
        provider="anthropic",
        from_file=keyfile,
    )
    assert code == 0
    assert "Delete that file" in rec.text
    assert KEY not in rec.text, "the key must not be echoed on the way in"
    assert KEY in (tmp_path / ".env").read_text(encoding="utf-8")


def test_a_key_can_arrive_from_the_environment(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("lulumelon.cli.keychain_available", lambda *a: False)
    rec = Recorder()
    code = init(
        rec.console,
        ask=answers("1"),
        secret=refuses,
        cwd=tmp_path,
        home=tmp_path,
        provider="anthropic",
        from_env=True,
        env={"ANTHROPIC_API_KEY": KEY},
    )
    assert code == 0
    assert "ANTHROPIC_API_KEY" in rec.text
    assert KEY not in rec.text


def test_an_empty_environment_says_which_names_it_looked_for(tmp_path: Path):
    rec = Recorder()
    code = init(
        rec.console,
        ask=answers(),
        secret=refuses,
        cwd=tmp_path,
        home=tmp_path,
        provider="anthropic",
        from_env=True,
        env={},
    )
    assert code == 1
    assert "ANTHROPIC_API_KEY" in rec.text
    assert "LULU_ANTHROPIC_API_KEY" in rec.text


def test_a_file_that_is_not_there_says_so_rather_than_storing_nothing_quietly(tmp_path: Path):
    rec = Recorder()
    code = init(
        rec.console,
        ask=answers(),
        secret=refuses,
        cwd=tmp_path,
        home=tmp_path,
        provider="anthropic",
        from_file=tmp_path / "missing.txt",
    )
    assert code == 1
    assert "Could not read" in rec.text


# -- the check call, which exists to prove more than the key ----------------


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def replying(payload: dict):
    def urlopen(req, timeout=None):
        return FakeResponse(json.dumps(payload).encode("utf-8"))

    return urlopen


def claude(content: list, **usage) -> dict:
    return {
        "content": content,
        "model": "claude-haiku-4-5",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 900, "output_tokens": 30, **usage},
    }


SOURCES = {
    "type": "web_search_tool_result",
    "tool_use_id": "srvtoolu_1",
    "content": [
        {"type": "web_search_result", "url": "https://a.example/today", "title": "t"}
    ],
}


def test_the_check_call_reports_the_searches_and_the_sources(monkeypatch):
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        replying(
            claude(
                [SOURCES, {"type": "text", "text": "1 August 2026."}],
                server_tool_use={"web_search_requests": 2},
            )
        ),
    )
    rec = Recorder()
    assert check_call(rec.console, ANTHROPIC, KEY) == 0
    text = rec.text
    assert "searches it ran: 2" in text
    assert "sources it returned: 1" in text
    assert "https://a.example/today" in text


def test_a_call_that_came_back_with_no_sources_is_called_out(monkeypatch):
    """The failure a keys-only check would have printed as a success.

    The key spends, the model answers, and the thing this product measures is
    not there. Collected in that state every question records as having no
    sources, which is a measurement nobody made.
    """
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        replying(claude([{"type": "text", "text": "I think it is August."}])),
    )
    rec = Recorder()
    assert check_call(rec.console, ANTHROPIC, KEY) == 0
    assert "NO SOURCES" in rec.text


def test_the_call_is_priced_by_the_searches_it_ran_not_by_being_one_call(monkeypatch):
    """Three searches on a per-search fee is three fees, and the screen says so.

    At ten dollars per thousand searches that is three cents rather than one,
    and the difference is the entire reason the fee carries its unit.
    """
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        replying(
            claude(
                [SOURCES, {"type": "text", "text": "1 August 2026."}],
                server_tool_use={"web_search_requests": 3},
            )
        ),
    )
    rec = Recorder()
    check_call(rec.console, ANTHROPIC, KEY)
    assert "$0.03" in rec.text


def test_the_key_never_reaches_the_screen_even_when_the_call_fails(monkeypatch):
    def urlopen(req, timeout=None):
        raise RuntimeError(f"boom while sending {KEY}")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    rec = Recorder()
    assert check_call(rec.console, ANTHROPIC, KEY) == 1
    assert KEY not in rec.text
