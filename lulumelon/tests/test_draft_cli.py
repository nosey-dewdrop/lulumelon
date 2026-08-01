"""One domain in, a measured question set out, with nothing spent in these tests.

`lulu draft` is the command that makes the acceptance gate true: the customer
types a url and nothing else. Everything under test here is about what that
costs them if it goes wrong, so the properties asserted hardest are the three
that would be invisible in a screenshot of a working run.

**The paid round is refused when there is nobody to screen on.** With no rival
declared, the only name available is the subject's own, and screening a set on
the subject's own mentions keeps the questions it scored well on and drops the
rest. That is score inflation with an audit trail, and it has to be a refusal
rather than a fallback.

**The draws follow the floor.** They are derived on the way past, so a stricter
floor is a bigger bill and the bill is printed before the money moves.

**Nothing that died disappears.** A candidate dropped by a gate, an entry the
model returned unreadable, a page that would not load: all three end up in the
draft ledger beside the subject file, because a set of nine questions that
started as forty is a different object from one that started as nine.

The whole path runs against a fake site and the deterministic stub, so the
network is closed and no key is spent.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from pathlib import Path

from lulumelon.cli import DRAFT_UNMEASURED, Console, draft
from lulumelon.collect import Answer, Ledger, Usage, replay
from lulumelon.collect.subject import load_subject

KEY = "sk-ant-" + "a1b2c3d4e5" * 4

HOME = "https://ornek.com"
TARIFELER = "https://ornek.com/tarifeler"

METERED = Usage(input_tokens=10046, output_tokens=210, searches=1)


def page(title: str, body: str, links: list[str] | None = None) -> str:
    hrefs = "".join(f'<a href="{href}">x</a>' for href in links or [])
    return f"<html><head><title>{title}</title></head><body>{hrefs}<p>{body}</p></body></html>"


SITE = {
    HOME: page("Ornek", "Insaat riskini gunluk fiyatlandiriyoruz.", [TARIFELER]),
    TARIFELER: page("Tarifeler", "Sigortacilarimiz her hakedis dosyasini inceler."),
}


def fetcher(pages: dict[str, str]):
    def fetch(url: str) -> tuple[int, str]:
        key = url.rstrip("/") or url
        return (200, pages[key]) if key in pages else (404, "")

    return fetch


def reply(*entries: dict) -> str:
    return json.dumps(list(entries))


GROUNDED = {
    "question": "Which lenders price construction risk daily?",
    "source": HOME,
    "evidence": "Insaat riskini gunluk fiyatlandiriyoruz.",
}
SECOND = {
    "question": "Who reviews a progress claim before funds release?",
    "source": TARIFELER,
    "evidence": "Sigortacilarimiz her hakedis dosyasini inceler.",
}
INVENTED = {
    "question": "Which lenders fund in one day?",
    "source": HOME,
    "evidence": "we guarantee same day funding",
}
NAMED = {
    "question": "What does Ornek charge?",
    "source": HOME,
    "evidence": "Insaat riskini gunluk fiyatlandiriyoruz.",
}


@dataclass
class Engine:
    """Answers the proposal call one way and every question another.

    One object rather than two, because the command builds a single provider
    and uses it for both, and a test that injected two would not notice if that
    ever stopped being true.
    """

    proposals: str = ""
    answer: str = "Numerai and Kalshi are the usual names."
    name: str = "anthropic"
    surface: str = "api"
    model: str = "claude-opus-5"
    asked: list[str] = field(default_factory=list)

    def ask(self, prompt: str) -> Answer:
        self.asked.append(prompt)
        proposing = "Reply with a JSON array" in prompt
        return Answer(
            text=self.proposals if proposing else self.answer,
            model=self.model,
            surface=self.surface,
            latency_ms=5,
            usage=METERED,
        )

    @property
    def draws(self) -> int:
        return sum(1 for p in self.asked if "Reply with a JSON array" not in p)


class Recorder:
    def __init__(self) -> None:
        self.out, self.err = io.StringIO(), io.StringIO()
        self.console = Console(out=self.out, err=self.err)

    @property
    def text(self) -> str:
        return self.out.getvalue() + self.err.getvalue()


def run(rec: Recorder, tmp_path: Path, *, engine: Engine | None = None, **over):
    engine = engine or Engine(proposals=reply(GROUNDED, SECOND))
    kw = dict(
        site=HOME,
        out=tmp_path / "subjects" / "ornek.json",
        floor=0.5,
        budget_usd=5.0,
        cwd=tmp_path,
        home=tmp_path / "home",
        ledger_dir=tmp_path / "ledger",
        rivals=["Numerai"],
        provider="anthropic",
        model="claude-opus-5",
        fetch=fetcher(SITE),
        env={"ANTHROPIC_API_KEY": KEY},
        keychain=lambda service, account: None,
        build_provider=lambda: engine,
        clock=lambda: "2026-08-02T03:30:00Z",
    )
    kw.update(over)
    return draft(rec.console, **kw), engine


def written(tmp_path: Path) -> tuple[dict, dict]:
    out = tmp_path / "subjects" / "ornek.json"
    return (
        json.loads(out.read_text(encoding="utf-8")),
        json.loads(out.with_suffix(".draft.json").read_text(encoding="utf-8")),
    )


# -- the cheapest stop: read the site and spend nothing ----------------------


def test_harvest_only_reads_the_site_and_calls_nothing(tmp_path):
    rec = Recorder()
    code, engine = run(rec, tmp_path, harvest_only=True)
    assert code == 0
    assert engine.asked == []
    assert "nothing was spent" in rec.text
    assert not (tmp_path / "subjects" / "ornek.json").exists()


def test_a_site_that_cannot_be_read_stops_before_a_key_is_looked_for(tmp_path):
    rec = Recorder()
    code, engine = run(rec, tmp_path, fetch=fetcher({}))
    assert code == 1
    assert engine.asked == []
    assert "nothing was read" in rec.text


# -- the floor decides the draws, and the bill is printed first --------------


def test_the_draw_count_is_derived_from_the_floor_and_shown(tmp_path):
    rec = Recorder()
    run(rec, tmp_path, floor=0.5)
    assert "4 draws each" in rec.text
    assert "derived from a floor of 0.50" in rec.text


def test_a_stricter_floor_buys_more_draws(tmp_path):
    rec = Recorder()
    _, engine = run(rec, tmp_path, floor=0.75)
    assert "12 draws each" in rec.text
    assert engine.draws == 24, "two questions, twelve draws each"


def test_the_worst_case_is_on_screen_before_anything_is_asked(tmp_path):
    rec = Recorder()
    run(rec, tmp_path, harvest_only=False, dry_run=True)
    before, _, after = rec.text.partition("PROPOSING")
    assert "BEFORE ANYTHING IS SPENT" in before
    assert "is the most this can cost" in before
    assert after, "the proposal call happens after the price is printed"


# -- the refusal that keeps a score honest ----------------------------------


def test_without_a_rival_the_paid_round_is_refused_and_says_why(tmp_path):
    rec = Recorder()
    code, engine = run(rec, tmp_path, rivals=[])
    assert code == DRAFT_UNMEASURED
    assert engine.draws == 0, "not one draw was bought"
    assert "deleting the evidence against it" in rec.text
    assert "--rivals" in rec.text


def test_the_unmeasured_file_says_that_nothing_measured_it(tmp_path):
    rec = Recorder()
    run(rec, tmp_path, rivals=[])
    subject, ledger = written(tmp_path)
    assert len(subject["prompts"]) == 2, "the free gates still produced a set"
    assert ledger["measured"] == []
    assert ledger["noise_floor"] is None
    assert "never measured" in rec.text


def test_a_dry_run_screens_for_free_and_buys_no_draws(tmp_path):
    rec = Recorder()
    code, engine = run(rec, tmp_path, dry_run=True)
    assert code == DRAFT_UNMEASURED
    assert engine.draws == 0
    assert len(engine.asked) == 1, "one proposal call and nothing else"
    assert written(tmp_path)[1]["measured"] == []


# -- the full path ----------------------------------------------------------


def test_a_full_draft_measures_the_survivors_and_writes_both_files(tmp_path):
    rec = Recorder()
    code, engine = run(rec, tmp_path)
    assert code == 0
    assert engine.draws == 8, "two questions, four draws each"

    subject, ledger = written(tmp_path)
    assert [p["id"] for p in subject["prompts"]] == ["p1", "p2"]
    assert all(p["source"] and p["evidence"] for p in subject["prompts"])
    assert ledger["screening_snapshot"]
    assert {m["verdict"] for m in ledger["measured"]} == {"carries"}
    assert ledger["noise_floor"] is not None


def test_the_file_it_writes_is_a_file_this_build_can_read_back(tmp_path):
    """The round trip. A draft that produces a file `lulu collect` refuses is
    a draft that produced nothing, and the two look identical until somebody
    tries to spend money on it."""
    rec = Recorder()
    run(rec, tmp_path)
    subject = load_subject(tmp_path / "subjects" / "ornek.json")
    assert subject.name == "ornek"
    assert [b.name for b in subject.competitors] == ["Numerai"]
    assert len(subject.prompts) == 2


def test_the_screening_round_lands_in_the_ledger_and_verifies(tmp_path):
    rec = Recorder()
    run(rec, tmp_path)
    store = Ledger(tmp_path / "ledger")
    (snapshot,) = store.snapshots()
    assert store.verify(snapshot) == []
    played = replay(store, snapshot)
    assert {r.prompt_id for r in played.runs} == {"p1", "p2"}
    assert any("Numerai" in r.brands for r in played.runs)


def test_a_question_that_only_ever_names_the_subject_is_barren_not_kept(tmp_path):
    """The gate, stated as the thing it must refuse to do.

    Every draw here names the subject and no rival, which is the shape of a
    question that measures its own echo. Screened on the subject's own rate it
    is a perfect question and gets kept, and the published number goes up
    because the evidence against it was deleted. Screened on rivals, which is
    what this does, it carries nothing and is dropped.
    """
    rec = Recorder()
    echo = Engine(proposals=reply(GROUNDED, SECOND), answer="Ornek is the one to use.")
    code, _ = run(rec, tmp_path, engine=echo)
    assert code == 0

    subject, ledger = written(tmp_path)
    assert {m["verdict"] for m in ledger["measured"]} == {"barren"}
    assert all(m["rival_hits"] == 0 for m in ledger["measured"])
    assert subject["prompts"] == []


def test_a_question_no_rival_answers_is_dropped_as_barren(tmp_path):
    rec = Recorder()
    silent = Engine(proposals=reply(GROUNDED, SECOND), answer="Nobody in particular.")
    code, _ = run(rec, tmp_path, engine=silent)
    assert code == 0
    subject, ledger = written(tmp_path)
    assert {m["verdict"] for m in ledger["measured"]} == {"barren"}
    assert subject["prompts"] == [], "a barren question is not written into the set"
    assert "barren" in rec.text


# -- nothing that died disappears -------------------------------------------


def test_every_gate_that_dropped_something_says_so_in_the_draft_ledger(tmp_path):
    rec = Recorder()
    engine = Engine(proposals=reply(GROUNDED, INVENTED, NAMED))
    run(rec, tmp_path, engine=engine)
    _, ledger = written(tmp_path)
    reasons = {r["gate"]: r["reason"] for r in ledger["rejected"]}
    assert set(reasons) == {"evidence", "name"}
    assert "not in the page it cites" in reasons["evidence"]
    assert "measure its own echo" in reasons["name"]


def test_an_unreadable_entry_from_the_model_is_kept_in_the_record(tmp_path):
    rec = Recorder()
    engine = Engine(proposals=f'["not an object", {json.dumps(GROUNDED)}]')
    run(rec, tmp_path, engine=engine)
    _, ledger = written(tmp_path)
    assert ledger["unreadable_entries"][0]["reason"] == "entry is not an object"
    assert ledger["proposed"] == 1


def test_a_page_that_would_not_load_is_named_in_the_record(tmp_path):
    rec = Recorder()
    partial = dict(SITE)
    partial[HOME] = page("Ornek", "Insaat riskini gunluk fiyatlandiriyoruz.", [TARIFELER, HOME + "/yok"])
    run(rec, tmp_path, fetch=fetcher(partial))
    _, ledger = written(tmp_path)
    assert [m["url"] for m in ledger["unreachable"]] == [HOME + "/yok"]
    assert "could not be read" in rec.text


def test_the_corpus_digest_pins_what_the_quotes_were_checked_against(tmp_path):
    rec = Recorder()
    run(rec, tmp_path)
    _, ledger = written(tmp_path)
    assert len(ledger["corpus_digest"]) == 64
    assert ledger["pages_read"] == [HOME, TARIFELER]


# -- ids, which every later comparison groups by ----------------------------


def test_a_second_draft_does_not_renumber_a_question_that_did_not_change(tmp_path):
    rec = Recorder()
    run(rec, tmp_path, engine=Engine(proposals=reply(SECOND)))
    first = written(tmp_path)[0]["prompts"][0]["id"]

    run(Recorder(), tmp_path, engine=Engine(proposals=reply(GROUNDED, SECOND)))
    again = {p["text"]: p["id"] for p in written(tmp_path)[0]["prompts"]}
    assert again[SECOND["question"]] == first, "the surviving question kept its id"
    assert len(set(again.values())) == 2, "and the new one did not take it"
