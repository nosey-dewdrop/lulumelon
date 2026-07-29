/**
 * The statistics layer. This is the whole argument of the product.
 *
 * Every tool in this category reports a single number: "your visibility is
 * 18.5%". That number comes from asking each tracked prompt once. But a large
 * language model is not a deterministic function — ask the same question twice
 * and you get different answers, different brands, different orderings. So a
 * one-shot reading is not a measurement, it is one draw from a distribution
 * nobody characterised.
 *
 * Here, a prompt is asked n times per provider and the result is reported as a
 * proportion with an interval. "3 of 10 samples, 30% (7% to 65%)" is a claim you
 * can act on; "30%" is not, because you cannot tell it apart from 20% or 45%.
 *
 * Nothing in this file calls a model.
 */

/** Round half-up to `digits` decimals. */
function round(value: number, digits: number): number {
  const f = 10 ** digits;
  return Math.round((value + Number.EPSILON) * f) / f;
}

/** z for a two-sided normal interval at the given confidence level. */
const Z: Record<number, number> = {
  0.8: 1.2815515655446004,
  0.9: 1.6448536269514722,
  0.95: 1.959963984540054,
  0.99: 2.5758293035489004,
};

export interface Proportion {
  /** Times the event was observed. */
  successes: number;
  /** Samples taken. */
  n: number;
  /** successes / n. */
  point: number;
  lower: number;
  upper: number;
  /** upper - lower. How much you do not know. */
  width: number;
  confidence: number;
}

/**
 * Wilson score interval.
 *
 * Chosen over the textbook normal approximation (p ± z·sqrt(p(1-p)/n)) because
 * the normal approximation is wrong at exactly the sample sizes this product
 * uses. At n=10 it produces intervals that run below 0 or above 1, and at p=0
 * it collapses to the degenerate [0, 0] — which would let the tool report
 * "you are definitely absent, zero uncertainty" after ten samples. That is the
 * single most misleading thing a visibility tool can say, because absence in
 * ten draws is entirely compatible with appearing a fifth of the time.
 *
 * Wilson stays inside [0, 1] and keeps a real interval at the boundaries.
 */
export function wilson(successes: number, n: number, confidence = 0.95): Proportion {
  if (!Number.isInteger(successes) || !Number.isInteger(n)) {
    throw new Error("wilson: successes and n must be integers");
  }
  if (n < 0 || successes < 0 || successes > n) {
    throw new Error(`wilson: invalid counts (${successes} of ${n})`);
  }

  const z = Z[confidence];
  if (z === undefined) {
    throw new Error(`wilson: unsupported confidence ${confidence}; use 0.8, 0.9, 0.95 or 0.99`);
  }

  if (n === 0) {
    return { successes: 0, n: 0, point: 0, lower: 0, upper: 1, width: 1, confidence };
  }

  const p = successes / n;
  const z2 = z * z;
  const denominator = 1 + z2 / n;
  const centre = (p + z2 / (2 * n)) / denominator;
  const spread = (z / denominator) * Math.sqrt((p * (1 - p)) / n + z2 / (4 * n * n));

  const lower = Math.max(0, centre - spread);
  const upper = Math.min(1, centre + spread);

  return {
    successes,
    n,
    point: round(p, 4),
    lower: round(lower, 4),
    upper: round(upper, 4),
    width: round(upper - lower, 4),
    confidence,
  };
}

/**
 * How many samples are needed for an interval no wider than `targetWidth`.
 *
 * Worst case, at p = 0.5. Used to answer the only question that matters when
 * setting up a run: "how many calls do I have to pay for to get an answer I can
 * quote?" The answer is unkind — halving the interval costs four times the
 * samples — and the product should say so rather than hide it.
 */
export function samplesForWidth(targetWidth: number, confidence = 0.95): number {
  const z = Z[confidence];
  if (z === undefined) throw new Error(`samplesForWidth: unsupported confidence ${confidence}`);
  if (targetWidth <= 0 || targetWidth >= 1) {
    throw new Error("samplesForWidth: targetWidth must be between 0 and 1");
  }
  // Normal-approximation sizing at p=0.5, which is close enough for planning
  // and always errs toward more samples than Wilson strictly needs.
  return Math.ceil((z * z) / (targetWidth * targetWidth));
}

/* ------------------------------------------------------------------ ranks */

export interface RankSummary {
  /** Samples in which the brand appeared at all. */
  appearances: number;
  mean: number;
  /** Sample standard deviation; 0 when it appeared once. */
  sd: number;
  best: number;
  worst: number;
}

/**
 * Rank across the samples where the brand appeared.
 *
 * Reported separately from the appearance proportion on purpose. A brand that
 * appears in 2 of 10 samples at rank 1 is in a different position from one that
 * appears in 9 of 10 at rank 5, and a single blended "average rank" hides which
 * one you are.
 */
export function summariseRanks(ranks: number[]): RankSummary | null {
  if (ranks.length === 0) return null;

  const n = ranks.length;
  const mean = ranks.reduce((a, b) => a + b, 0) / n;
  const variance = n < 2 ? 0 : ranks.reduce((acc, r) => acc + (r - mean) ** 2, 0) / (n - 1);

  return {
    appearances: n,
    mean: round(mean, 2),
    sd: round(Math.sqrt(variance), 2),
    best: Math.min(...ranks),
    worst: Math.max(...ranks),
  };
}

/* ------------------------------------------------------------- agreement */

export interface Agreement<T extends string> {
  /** The label that won. */
  majority: T;
  /** Fraction of votes for the majority label. */
  ratio: number;
  votes: Record<string, number>;
  n: number;
  /** True when the classifier did not reach a clear majority. */
  contested: boolean;
}

/**
 * Majority label plus how unanimous the vote was.
 *
 * Used for sentiment, which is the one part of the extraction pipeline that
 * needs a model and is therefore the one part that can be quietly unstable. A
 * sentiment label from a single classification is a coin whose bias nobody
 * measured; classifying n times and reporting the agreement ratio makes the
 * instability visible instead of averaging it into the headline number.
 *
 * Ties break toward the alphabetically first label so the result is
 * reproducible, and `contested` flags them for a human.
 */
export function agreement<T extends string>(labels: T[], threshold = 0.7): Agreement<T> {
  if (labels.length === 0) throw new Error("agreement: no labels");

  const votes: Record<string, number> = {};
  for (const label of labels) votes[label] = (votes[label] ?? 0) + 1;

  const ranked = Object.entries(votes).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const [majority, count] = ranked[0];
  const ratio = count / labels.length;

  return {
    majority: majority as T,
    ratio: round(ratio, 3),
    votes,
    n: labels.length,
    contested: ratio < threshold,
  };
}

/* ------------------------------------------------------------------ drift */

export type DriftVerdict = "unchanged" | "moved" | "inconclusive";

export interface DriftResult {
  verdict: DriftVerdict;
  before: Proportion;
  after: Proportion;
  delta: number;
  /** Plain-language reason, shown in the report. */
  reason: string;
}

/**
 * Did anything actually change between two measurement rounds?
 *
 * The question every tool in this category dodges. Publish something, re-measure,
 * see 18% become 24%, and there is no way to tell whether the content worked or
 * whether the dice fell differently. Here the two intervals are compared: if
 * they overlap, the movement is inside the noise and the honest answer is "we
 * cannot tell yet, take more samples".
 *
 * `inconclusive` is a first-class verdict, not a failure. Reporting a change
 * that the sample size cannot support is how these tools produce confident
 * nonsense.
 */
export function detectDrift(
  before: { successes: number; n: number },
  after: { successes: number; n: number },
  confidence = 0.95,
): DriftResult {
  const a = wilson(before.successes, before.n, confidence);
  const b = wilson(after.successes, after.n, confidence);
  const delta = round(b.point - a.point, 4);

  const overlap = a.lower <= b.upper && b.lower <= a.upper;

  if (!overlap) {
    return {
      verdict: "moved",
      before: a,
      after: b,
      delta,
      reason:
        `intervals do not overlap: ${pct(a.lower)}-${pct(a.upper)} then ` +
        `${pct(b.lower)}-${pct(b.upper)}. The change is larger than sampling noise.`,
    };
  }

  // Overlapping intervals mean the data cannot separate the two rounds. Whether
  // that reads as "nothing moved" or "we do not know" depends on how tight the
  // measurement was: wide intervals cannot support either claim.
  const looseEnoughToHideRealChange = Math.max(a.width, b.width) > 0.25;

  if (looseEnoughToHideRealChange) {
    const needed = samplesForWidth(0.2, confidence);
    return {
      verdict: "inconclusive",
      before: a,
      after: b,
      delta,
      reason:
        `intervals overlap and are wide (${pct(a.width)} and ${pct(b.width)}). ` +
        `A real change could hide in that. About ${needed} samples per round would be needed to see a 20-point shift.`,
    };
  }

  return {
    verdict: "unchanged",
    before: a,
    after: b,
    delta,
    reason:
      `intervals overlap and both are tight (${pct(a.width)} and ${pct(b.width)}). ` +
      `The observed ${pct(Math.abs(delta))} move is consistent with sampling noise.`,
  };
}

/** Formats a proportion as a percentage string, for report text. */
export function pct(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`;
}

/** "3/10 = 30.0% (6.7% to 65.2%)" — the format the whole product exists to print. */
export function formatProportion(p: Proportion): string {
  return `${p.successes}/${p.n} = ${pct(p.point)} (${pct(p.lower)} to ${pct(p.upper)})`;
}
