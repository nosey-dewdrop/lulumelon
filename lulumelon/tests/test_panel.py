"""What the customer-facing surface must show, and must never show."""

from __future__ import annotations

from lulumelon.collect.ask import UNSEARCHED_SURFACE
from lulumelon.collect.audit import Finding, SiteAudit
from lulumelon.mirror.report import brand_report
from lulumelon.mirror.sources import source_graph
from lulumelon.mirror.types import Run, snapshot_from_runs
from lulumelon.panel import TERMINAL_QUESTIONS, Panel, Question

BLOCKED = SiteAudit(
    base_url="https://marx.finance/",
    findings=(
        Finding(
            id="robots.blocked.GPTBot",
            severity="blocking",
            title="GPTBot is disallowed (ChatGPT)",
            evidence="User-agent: GPTBot / Disallow: /",
            blocks="this closes the retrieval channel for ChatGPT",
        ),
    ),
)

CLEAN = SiteAudit(base_url="https://marx.finance/", findings=())


def snap(seen_rate=0.5, n_prompts=8, k=6, cite=False):
    runs = []
    for i in range(n_prompts):
        for j in range(k):
            named = (j / k) < seen_rate
            runs.append(
                Run(
                    prompt_id=f"p{i}",
                    engine="perplexity",
                    model="sonar-2026-07",
                    asked_at=f"2026-07-31T12:{i:02d}:{j:02d}Z",
                    brands=("Marx",) if named else ("Rival",),
                    citations=(("https://g2.com/x",) if (cite and named) else ()),
                    surface="api",
                )
            )
    return snapshot_from_runs("t", runs)


def panel(**over):
    s = over.pop("snapshot", None) or snap()
    self_naming = over.pop("self_naming", ())
    return Panel(report=brand_report(s, "Marx", self_naming=self_naming), **over)


def test_access_comes_before_the_score():
    text = panel(audit=BLOCKED).as_text()
    # a customer who reads a low visibility number first goes and buys content
    # they did not need. The closed channel has to be the first thing on screen.
    assert text.index("ACCESS") < text.index("APPEARANCE")
    assert text.index("BLOCKED") < text.index("APPEARANCE")


def test_a_blocked_crawler_reframes_the_number_as_a_floor():
    text = panel(audit=BLOCKED).as_text()
    assert "floor, not a" in text
    assert "Writing more will not move a channel that is closed." in text


def test_a_clean_site_makes_no_such_claim():
    text = panel(audit=CLEAN).as_text()
    assert "floor, not a" not in text
    assert "no crawler of a tracked engine is disallowed" in text


def test_the_interval_is_never_printed_without_its_range():
    text = panel().as_text()
    assert "honest range" in text
    assert "confidence, prompt-clustered" in text


def test_the_range_is_the_clustered_one_the_caption_names():
    """The line says prompt-clustered, so the estimator behind it has to be.

    The Wilson interval over pooled runs counts k repeats of one prompt as k
    independent draws, which is the narrowing this library was built to argue
    against. Printed under this caption it was the argument, made against the
    reader.
    """
    s = snap(seen_rate=0.5, n_prompts=8, k=6)
    report = brand_report(s, "Marx", self_naming=())
    text = Panel(report=report).as_text()

    assert report.detection_by_prompt.method.startswith("cluster_bootstrap")
    for value in (
        report.detection_by_prompt.point,
        report.detection_by_prompt.low,
        report.detection_by_prompt.high,
    ):
        assert f"{value * 100:.1f}%" in text
    assert report.headline.startswith(f"{report.detection_by_prompt.point * 100:.1f}%")


def test_a_prompt_excluded_from_the_rate_is_named_on_the_panel_too():
    """Verbatim from the report, so the two surfaces cannot drift apart."""
    report = brand_report(snap(), "Marx", self_naming=("p0",))
    text = Panel(report=report).as_text()

    for line in report.exclusion:
        assert line in text
    assert "7 prompts" in text


def test_a_brand_nobody_named_has_its_rank_said_rather_than_formatted():
    """Empty answers repeat perfectly, so the stability test passes with no rank.

    This is the one arrangement where the reportable branch has nothing to
    print, and it is the arrangement the unsearched arm of a real round is in.
    """
    text = panel(snapshot=snap(seen_rate=0.0)).as_text()
    assert "never named, no rank exists" in text
    assert "average position" not in text


def test_the_panel_says_where_the_uncertainty_comes_from():
    text = panel().as_text()
    assert "WHAT IS CONTRIBUTING TO YOUR INTERVAL WIDTH" in text
    assert "the model answering differently" in text
    assert "which questions you chose to ask" in text
    # and turns it into a move, not a fact to admire
    assert "next:" in text


def test_a_withheld_rank_says_so_instead_of_printing_a_position():
    text = panel().as_text()
    assert "WITHHELD" in text
    assert "average position" not in text.split("VERDICTS")[1]


def test_failed_asks_are_shown_in_the_design_not_hidden():
    text = panel(dropped_runs=7).as_text()
    assert "7 asks failed" in text
    assert "recorded not dropped" in text


def test_sources_are_never_called_an_effect():
    s = snap(cite=True)
    text = Panel(
        report=brand_report(s, "Marx", self_naming=()),
        sources=source_graph(s, "Marx", top=3),
    ).as_text()
    assert "These are associations" in text
    assert "counterfactual" in text
    assert "ablation" in text


def test_there_is_no_chart_and_no_grade():
    text = panel(audit=CLEAN, dropped_runs=1).as_text()
    for banned in ("score:", "grade", "/100", "▁", "█", "▇"):
        assert banned not in text, f"{banned!r} has no business on this panel"


def test_the_limitation_line_states_what_the_round_covers():
    text = panel().as_text()
    assert "this round only" in text
    assert "reproducible from the ledger" in text


# -- the questions, and what was asked of each one ---------------------------

#: An unbalanced round, which is the shape a real one takes: every question
#: asked the same number of times and each keeping a different number of them.
UNBALANCED = (
    Question(id="m1", text="What is marx.finance?", asked=20, usable=20, excluded=True),
    Question(id="m6", text="How does an agent build a record?", asked=20, usable=7, excluded=False),
    Question(id="m8", text="Agentic finance platforms in 2026", asked=20, usable=20, excluded=False),
)


def test_every_question_is_printed_with_the_text_that_was_asked():
    """The list a buyer is advised to ask for, on the page rather than on request."""
    text = panel(questions=UNBALANCED).as_text()
    assert "QUESTIONS" in text
    for question in UNBALANCED:
        assert question.text in text
        assert f"  {question.id:<5} {question.text}" in text.splitlines()


def test_the_questions_keep_the_order_the_subject_file_states_them_in():
    """Reproducing a round means asking the same questions in the same order."""
    text = panel(questions=UNBALANCED).as_text()
    at = [text.index(question.text) for question in UNBALANCED]
    assert at == sorted(at)


def test_each_question_says_how_many_of_its_asks_came_back():
    """The unevenness the design line averages away.

    Three questions asked twenty times each, keeping twenty, seven and twenty,
    is a design the round prints as an average of sixteen that no question was
    asked at.
    """
    text = panel(questions=UNBALANCED).as_text()
    assert "20 usable of 20 asked" in text
    assert "7 usable of 20 asked" in text


def test_a_question_left_out_of_the_rate_is_marked_on_its_own_line():
    """The round's sentence names the ids; this puts the mark beside the words."""
    body = "\n".join(panel(questions=UNBALANCED).question_section())
    marked = [line for line in body.splitlines() if "excluded from the rate" in line]

    assert marked == ["        20 usable of 20 asked, excluded from the rate and its interval"]
    assert "        20 usable of 20 asked" in body.splitlines(), "m8 is scored and unmarked"


def test_a_question_the_round_never_reached_is_listed_with_nothing_against_it():
    """What a budget ceiling leaves behind, said rather than dropped from the list."""
    unasked = Question(id="m9", text="Reputation systems", asked=0, usable=0, excluded=False)
    text = panel(questions=(*UNBALANCED, unasked)).as_text()
    assert "Reputation systems" in text
    assert "0 usable of 0 asked" in text


def test_the_terminal_stops_at_a_screenful_and_says_how_many_it_did_not_print():
    many = tuple(
        Question(id=f"q{i}", text=f"Question number {i}", asked=2, usable=2, excluded=False)
        for i in range(TERMINAL_QUESTIONS + 2)
    )
    text = panel(questions=many).as_text()

    assert "2 questions not printed here" in text
    assert f"Question number {TERMINAL_QUESTIONS - 1}" in text
    assert f"Question number {TERMINAL_QUESTIONS}" not in text


def test_a_panel_with_no_questions_prints_no_heading_for_them():
    assert "QUESTIONS" not in panel().as_text()


# -- what the round was collected under, and how it was scored ---------------


def test_the_report_says_no_location_was_asked_for():
    """Silence about geography reads as a geography somebody chose."""
    text = panel(surfaces=("api",)).as_text()
    assert "PARAMETERS" in text
    assert "location" in text
    assert "no location was requested" in text


def test_an_unrecoverable_search_cap_is_said_to_be_unrecoverable():
    text = panel(surfaces=("api",)).as_text()
    assert "not recoverable from this round" in text


def test_the_arm_with_no_search_tool_says_that_instead_of_guessing_a_cap():
    """This half is recoverable: the arm is a surface and it is on every record."""
    text = panel(surfaces=(UNSEARCHED_SURFACE,)).as_text()
    assert "no search tool was attached to this arm" in text
    assert "not recoverable" not in text


def test_a_panel_that_was_handed_no_surface_describes_no_call():
    assert "PARAMETERS" not in panel().as_text()


def test_the_scoring_lines_name_the_estimator_the_round_actually_used():
    """The method string carries the draws and the seed, so it is printed whole."""
    report = brand_report(snap(), "Marx", self_naming=())
    text = Panel(report=report).as_text()

    assert "the rate is the mean of the per-prompt means" in text
    assert f"the range is {report.detection_by_prompt.method}," in text
    assert "cluster_bootstrap(B=2000,seed=0)" in report.detection_by_prompt.method


def test_severity_labels_do_not_run_into_the_title():
    audit = SiteAudit(
        base_url="https://marx.finance/",
        findings=(
            Finding("canonical.absent", "degrading", "no canonical link", "", "x"),
            Finding("llms.absent", "missing", "no llms.txt", "", "y"),
        ),
    )
    text = panel(audit=audit).as_text()
    assert "degradingno" not in text
    # the labels are a column, so the titles have to start at one offset
    starts = [
        line.index(title)
        for line, title in (
            (next(l for l in text.splitlines() if "no canonical link" in l), "no canonical link"),
            (next(l for l in text.splitlines() if "no llms.txt" in l), "no llms.txt"),
        )
    ]
    assert len(set(starts)) == 1, f"severity labels do not line up: {starts}"
