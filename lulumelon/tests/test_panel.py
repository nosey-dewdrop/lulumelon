"""What the customer-facing surface must show, and must never show."""

from __future__ import annotations

from lulumelon.collect.audit import Finding, SiteAudit
from lulumelon.mirror.report import brand_report
from lulumelon.mirror.sources import source_graph
from lulumelon.mirror.types import Run, snapshot_from_runs
from lulumelon.panel import Panel

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
