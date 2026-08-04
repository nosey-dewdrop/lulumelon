"""The demo in a public repository, run rather than read.

It is the first thing a stranger executes and it was broken for weeks by an
import path, in a repository whose whole argument is that a number nobody can
reproduce is not a number. Nothing else in the suite touches it, because it is
the one file that exists to be run by hand, so a test that runs it is the only
thing standing between the next path change and a stranger's first impression.

Executed as a subprocess rather than imported. Importing would exercise the
functions and not the entry point, and the entry point is the part that broke.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_the_demo_runs_and_prints_the_argument_it_was_written_for():
    done = subprocess.run(
        [sys.executable, "lulumelon/demo.py"], capture_output=True, text=True, cwd=ROOT
    )

    assert done.returncode == 0, done.stderr[-800:]
    out = done.stdout
    assert "what a single daily run reports" in out
    assert "the same measurement, asked 12 times per prompt" in out
    # The whole point of the file, in the order it makes it: one number, then
    # the interval around it, then the refusal a single number cannot make.
    assert "no interval, k=1" in out
    assert "95% CI" in out
    assert "RANK NOT REPORTABLE" in out


def test_the_demo_reaches_no_network():
    """It simulates an answer engine. A demo that called one would cost money."""
    source = (ROOT / "lulumelon" / "demo.py").read_text(encoding="utf-8")
    for reached in ("urllib", "requests", "http", "socket", "api_key"):
        assert reached not in source, reached
