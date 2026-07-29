/**
 * The statistics are the product's only real claim, so they get tested against
 * known values rather than against themselves.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  agreement,
  detectDrift,
  formatProportion,
  samplesForWidth,
  summariseRanks,
  wilson,
} from "../src/lib/stats.ts";

/** Wilson interval for 3/10 at 95%, computed independently: 0.1078 to 0.6032. */
test("wilson matches hand-computed values", () => {
  const p = wilson(3, 10);
  assert.equal(p.point, 0.3);
  assert.ok(Math.abs(p.lower - 0.1078) < 0.001, `lower was ${p.lower}`);
  assert.ok(Math.abs(p.upper - 0.6032) < 0.001, `upper was ${p.upper}`);

  // 5/10 at 95% is symmetric around 0.5: 0.2366 to 0.7634.
  const half = wilson(5, 10);
  assert.ok(Math.abs(half.lower - 0.2366) < 0.001, `lower was ${half.lower}`);
  assert.ok(Math.abs(half.upper - 0.7634) < 0.001, `upper was ${half.upper}`);
  assert.ok(Math.abs((half.lower + half.upper) / 2 - 0.5) < 1e-9, "should be symmetric at p=0.5");
});

test("zero successes still carries uncertainty, which is the point", () => {
  const p = wilson(0, 10);
  assert.equal(p.point, 0);
  assert.equal(p.lower, 0);
  // The normal approximation gives [0, 0] here and would let the tool claim
  // certainty of absence after ten samples. Wilson keeps a real upper bound.
  assert.ok(p.upper > 0.25, `upper was ${p.upper}, should leave room for real presence`);
  assert.ok(p.upper < 0.35, `upper was ${p.upper}`);
});

test("full success also carries uncertainty", () => {
  const p = wilson(10, 10);
  assert.equal(p.point, 1);
  assert.equal(p.upper, 1);
  assert.ok(p.lower < 0.75 && p.lower > 0.65, `lower was ${p.lower}`);
});

test("intervals stay inside [0,1] and narrow as n grows", () => {
  let previousWidth = 1;
  for (const n of [5, 10, 20, 50, 200]) {
    const p = wilson(Math.round(n * 0.3), n);
    assert.ok(p.lower >= 0 && p.upper <= 1, `n=${n} escaped [0,1]`);
    assert.ok(p.width < previousWidth, `n=${n} did not narrow (${p.width} vs ${previousWidth})`);
    previousWidth = p.width;
  }
});

test("higher confidence gives a wider interval", () => {
  const w90 = wilson(3, 10, 0.9).width;
  const w95 = wilson(3, 10, 0.95).width;
  const w99 = wilson(3, 10, 0.99).width;
  assert.ok(w90 < w95 && w95 < w99, `${w90} < ${w95} < ${w99}`);
});

test("wilson rejects nonsense rather than returning it", () => {
  assert.throws(() => wilson(11, 10), /invalid counts/);
  assert.throws(() => wilson(-1, 10), /invalid counts/);
  assert.throws(() => wilson(1.5, 10), /must be integers/);
  assert.throws(() => wilson(3, 10, 0.5), /unsupported confidence/);
  // n=0 is a legitimate "not measured yet", not an error.
  const empty = wilson(0, 0);
  assert.equal(empty.width, 1);
});

test("sample sizing shows the quadratic cost of precision", () => {
  const wide = samplesForWidth(0.4);
  const half = samplesForWidth(0.2);
  assert.ok(half >= wide * 3.5, `halving the width should cost ~4x: ${wide} -> ${half}`);
  // Concrete number the report quotes: a 20-point interval needs ~97 samples.
  assert.equal(samplesForWidth(0.2), 97);
});

/* -------------------------------------------------------------------- ranks */

test("rank summary separates how often from how high", () => {
  // Appears twice, always first.
  const rare = summariseRanks([1, 1])!;
  assert.equal(rare.appearances, 2);
  assert.equal(rare.mean, 1);
  assert.equal(rare.sd, 0);

  // Appears often but low, and unstably.
  const common = summariseRanks([4, 5, 6, 5, 5, 7, 3, 5, 5])!;
  assert.equal(common.appearances, 9);
  assert.equal(common.mean, 5);
  assert.ok(common.sd > 1, `sd was ${common.sd}`);
  assert.equal(common.best, 3);
  assert.equal(common.worst, 7);

  assert.equal(summariseRanks([]), null);
});

/* ---------------------------------------------------------------- agreement */

test("agreement reports the majority and flags a contested vote", () => {
  const clear = agreement(["positive", "positive", "positive", "neutral"]);
  assert.equal(clear.majority, "positive");
  assert.equal(clear.ratio, 0.75);
  assert.equal(clear.contested, false);

  const split = agreement(["positive", "neutral", "negative", "positive", "neutral"]);
  assert.equal(split.contested, true, "2/5 majority must be flagged");
  assert.deepEqual(split.votes, { positive: 2, neutral: 2, negative: 1 });
  // Tie broken alphabetically for reproducibility.
  assert.equal(split.majority, "neutral");
});

test("agreement is reproducible for the same votes in any order", () => {
  const a = agreement(["neutral", "positive", "positive"]);
  const b = agreement(["positive", "neutral", "positive"]);
  assert.deepEqual(a, b);
});

/* -------------------------------------------------------------------- drift */

test("a large move with tight intervals is reported as moved", () => {
  const d = detectDrift({ successes: 5, n: 100 }, { successes: 40, n: 100 });
  assert.equal(d.verdict, "moved");
  assert.ok(d.delta > 0.3);
  assert.match(d.reason, /do not overlap/);
});

test("a small move with tight intervals is reported as unchanged", () => {
  const d = detectDrift({ successes: 30, n: 200 }, { successes: 34, n: 200 });
  assert.equal(d.verdict, "unchanged");
  assert.match(d.reason, /sampling noise/);
});

test("the same move on ten samples is inconclusive, not a win", () => {
  // 2/10 -> 4/10 looks like a doubling and means nothing at this sample size.
  const d = detectDrift({ successes: 2, n: 10 }, { successes: 4, n: 10 });
  assert.equal(d.verdict, "inconclusive");
  assert.match(d.reason, /wide/);
  assert.match(d.reason, /97 samples/, "should tell the user what it would take");
});

test("the headline format is the one the product exists to print", () => {
  assert.equal(formatProportion(wilson(3, 10)), "3/10 = 30.0% (10.8% to 60.3%)");
});
