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


def test_the_check_call_reports_the_searches_and_the_sources(tmp_path: Path, monkeypatch):
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
    assert check_call(rec.console, ANTHROPIC, KEY, ledger_dir=tmp_path / "ledger") == 0
    text = rec.text
    assert "searches it ran: 2" in text
    assert "sources it returned: 1" in text
    assert "https://a.example/today" in text


def test_a_call_that_came_back_with_no_sources_is_called_out(tmp_path: Path, monkeypatch):
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
    assert check_call(rec.console, ANTHROPIC, KEY, ledger_dir=tmp_path / "ledger") == 0
    assert "NO SOURCES" in rec.text


def test_the_call_is_priced_by_the_searches_it_ran_not_by_being_one_call(tmp_path: Path, monkeypatch):
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
    check_call(rec.console, ANTHROPIC, KEY, ledger_dir=tmp_path / "ledger")
    assert "$0.03" in rec.text


def test_the_key_never_reaches_the_screen_even_when_the_call_fails(tmp_path: Path, monkeypatch):
    def urlopen(req, timeout=None):
        raise RuntimeError(f"boom while sending {KEY}")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    rec = Recorder()
    assert check_call(rec.console, ANTHROPIC, KEY, ledger_dir=tmp_path / "ledger") == 1
    assert KEY not in rec.text


# -- one command, no questions ----------------------------------------------

from lulumelon.cli import provider_of, read_key, setup  # noqa: E402


class FakeStdin(io.StringIO):
    def __init__(self, text: str, tty: bool) -> None:
        super().__init__(text)
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


def stub_check(seen: list):
    def check(console, spec, key, **kw):
        seen.append((spec.name, key))
        console.say("check ran")
        return 0

    return check


def test_the_engine_is_read_off_the_key_rather_than_asked_for():
    assert provider_of(KEY) == "anthropic"
    assert provider_of("pplx-" + "z" * 40) == "perplexity"
    assert provider_of("ghp_something") is None


def test_setup_stores_and_checks_in_one_command(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("lulumelon.cli.keychain_available", lambda *a: False)
    seen: list = []
    rec = Recorder()

    code = setup(rec.console, key=KEY, cwd=tmp_path, home=tmp_path, check=stub_check(seen))

    assert code == 0
    assert seen == [("anthropic", KEY)], "the check has to run in the same breath"
    assert "check ran" in rec.text
    text = rec.text
    assert "Stored your anthropic key" in text
    assert KEY not in text, "the key must never reach the screen"
    assert KEY in (tmp_path / ".lulu" / "env").read_text(encoding="utf-8")


def test_setup_asks_nothing(tmp_path: Path, monkeypatch):
    """No prompt, no menu, no provider flag. The failure being fixed was a
    person stopping at a question the tool could answer itself."""
    monkeypatch.setattr("lulumelon.cli.keychain_available", lambda *a: False)
    rec = Recorder()
    setup(rec.console, key=KEY, cwd=tmp_path, home=tmp_path, check=stub_check([]))
    assert "?" not in rec.text
    assert "Choose" not in rec.text


def test_a_key_that_matches_no_engine_says_which_ones_exist(tmp_path: Path):
    rec = Recorder()
    code = setup(rec.console, key="ghp_notours", cwd=tmp_path, home=tmp_path, check=stub_check([]))
    assert code == 1
    assert "sk-ant-" in rec.text and "pplx-" in rec.text
    assert "--provider" in rec.text


def test_an_empty_key_names_the_one_line_that_works(tmp_path: Path):
    rec = Recorder()
    assert setup(rec.console, key="   ", cwd=tmp_path, home=tmp_path, check=stub_check([])) == 1
    assert "pbpaste | lulu setup" in rec.text


def test_a_piped_key_needs_no_terminal():
    rec = Recorder()
    got = read_key(rec.console, FakeStdin(KEY + "\n", tty=False), refuses)
    assert got == KEY


def test_a_terminal_gets_the_hidden_prompt():
    rec = Recorder()
    got = read_key(rec.console, FakeStdin("", tty=True), lambda p: KEY)
    assert got == KEY
    assert "not be shown" in rec.text


# -- the call that cost money is on the record ------------------------------
#
# `lulu setup` and `lulu doctor` each bill one real call. Until these tests
# existed nothing wrote it down, so `lulu usage` could not see money that had
# actually been spent and `lulu plan --pilot` had no measured token rate to
# size a round from. The budget arithmetic in the last handoff was done by
# hand for exactly that reason.

import urllib.error  # noqa: E402

import pytest  # noqa: E402,F811

from lulumelon.cli import doctor, usage as run_usage  # noqa: E402
from lulumelon.collect import Ledger, is_diagnostic, replay  # noqa: E402

#: The model id the first real call this repo ever made came back under. The
#: alias asked for is `claude-haiku-4-5`; the response names the dated
#: snapshot, which is the same model at the same published price. The record
#: carries what answered, so this is the string the invoice has to price.
ANSWERED_AS = "claude-haiku-4-5-20251001"

DATED = "1 August 2026."


def searched_once(**over) -> dict:
    return {
        **claude(
            [SOURCES, {"type": "text", "text": DATED}],
            server_tool_use={"web_search_requests": 1},
        ),
        **over,
    }


def refusing(code: int, body: str):
    def urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, code, "denied", {}, io.BytesIO(body.encode()))

    return urlopen


def only_round(ledger_dir: Path) -> tuple[Ledger, str]:
    """The one snapshot a single check call is expected to have opened."""
    led = Ledger(ledger_dir)
    written = led.snapshots()
    assert len(written) == 1, f"one call should open one round, got {written}"
    return led, written[0]


def test_a_billed_check_call_lands_one_record_that_verifies(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", replying(searched_once()))
    rec = Recorder()
    assert check_call(rec.console, ANTHROPIC, KEY, ledger_dir=tmp_path / "ledger") == 0

    led, snapshot_id = only_round(tmp_path / "ledger")
    assert led.verify(snapshot_id) == [], "the round it wrote must re-derive"
    record, seal = list(led.read(snapshot_id))

    assert record.status == "ok"
    assert record.model == "claude-haiku-4-5", "the model as the response named it"
    assert (record.input_tokens, record.output_tokens) == (900, 30)
    assert record.searches == 1, "the count a per-search fee multiplies, as the response gave it"
    assert record.citations == ("https://a.example/today",)
    assert record.brands == (), "no brand list was supplied, so nothing was looked for"
    assert str(led.path_of(snapshot_id)) in rec.text, "it must say where it wrote"

    # One call is a round, and a round says how long it was. Without this a
    # diagnostic reduced to an empty file reads as a call that never happened.
    assert (seal.round_asked, seal.round_ok, seal.round_errors) == (1, 1, 0)
    assert led.calls(snapshot_id) == 1


def test_a_check_call_that_failed_is_recorded_with_its_reason(tmp_path: Path, monkeypatch):
    """The failures are the half worth keeping.

    An account that cannot spend is the state this command exists to find, and
    a diagnostic that records only its successes flatters itself. Nothing is
    swallowed and nothing is retried.
    """
    body = json.dumps({"error": {"type": "authentication_error", "message": "invalid x-api-key"}})
    monkeypatch.setattr(urllib.request, "urlopen", refusing(401, body))
    rec = Recorder()
    assert check_call(rec.console, ANTHROPIC, KEY, ledger_dir=tmp_path / "ledger") == 1

    led, snapshot_id = only_round(tmp_path / "ledger")
    assert led.verify(snapshot_id) == []
    record, seal = list(led.read(snapshot_id))

    assert record.status == "error"
    assert "401" in record.error and "invalid x-api-key" in record.error
    assert record.model == "unknown", "nothing answered, so no model can be named"
    assert record.input_tokens is None, "a call that failed reported no tokens"
    assert "recorded as an error in" in rec.text
    # The round closes on the failing path too, and closes honestly: one call
    # made, none answered. A seal written only where the call worked would make
    # a refused key look like a round that lost its records.
    assert (seal.round_asked, seal.round_ok, seal.round_errors) == (1, 0, 1)


def test_lulu_usage_sees_the_check_call_and_prices_it(tmp_path: Path, monkeypatch):
    """The money is now visible to the command that reports money.

    Priced from the figures the response itself carried: 900 in and 30 out at
    $1 and $5 per million is $0.001050, plus one search fee at $10 per
    thousand. The response named the dated snapshot of the model, which is the
    same model at the same published price, so it prices rather than landing
    in `no published price on file`.
    """
    monkeypatch.setattr(urllib.request, "urlopen", replying(searched_once(model=ANSWERED_AS)))
    ledger_dir = tmp_path / "ledger"
    assert check_call(Recorder().console, ANTHROPIC, KEY, ledger_dir=ledger_dir) == 0

    rec = Recorder()
    assert run_usage(rec.console, ledger_dir=ledger_dir) == 0
    text = rec.text
    assert "chain intact" in text
    assert "1 call recorded: 1 answered, 0 failed" in text
    assert "input   900" in text and "output  30" in text
    assert "$0.011050" in text
    assert f"anthropic/{ANSWERED_AS}" in text


def test_the_diagnostic_round_cannot_be_read_as_a_measurement(tmp_path: Path, monkeypatch):
    """The separation is in the file name and enforced at the one door.

    `mirror` consumes `Run` objects and nothing else, and `replay` is the only
    thing that makes them, so a check call refused there cannot be pooled into
    a brand's sample by anything downstream.
    """
    monkeypatch.setattr(urllib.request, "urlopen", replying(searched_once()))
    assert check_call(Recorder().console, ANTHROPIC, KEY, ledger_dir=tmp_path / "ledger") == 0

    led, snapshot_id = only_round(tmp_path / "ledger")
    assert snapshot_id.startswith("diagnostic__anthropic__api__")
    assert is_diagnostic(snapshot_id)
    assert not is_diagnostic("marx__anthropic__api__20260801T014500Z__0001")

    with pytest.raises(ValueError, match="diagnostic round"):
        replay(led, snapshot_id)


def test_the_offline_path_writes_nothing_because_it_spends_nothing(tmp_path: Path):
    (tmp_path / ".env").write_text(f"ANTHROPIC_API_KEY={KEY}\n", encoding="utf-8")
    rec = Recorder()
    code = doctor(
        rec.console,
        cwd=tmp_path,
        home=tmp_path / "home",
        provider="anthropic",
        offline=True,
        env={},
        keychain=lambda service, account: None,
    )
    assert code == 0
    assert "nothing was spent" in rec.text
    assert not (tmp_path / "ledger").exists(), "nothing spent is nothing written, not even a directory"


def test_the_key_reaches_neither_the_screen_nor_the_ledger(tmp_path: Path, monkeypatch):
    """The provider's own words go on the record; the secret in them does not.

    Redaction happens where those words are made, before the record is hashed,
    so the key never exists on disk rather than being taken out afterwards.
    """
    def urlopen(req, timeout=None):
        raise RuntimeError(f"boom while sending {KEY}")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    ledger_dir = tmp_path / "ledger"
    rec = Recorder()
    assert check_call(rec.console, ANTHROPIC, KEY, ledger_dir=ledger_dir) == 1

    led, snapshot_id = only_round(ledger_dir)
    written = led.path_of(snapshot_id).read_text(encoding="utf-8")
    assert KEY not in written
    assert KEY not in rec.text
    assert "[redacted key]" in written, "the reason is kept, the secret is not"
