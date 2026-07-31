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
need.
"""

from __future__ import annotations

from dataclasses import dataclass

from .collect.audit import SiteAudit
from .mirror.report import BrandReport
from .mirror.sources import SourceAssociation

RULE = "-" * 66


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


@dataclass(frozen=True, slots=True)
class Panel:
    """Everything known about one brand in one round, ready to print."""

    report: BrandReport
    sources: tuple[SourceAssociation, ...] = ()
    audit: SiteAudit | None = None
    dropped_runs: int = 0
    target_half_width: float = 0.02

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
            f"  {r.n_prompts} prompts x {k:.0f} runs = {r.total_runs} answers"
            f" on {', '.join(r.engines)}",
        ]
        if self.dropped_runs:
            out.append(
                f"  {self.dropped_runs} asks failed and are excluded, recorded not dropped"
            )
        if r.surface_mix:
            out.append(f"  surfaces mixed: {r.surface_mix}")
        if r.model_drift:
            out.append(f"  model changed underneath: {r.model_drift}")
        return out

    def appearance(self) -> list[str]:
        d = self.report.detection
        return [
            "APPEARANCE",
            f"  {self.report.brand} is named in {_pct(d.point)} of answers",
            f"  honest range {_pct(d.low)} to {_pct(d.high)}"
            f"  ({int(d.confidence * 100)}% confidence, prompt-clustered)",
        ]

    def contributing(self) -> list[str]:
        """What is contributing to your interval width.

        The split decides the next move: more repeats when the model's own dice
        dominate, more prompts when the question set does. Buying a fixed number
        of daily reruns without reading it is how a measurement budget goes on
        repeats when it was prompts that were short.
        """
        v = self.report.variance
        total = v.within + v.between or 1.0
        within_share = v.within / total
        return [
            "WHAT IS CONTRIBUTING TO YOUR INTERVAL WIDTH",
            f"  the model answering differently   {_pct(within_share)}",
            f"  which questions you chose to ask  {_pct(1 - within_share)}",
            f"  noise floor  +/-{v.noise_floor * 100:.1f} points  (icc {v.icc:.2f})",
            "",
            f"  next: {self.report.advice(self.target_half_width)}",
        ]

    def verdicts(self) -> list[str]:
        """Every place the round refuses to give a number, and why."""
        out = ["VERDICTS"]
        if self.report.rank_reportable:
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
            self.appearance(),
            self.contributing(),
            self.source_section(),
            self.verdicts(),
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
