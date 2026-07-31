"""The setup page is checked against the code, so it cannot quietly go stale.

Documentation about money and about where files live is the part of a product
that rots first and is noticed last. Every figure on `docs/keys.md` that also
exists in the code is asserted here, so a price edited in one place and not the
other fails the suite instead of misleading a reader.
"""

from __future__ import annotations

from pathlib import Path

from lulumelon.cli import build_parser
from lulumelon.keys import KEYCHAIN_SERVICE, spec_for
from lulumelon.prices import PRICES, estimate, price_for

DOCS = Path(__file__).resolve().parents[2] / "docs" / "keys.md"
TEXT = DOCS.read_text(encoding="utf-8")


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
            price.request_fee_per_k_low_usd,
            price.request_fee_per_k_high_usd,
        ):
            assert f"${value:g}" in row, f"{model}: ${value:g} is in the code but not in its row"


def test_the_page_says_when_the_prices_were_read():
    for price in PRICES.values():
        assert price.source in TEXT
    assert "31 July 2026" in TEXT


def test_the_cost_of_a_first_measurement_is_the_one_the_code_computes():
    """The page quotes a figure for 200 calls. It is recomputed here."""
    price = price_for("perplexity", "sonar")
    assert price is not None
    cost = estimate(price, input_tokens=0, output_tokens=0, requests=200)
    assert f"${cost.low_usd:.2f} to ${cost.high_usd:.2f}" in TEXT


def test_every_command_the_page_tells_you_to_run_is_a_real_command():
    parser = build_parser()
    for line in TEXT.splitlines():
        stripped = line.strip()
        if not stripped.startswith("lulu "):
            continue
        args = stripped.split()[1:]
        parser.parse_args(args)
