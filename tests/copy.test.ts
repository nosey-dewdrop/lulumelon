/**
 * Every interval printed in the site's copy, re-derived.
 *
 * A landing page for a measurement tool that quotes a bound from the wrong
 * sample size is the defect the tool exists to name. One shipped: the home page
 * said "never being named in ten draws is compatible with 43.4%", and 43.4% is
 * the bound for five draws. Ten is 27.8%. Nobody caught it by reading, because
 * a plausible number reads exactly like a correct one.
 *
 * So the claims are listed here as (draws seen, of, low, high) and checked
 * against the same function the product reports with. A wrong figure in the
 * copy now fails the suite rather than the reader.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { wilson } from "../src/lib/stats.ts";

/** What the copy says, and where it says it. */
const CLAIMS: { where: string; seen: number; of: number; low?: number; high: number }[] = [
  { where: "home, is 0 of 10 zero?", seen: 0, of: 5, high: 43.4 },
  { where: "home, is 0 of 10 zero?", seen: 0, of: 10, high: 27.8 },
  { where: "terminal, stitchu row", seen: 0, of: 5, low: 0, high: 43.4 },
  { where: "terminal, named once", seen: 1, of: 10, low: 1.8, high: 40.4 },
  { where: "named/[slug], what does this not say?", seen: 6, of: 6, low: 61, high: 100 },
];

/**
 * The copy quotes to a tenth of a point, so a claim has to sit within one
 * rounding step of the truth. Not equality: `wilson` rounds its own result to
 * four decimals before returning, so 0 of 5 comes back as 0.4345 where the
 * unrounded bound is 0.434482, and re-rounding that to one decimal reads 43.5
 * for a figure that is honestly 43.4. Half a tenth of a point is the width of
 * that argument, and a claim carrying the wrong sample size misses by points.
 */
const TOLERANCE = 0.06;
const off = (fraction: number, quoted: number) => Math.abs(fraction * 100 - quoted);

for (const claim of CLAIMS) {
  test(`${claim.where}: ${claim.seen} of ${claim.of} really is that interval`, () => {
    const interval = wilson(claim.seen, claim.of);
    assert.ok(
      off(interval.upper, claim.high) <= TOLERANCE,
      `copy says ${claim.high}%, ${claim.seen} of ${claim.of} is ${(interval.upper * 100).toFixed(2)}%`,
    );
    if (claim.low !== undefined) {
      assert.ok(
        off(interval.lower, claim.low) <= TOLERANCE,
        `copy says ${claim.low}%, ${claim.seen} of ${claim.of} is ${(interval.lower * 100).toFixed(2)}%`,
      );
    }
  });
}

test("the home page quotes five draws for 43.4%, not ten", () => {
  const page = readFileSync(new URL("../src/app/page.tsx", import.meta.url), "utf8");
  const sentence = page.slice(page.indexOf("never being named in"), page.indexOf("wilson keeps"));
  assert.match(sentence, /five draws/);
  assert.match(sentence, /43\.4%/);
  assert.doesNotMatch(sentence, /ten draws is compatible/);
});

test("a competitor at 6 of 10 does overlap you at 4 of 10, which is what the card claims", () => {
  const theirs = wilson(6, 10);
  const yours = wilson(4, 10);
  // Overlapping at all is the claim; the card says "almost entirely", so the
  // shared span is checked to be most of the narrower of the two.
  const shared = Math.min(theirs.upper, yours.upper) - Math.max(theirs.lower, yours.lower);
  assert.ok(shared > 0, "the ranges must overlap for the card to be true");
  assert.ok(shared > 0.5 * (yours.upper - yours.lower));
});
