"""No screen and no page of ours carries an em dash, checked by reading them.

The house rule is that the dash is never used and a sentence that wants one is
split into two. It is the one mark that makes written text read as machine
written, and it was on screen: `lulu report` set its header with a dash between
the command and the ledger path, nine more commands set the same header, the
menu that offers to store a key set three lines that way, and the trail
`lulu doctor` prints set one more.

The check is on rendered output rather than on source text, for the reason the
agreement check next door is. A pattern over source stops matching the day
somebody splits an f-string while the same characters still reach the screen, so
what is scanned here is **output**: every command is driven to completion, the
document is written from the same round the terminal printed, argparse is asked
for the help of every subcommand, and the resulting text is read. A dash written
into a new sentence tomorrow is caught by that sentence being rendered, not by
anybody adding an assertion for it.

The en dash is scanned for beside the em dash. It is the same mark one keystroke
narrower, it was in the README's example table and in the range the landing page
prints, and a rule that removed only the wider one would leave the substitution
that gets reached for next.

**A dash a customer typed stays theirs.** A brand name, a question and a source
URL are arbitrary text somebody put in a subject file, and rewriting the
punctuation of a brand called `Ben & Jerry's - Vermont` would be editing their
data on the way to their own report. So the scan blanks the strings the customer
supplied before it looks, in the form the terminal prints them and in the form
`escape` gives them on a page, and everything left is ours.
`test_a_dash_a_customer_typed_reaches_the_page_and_ours_does_not` holds both
halves of that: our lines come back clean, and theirs is still on the page.

`test_the_check_catches_the_dashes_it_was_written_for` is the guard on the
guard, fed the lines this build printed before they were removed. A detector
nobody has watched reject anything may be matching nothing at all.
"""

from __future__ import annotations

import io
import json
from collections.abc import Sequence
from pathlib import Path

from lulumelon import cli
from lulumelon.cli import (
    Console,
    ablate,
    build_parser,
    collect,
    doctor,
    evidence_of,
    init,
    lift,
    questions_of,
    report,
    storage_menu,
)
from lulumelon.cli import plan as run_plan
from lulumelon.cli import usage as run_usage
from lulumelon.cli import verify as run_verify
from lulumelon.collect import (
    Brand,
    FakeProvider,
    Ledger,
    Prompt,
    ReplicaProvider,
    Usage,
    load_subject,
    replay,
    replica_prompt,
    run_round,
    without,
)
from lulumelon.collect.audit import audit
from lulumelon.latex import escape, tex_document
from lulumelon.mirror.compare import paired_difference
from lulumelon.mirror.intervals import wilson_interval
from lulumelon.mirror.report import brand_report
from lulumelon.mirror.sources import associate
from lulumelon.mirror.stability import stability_of
from lulumelon.mirror.types import Snapshot, group_runs
from lulumelon.mirror.variance import decompose, prompts_needed, runs_needed
from lulumelon.panel import Panel

HAIKU = "claude-haiku-4-5"
KEY = "sk-ant-" + "a1b2c3d4e5" * 4
GUIDE = "https://a.example/guide"


# -- the detector ------------------------------------------------------------

#: The two marks. Both are scanned for, and neither is ever written by us.
EM_DASH = "—"
EN_DASH = "–"
DASHES = (EM_DASH, EN_DASH)


def ours(text: str, theirs: Sequence[str] = ()) -> str:
    """`text` with every string the customer supplied taken out of it.

    Both forms of each string, because the same brand name reaches a terminal as
    the customer typed it and reaches a page through `escape`. Replaced with a
    space rather than deleted, so two of our own words cannot be joined into a
    line that never existed.
    """
    for supplied in theirs:
        for form in (supplied, escape(supplied)):
            text = text.replace(form, " ")
    return text


def dashes(text: str, theirs: Sequence[str] = ()) -> list[str]:
    """Every line of our own writing in `text` that carries a dash."""
    return [
        line.strip()
        for line in ours(text, theirs).splitlines()
        if any(mark in line for mark in DASHES)
    ]


def assert_clean(surfaces: dict[str, str], theirs: Sequence[str] = ()) -> None:
    found = {name: dashes(text, theirs) for name, text in surfaces.items()}
    offenders = {name: lines for name, lines in found.items() if lines}
    assert not offenders, "\n".join(
        f"{name}: {line}" for name, lines in offenders.items() for line in lines
    )


def test_the_check_catches_the_dashes_it_was_written_for():
    """The lines this build printed before they were removed, verbatim."""
    printed_before = [
        "lulu report — ./ledger",
        "  1. the OS keychain (service lulumelon) — not a file, not in the repo",
        "[empty] OS keychain (service lulumelon, account perplexity) "
        "— not available on this platform",
        "    CLO3D               5/5    100.0%      56.6% – 100.0%      1.2",
    ]
    for line in printed_before:
        assert dashes(line) == [line.strip()], line


def test_the_check_leaves_alone_the_marks_that_are_not_a_dash():
    """The hyphen and the minus sign, which these screens print everywhere."""
    for line in (
        "  " + "-" * 66,
        "  noise floor  +/-1.4 points  (icc 0.10)",
        "  anthropic/claude-haiku-4-5: charged 2 search fees over 6 calls",
        "    16.0% when cited vs 4.0% when not   +12.0 pts (+1.1..+22.9)",
        "  marx__anthropic__api__20260801T033000Z__0001",
    ):
        assert dashes(line) == [], line


# -- one round, collected and reported ---------------------------------------

SUBJECT = {
    "subject": {"id": "marx", "name": "Marx", "aliases": ["Marx Finance", "marx.finance"]},
    "prompts": [
        {"id": "m1", "text": "What is marx.finance?", "intent": "entity"},
        {"id": "m2", "text": "Agentic finance platforms in 2026", "intent": "category"},
        {"id": "m3", "text": "Reputation systems for AI trading agents", "intent": "solution"},
    ],
}

SCRIPT = {
    "What is marx.finance?": ("Marx Finance is the one asked about.",),
    "Agentic finance platforms in 2026": ("Marx Finance is one.", "nobody."),
    "Reputation systems for AI trading agents": ("nobody.",),
}

#: A subject whose every free-text field carries the mark. None of it is ours to
#: rewrite, and all of it reaches both surfaces.
THEIR_BRAND = "Ben & Jerry's — Vermont"
THEIR_QUESTIONS = (
    f"What is {THEIR_BRAND} known for?",
    "Which ice cream brands – really – lead in 2026?",
)
THEIR_SUBJECT = {
    "subject": {"id": "benjerry", "name": THEIR_BRAND, "aliases": ["B&J — VT"]},
    "prompts": [
        {"id": "b1", "text": THEIR_QUESTIONS[0]},
        {"id": "b2", "text": THEIR_QUESTIONS[1]},
    ],
}
THEIR_SCRIPT = {
    THEIR_QUESTIONS[0]: (f"{THEIR_BRAND} makes ice cream.",),
    THEIR_QUESTIONS[1]: (f"{THEIR_BRAND} leads.", "nobody."),
}


class Recorder:
    """A console whose whole output is one searchable string."""

    def __init__(self) -> None:
        self.out, self.err = io.StringIO(), io.StringIO()
        self.console = Console(out=self.out, err=self.err)

    @property
    def text(self) -> str:
        return self.out.getvalue() + self.err.getvalue()


def collected(
    console: Console, tmp_path: Path, doc: dict, script: dict, *, folder: str
) -> tuple[Ledger, str, Path]:
    """One sealed round, collected through the command a customer runs."""
    subject_path = tmp_path / f"{folder}.json"
    subject_path.write_text(json.dumps(doc), encoding="utf-8")
    ledger_dir = tmp_path / folder
    assert (
        collect(
            console,
            subject_path=subject_path,
            ledger_dir=ledger_dir,
            k=2,
            budget_usd=5.0,
            cwd=tmp_path,
            home=tmp_path / "home",
            provider="anthropic",
            model=HAIKU,
            max_searches=2,
            env={"ANTHROPIC_API_KEY": KEY},
            keychain=lambda service, account: None,
            build_provider=lambda: FakeProvider(
                name="anthropic",
                model=HAIKU,
                script=script,
                citations=(GUIDE,),
                usage=Usage(input_tokens=900, output_tokens=30, searches=2),
            ),
            clock=lambda: "2026-08-01T03:30:00Z",
        )
        == 0
    )
    store = Ledger(ledger_dir)
    return store, store.snapshots()[-1], subject_path


def reported(
    tmp_path: Path, doc: dict, script: dict, brand: str, *, folder: str
) -> dict[str, str]:
    """The terminal report and the document, from one collected round."""
    rec = Recorder()
    store, snapshot, subject_path = collected(rec.console, tmp_path, doc, script, folder=folder)
    surfaces = {f"collect, {folder}": rec.text}

    printed = Recorder()
    tex_path = tmp_path / f"{folder}.tex"
    assert (
        report(
            printed.console,
            ledger_dir=store.root,
            snapshot=snapshot,
            subject_path=subject_path,
            brand=brand,
            tex_path=tex_path,
        )
        == 0
    )
    surfaces[f"report, {folder}"] = printed.text
    surfaces[f"document, {folder}"] = tex_path.read_text(encoding="utf-8")

    for name, command in (("usage", run_usage), ("verify", run_verify)):
        rec = Recorder()
        assert command(rec.console, ledger_dir=store.root) == 0
        surfaces[f"{name}, {folder}"] = rec.text
    return surfaces


def arms(tmp_path: Path):
    """A live round and both replica arms, which is what the two gates read."""
    ledger = Ledger(tmp_path / "arms")
    prompts = [Prompt(id="p0", text="who should I use for job 0?")]
    brands = (Brand(name="marx"),)
    sources = (GUIDE, "https://b.example/list")
    drop = sources[1]

    live = run_round(
        ledger=ledger,
        provider=FakeProvider(surface="api", script={prompts[0].text: ("marx.", "nobody.")}),
        prompts=prompts,
        brands=brands,
        k=2,
        subject="marx",
    )
    base = FakeProvider(surface="api")
    full = ReplicaProvider(base=base, sources=sources)
    base.script = {replica_prompt(prompts[0].text, sources): ("marx.", "nobody.")}
    held = run_round(
        ledger=ledger, provider=full, prompts=prompts, brands=brands, k=2, subject="marx"
    )
    other = FakeProvider(surface="api")
    arm = ReplicaProvider(base=other, sources=without(sources, drop))
    other.script = {replica_prompt(prompts[0].text, arm.sources): ("nobody.", "nobody.")}
    dropped = run_round(
        ledger=ledger, provider=arm, prompts=prompts, brands=brands, k=2, subject="marx"
    )
    return ledger, live.snapshot_id, held.snapshot_id, dropped.snapshot_id, sources, drop


# -- the commands ------------------------------------------------------------


def test_no_command_prints_a_dash(tmp_path, monkeypatch):
    """Every command a customer can run, driven to completion.

    `init` is driven to its menu and refused there. The three lines that carried
    a dash are the menu, and the step after it writes a key into the machine's
    own keychain, which a test suite has no business doing. The keychain is
    forced on so the option that only exists on a Mac is printed and read.
    """
    surfaces = reported(tmp_path, SUBJECT, SCRIPT, "Marx", folder="marx")

    monkeypatch.setattr(cli, "keychain_available", lambda *a: True)
    menu = Recorder()
    assert (
        init(
            menu.console,
            ask=lambda prompt: "9",
            secret=lambda prompt: KEY,
            cwd=tmp_path,
            home=tmp_path / "home",
            provider="anthropic",
        )
        == 1
    )
    assert not (tmp_path / ".env").exists(), "the menu was refused, so nothing was stored"
    surfaces["init, at the menu"] = menu.text
    surfaces["init, the menu itself"] = "\n".join(
        f"  {i}. {line}" for i, (_, line) in enumerate(storage_menu(tmp_path, tmp_path), 1)
    )

    for label, offline in (("offline", True), ("with a key", False)):
        rec = Recorder()
        doctor(
            rec.console,
            cwd=tmp_path,
            home=tmp_path / "nowhere",
            provider="anthropic",
            offline=offline,
            env={},
            keychain=lambda service, account: None,
        )
        surfaces[f"doctor, {label}"] = rec.text

    rec = Recorder()
    assert run_plan(rec.console, prompts=40, half_width=0.05, brands=5, days=30) == 0
    surfaces["plan"] = rec.text

    ledger, live, held, dropped, sources, drop = arms(tmp_path)

    gated = Recorder()
    ablate(
        gated.console, ledger_dir=ledger.root, live=live, replica=held, brand="marx", margin=0.05
    )
    assert gated.text
    surfaces["ablate"] = gated.text

    for label, with_live in (("gated", live), ("ungated", None)):
        rec = Recorder()
        lift(
            rec.console,
            ledger_dir=ledger.root,
            held=held,
            dropped=dropped,
            brand="marx",
            source=drop,
            sources=sources,
            margin=0.05,
            live=with_live,
        )
        assert rec.text
        surfaces[f"lift, {label}"] = rec.text

    assert_clean(surfaces)


def test_no_help_screen_prints_a_dash():
    """Every `--help` argparse can be asked for, including each subcommand."""
    parser = build_parser()
    surfaces = {"lulu --help": parser.format_help()}
    for name, sub in parser._subparsers._group_actions[0].choices.items():
        surfaces[f"lulu {name} --help"] = sub.format_help()
    assert len(surfaces) > 1, "the parser stopped offering subcommands"
    assert_clean(surfaces)


# -- the sections no command reaches yet -------------------------------------


def test_no_report_section_prints_a_dash(tmp_path):
    """The blocks a panel can hold that `lulu report` does not hand it today.

    Access and sources are rendered here because nothing on the command line
    passes an audit or a source association yet, and both are prose. A section
    that only exists in a constructor is still a section a customer will read
    the moment it is wired up, and it is the wiring that is missing, not the
    words.
    """
    rec = Recorder()
    store, snapshot, subject_path = collected(
        rec.console, tmp_path, SUBJECT, SCRIPT, folder="sections"
    )
    subject = load_subject(subject_path)
    played = replay(store, snapshot)
    records = list(store.read(snapshot))
    grouped = Snapshot(label=snapshot, samples=group_runs(played.runs))
    scored = brand_report(grouped, "Marx", self_naming=subject.self_naming("Marx"))

    blocked = audit(
        "https://one.example",
        fetch=lambda url: {
            "https://one.example/robots.txt": (200, "User-agent: *\nDisallow: /\n"),
            "https://one.example/llms.txt": (0, ""),
        }.get(url, (200, "<html><title>t</title><body>x</body></html>")),
    )
    open_site = audit(
        "https://two.example",
        fetch=lambda url: {
            "https://two.example/robots.txt": (200, "User-agent: *\nAllow: /\n"),
            "https://two.example/llms.txt": (200, "x"),
        }.get(url, (200, "<html><title>t</title><body>x</body></html>")),
    )

    whole = Panel(
        report=scored,
        sources=(
            associate(grouped, "Marx", GUIDE),
            associate(grouped, "Marx", "https://z.example/never"),
        ),
        audit=blocked,
        dropped_runs=1,
        surfaces=played.surfaces,
        questions=questions_of(subject, played, records, subject.self_naming("Marx")),
    )
    variance = decompose([[1.0, 0.0], [0.0, 0.0]])

    assert_clean(
        {
            "panel, every section": whole.as_text(),
            "document, every section": tex_document(whole, evidence_of(records, played)),
            "site audit, blocked": blocked.as_text(),
            "site audit, open": open_site.as_text(),
            "brand report": scored.as_text(),
            "brand report advice": scored.advice(0.02),
            "wilson interval": wilson_interval(1, 5).as_text(),
            "paired difference": paired_difference(
                {"p0": [1.0, 0.0]}, {"p0": [0.0, 0.0]}, resamples=200
            ).as_text(),
            "stability": stability_of([["marx"], ["marx", "numerai"]]).as_text(),
            "variance split": variance.as_text(),
            "runs needed": runs_needed(variance, 0.05, n_prompts=2).as_text(),
            "prompts needed": prompts_needed(variance, 0.05, k_runs=2).as_text(),
        }
    )


# -- whose dash is it? -------------------------------------------------------


def test_a_dash_a_customer_typed_reaches_the_page_and_ours_does_not(tmp_path):
    """Their punctuation is data, ours is writing, and the two are told apart.

    Both halves are asserted. Blanking their strings and finding nothing proves
    our lines are clean; scanning the same output without blanking anything and
    finding their dash proves it was really there, and that the exemption is
    doing work rather than describing an empty set.
    """
    theirs = (THEIR_BRAND, "B&J — VT", *THEIR_QUESTIONS)
    surfaces = reported(tmp_path, THEIR_SUBJECT, THEIR_SCRIPT, THEIR_BRAND, folder="benjerry")

    assert_clean(surfaces, theirs)

    for name in ("report, benjerry", "document, benjerry"):
        assert dashes(surfaces[name]), f"{name} lost the customer's own punctuation"
