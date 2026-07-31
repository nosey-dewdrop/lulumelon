"""The pages are checked against the code, so they cannot quietly go stale.

Documentation about money and about where files live is the part of a product
that rots first and is noticed last. Every figure on `docs/keys.md` and in the
README that also exists in the code is asserted here, so a number edited in one
place and not the other fails the suite instead of misleading a reader.

The README half of this exists because it was missing: a session found the
README describing a better product than the code shipped, and found it by hand
rather than by running anything. The drift was in the flattering direction,
which is the direction drift takes when nothing checks it.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from lulumelon.cli import build_parser
from lulumelon.keys import KEYCHAIN_SERVICE, spec_for
from lulumelon.mirror.intervals import wilson_interval
from lulumelon.prices import PRICES, fees, price_for

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs" / "keys.md"
TEXT = DOCS.read_text(encoding="utf-8")
README = ROOT / "README.md"
README_TEXT = README.read_text(encoding="utf-8")


def test_the_page_exists_where_the_readme_points():
    assert DOCS.is_file()
    readme = (DOCS.parents[1] / "README.md").read_text(encoding="utf-8")
    assert "docs/keys.md" in readme


def test_every_place_the_code_looks_is_named_on_the_page():
    spec = spec_for("perplexity")
    for name in spec.env_names:
        assert name in TEXT, f"{name} is read by the code but not documented"
    assert KEYCHAIN_SERVICE in TEXT
    assert "~/.lulu/env" in TEXT
    assert spec.key_page in TEXT


def test_the_published_prices_match_the_table_in_the_code():
    for (_, model), price in PRICES.items():
        row = next((line for line in TEXT.splitlines() if line.startswith(f"| {model} |")), None)
        assert row is not None, f"{model} has a price in the code and no row on the page"
        for value in (
            price.input_per_mtok_usd,
            price.output_per_mtok_usd,
            price.fee_per_k_low_usd,
            price.fee_per_k_high_usd,
        ):
            assert f"${value:g}" in row, f"{model}: ${value:g} is in the code but not in its row"


def test_the_page_says_when_the_prices_were_read():
    for price in PRICES.values():
        for source in price.sources:
            assert source in TEXT, f"{price.model} cites {source} and the page does not"
    assert "31 July 2026" in TEXT
    assert "1 August 2026" in TEXT


def test_the_cost_of_a_first_measurement_is_the_one_the_code_computes():
    """The page quotes a figure for 200 calls. It is recomputed here.

    Through `fees`, not `estimate` with zero tokens. The page says
    "in request fees plus a few cents of tokens", which is the truth; computing
    it with a fabricated zero token count would have produced the same digits
    under a label that claims the tokens were counted.
    """
    price = price_for("perplexity", "sonar")
    assert price is not None
    cost = fees(price, fee_units=200)
    assert f"${cost.low_usd:.2f} to ${cost.high_usd:.2f}" in TEXT
    assert "in request fees" in TEXT, "the page must not present a floor as a total"


def test_every_command_the_page_tells_you_to_run_is_a_real_command():
    parser = build_parser()
    for line in TEXT.splitlines():
        stripped = line.strip()
        if not stripped.startswith("lulu "):
            continue
        args = stripped.split()[1:]
        parser.parse_args(args)


# -- the README ------------------------------------------------------------


def _invocations(text: str) -> list[list[str]]:
    """Every `lulu ...` the page tells a reader to type, continuations joined."""
    out: list[list[str]] = []
    current: list[str] | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if current is not None:
            current.extend(stripped.rstrip("\\").split())
            if not stripped.endswith("\\"):
                out.append(current)
                current = None
            continue
        if not stripped.startswith("lulu "):
            continue
        words = stripped.rstrip("\\").split()[1:]
        if stripped.endswith("\\"):
            current = words
        else:
            out.append(words)
    return out


def test_every_command_the_readme_shows_is_a_real_command():
    parser = build_parser()
    shown = _invocations(README_TEXT)
    assert shown, "the README stopped showing any commands at all"
    for args in shown:
        # `#` starts a trailing comment in the README's shell blocks.
        clean = args[: args.index("#")] if "#" in args else args
        parser.parse_args(clean)


def test_every_command_the_cli_offers_is_shown_in_the_readme():
    """A command nobody documents is a command nobody runs."""
    offered = set(build_parser()._subparsers._group_actions[0].choices)
    shown = {args[0] for args in _invocations(README_TEXT) if args}
    assert offered == shown, f"undocumented: {sorted(offered - shown)}"


def test_every_interval_in_the_readme_table_is_the_one_wilson_returns():
    """The first table a reader sees is recomputed rather than transcribed."""
    for successes, n in ((5, 5), (4, 5), (2, 5), (1, 5), (0, 5)):
        row = next(
            (line for line in README_TEXT.splitlines() if f"{successes}/{n}" in line), None
        )
        assert row is not None, f"the {successes}/{n} row left the table"
        interval = wilson_interval(successes, n)
        for value in (interval.point, interval.low, interval.high):
            assert f"{value * 100:.1f}%" in row, (
                f"{successes}/{n}: the code says {value * 100:.1f}% and the row does not"
            )


def test_the_two_figures_the_readme_argues_from_are_the_computed_ones():
    """The prose picks two numbers out of the table and leans on them."""
    never_named = wilson_interval(0, 5)
    five_of_five = wilson_interval(5, 5)
    assert f"named {never_named.high * 100:.0f}% of the time" in README_TEXT
    assert f"lower bound of {five_of_five.low * 100:.1f}%" in README_TEXT


def test_the_readme_layout_names_every_module_and_no_others():
    block = README_TEXT.split("```")[1]
    listed = set(re.findall(r"[\w]+\.py", block))
    on_disk = {
        path.name
        for path in (ROOT / "lulumelon").rglob("*.py")
        if "tests" not in path.parts and path.name != "__init__.py"
    }
    assert listed == on_disk, (
        f"in the README only: {sorted(listed - on_disk)}; "
        f"on disk only: {sorted(on_disk - listed)}"
    )


def test_the_test_counts_in_the_readme_are_the_counts_that_run():
    """Two numbers that go stale by themselves, so they are read back.

    Collected rather than passed. The suite has carried a deliberately red test
    before, standing on a hole in the ledger until it was closed, and a README
    quoting the passing count would have gone stale on the day it turned green.
    The count that does not depend on today's colours is the one to quote.
    """
    collected = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "lulumelon/tests"],
        capture_output=True, text=True, cwd=ROOT,
    )
    found = re.search(r"^(\d+) tests? collected", collected.stdout, re.M)
    assert found, collected.stdout[-500:]
    assert f"# {found.group(1)} tests, offline" in README_TEXT

    node = subprocess.run(
        ["npm", "test", "--silent"], capture_output=True, text=True, cwd=ROOT
    )
    counted = re.search(r"^. tests (\d+)$", node.stdout, re.M)
    assert counted, node.stdout[-500:] + node.stderr[-500:]
    assert f"# {counted.group(1)} tests, offline" in README_TEXT
