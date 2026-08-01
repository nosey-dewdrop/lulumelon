"""The surface a customer actually reads.

The rest of this package computes. This renders, and the two are separate files
because the moment a renderer is allowed to compute, someone rounds a number to
make a line fit.

Shape borrowed on purpose from a terminal usage panel: sections, a plain
breakdown, and a stated limitation at the bottom. No charts. A trend line drawn
through points that each carry a fourteen point interval reads as movement when
it is dice, and a line has no way to say so. Text does: it can print a refusal
where a number would mislead, and that is the whole reason this surface is text.

The structural idea taken from that reference is its best line, *what is
contributing to your usage*, turned into the question this library exists to
answer: **what is contributing to your interval width**. A score on its own does
not tell anyone what to do next; the split behind it does.

Order is deliberate and it is not the order of interest. Access comes before
measurement, because a blocked crawler explains a low number completely and a
customer who reads a visibility score first will go buy content they did not
need. The questions come last for the opposite reason: the list is long, it is
read once against a claim rather than every time, and putting it above the
figure would push the figure off the screen.
"""

from __future__ import annotations

from dataclasses import dataclass

from .collect.ask import (
    NO_LOCATION,
    NO_SEARCH_TOOL,
    SEARCH_CAP_UNRECORDED,
    is_unsearched_surface,
)
from .collect.audit import SiteAudit
from .mirror.report import BrandReport
from .mirror.sources import SourceAssociation
from .text import counted

RULE = "-" * 66

#: Questions the terminal prints in full before it stops counting them out. Two
#: lines each, so a dozen is about a screen; past that the list stops being
#: readable where it is and the document, which prints every one, is where the
#: whole of it lives.
TERMINAL_QUESTIONS = 12


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


@dataclass(frozen=True, slots=True)
class Question:
    """One question as the subject file states it, and how it came back.

    `asked` is the records the round wrote for it and `usable` is what is left
    after the failures are excluded. Both, per question, because a round is not
    balanced: the design line above divides the answers by the questions and
    prints an average that no question was actually asked.

    `excluded` is per question what `BrandReport.exclusion` states for the
    round. The round's own sentence says how many prompts were left out and
    names their ids; this puts the mark on the line the reader is looking at,
    so a list of questions cannot be read as the list that was scored.
    """

    id: str
    text: str
    asked: int
    usable: int
    excluded: bool

    def lines(self) -> list[str]:
        """The question, then what it produced. Two lines, in that order.

        The question first because the question is the thing being disclosed.
        The wording of the counts is `Replay.as_text`'s, and the wording of the
        exclusion is `BrandReport.exclusion`'s, so the same fact reads the same
        way wherever the reader meets it.
        """
        tail = ", excluded from the rate and its interval" if self.excluded else ""
        return [
            f"  {self.id:<5} {self.text}",
            f"        {self.usable} usable of {self.asked} asked{tail}",
        ]


@dataclass(frozen=True, slots=True)
class Panel:
    """Everything known about one brand in one round, ready to print."""

    report: BrandReport
    sources: tuple[SourceAssociation, ...] = ()
    audit: SiteAudit | None = None
    dropped_runs: int = 0
    target_half_width: float = 0.02
    questions: tuple[Question, ...] = ()
    surfaces: tuple[str, ...] = ()

    # -- sections ----------------------------------------------------------

    def access(self) -> list[str]:
        """First, because it can explain the whole number on its own."""
        if self.audit is None:
            return []
        out = [f"ACCESS   {self.audit.base_url}"]
        blocking = self.audit.by_severity("blocking")
        if blocking:
            out.append("")
            for f in blocking:
                out.append(f"  BLOCKED  {f.title}")
                out.append(f"           {f.evidence}")
                out.append(f"           {f.blocks}")
            out.append("")
            out.append(
                "  While this stands, the measurement below is a floor, not a"
            )
            out.append(
                "  ceiling. Writing more will not move a channel that is closed."
            )
        else:
            out.append("  no crawler of a tracked engine is disallowed")

        for sev in ("degrading", "missing"):
            group = self.audit.by_severity(sev)
            if group:
                out.append("")
                for f in group:
                    out.append(f"  {sev:<10}{f.title}")
        if self.audit.unreachable:
            out.append("")
            out.append("  not reached, so not judged: " + ", ".join(self.audit.unreachable))
        return out

    def design(self) -> list[str]:
        r = self.report
        k = r.total_runs / max(r.n_prompts, 1)
        out = [
            "DESIGN",
            f"  {counted(r.n_prompts, 'prompt')} x {counted(k, 'run', fmt='.0f')}"
            f" = {counted(r.total_runs, 'answer')}"
            f" on {', '.join(r.engines)}",
        ]
        if self.dropped_runs:
            out.append(
                f"  {counted(self.dropped_runs, 'ask')} failed and are excluded, "
                "recorded not dropped"
            )
        # Verbatim from the report, because a prompt left out of the rate has to
        # read the same here as it does there. A count that got smaller between
        # two screens with an explanation on only one of them is worse than no
        # explanation at all.
        out.extend(f"  {line}" for line in r.exclusion)
        if r.surface_mix:
            out.append(f"  surfaces mixed: {r.surface_mix}")
        if r.model_drift:
            out.append(f"  model changed underneath: {r.model_drift}")
        return out

    def parameters(self) -> list[str]:
        """What was requested of the engine, beside what the answers came to.

        Two of the things an independent critique of this category says these
        products keep from the buyer, and both of them are things this build
        knows and was not printing. A report that says nothing about where it
        asked from reads as a report that chose somewhere, and a search cap the
        ledger never wrote down has to be said to be missing rather than filled
        in from whatever this build happens to send today.

        Both lines describe the call that was made, and which arm made it is
        read off the round's own surfaces. A panel that was not handed them
        prints nothing here rather than describing a call it cannot see.
        """
        if not self.surfaces:
            return []
        searched = not all(is_unsearched_surface(s) for s in self.surfaces)
        return [
            "PARAMETERS",
            f"  location  {NO_LOCATION}",
            f"  searches  {SEARCH_CAP_UNRECORDED if searched else NO_SEARCH_TOOL}",
        ]

    def question_section(self, limit: int | None = TERMINAL_QUESTIONS) -> list[str]:
        """The questions themselves, so the round can be reproduced from the page.

        The first thing a critique of this category says these products hide is
        the prompt list, and the advice given to buyers is to ask to see the
        prompts for their category and run the round again themselves. Neither
        is possible from a rate and an interval. Everything needed is in the
        subject file the report already opens: the questions, in the order that
        file states them, with the ids the ledger grouped them by.

        `limit` is the terminal's problem and not the document's. A screen is
        where a long list stops being read, and the document is the copy
        somebody checks a claim against, so it is rendered with no limit at all.
        """
        if not self.questions:
            return []
        out = [
            "QUESTIONS",
            "  every question this round asked, in the order the subject file states them",
            "",
        ]
        shown = self.questions if limit is None else self.questions[:limit]
        for question in shown:
            out.extend(question.lines())
        left = len(self.questions) - len(shown)
        if left:
            out.append("")
            out.append(
                f"  {counted(left, 'question')} not printed here, and --pdf writes all of them"
            )
        return out

    def appearance(self) -> list[str]:
        """The rate, from the estimator the line beside it names.

        `detection_by_prompt`, not `detection`. The caption says the range is
        prompt-clustered and `detection` is the Wilson interval over pooled
        runs, which is the estimator `intervals.naive_bootstrap_ci` is kept
        around to show is too narrow: repeats of one prompt are correlated, so
        pooling them counts k answers as k independent draws. This surface was
        printing that interval under the other one's name, which on the round
        in `./ledger` read 16.0% (10.6 to 23.4) where the clustered figure is
        11.1% (0.0 to 33.3). `BrandReport.headline` has always used the
        clustered one, so the two surfaces disagreed as well.

        The two lines under the figure are how it was arrived at, which is the
        last of the things a critique of this category says these products keep
        from the buyer. They are the estimators' own sentences and the method
        string the interval carries, rather than a description of a bootstrap in
        general: the draws and the seed are in that string, and they are what a
        second run of this arithmetic has to match.
        """
        d = self.report.detection_by_prompt
        return [
            "APPEARANCE",
            f"  {self.report.brand} is named in {_pct(d.point)} of answers",
            f"  honest range {_pct(d.low)} to {_pct(d.high)}"
            f"  ({int(d.confidence * 100)}% confidence, prompt-clustered)",
            "",
            "  the rate is the mean of the per-prompt means, and each prompt gets equal"
            " weight regardless of how many times it was asked",
            f"  the range is {d.method}, the percentile bootstrap"
            " where the prompt, not the run, is resampled",
        ]

    def contributing(self) -> list[str]:
        """What is contributing to your interval width?

        The split decides the next move: more repeats when the model's own dice
        dominate, more prompts when the question set does. Buying a fixed number
        of daily reruns without reading it is how a measurement budget goes on
        repeats when it was prompts that were short.

        The heading carries its question mark. It is a question, the docstring
        at the top of this file calls it one, and a heading in question form
        without one is the house rule this project is held to on every surface
        it writes. It reads the same on the printed report, which renders these
        lines rather than its own.
        """
        v = self.report.variance
        total = v.within + v.between or 1.0
        within_share = v.within / total
        return [
            "WHAT IS CONTRIBUTING TO YOUR INTERVAL WIDTH?",
            f"  the model answering differently   {_pct(within_share)}",
            f"  which questions you chose to ask  {_pct(1 - within_share)}",
            f"  noise floor  +/-{v.noise_floor * 100:.1f} points  (icc {v.icc:.2f})",
            "",
            f"  next: {self.report.advice(self.target_half_width)}",
        ]

    def verdicts(self) -> list[str]:
        """Every place the round refuses to give a number, and why."""
        out = ["VERDICTS"]
        if self.report.mean_rank is None:
            # Checked before reportability, in the order `BrandReport.as_text`
            # checks it and for the reason it does. A brand nobody named has no
            # position to withhold and none to print, and the repeats of an
            # answer that named nobody agree with each other perfectly, so the
            # stability test passes and the branch below would format a missing
            # number. The words are that report's, verbatim.
            out.append("  rank      never named, no rank exists")
        elif self.report.rank_reportable:
            out.append(f"  rank      average position {self.report.mean_rank:.2f}")
        else:
            out.append(
                "  rank      WITHHELD, the leading brand does not repeat often"
            )
            out.append(
                "            enough for a position to describe anything but the sampling"
            )
        if self.report.model_drift:
            out.append(
                "  compare   NO VERDICT against earlier rounds, the model version moved"
            )
        withheld = [s for s in self.sources if not s.is_reportable]
        if withheld:
            out.append(f"  sources   {len(withheld)} of {len(self.sources)} carry no readable contrast")
        return out

    def source_section(self) -> list[str]:
        if not self.sources:
            return []
        out = ["SOURCES", "  which pages the answers cited, and whether your name travels with them", ""]
        for s in self.sources:
            if s.is_reportable:
                out.append(f"  {s.url}")
                out.append(
                    f"    {_pct(s.rate_when_cited)} when cited vs {_pct(s.rate_when_not)} when not"
                    f"   {s.difference * 100:+.1f} pts"
                    f" ({s.interval.low * 100:+.1f}..{s.interval.high * 100:+.1f})"
                )
            else:
                out.append(f"  {s.url}")
                out.append(f"    {s.verdict.split(':')[0]}")
        out.append("")
        out.append("  These are associations. Whether entering a source would move the")
        out.append("  rate is a counterfactual and needs an ablation, not this round.")
        return out

    def limitation(self) -> list[str]:
        """The reference panel says its numbers are approximate. Ours says what it is."""
        return [
            "Computed from the recorded answers of this round only, on the surfaces",
            "listed above. Every number here is reproducible from the ledger, and",
            "the raw answer behind any of them can be printed on request.",
        ]

    def as_text(self) -> str:
        blocks = [
            self.access(),
            self.design(),
            self.parameters(),
            self.appearance(),
            self.contributing(),
            self.source_section(),
            self.verdicts(),
            self.question_section(),
        ]
        lines: list[str] = []
        for block in blocks:
            if not block:
                continue
            if lines:
                lines.append("")
                lines.append(RULE)
                lines.append("")
            lines.extend(block)
        lines.append("")
        lines.append(RULE)
        lines.extend(self.limitation())
        return "\n".join(lines)
