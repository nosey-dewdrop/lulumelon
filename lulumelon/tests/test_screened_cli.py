"""Reading a finished screening round back, stated as what the document may not hide.

The round this prints is the one that decides which questions are worth paying
to measure, and the finding it produced first was not a score. Eleven of twenty
questions came back with none of the declared rivals named in any draw, and the
only place that fact existed was a terminal scrollback.

So the properties tested hardest are the ones that would let a document flatter
a round: a barren question that quietly disappears, a name list that stops
without saying it stopped, and an undecided verdict printed as if it were a
pass.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from lulumelon.cli import NOT_A_DRAFT, Console, screened
from lulumelon.collect import Brand, FakeProvider, Ledger, Prompt, Usage, run_round


class Recorder:
    def __init__(self) -> None:
        self.out, self.err = io.StringIO(), io.StringIO()
        self.console = Console(out=self.out, err=self.err)

    @property
    def text(self) -> str:
        return self.out.getvalue() + self.err.getvalue()


BARREN = {
    "id": "p1",
    "text": "Which platforms let trading agents publish their calls?",
    "source": "https://ornek.com",
    "evidence": "agents publish their calls",
    "verdict": "barren",
    "rival_hits": 0,
    "draws": 4,
    "floor": 0.5,
    "interval": [0.0, 0.49],
}
CARRIES = {
    "id": "p2",
    "text": "Best API for live market data",
    "source": "https://ornek.com/tarifeler",
    "evidence": "live market data",
    "verdict": "carries",
    "rival_hits": 4,
    "draws": 4,
    "floor": 0.5,
    "interval": [0.51, 1.0],
}
UNDECIDED = {
    "id": "p3",
    "text": "Where do autonomous agents compare notes?",
    "source": "https://ornek.com",
    "evidence": "compare notes",
    "verdict": "undecided",
    "rival_hits": 1,
    "draws": 4,
    "floor": 0.5,
    "interval": [0.046, 0.699],
}


def draft_file(tmp_path: Path, **over) -> Path:
    body = {
        "site": "https://ornek.com",
        "corpus_digest": "455d694604df6017e293",
        "pages_read": ["https://ornek.com", "https://ornek.com/tarifeler"],
        "unreachable": [],
        "not_documents": [],
        "proposed": 3,
        "unreadable_entries": [],
        "rejected": [
            {"id": "c9", "text": "What does Ornek charge?", "gate": "name", "reason": "own echo"}
        ],
        "screening_snapshot": "",
        "measured": [BARREN, CARRIES, UNDECIDED],
        "noise_floor": 0.126,
    }
    body.update(over)
    path = tmp_path / "pool.draft.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def read(tmp_path: Path, **over) -> tuple[int, str]:
    rec = Recorder()
    code = screened(
        rec.console, draft_path=draft_file(tmp_path, **over), ledger_dir=tmp_path / "ledger"
    )
    return code, rec.text


# -- nothing that was measured disappears -----------------------------------


def test_a_question_that_named_nobody_is_printed_with_its_words(tmp_path):
    """The finding, not the leftovers.

    A round where most questions come back this way is telling a customer
    something larger than a percentage would, and `barren` on its own is a
    verdict nobody can check.
    """
    code, text = read(tmp_path)
    assert code == 0
    assert "[barren] p1" in text
    assert BARREN["text"] in text
    assert "named in 0/4" in text


def test_the_three_verdicts_are_counted_on_one_line(tmp_path):
    _, text = read(tmp_path)
    assert "1 of 3 questions clear the floor, 1 are undecided, and 1 named nobody" in text


def test_undecided_is_never_printed_as_a_pass(tmp_path):
    _, text = read(tmp_path)
    assert "undecided is not a pass" in text
    assert "The interval covers the floor" in text


def test_a_barren_verdict_says_what_it_is_a_fact_about(tmp_path):
    """It is a fact about the list that was declared, and not about the market."""
    _, text = read(tmp_path)
    assert "a fact about the list that was declared" in text
    assert "not" in text and "nobody sells into that question" in text


def test_the_noise_floor_is_worded_the_way_the_round_worded_it(tmp_path):
    """The same fact under two sentences reads as two facts."""
    _, text = read(tmp_path)
    assert "12.6 points is the noise floor" in text


def test_a_draft_with_no_draws_behind_it_says_so_instead_of_naming_nobody(tmp_path):
    _, text = read(tmp_path)
    assert "no draws were bought, so nothing was named" in text


def test_a_draft_written_before_the_words_were_kept_still_opens(tmp_path):
    """Every draft this build ever wrote has to stay readable by it."""
    old = {k: v for k, v in BARREN.items() if k != "text"}
    code, text = read(tmp_path, measured=[old])
    assert code == 0
    assert "not recorded by the build that wrote this draft" in text


def test_a_file_that_is_not_a_draft_ledger_is_refused_with_its_own_code(tmp_path):
    rec = Recorder()
    path = tmp_path / "nonsense.json"
    path.write_text('{"site": "https://ornek.com"}', encoding="utf-8")

    code = screened(rec.console, draft_path=path, ledger_dir=tmp_path)
    assert code == NOT_A_DRAFT
    assert "is not a draft ledger this build can read" in rec.text


def test_a_file_that_is_not_there_is_refused_rather_than_raised(tmp_path):
    rec = Recorder()
    code = screened(rec.console, draft_path=tmp_path / "missing.json", ledger_dir=tmp_path)
    assert code == NOT_A_DRAFT


# -- the names come off the round, not out of the draft ---------------------


def test_the_names_are_read_off_the_round_the_draft_points_at(tmp_path):
    """The draft records which declared rivals were hit. This is the other list.

    A round is screened against names somebody wrote down in advance, and the
    question a customer is actually asking is who the model reaches for when
    nobody suggested anybody. That list can only come from the answers.
    """
    ledger_dir = tmp_path / "ledger"
    led = Ledger(ledger_dir)
    result = run_round(
        ledger=led,
        provider=FakeProvider(
            script={"q": ("Most teams use Finnhub for this, and Alpaca for execution.",)},
            usage=Usage(input_tokens=100, output_tokens=20),
        ),
        prompts=[Prompt(id="p1", text="q")],
        brands=[Brand(name="ornek", aliases=())],
        k=2,
        subject="ornek",
        clock=lambda: "2026-08-04T21:00:00Z",
    )

    rec = Recorder()
    code = screened(
        rec.console,
        draft_path=draft_file(tmp_path, screening_snapshot=result.snapshot_id),
        ledger_dir=ledger_dir,
    )

    assert code == 0
    assert "Finnhub" in rec.text and "Alpaca" in rec.text
    assert "p1 2/2" in rec.text, "counted per question and per draw"
    assert "not a rival" not in rec.text
    assert "is a name the model wrote" in rec.text


def test_a_name_list_the_document_cut_says_it_was_cut(tmp_path):
    """A table that quietly stops is a table that reads as complete.

    A screening round of twenty questions reaches for hundreds of names, most
    of them the genre words a model writes with. The page cannot carry all of
    them and is not allowed to pretend it did.
    """
    ledger_dir = tmp_path / "ledger"
    led = Ledger(ledger_dir)
    crowd = " ".join(f"Teams use Firma{i}x for this." for i in range(40))
    result = run_round(
        ledger=led,
        provider=FakeProvider(script={"q": (crowd,)}, usage=Usage(input_tokens=99, output_tokens=9)),
        prompts=[Prompt(id="p1", text="q")],
        brands=[Brand(name="ornek", aliases=())],
        k=2,
        subject="ornek",
        clock=lambda: "2026-08-04T21:30:00Z",
    )

    rec = Recorder()
    screened(
        rec.console,
        draft_path=draft_file(tmp_path, screening_snapshot=result.snapshot_id),
        ledger_dir=ledger_dir,
    )

    assert "25 of 40 names, the ones in the most questions" in rec.text
    assert "`lulu rivals` prints the whole list" in rec.text


def test_a_round_that_cannot_be_opened_says_so_where_the_names_would_be(tmp_path):
    """An empty table reads as an answer. A missing round has to read as missing."""
    _, text = read(tmp_path, screening_snapshot="ornek__anthropic__api__20260804T000000Z__0009")
    assert "holds no readable answer in" in text
    assert "NAMED" in text, "the heading stays, with the reason under it"


# -- the document ------------------------------------------------------------


def test_the_document_carries_every_question_the_screen_did(tmp_path):
    rec = Recorder()
    out = tmp_path / "screened.tex"
    code = screened(
        rec.console,
        draft_path=draft_file(tmp_path),
        ledger_dir=tmp_path / "ledger",
        tex_path=out,
    )

    assert code == 0
    tex = out.read_text(encoding="utf-8")
    assert tex.startswith("\\documentclass")
    assert tex.rstrip().endswith("\\end{document}")
    for one in (BARREN, CARRIES, UNDECIDED):
        assert one["text"] in tex, one["id"]
    assert "undecided is not a pass" in tex


def test_the_document_is_refused_rather_than_written_into_nowhere(tmp_path):
    rec = Recorder()
    try:
        screened(
            rec.console,
            draft_path=draft_file(tmp_path),
            ledger_dir=tmp_path / "ledger",
            tex_path=tmp_path / "nope" / "screened.tex",
        )
    except ValueError as e:
        assert "is not a directory" in str(e)
    else:
        raise AssertionError("a document written into a directory that is not there")
