"""The report as a document, pinned line for line and character for character.

Two things can go wrong here and only one of them is visible. The first is that
the page says something the screen does not, which is why the whole document is
pinned below rather than probed for substrings: a renderer that quietly reworded
a refusal would still pass every `in text` assertion ever written about it.

The second is that the document does not compile. A brand name is arbitrary text
somebody typed, and `&`, `%`, `_`, `#`, `$` and `~` are ordinary in a brand name
and fatal in TeX, so a customer called `Ben & Jerry's` is a report that never
arrives. That is checked by rendering a subject file made of nothing else and
then scanning the output for a control character standing on its own.

Nothing here runs a typesetter. The string is a pure function of a round, so it
is tested as one, and the suite stays offline and stays free of a build tool.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from lulumelon.cli import questions_of
from lulumelon.collect import FakeProvider, Ledger, load_subject, replay, run_round
from lulumelon.latex import Evidence, escape, tex_document
from lulumelon.mirror.report import brand_report
from lulumelon.mirror.types import Snapshot, group_runs
from lulumelon.panel import TERMINAL_QUESTIONS, Panel
from lulumelon.usage import spend_of

HAIKU = "claude-haiku-4-5"

#: The same three questions `test_report_cli` collects, so the document below is
#: a document about a round this suite already reports on screen.
SUBJECT = {
    "subject": {"id": "ornek", "name": "Ornek", "aliases": ["Ornek Finance", "ornek.com"]},
    "prompts": [
        {"id": "m1", "text": "What is ornek.com?", "intent": "entity"},
        {"id": "m2", "text": "Agentic finance platforms in 2026", "intent": "category"},
        {"id": "m3", "text": "Reputation systems for AI trading agents", "intent": "solution"},
    ],
}

SCRIPT = {
    "What is ornek.com?": (
        "I don't have specific information about ornek.com in my training data.",
    ),
    "Agentic finance platforms in 2026": ("Ornek Finance is one.", "nobody."),
    "Reputation systems for AI trading agents": ("nobody.",),
}

#: A subject file made of the characters TeX reads as instructions. Every one of
#: these is legal in a brand name, and a document is worth nothing if one of them
#: stops it compiling.
HOSTILE_BRAND = "Ben & Jerry's 100% #1 $_x ~y ^z {q} \\r"

HOSTILE = {
    "subject": {"id": "hostile", "name": HOSTILE_BRAND, "aliases": ["B&J_100%"]},
    "prompts": [
        {"id": "h#1", "text": "Who makes Ben & Jerry's 100% #1 $_x ~y ^z {q} \\r?"},
        {"id": "h_2", "text": "Best 50% & 50% ice cream"},
    ],
}

HOSTILE_SCRIPT = {
    "Who makes Ben & Jerry's 100% #1 $_x ~y ^z {q} \\r?": ("No idea what that is.",),
    "Best 50% & 50% ice cream": ("Ben & Jerry's 100% #1 $_x ~y ^z {q} \\r leads.", "nobody."),
}

#: Characters TeX acts on. Every one of them has to reach the page behind a
#: backslash, and `&` is the only one this renderer also uses as itself: it
#: separates the two columns of the evidence table, once per row.
CONTROL = "%$#_~^"


def _round(tmp_path: Path, doc: dict, script: dict, brand: str) -> tuple[Panel, Evidence, str]:
    """One sealed round, scored, with the facts about the file it is written on.

    Collected through the stub rather than assembled by hand, so the document
    under test is a document about a round that came down the path a real one
    comes down.
    """
    path = tmp_path / "subject.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    subject = load_subject(path)
    ledger = Ledger(tmp_path / "ledger")
    result = run_round(
        ledger=ledger,
        provider=FakeProvider(name="anthropic", model=HAIKU, script=script),
        prompts=subject.prompts,
        brands=subject.brands,
        k=2,
        subject=subject.id,
        clock=lambda: "2026-08-01T03:30:00Z",
    )
    played = replay(ledger, result.snapshot_id)
    scored = brand_report(
        Snapshot(label=result.snapshot_id, samples=group_runs(played.runs)),
        brand,
        self_naming=subject.self_naming(brand),
    )
    records = list(ledger.read(result.snapshot_id))
    last = records[-1]
    evidence = Evidence(
        records=len(records),
        seal=f"{last.round_asked} calls sealed, {last.round_ok} answered, "
        f"{last.round_errors} failed",
        final_hash=last.hash,
        models=played.models,
        surfaces=played.surfaces,
        dates=tuple(sorted({r.asked_at[:10] for r in records if not r.is_seal})),
        cost=spend_of(records).total_lines(),
    )
    panel = Panel(
        report=scored,
        dropped_runs=played.dropped,
        surfaces=played.surfaces,
        # Through the command's own assembler rather than built here, so the
        # questions on the page are the ones the report path puts there.
        questions=questions_of(subject, played, records, subject.self_naming(brand)),
    )
    return panel, evidence, result.snapshot_id


@pytest.fixture
def ornek(tmp_path):
    return _round(tmp_path, SUBJECT, SCRIPT, "Ornek")


@pytest.fixture
def hostile(tmp_path):
    return _round(tmp_path, HOSTILE, HOSTILE_SCRIPT, HOSTILE_BRAND)


def _unescaped(text: str, ch: str) -> list[int]:
    """Every position where `ch` stands in the document as itself."""
    return [i for i, c in enumerate(text) if c == ch and (i == 0 or text[i - 1] != "\\")]


def _spoken(text: str) -> str:
    """A document with its typesetting taken back out, so words can be compared.

    The renderer sets a run of spaces as one explicit gap and ends a line with
    an explicit break. Both are undone here rather than reproduced, so this
    file compares what the page says against what the screen says instead of
    against a second copy of the rule that put it there.
    """
    return re.sub(r" +", " ", text.replace("\\quad{}", " ").replace("\\\\", " "))


# -- escaping ----------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, written",
    [
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("{", r"\{"),
        ("}", r"\}"),
        ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
        ("\\", r"\textbackslash{}"),
        ("<", r"\textless{}"),
        (">", r"\textgreater{}"),
        ("|", r"\textbar{}"),
    ],
)
def test_every_character_tex_acts_on_is_written_as_itself(raw, written):
    assert escape(raw) == written


def test_a_backslash_does_not_escape_the_character_after_it():
    """The failure a sequential replace table produces, and this one cannot.

    Replacing `\\` first and `&` second turns `\\&` into a backslash command
    followed by a live ampersand; replacing them the other way round leaves the
    backslash of `\\&` to be replaced on the next pass.
    """
    assert escape("\\&") == r"\textbackslash{}\&"
    assert escape("a\\_b") == r"a\textbackslash{}\_b"


def test_ordinary_text_is_left_alone():
    assert escape("Ornek Finance, 11.1% of answers") == r"Ornek Finance, 11.1\% of answers"


# -- the document ------------------------------------------------------------


GOLDEN = """\\documentclass[11pt,a4paper]{article}
\\usepackage[T1]{fontenc}
\\usepackage{newtxtext,newtxmath}
\\usepackage{tabularx}
\\usepackage[margin=25mm]{geometry}
\\pagestyle{plain}
\\setlength{\\parindent}{0pt}
\\setlength{\\parskip}{0.4\\baselineskip}
\\emergencystretch=2em
\\makeatletter
\\renewcommand\\section{\\@startsection{section}{1}{0pt}{1.1\\baselineskip}{0.3\\baselineskip}{\\normalsize\\bfseries}}
\\makeatother
\\begin{document}
{\\large\\bfseries lulu report\\par}
brand: Ornek\\quad{}snapshot: SNAPSHOT\\par
\\section*{DESIGN}
2 prompts x 2 runs = 4 answers on anthropic\\\\
excluded from the rate and its interval: 1 prompt whose own text names Ornek (m1)\\\\
detection matches declared literals, so a question carrying the name is answered with it whatever the model knows\\par
\\section*{PARAMETERS}
location\\quad{}no location was requested, so the answers are whatever the engine serves a call that named none\\\\
searches\\quad{}the cap on how many searches a call may run is not written to the ledger, so it is not recoverable from this round\\par
\\section*{APPEARANCE}
Ornek is named in 25.0\\% of answers\\\\
honest range 0.0\\% to 50.0\\%\\quad{}(95\\% confidence, prompt-clustered)\\par
the rate is the mean of the per-prompt means, and each prompt gets equal weight regardless of how many times it was asked\\\\
the range is cluster\\_bootstrap(B=2000,seed=0), the percentile bootstrap where the prompt, not the run, is resampled\\par
\\section*{WHAT IS CONTRIBUTING TO YOUR INTERVAL WIDTH?}
the model answering differently\\quad{}100.0\\%\\\\
which questions you chose to ask\\quad{}0.0\\%\\\\
noise floor\\quad{}+/-49.0 points\\quad{}(icc 0.00)\\par
next: repeats will not get you there: with 2 prompts the prompt set alone already carries +/-0.0 points, past your +/-2.0 target. Reach it with 801 prompts at k=3 instead (icc 0.00).\\par
\\section*{VERDICTS}
rank\\quad{}WITHHELD, the leading brand does not repeat often\\\\
\\hspace*{5em}enough for a position to describe anything but the sampling\\par
\\section*{QUESTIONS}
every question this round asked, in the order the subject file states them\\par
m1\\quad{}What is ornek.com?\\\\
\\hspace*{3em}2 usable of 2 asked, excluded from the rate and its interval\\\\
m2\\quad{}Agentic finance platforms in 2026\\\\
\\hspace*{3em}2 usable of 2 asked\\\\
m3\\quad{}Reputation systems for AI trading agents\\\\
\\hspace*{3em}2 usable of 2 asked\\par
\\section*{EVIDENCE}
\\begin{tabularx}{\\textwidth}{@{}lX@{}}
records & 7 records\\\\
sealed & 6 calls sealed, 6 answered, 0 failed\\\\
final hash & HASH\\\\
model & claude-haiku-4-5, as reported by the response\\\\
surfaces & api\\\\
collected & 2026-08-01\\\\
cost & total\\quad{}\\$0.060000 to \\$0.060000\\quad{}(0 of 6 priced calls metered) \\newline per call\\quad{}\\$0.010000 to \\$0.010000\\\\
\\end{tabularx}\\par
\\vspace{1.6\\baselineskip}
\\noindent\\rule{\\textwidth}{0.4pt}\\par
Computed from the recorded answers of this round only, on the surfaces listed above. Every number here is reproducible from the ledger, and the raw answer behind any of them can be printed on request.\\par
\\end{document}
"""


def test_the_whole_document_is_the_one_pinned_here(ornek):
    """Pinned entire, because a substring test cannot see a reworded sentence.

    The snapshot id and the chain hash are the two things in it that a
    collector decides rather than this renderer, so they are substituted in
    from the round rather than frozen; everything else is a byte.
    """
    panel, evidence, snapshot = ornek
    expected = GOLDEN.replace("SNAPSHOT", escape(snapshot)).replace(
        "HASH", evidence.final_hash
    )
    assert tex_document(panel, evidence) == expected


def test_the_document_stands_on_its_own(ornek):
    panel, evidence, _ = ornek
    tex = tex_document(panel, evidence)
    assert tex.startswith("\\documentclass")
    assert "\\begin{document}" in tex
    assert tex.rstrip().endswith("\\end{document}")


def test_the_sentences_are_the_ones_the_screen_prints(ornek):
    """Every line of panel output reaches the page, escaped and in order.

    Read off `Panel` rather than typed here. A test that quoted the sentences
    would be a second copy of them, and the point of rendering through the
    panel is that there is only ever one.
    """
    panel, evidence, _ = ornek
    spoken = _spoken(tex_document(panel, evidence))
    for block in (
        panel.design(),
        panel.parameters(),
        panel.appearance(),
        panel.contributing(),
        panel.verdicts(),
        panel.question_section(limit=None),
    ):
        for line in block:
            assert escape(re.sub(r" +", " ", line.strip())) in spoken, line


def test_the_excluded_question_and_the_failed_asks_are_on_the_page(tmp_path):
    """Both counts that make the rate smaller, as they read on screen."""
    doc = json.loads(json.dumps(SUBJECT))
    ledger = Ledger(tmp_path / "ledger")
    path = tmp_path / "subject.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    subject = load_subject(path)
    result = run_round(
        ledger=ledger,
        provider=FakeProvider(name="anthropic", model=HAIKU, script=SCRIPT, fail_on=(1, 5)),
        prompts=subject.prompts,
        brands=subject.brands,
        k=2,
        subject=subject.id,
        clock=lambda: "2026-08-01T03:30:00Z",
    )
    played = replay(ledger, result.snapshot_id)
    scored = brand_report(
        Snapshot(label=result.snapshot_id, samples=group_runs(played.runs)),
        "Ornek",
        self_naming=subject.self_naming("Ornek"),
    )
    records = list(ledger.read(result.snapshot_id))
    evidence = Evidence(
        records=len(records),
        seal="x",
        final_hash=records[-1].hash,
        models=played.models,
        surfaces=played.surfaces,
        dates=("2026-08-01",),
        cost=spend_of(records).total_lines(),
    )
    spoken = _spoken(tex_document(Panel(report=scored, dropped_runs=played.dropped), evidence))

    assert played.dropped == 2
    assert "2 asks failed and are excluded, recorded not dropped" in spoken
    assert (
        "excluded from the rate and its interval: 1 prompt whose own text names Ornek (m1)"
        in spoken
    )


def test_the_evidence_names_the_file_the_numbers_came_from(ornek):
    """Snapshot, length, seal, chain, model, surface, dates and money."""
    panel, evidence, snapshot = ornek
    tex = tex_document(panel, evidence)

    assert escape(snapshot) in tex
    assert "records & 7 records" in tex
    assert "sealed & 6 calls sealed, 6 answered, 0 failed" in tex
    assert f"final hash & {evidence.final_hash}" in tex
    assert f"model & {HAIKU}, as reported by the response" in tex
    assert "surfaces & api" in tex
    assert "collected & 2026-08-01" in tex
    assert "0 of 6 priced calls metered" in tex


def test_the_cost_wording_is_the_one_lulu_usage_prints(ornek):
    """The total is quoted, not restated: one sentence, two surfaces."""
    panel, evidence, _ = ornek
    spoken = _spoken(tex_document(panel, evidence))
    for line in evidence.cost:
        assert escape(re.sub(r" +", " ", line)) in spoken


def test_the_document_prints_every_question_where_the_screen_stops(tmp_path):
    """The screen holds a screenful. The page is what somebody checks against.

    Collected over more questions than the terminal prints, so the two surfaces
    disagree here by design and the document is the one carrying all of them.
    """
    doc = json.loads(json.dumps(SUBJECT))
    doc["prompts"] = [
        {"id": f"q{i}", "text": f"Question number {i}"} for i in range(TERMINAL_QUESTIONS + 3)
    ]
    panel, evidence, _ = _round(tmp_path, doc, {}, "Ornek")
    spoken = _spoken(tex_document(panel, evidence))

    assert len(panel.question_section()) < len(panel.question_section(limit=None))
    assert "3 questions not printed here" in "\n".join(panel.question_section())
    for prompt in doc["prompts"]:
        assert prompt["text"] in spoken, prompt["id"]
    assert "not printed here" not in spoken


# -- arbitrary input ---------------------------------------------------------


def test_a_brand_made_of_control_characters_still_produces_a_document(hostile):
    """The report that never arrives, if this is got wrong."""
    panel, evidence, _ = hostile
    tex = tex_document(panel, evidence)

    assert HOSTILE_BRAND not in tex, "the brand reached the page unescaped"
    assert escape(HOSTILE_BRAND) in tex
    assert "(h\\#1)" in tex, "the self-naming prompt id is escaped too"


@pytest.mark.parametrize("ch", list(CONTROL))
def test_no_control_character_stands_on_its_own(hostile, ch):
    panel, evidence, _ = hostile
    tex = tex_document(panel, evidence)
    at = _unescaped(tex, ch)
    assert not at, f"{ch!r} is live at {at[:3]} in {[tex[i - 40 : i + 10] for i in at[:3]]}"


def test_the_only_live_ampersands_are_the_columns_of_the_evidence_table(hostile):
    panel, evidence, _ = hostile
    tex = tex_document(panel, evidence)
    assert len(_unescaped(tex, "&")) == len(evidence.rows())


def test_a_question_carrying_a_blank_line_does_not_put_one_on_the_page(tmp_path):
    """A blank line is `\\par`, and after a `\\\\` it is an error and no PDF.

    Prompt text is arbitrary JSON somebody wrote by hand, and it is the only
    thing on this page that can carry a line ending. Set as itself inside a
    block whose lines are joined with explicit breaks, two of them in a row end
    the document with `There's no line here to end`.
    """
    doc = json.loads(json.dumps(SUBJECT))
    doc["prompts"] = [{"id": "n1", "text": "Best ice cream\n\nin Vermont"}]
    panel, evidence, _ = _round(tmp_path, doc, {}, "Ornek")
    tex = tex_document(panel, evidence)

    assert "" not in tex.splitlines(), "a blank line reached the document"
    assert "Best ice cream in Vermont" in _spoken(tex)


def test_braces_are_balanced(hostile):
    """A stray brace from a brand name eats the rest of the document."""
    panel, evidence, _ = hostile
    tex = tex_document(panel, evidence)
    depth = 0
    for i, ch in enumerate(tex):
        if i and tex[i - 1] == "\\":
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        assert depth >= 0, f"closed one too many at {i}"
    assert depth == 0


# -- the typography this document is set under -------------------------------


def test_the_document_is_set_in_times(ornek):
    panel, evidence, _ = ornek
    assert "newtxtext" in tex_document(panel, evidence)


@pytest.mark.parametrize(
    "banned",
    [
        "tcolorbox",
        "framed",
        "mdframed",
        "\\fbox",
        "\\fcolorbox",
        "\\colorbox",
        "xcolor",
        "\\definecolor",
        "\\color",
        "\\sffamily",
        "\\textsf",
        "sfdefault",
        "hyperref",
        "\\begin{quote}",
        "\\begin{quotation}",
    ],
)
def test_nothing_that_draws_a_box_or_a_colour_is_loaded(hostile, banned):
    panel, evidence, _ = hostile
    assert banned not in tex_document(panel, evidence)


def test_there_is_no_em_dash_anywhere(hostile):
    """Not in a heading, not in a sentence, not in a caption."""
    panel, evidence, _ = hostile
    tex = tex_document(panel, evidence)
    assert "—" not in tex
    assert "–" not in tex


def test_every_question_on_the_page_ends_in_a_question_mark(hostile):
    """Headings included, which is where one goes missing.

    Read off the document rather than off a list, so a section added later is
    covered by having been added.
    """
    panel, evidence, _ = hostile
    tex = tex_document(panel, evidence)
    for line in tex.splitlines():
        if line.startswith("\\section*{") and line.rstrip().endswith("}"):
            head = line[len("\\section*{") : -1]
            asks = head.lower().startswith(("what", "why", "how", "who", "when", "where"))
            assert not asks or head.endswith("?"), head
