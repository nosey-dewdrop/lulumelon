"""Turning a paid round into a public url, stated as what it must not publish.

This is the only command in the repository whose output is meant to be read by
people who did not pay for it, so the properties tested hardest are the two
that would turn a measurement into a leak or into an advertisement.

**A round about a brand is not published from here.** A question carrying a
tracked name measures that brand, and the page this writes is a page about a
market. The refusal is on the questions rather than on a flag, because a flag
is a thing somebody forgets.

**Nothing is removed quietly.** The name counter cannot tell a company from a
genre word, so a person drops those by hand, and every name dropped is written
into the file so the page can say it happened.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from lulumelon.cli import CHAIN_BROKEN, NOT_PUBLISHABLE, Console, publish
from lulumelon.collect import Brand, FakeProvider, Ledger, Prompt, Usage, run_round


class Recorder:
    def __init__(self) -> None:
        self.out, self.err = io.StringIO(), io.StringIO()
        self.console = Console(out=self.out, err=self.err)

    @property
    def text(self) -> str:
        return self.out.getvalue() + self.err.getvalue()


ANSWER = (
    "Most teams use Finnhub for this, and Alpaca for execution. The API is fine, "
    "and the free tier covers a small agent."
)


def round_on(tmp_path: Path, answer: str = ANSWER) -> tuple[Path, str]:
    ledger_dir = tmp_path / "ledger"
    result = run_round(
        ledger=Ledger(ledger_dir),
        provider=FakeProvider(
            script={"q": (answer,)}, usage=Usage(input_tokens=100, output_tokens=20)
        ),
        prompts=[Prompt(id="p1", text="q")],
        brands=[Brand(name="ornek", aliases=())],
        k=4,
        subject="ornek",
        clock=lambda: "2026-08-05T01:00:00Z",
    )
    return ledger_dir, result.snapshot_id


def questions(tmp_path: Path, text: str, **over) -> Path:
    doc = {
        "subject": {"id": "ornek", "name": "Ornek", "domain": "ornek.com"},
        "competitors": [],
        "prompts": [{"id": "p1", "text": text}],
    }
    doc.update(over)
    path = tmp_path / "questions.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def written(out_dir: Path) -> dict:
    files = list(out_dir.glob("*.json"))
    assert len(files) == 1, files
    return json.loads(files[0].read_text(encoding="utf-8"))


# -- what may not become a url ----------------------------------------------


def test_a_round_whose_question_names_a_tracked_brand_is_refused(tmp_path):
    ledger_dir, snapshot = round_on(tmp_path)
    rec = Recorder()

    code = publish(
        rec.console,
        ledger_dir=ledger_dir,
        snapshot=snapshot,
        questions_path=questions(tmp_path, "What is Ornek and who competes with it?"),
        out_dir=tmp_path / "published",
    )

    assert code == NOT_PUBLISHABLE
    assert "about a brand rather than about a market" in rec.text
    assert not (tmp_path / "published").exists(), "nothing is written on the way to the refusal"


def test_a_round_that_does_not_re_derive_is_refused(tmp_path):
    ledger_dir, snapshot = round_on(tmp_path)
    path = Ledger(ledger_dir).path_of(snapshot)
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(lines[:2]) + "\n", encoding="utf-8")

    rec = Recorder()
    code = publish(
        rec.console,
        ledger_dir=ledger_dir,
        snapshot=snapshot,
        questions_path=questions(tmp_path, "Which platforms do trading agents use?"),
        out_dir=tmp_path / "published",
    )

    assert code == CHAIN_BROKEN


def test_a_question_this_build_has_no_wording_for_stops_the_whole_round(tmp_path):
    """A page cannot report on a question it would have to invent."""
    ledger_dir, snapshot = round_on(tmp_path)
    doc = {
        "subject": {"id": "ornek", "name": "Ornek", "domain": "ornek.com"},
        "competitors": [],
        "prompts": [{"id": "somewhere-else", "text": "Which platforms do agents use?"}],
    }
    path = tmp_path / "wrong.json"
    path.write_text(json.dumps(doc), encoding="utf-8")

    rec = Recorder()
    code = publish(
        rec.console,
        ledger_dir=ledger_dir,
        snapshot=snapshot,
        questions_path=path,
        out_dir=tmp_path / "published",
    )

    assert code != 0
    assert "states no wording for p1" in rec.text


# -- what a published page carries ------------------------------------------


def test_a_published_page_carries_the_round_it_re_derives_from(tmp_path):
    ledger_dir, snapshot = round_on(tmp_path)
    rec = Recorder()
    out = tmp_path / "published"

    code = publish(
        rec.console,
        ledger_dir=ledger_dir,
        snapshot=snapshot,
        questions_path=questions(tmp_path, "Which platforms do trading agents use?"),
        out_dir=out,
        least=1,
    )

    assert code == 0
    body = written(out)
    assert body["question"] == "Which platforms do trading agents use?"
    assert body["snapshot"] == snapshot
    assert body["draws"] == 4
    assert body["arm"] == "api"
    assert body["slug"] == "which-platforms-do-trading-agents-use"


def test_every_name_carries_the_interval_the_sample_supports(tmp_path):
    """Four of four is not a certainty, and the page has to say the range."""
    ledger_dir, snapshot = round_on(tmp_path)
    rec = Recorder()
    out = tmp_path / "published"

    publish(
        rec.console,
        ledger_dir=ledger_dir,
        snapshot=snapshot,
        questions_path=questions(tmp_path, "Which platforms do trading agents use?"),
        out_dir=out,
        least=1,
    )

    finnhub = next(one for one in written(out)["names"] if one["name"] == "Finnhub")
    assert (finnhub["draws"], finnhub["of"]) == (4, 4)
    assert finnhub["rate"] == 1.0
    assert finnhub["low"] < 1.0, "a clean sweep of four still has a lower bound below one"
    assert finnhub["high"] == 1.0


def test_a_name_dropped_by_hand_is_named_in_the_file(tmp_path):
    """The counter cannot tell a company from a genre word. A person can, and says so.

    `The API` rather than `API`, because that is what the counter produced: a
    clause opening with a determiner capitalises it exactly where a company's
    first word would be, and the extraction reports what it saw.
    """
    ledger_dir, snapshot = round_on(tmp_path)
    rec = Recorder()
    out = tmp_path / "published"

    publish(
        rec.console,
        ledger_dir=ledger_dir,
        snapshot=snapshot,
        questions_path=questions(tmp_path, "Which platforms do trading agents use?"),
        out_dir=out,
        least=1,
        drop=["The API"],
    )

    body = written(out)
    assert body["dropped"] == ["The API"]
    assert all(one["name"] != "The API" for one in body["names"])
    assert any(one["name"] == "Finnhub" for one in body["names"]), "only what was named is dropped"
    assert "1 dropped by hand" in rec.text


def test_a_name_seen_once_is_left_out_of_a_page_that_asked_for_two(tmp_path):
    ledger_dir, snapshot = round_on(
        tmp_path, "Most teams use Finnhub. Somebody mentioned Kalshi once."
    )
    rec = Recorder()
    out = tmp_path / "published"

    publish(
        rec.console,
        ledger_dir=ledger_dir,
        snapshot=snapshot,
        questions_path=questions(tmp_path, "Which platforms do trading agents use?"),
        out_dir=out,
        least=5,
    )

    assert written(out)["names"] == [], "four draws cannot clear a floor of five"
