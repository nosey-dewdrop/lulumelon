"""The round a customer reads, as a document a customer can file.

`panel.py` renders one round for a terminal. This renders the same round for a
page, and it renders it *through* `Panel`: every section below is the list of
lines that surface already produces, escaped and set. Nothing is reworded on
the way. Two surfaces printing the same figure under different sentences is the
defect `BrandReport.exclusion` was made a tuple of lines to prevent, and a PDF
is the surface where a reworded sentence would outlive the screen it came from.

**Why this sits here and not under `mirror/`.** Turning a report into a string
computes nothing and reaches nothing, which is the argument for putting it with
the rest of the pure code. It is not there because the document is not only the
arithmetic. Half of what makes it worth filing is the file the arithmetic came
from: which snapshot, how many records are on it, what the round's own seal says
it did, and the hash the chain ends on. `mirror/` is not allowed to know that a
file exists, and a renderer that accepted those as arguments would be teaching
it the shape of one. So this lives beside `panel.py`, above both walls, for the
reason `panel.py` lives there: it computes nothing, and it reads both sides.

**Running a typesetter is not in here.** Producing the string is pure; spawning
a process is not, and that belongs to the layer that already owns the filesystem.
`lulu report` shells out. This module hands back text and never learns whether
anything was written with it.

**On escaping.** A brand name, a question and a source URL are arbitrary text
somebody typed into a subject file, and `&`, `%`, `_`, `#`, `$` and `~` are all
ordinary characters in a brand name and all control characters in TeX. A
document that will not compile because a customer's brand had an ampersand in it
is not a document, so every string that reaches the page goes through `escape`
and nothing is interpolated raw.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .panel import Panel
from .text import counted

#: Every character TeX reads as an instruction, and what it is written as when
#: it is meant as itself. Applied one character at a time so a replacement can
#: never be rescanned: a table walked in sequence turns the backslash of `\&`
#: into `\textbackslash{}&` on whichever pass came second.
_ESCAPES = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "$": r"\$",
    "&": r"\&",
    "#": r"\#",
    "%": r"\%",
    "_": r"\_",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    # Printable in T1 and not in OT1, where they come out as inverted
    # punctuation. Written as commands so the page does not depend on which
    # encoding a future preamble asks for.
    "<": r"\textless{}",
    ">": r"\textgreater{}",
    "|": r"\textbar{}",
    # A line ending is an instruction too, and the one that ends a document.
    # Nothing the panel builds carries one, but a question does: prompt text is
    # arbitrary JSON somebody wrote by hand, and two line endings in a row are a
    # blank line, which is `\par`. Set inside a block whose lines are joined
    # with `\\`, that is `\\` followed by a paragraph break, which is the error
    # `There's no line here to end` and no PDF at all. Written as a space, which
    # is what a line ending means inside a sentence.
    "\n": " ",
    "\r": " ",
}

#: A run of spaces the terminal uses as a column gap. TeX collapses it, so it is
#: set as one explicit space instead. The columns are not realigned: a
#: proportional font has no columns to align to, and inventing a table around a
#: line that was never one would be putting a shape on the page that the data
#: does not have.
_GAP = re.compile(r" {2,}")

#: Indentation the panel gives a line that continues the one above it. Half an
#: em per space of terminal indent past the block's own two, which keeps the
#: hierarchy the screen has without pretending to monospace alignment.
_INDENT_EM = 0.5
_BLOCK_INDENT = 2

PREAMBLE = r"""\documentclass[11pt,a4paper]{article}
\usepackage[T1]{fontenc}
\usepackage{newtxtext,newtxmath}
\usepackage{tabularx}
\usepackage[margin=25mm]{geometry}
\pagestyle{plain}
\setlength{\parindent}{0pt}
\setlength{\parskip}{0.4\baselineskip}
\emergencystretch=2em
\makeatletter
\renewcommand\section{\@startsection{section}{1}{0pt}{1.1\baselineskip}{0.3\baselineskip}{\normalsize\bfseries}}
\makeatother
\begin{document}"""

#: The command that produced the page, at the top of it, so a reader who wants
#: to reproduce the document knows what to type.
TITLE = "lulu report"

#: Heading of the section that carries the file the numbers came from.
EVIDENCE = "EVIDENCE"


def escape(text: str) -> str:
    """`text`, set as itself rather than read as TeX."""
    return "".join(_ESCAPES.get(ch, ch) for ch in text)


def _set(text: str) -> str:
    """One line of panel output, escaped and with its column gaps kept."""
    return _GAP.sub(r"\\quad{}", escape(text))


def _paragraphs(lines: tuple[str, ...] | list[str]) -> list[str]:
    """Panel lines as paragraphs, one typeset line per screen line.

    A blank line on screen opens a new paragraph, and everything between two of
    them is one paragraph with explicit breaks, so a sentence too long for the
    measure wraps and a new screen line still starts a new line.
    """
    out: list[str] = []
    block: list[str] = []

    def flush() -> None:
        if block:
            out.append("\\\\\n".join(block) + "\\par")
            block.clear()

    for line in lines:
        if not line.strip():
            flush()
            continue
        indent = len(line) - len(line.lstrip(" "))
        hang = (indent - _BLOCK_INDENT) * _INDENT_EM
        prefix = f"\\hspace*{{{hang:g}em}}" if hang > 0 else ""
        block.append(prefix + _set(line.strip()))
    flush()
    return out


def _section(lines: list[str]) -> list[str]:
    """One panel block: its first line is the heading and the rest is the body."""
    return [f"\\section*{{{escape(lines[0])}}}", *_paragraphs(lines[1:])]


def _flowed(lines: tuple[str, ...] | list[str]) -> str:
    """Lines the terminal wrapped, set as the one paragraph they are.

    Used for the closing note and nowhere else. Every other block on the panel
    is one fact to a line, and a break there is the shape of the content; that
    block is two sentences broken at 66 columns because that is how wide a
    terminal was, and a page has its own measure to break them at.
    """
    return _set(" ".join(line.strip() for line in lines)) + "\\par"


@dataclass(frozen=True, slots=True)
class Evidence:
    """What the round is on disk, so the page can be checked against the ledger.

    Every field is a fact about the file, read by the caller and handed over as
    text. None of it is computed here and none of it is fetched here: this
    module renders, and the module that opens files is the one that owns them.

    A figure printed with no way back to the record behind it is the thing this
    library argues with, so a document carrying figures carries this too. The
    reader who wants to check one takes the snapshot id, counts the lines,
    reads the round's own closing record, and recomputes the chain.
    """

    records: int
    seal: str
    final_hash: str
    models: tuple[str, ...]
    surfaces: tuple[str, ...]
    dates: tuple[str, ...]
    cost: tuple[str, ...]

    def rows(self) -> tuple[tuple[str, tuple[str, ...]], ...]:
        """Each fact with the label it is filed under, in the order it is set."""
        return (
            ("records", (counted(self.records, "record"),)),
            ("sealed", (self.seal,)),
            ("final hash", (self.final_hash,)),
            ("model", (f"{', '.join(self.models)}, as reported by the response",)),
            ("surfaces", (", ".join(self.surfaces),)),
            ("collected", (", ".join(self.dates),)),
            ("cost", self.cost),
        )


def tex_document(panel: Panel, evidence: Evidence) -> str:
    """One round as a complete, standalone LaTeX document.

    The blocks are taken in the order `Panel.as_text` prints them, and access
    is first there for the reason it is first there: a blocked crawler explains
    a low number on its own, and a reader who meets the visibility figure first
    goes and buys content they did not need.
    """
    parts = [
        PREAMBLE,
        f"{{\\large\\bfseries {escape(TITLE)}\\par}}",
        _set(panel.report.identity) + "\\par",
    ]
    for block in (
        panel.access(),
        panel.design(),
        panel.parameters(),
        panel.appearance(),
        panel.contributing(),
        panel.source_section(),
        panel.verdicts(),
        # Every question, where the terminal stops at a screenful. This is the
        # copy somebody checks a claim against, and a list of questions with
        # some of them missing cannot be checked against anything.
        panel.question_section(limit=None),
    ):
        if block:
            parts.extend(_section(block))

    parts.append(f"\\section*{{{escape(EVIDENCE)}}}")
    parts.append("\\begin{tabularx}{\\textwidth}{@{}lX@{}}")
    for label, values in evidence.rows():
        parts.append(f"{escape(label)} & " + " \\newline ".join(_set(v) for v in values) + "\\\\")
    # The table closes its own paragraph. Without that the rule below it is set
    # as the next line of the same paragraph, lands hard against the last row,
    # and reads as the table's bottom border rather than as a rule between two
    # sections. The vertical space that is supposed to separate them is a
    # horizontal-mode `\vspace` at that point, and does nothing visible.
    parts.append("\\end{tabularx}\\par")

    # Air above the rule as well as below it. Set tight against the table it
    # follows, a plain horizontal line stops reading as a rule between two
    # sections and starts reading as the bottom border of the thing above it,
    # which is a box by another name.
    parts.append("\\vspace{1.6\\baselineskip}")
    parts.append("\\noindent\\rule{\\textwidth}{0.4pt}\\par")
    parts.append(_flowed(panel.limitation()))
    parts.append("\\end{document}")
    return "\n".join(parts) + "\n"
