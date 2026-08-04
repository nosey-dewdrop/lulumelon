"""No screen prints `1` with a plural noun beside it, checked by reading the screen.

`searchs` reached a customer on the first real run of the command that prices a
call, and four more surfaces then printed `1 calls`, `1 searches` and
`1 search fees` on the night the first round was collected. The defect is
cheap, it is on the first line a stranger reads, and it is about money and
evidence, which is the material this library asks to be trusted on.

So the check is not a regex over the source. Source text can be rearranged
until a pattern stops matching while the same words still reach the screen, and
a rule written that way passes hardest on the day somebody splits a long
f-string. What is scanned here is **output**: every command below is driven to
completion with its counts forced to one, every report is rendered, and the
resulting text is read for a bare `1` followed by a word that is plural.

That form catches the next one too, which the alternative does not. A new line
printing `1 rounds` fails this without anybody adding an assertion for it,
because the surface it lives on is already being rendered here.

`test_the_check_catches_the_defect_it_was_written_for` is the guard on the
guard. A detector nobody has seen reject anything is a detector that might be
matching nothing at all, so the five lines from the incident are fed to it and
it has to flag every one.
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

import pytest

from lulumelon.cli import Console, ablate, collect, doctor, lift
from lulumelon.cli import plan as run_plan
from lulumelon.cli import usage as run_usage
from lulumelon.cli import verify as run_verify
from lulumelon.collect import (
    UNSEARCHED_SURFACE,
    Brand,
    Budget,
    FakeProvider,
    Ledger,
    Prompt,
    Record,
    ReplicaProvider,
    Usage,
    replay,
    replica_prompt,
    run_round,
    without,
)
from lulumelon.collect.audit import audit
from lulumelon.mirror.ablation import replica_gate
from lulumelon.mirror.compare import paired_difference
from lulumelon.mirror.lift import source_effect
from lulumelon.mirror.report import brand_report
from lulumelon.mirror.sources import associate
from lulumelon.mirror.types import Run, snapshot_from_runs
from lulumelon.mirror.variance import decompose, prompts_needed, runs_needed
from lulumelon.panel import Panel
from lulumelon.plan import Comparison, critical_value, draws_needed, total_variance
from lulumelon.prices import price_for
from lulumelon.text import counted
from lulumelon.usage import spend_of

FIXTURES = Path(__file__).resolve().parent / "fixtures"

#: A three-record round written before rounds sealed their own length. Its
#: first line alone is the one-record version, which is the only way to reach
#: the "length never sealed" line with a count of one.
V2_SNAPSHOT = "ornek__perplexity__api__20260801T020000Z__0002"

KEY = "sk-ant-" + "a1b2c3d4e5" * 4
HAIKU = "claude-haiku-4-5"

SUBJECT = {
    "subject": {"id": "ornek", "name": "Ornek", "aliases": ["ornek.com"]},
    "prompts": [{"id": "m1", "text": "What is ornek.com?"}],
}


# -- the detector ------------------------------------------------------------

#: A count of exactly one and the two words after it. Two, because a counted
#: noun here is a phrase as often as a word and the plural lands on the end of
#: it: `1 search fees` is the defect, and reading only the first word would
#: stop at `search` and pass. The lookbehind keeps out the places a `1` is not
#: a count at all: `v1`, `[1]`, `$1`, `k=1`, `0.1`, a date, the bracketed
#: source index the lift command prints.
_A_COUNT_OF_ONE = re.compile(
    r"(?<![\w.,$\[/-])1 ([A-Za-z][A-Za-z-]*)(?: ([A-Za-z][A-Za-z-]*))?"
)

#: Words that close a noun phrase. The scan stops at one of these, so nothing
#: past the end of the phrase is read as the noun that had to agree.
_ENDS_THE_PHRASE = frozenset(
    """a an the of at in on over per to for from and or with by that which
    was were is are had have would will could cannot no not so than then""".split()
)

#: Words ending in `s` that these screens print inside that window without
#: being plural nouns. Both are verbs following a singular subject, which is
#: the shape a word list cannot tell from a noun. Kept short and literal: every
#: entry is a word one of the surfaces below actually prints, so the list is
#: evidence rather than a guess about English.
_NOT_A_PLURAL_NOUN = frozenset({"describes", "spends", "ms"})


def disagreements(text: str) -> list[str]:
    """Every line where a count of one is followed by a plural noun."""
    bad = []
    for line in text.splitlines():
        for match in _A_COUNT_OF_ONE.finditer(line):
            for word in (w for w in match.groups() if w):
                lowered = word.lower()
                if lowered in _ENDS_THE_PHRASE:
                    break
                if word.endswith("s") and lowered not in _NOT_A_PLURAL_NOUN:
                    bad.append(line.strip())
                    break
    return bad


def assert_agrees(surfaces: dict[str, str]) -> None:
    found = {name: disagreements(text) for name, text in surfaces.items()}
    offenders = {name: lines for name, lines in found.items() if lines}
    assert not offenders, "\n".join(
        f"{name}: {line}" for name, lines in offenders.items() for line in lines
    )


class Recorder:
    """A console whose whole output is one searchable string."""

    def __init__(self) -> None:
        self.out, self.err = io.StringIO(), io.StringIO()
        self.console = Console(out=self.out, err=self.err)

    @property
    def text(self) -> str:
        return self.out.getvalue() + self.err.getvalue()


def test_the_check_catches_the_defect_it_was_written_for():
    """The five lines from the incident, verbatim, all flagged.

    Without this the suite could go green on a detector that matches nothing,
    which is the failure mode of every check written as a pattern.
    """
    seen_tonight = [
        "1 calls recorded: 1 answered, 0 failed",
        "anthropic/claude-haiku-4-5-20251001: charged 1 search fees over 1 call",
        "intact  diagnostic__x__0001  1 calls sealed, 1 answered, 0 failed",
        "arm  with the search tool, capped at 1 searches a call",
        "plus up to 1 searches at $10 per thousand searches",
    ]
    for line in seen_tonight:
        assert disagreements(line) == [line], line


def test_the_detector_does_not_flag_a_one_that_is_not_a_count():
    """The shapes a `1` takes on these screens without being a plural beside it."""
    for line in (
        "  [1] https://a.example/guide",
        "  this build writes schema v1 records",
        "  icc 0.10   k=1     385 calls",
        "  it worked, in 1 ms",
        "  1 call recorded: 1 answered, 0 failed",
        "  reported by 0 of 1 answered call",
        "  asking each of 1 prompt once a day for 1 day spends 1 call",
        "  An interval over 1 cluster describes this round, not the question.",
    ):
        assert disagreements(line) == [], line


# -- fixtures ----------------------------------------------------------------


def subject_file(tmp_path: Path) -> Path:
    path = tmp_path / "ornek.json"
    path.write_text(json.dumps(SUBJECT), encoding="utf-8")
    return path


def one_call_ledger(tmp_path: Path) -> tuple[Ledger, str]:
    """A sealed round of exactly one call, which is what a check call is."""
    ledger = Ledger(tmp_path / "ledger")
    snapshot = ledger.next_snapshot_id("ornek", "anthropic", "api")
    ledger.append(
        snapshot,
        Record(
            snapshot_id=snapshot,
            seq=0,
            prompt_id="m1",
            repeat=0,
            engine="anthropic",
            surface="api",
            model=HAIKU,
            asked_at="2026-08-01T03:30:00Z",
            status="ok",
            latency_ms=1100,
            answer_text="Ornek does.",
            brands=("Ornek",),
            citations=("https://a.example/guide",),
            provider="anthropic",
            input_tokens=900,
            output_tokens=30,
            searches=1,
        ),
    )
    ledger.seal(snapshot, asked=1, ok=1, errors=0, at="2026-08-01T03:30:01Z")
    return ledger, snapshot


def one_record_unsealed(tmp_path: Path) -> Ledger:
    """The v2 fixture cut to its first line: one record, no seal, chain intact.

    Truncated rather than rewritten, because the record carries its own name
    and its own hash and a round assembled by hand would not verify.
    """
    directory = tmp_path / "archive"
    directory.mkdir(parents=True)
    path = directory / f"{V2_SNAPSHOT}.jsonl"
    lines = (FIXTURES / f"{V2_SNAPSHOT}.jsonl").read_text(encoding="utf-8").splitlines()
    path.write_text(lines[0] + "\n", encoding="utf-8")
    return Ledger(directory)


def one_broken_record(tmp_path: Path) -> Ledger:
    """The same one-record round with its answer edited, which is one problem."""
    ledger = one_record_unsealed(tmp_path / "broken")
    path = ledger.path_of(V2_SNAPSHOT)
    row = json.loads(path.read_text(encoding="utf-8"))
    row["answer_text"] = "something else entirely"
    path.write_text(
        json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    return ledger


def one_prompt_rounds(tmp_path: Path):
    """A live round and both replica arms over one shared prompt."""
    ledger = Ledger(tmp_path / "arms")
    prompts = [Prompt(id="p0", text="who should I use for job 0?")]
    brands = (Brand(name="ornek"),)
    sources = ("https://a.example/guide", "https://b.example/list")
    drop = sources[1]

    live = run_round(
        ledger=ledger,
        provider=FakeProvider(surface="api", script={prompts[0].text: ("ornek.", "nobody.")}),
        prompts=prompts,
        brands=brands,
        k=2,
        subject="ornek",
    )
    base = FakeProvider(surface="api")
    full = ReplicaProvider(base=base, sources=sources)
    base.script = {replica_prompt(prompts[0].text, sources): ("ornek.", "nobody.")}
    held = run_round(
        ledger=ledger, provider=full, prompts=prompts, brands=brands, k=2, subject="ornek"
    )
    other = FakeProvider(surface="api")
    arm = ReplicaProvider(base=other, sources=without(sources, drop))
    other.script = {replica_prompt(prompts[0].text, arm.sources): ("nobody.", "nobody.")}
    dropped = run_round(
        ledger=ledger, provider=arm, prompts=prompts, brands=brands, k=2, subject="ornek"
    )
    return ledger, live.snapshot_id, held.snapshot_id, dropped.snapshot_id, sources, drop


# -- the commands ------------------------------------------------------------


def test_the_commands_never_print_a_one_beside_a_plural_noun(tmp_path):
    """Every command driven to completion with its counts at one.

    `collect` twice: once with a single repeat, which is refused after the
    screen that sizes the round has already been printed, and once as a round
    that actually runs. Both screens are output a person sees, so both are read
    here.
    """
    surfaces: dict[str, str] = {}

    asked = Recorder()
    with pytest.raises(ValueError, match="cannot support an interval"):
        collect(
            asked.console,
            subject_path=subject_file(tmp_path),
            ledger_dir=tmp_path / "k1",
            k=1,
            budget_usd=5.0,
            cwd=tmp_path,
            home=tmp_path / "home",
            provider="anthropic",
            model=HAIKU,
            max_searches=1,
            env={"ANTHROPIC_API_KEY": KEY},
            keychain=lambda service, account: None,
            build_provider=lambda: FakeProvider(name="anthropic", model=HAIKU),
            clock=lambda: "2026-08-01T03:30:00Z",
        )
    surfaces["collect, one repeat"] = asked.text

    collected = Recorder()
    assert (
        collect(
            collected.console,
            subject_path=subject_file(tmp_path),
            ledger_dir=tmp_path / "round",
            k=2,
            budget_usd=5.0,
            cwd=tmp_path,
            home=tmp_path / "home",
            provider="anthropic",
            model=HAIKU,
            max_searches=1,
            env={"ANTHROPIC_API_KEY": KEY},
            keychain=lambda service, account: None,
            build_provider=lambda: FakeProvider(
                name="anthropic",
                model=HAIKU,
                usage=Usage(input_tokens=900, output_tokens=30, searches=1),
            ),
            clock=lambda: "2026-08-01T03:30:00Z",
        )
        == 0
    )
    surfaces["collect, one prompt"] = collected.text

    ledger, snapshot = one_call_ledger(tmp_path)
    for name, command in (("usage", run_usage), ("verify", run_verify)):
        rec = Recorder()
        assert command(rec.console, ledger_dir=ledger.root) == 0
        surfaces[f"{name}, one call"] = rec.text

    unsealed = one_record_unsealed(tmp_path)
    rec = Recorder()
    assert run_verify(rec.console, ledger_dir=unsealed.root) == 0
    surfaces["verify, one unsealed record"] = rec.text

    broken = one_broken_record(tmp_path)
    for name, command in (("usage", run_usage), ("verify", run_verify)):
        rec = Recorder()
        assert command(rec.console, ledger_dir=broken.root) == 1
        surfaces[f"{name}, one problem"] = rec.text

    for label, days in (("thirty days", 30), ("one day", 1)):
        rec = Recorder()
        assert run_plan(rec.console, prompts=1, half_width=0.05, brands=1, days=days) == 0
        surfaces[f"plan, one prompt, {label}"] = rec.text

    keyed = Recorder()
    assert (
        doctor(
            keyed.console,
            cwd=tmp_path,
            home=tmp_path / "home",
            provider="anthropic",
            offline=True,
            env={"ANTHROPIC_API_KEY": "x"},
            keychain=lambda service, account: None,
        )
        == 0
    )
    surfaces["doctor, a one-character key"] = keyed.text

    assert_agrees(surfaces)


def test_the_two_causal_commands_never_print_a_one_beside_a_plural_noun(tmp_path):
    """`ablate` and `lift` over a single shared prompt.

    Split from the rest because they need three collected rounds rather than
    one, and because their screens are where the counts are smallest: a paired
    prompt count, an unpaired one, and the calls a design still owes.
    """
    ledger, live, held, dropped, sources, drop = one_prompt_rounds(tmp_path)
    surfaces: dict[str, str] = {}

    gated = Recorder()
    ablate(
        gated.console,
        ledger_dir=ledger.root,
        live=live,
        replica=held,
        brand="ornek",
        margin=0.05,
    )
    surfaces["ablate, one paired prompt"] = gated.text

    for label, with_live in (("gated", live), ("ungated", None)):
        rec = Recorder()
        lift(
            rec.console,
            ledger_dir=ledger.root,
            held=held,
            dropped=dropped,
            brand="ornek",
            source=drop,
            sources=sources,
            margin=0.05,
            live=with_live,
        )
        surfaces[f"lift, one paired prompt, {label}"] = rec.text

    assert_agrees(surfaces)


# -- the reports -------------------------------------------------------------


def one_prompt_snapshot():
    runs = [
        Run(
            prompt_id="p0",
            engine="anthropic",
            model=HAIKU,
            asked_at=f"2026-08-01T0{i}:00:00Z",
            brands=("ornek",) if i == 0 else ("numerai",),
            citations=("https://a.example/guide",) if i == 0 else (),
        )
        for i in range(2)
    ]
    return snapshot_from_runs("one-prompt", runs)


def two_prompt_snapshot():
    """Two prompts, so one of them can be excluded and one can still be scored."""
    return snapshot_from_runs(
        "two-prompt",
        [
            Run(
                prompt_id=f"p{p}",
                engine="anthropic",
                model=HAIKU,
                asked_at=f"2026-08-01T0{i}:00:00Z",
                brands=("ornek",) if i == 0 else ("numerai",),
            )
            for p in range(2)
            for i in range(2)
        ],
    )


def test_the_reports_never_print_a_one_beside_a_plural_noun(tmp_path):
    """Every renderer, at the smallest design each of them accepts.

    These are the same strings the commands print, reached directly so that a
    report which no command currently renders at a count of one is still read.
    """
    snapshot = one_prompt_snapshot()
    report = brand_report(snapshot, "ornek", self_naming=(), resamples=200)
    excluded = brand_report(
        two_prompt_snapshot(), "ornek", self_naming=("p0",), resamples=200
    )
    price = price_for("anthropic", HAIKU)
    assert price is not None

    site = audit(
        "https://one.example",
        fetch=lambda url: {
            "https://one.example/robots.txt": (200, "User-agent: *\nAllow: /\n"),
            "https://one.example/llms.txt": (200, "x"),
        }.get(url, (200, "<html><title>t</title><body>x</body></html>")),
    )

    budget = Budget(price=price, limit_usd=5.0, max_searches=1, max_output_tokens=1024)
    budget.charge(
        FakeProvider(usage=Usage(input_tokens=900, output_tokens=30, searches=1)).ask("q")
    )

    silent = Record(
        snapshot_id="ornek__anthropic__api__20260801T033000Z__0001",
        seq=0,
        prompt_id="m1",
        repeat=0,
        engine="anthropic",
        surface="api",
        model=HAIKU,
        asked_at="2026-08-01T03:30:00Z",
        status="ok",
        latency_ms=1100,
        answer_text="Ornek does.",
        brands=("Ornek",),
        citations=(),
        provider="anthropic",
    )
    from dataclasses import replace as _replace

    variance = decompose([[1.0, 0.0]])
    z = critical_value(0.95, 1, family=True)

    surfaces = {
        "brand report": report.as_text(),
        "brand report advice": report.advice(0.02),
        "brand report, one prompt excluded": excluded.as_text(),
        "panel": Panel(report=report, audit=site, dropped_runs=1).as_text(),
        "panel, one prompt excluded": Panel(report=excluded).as_text(),
        "site audit": site.as_text(),
        "paired difference": paired_difference(
            {"p0": [1.0, 0.0]}, {"p0": [0.0, 0.0]}, resamples=200
        ).as_text(),
        "source association": associate(snapshot, "ornek", "https://a.example/guide").as_text(),
        "source withheld": associate(
            snapshot_from_runs(
                "two",
                [
                    Run(
                        prompt_id=f"p{p}",
                        engine="anthropic",
                        model=HAIKU,
                        asked_at="2026-08-01T00:00:00Z",
                        brands=("ornek",) if i % 2 else (),
                        citations=("https://a.example/guide",) if i < 2 else (),
                    )
                    for p in range(1)
                    for i in range(4)
                ],
            ),
            "ornek",
            "https://a.example/guide",
        ).as_text(),
        "source no contrast": associate(snapshot, "ornek", "https://z.example/never").as_text(),
        "runs unreachable": runs_needed(variance, 0.0001, n_prompts=1).as_text(),
        "runs above max_k": runs_needed(variance, 0.2, n_prompts=1, max_k=0).as_text(),
        "prompts above max_n": prompts_needed(variance, 0.2, k_runs=1, max_n=0).as_text(),
        "design reachable": draws_needed(1, 0.05, z, total_variance(0.5), 0.0).as_text(),
        "design unreachable": draws_needed(1, 0.05, z, total_variance(0.5), 0.9).as_text(),
        "daily comparison": Comparison(
            designed_calls=1, daily_calls=1, days=1, scans_per_day=1, n_prompts=1
        ).as_text(),
        "gate, undecided": replica_gate(
            {"p0": [1.0, 0.0], "p1": [1.0, 1.0]},
            {"p0": [1.0, 1.0], "p1": [0.0, 0.0]},
            margin=0.3,
            resamples=200,
        ).as_text(),
        "source effect, one unpaired prompt": source_effect(
            {"p0": [1.0, 0.0], "p1": [1.0, 1.0], "p2": [1.0, 1.0]},
            {"p0": [1.0, 1.0], "p1": [0.0, 0.0]},
            source="https://a.example/guide",
            margin=0.3,
            gate=None,
            resamples=200,
        ).as_text(),
        "budget": budget.as_text(),
        "spend, one silent call": spend_of([silent]).as_text(),
        "spend, one unsearched call": spend_of(
            [_replace(silent, surface=UNSEARCHED_SURFACE)]
        ).as_text(),
        "spend, one failed call": spend_of([_replace(silent, status="error")]).as_text(),
        "spend, one unpriced call": spend_of([_replace(silent, model="claude-opus-9")]).as_text(),
        "replay": replay(*one_call_ledger(tmp_path)).as_text(),
    }
    assert_agrees(surfaces)


def test_the_ledger_never_reports_a_one_beside_a_plural_noun(tmp_path):
    """The problems `verify` prints, each raised by a round of one.

    Reached through the ledger rather than through a fixture of expected
    strings, so a message reworded upstream is still read here.
    """
    ledger, snapshot = one_call_ledger(tmp_path)
    path = ledger.path_of(snapshot)
    lines = path.read_text(encoding="utf-8").splitlines()

    surfaces = {}

    # One record appended after the round said it was over.
    spliced = tmp_path / "spliced"
    spliced.mkdir()
    (spliced / path.name).write_text("\n".join(lines + [lines[0]]) + "\n", encoding="utf-8")
    surfaces["a record after the seal"] = "\n".join(Ledger(spliced).verify(snapshot))

    # One line nobody can read, so the seal's count cannot be checked.
    torn = tmp_path / "torn"
    torn.mkdir()
    (torn / path.name).write_text(
        "\n".join(["{not json at all", lines[1]]) + "\n", encoding="utf-8"
    )
    surfaces["a line that cannot be read"] = "\n".join(Ledger(torn).verify(snapshot))

    # A sealed round refuses a further call, and says how long it already is.
    with pytest.raises(ValueError) as sealed:
        ledger.append(snapshot, list(ledger.read(snapshot))[0])
    surfaces["a sealed round"] = str(sealed.value)

    assert_agrees(surfaces)


# -- the helper itself -------------------------------------------------------


def test_the_helper_agrees_on_the_number_it_prints():
    assert counted(1, "call") == "1 call"
    assert counted(0, "call") == "0 calls"
    assert counted(2, "call") == "2 calls"
    assert counted(1, "search", "searches") == "1 search"
    assert counted(3, "search", "searches") == "3 searches"
    assert counted(1, "answered call") == "1 answered call"


def test_the_helper_pluralises_on_the_digits_it_shows():
    """`1.0 runs` is right and `1.0 run` is not, so the word follows the format."""
    assert counted(1.0, "run", fmt=".1f") == "1.0 runs"
    assert counted(1.4, "run", fmt=".0f") == "1 run"
    assert counted(1000, "token", fmt=",") == "1,000 tokens"


def test_the_helper_refuses_to_guess_a_plural_it_would_get_wrong():
    """The guess that produced `searchs` raises instead of printing."""
    for singular in ("search", "fix", "entry", "bus", "dish"):
        with pytest.raises(ValueError, match="does not pluralise"):
            counted(2, singular)


def test_the_helper_still_takes_the_regular_case_in_one_argument():
    """A rule that costs a second argument every time gets bypassed."""
    for singular, plural in (("call", "calls"), ("day", "days"), ("prompt", "prompts")):
        assert counted(2, singular) == f"2 {plural}"
