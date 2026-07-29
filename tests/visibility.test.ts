/**
 * Aggregation tests. The fixture is authored here, not imported from anywhere:
 * these are hand-built samples whose correct answers are known by construction.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  computeAxisVisibility,
  computePromptVisibility,
  computeShareOfVoice,
  mentionKey,
  usableSamples,
} from "../src/lib/visibility.ts";
import { CorpusSchema, type Corpus, type Sample, type Sentiment } from "../src/lib/schemas.ts";

const CORPUS: Corpus = CorpusSchema.parse({
  subject: { id: "subject", name: "Subject" },
  projects: [{ id: "widget", name: "Widget" }],
  competitors: [
    { id: "rival-a", name: "RivalA" },
    { id: "rival-b", name: "RivalB" },
  ],
  prompts: [
    { id: "p1", text: "Which tool should I use for this?", intent: "category", axis: "tools" },
    { id: "p2", text: "Alternatives to RivalA for this job", intent: "competitor", axis: "tools" },
    { id: "p3", text: "Who builds Widget?", intent: "entity", axis: "widget" },
  ],
});

/** Builds a draw whose mentions are exactly the brand ids given, in order. */
function draw(
  promptId: string,
  drawIndex: number,
  brandIds: string[],
  options: { provider?: string; error?: string; ambiguous?: string[] } = {},
): Sample {
  return {
    promptId,
    provider: options.provider ?? "modelx",
    model: "modelx-1",
    drawIndex,
    answer: options.error ? "" : brandIds.join(", "),
    mentions: options.error
      ? []
      : brandIds.map((brandId, i) => ({
          brandId,
          rank: i + 1,
          charOffset: i * 10,
          matchedAlias: brandId,
          ambiguous: (options.ambiguous ?? []).includes(brandId),
        })),
    latencyMs: 100,
    ...(options.error ? { error: options.error } : {}),
  };
}

test("appearance rate is a proportion over draws, with an interval", () => {
  // Subject appears in 3 of 10 draws.
  const samples = [
    draw("p1", 0, ["rival-a", "subject"]),
    draw("p1", 1, ["rival-a"]),
    draw("p1", 2, ["rival-a", "rival-b"]),
    draw("p1", 3, ["subject", "rival-a"]),
    draw("p1", 4, ["rival-a"]),
    draw("p1", 5, ["rival-b"]),
    draw("p1", 6, ["rival-a", "rival-b", "subject"]),
    draw("p1", 7, ["rival-a"]),
    draw("p1", 8, ["rival-b"]),
    draw("p1", 9, ["rival-a"]),
  ];

  const [row] = computePromptVisibility(CORPUS, samples);
  const subject = row.brands.find((b) => b.brandId === "subject")!;

  assert.equal(row.draws, 10);
  assert.equal(row.usable, 10);
  assert.equal(subject.appearance.successes, 3);
  assert.equal(subject.appearance.n, 10);
  assert.equal(subject.appearance.point, 0.3);
  assert.ok(subject.appearance.lower > 0.1 && subject.appearance.upper < 0.61);
  // The interval is the product: a 30% reading on ten draws is not a fact.
  assert.ok(subject.appearance.width > 0.4, `width was ${subject.appearance.width}`);
});

test("rank is summarised only over draws where the brand appeared", () => {
  const samples = [
    draw("p1", 0, ["rival-a", "subject"]), // subject rank 2
    draw("p1", 1, ["rival-a"]),
    draw("p1", 2, ["subject"]), // rank 1
    draw("p1", 3, ["rival-a", "rival-b", "subject"]), // rank 3
  ];

  const [row] = computePromptVisibility(CORPUS, samples);
  const subject = row.brands.find((b) => b.brandId === "subject")!;

  assert.equal(subject.appearance.successes, 3);
  assert.equal(subject.rank!.appearances, 3);
  assert.equal(subject.rank!.mean, 2);
  assert.equal(subject.rank!.best, 1);
  assert.equal(subject.rank!.worst, 3);
  assert.ok(subject.rank!.sd > 0, "rank varied across draws and that should show");
});

test("a brand that never appeared has a null rank, not a rank of zero", () => {
  const [row] = computePromptVisibility(CORPUS, [draw("p1", 0, ["rival-a"])]);
  const subject = row.brands.find((b) => b.brandId === "subject")!;
  assert.equal(subject.rank, null);
  assert.equal(subject.appearance.successes, 0);
});

test("a failed draw is not counted as evidence of absence", () => {
  const samples = [
    draw("p1", 0, ["subject"]),
    draw("p1", 1, [], { error: "provider timeout" }),
    draw("p1", 2, ["rival-a"]),
  ];

  assert.equal(usableSamples(samples).length, 2);

  const [row] = computePromptVisibility(CORPUS, samples);
  const subject = row.brands.find((b) => b.brandId === "subject")!;

  assert.equal(row.draws, 3, "the attempt is recorded");
  assert.equal(row.usable, 2, "but the denominator is only usable draws");
  assert.equal(subject.appearance.n, 2);
  assert.equal(subject.appearance.point, 0.5);
});

test("ambiguous mentions are withheld from the rate and counted separately", () => {
  const samples = [
    draw("p1", 0, ["subject"], { ambiguous: ["subject"] }),
    draw("p1", 1, ["subject"]),
  ];

  const [row] = computePromptVisibility(CORPUS, samples);
  const subject = row.brands.find((b) => b.brandId === "subject")!;

  assert.equal(subject.appearance.successes, 1, "only the unambiguous match counts");
  assert.equal(subject.appearance.n, 2);
  assert.equal(subject.withheldCount, 1, "the withheld one is reported, not lost");
});

test("providers are never pooled into one proportion", () => {
  const samples = [
    draw("p1", 0, ["subject"], { provider: "modelx" }),
    draw("p1", 1, ["subject"], { provider: "modelx" }),
    draw("p1", 0, ["rival-a"], { provider: "modely" }),
    draw("p1", 1, ["rival-a"], { provider: "modely" }),
  ];

  const rows = computePromptVisibility(CORPUS, samples);
  assert.equal(rows.length, 2, "one row per (prompt, provider)");

  const x = rows.find((r) => r.provider === "modelx")!;
  const y = rows.find((r) => r.provider === "modely")!;
  assert.equal(x.brands.find((b) => b.brandId === "subject")!.appearance.point, 1);
  assert.equal(y.brands.find((b) => b.brandId === "subject")!.appearance.point, 0);
});

test("the leaderboard excludes brands that never appeared", () => {
  const samples = [draw("p1", 0, ["rival-a", "subject"]), draw("p1", 1, ["rival-a"])];
  const [row] = computePromptVisibility(CORPUS, samples);

  assert.deepEqual(
    row.leaderboard.map((b) => b.brandId),
    ["rival-a", "subject"],
  );
  assert.ok(!row.leaderboard.some((b) => b.brandId === "rival-b"));
});

test("sentiment is tallied per appearance when labels are supplied", () => {
  const samples = [draw("p1", 0, ["subject"]), draw("p1", 1, ["subject"])];
  const labels = new Map<string, Sentiment>([
    [mentionKey("p1", "modelx", 0, "subject"), "positive"],
    [mentionKey("p1", "modelx", 1, "subject"), "neutral"],
  ]);

  const [row] = computePromptVisibility(CORPUS, samples, { sentimentByMention: labels });
  const subject = row.brands.find((b) => b.brandId === "subject")!;
  assert.deepEqual(subject.sentiment, { positive: 1, neutral: 1, negative: 0 });
});

test("an unknown prompt id is a loud failure, not a silent skip", () => {
  assert.throws(
    () => computePromptVisibility(CORPUS, [draw("nope", 0, ["subject"])]),
    /unknown prompt nope/,
  );
});

/* -------------------------------------------------------------------- axes */

test("axis pooling counts draws, not per-prompt averages", () => {
  // Axis "tools" has p1 and p2. Subject: 1 of 2 on p1, 3 of 4 on p2.
  // Pooled is 4 of 6, not the mean of 50% and 75%.
  const samples = [
    draw("p1", 0, ["subject"]),
    draw("p1", 1, ["rival-a"]),
    draw("p2", 0, ["subject"]),
    draw("p2", 1, ["subject"]),
    draw("p2", 2, ["subject"]),
    draw("p2", 3, ["rival-a"]),
  ];

  const axes = computeAxisVisibility(CORPUS, computePromptVisibility(CORPUS, samples));
  const tools = axes.find((a) => a.axis === "tools")!;

  assert.equal(tools.promptCount, 2);
  assert.equal(tools.subjectAppearance.successes, 4);
  assert.equal(tools.subjectAppearance.n, 6);
});

test("axes are kept apart so one blended score is never reported", () => {
  const samples = [
    draw("p1", 0, ["subject"]),
    draw("p3", 0, ["rival-a"]),
    draw("p3", 1, ["rival-a"]),
  ];

  const axes = computeAxisVisibility(CORPUS, computePromptVisibility(CORPUS, samples));
  assert.deepEqual(
    axes.map((a) => a.axis),
    ["tools", "widget"],
  );
  assert.equal(axes.find((a) => a.axis === "tools")!.subjectAppearance.point, 1);
  assert.equal(axes.find((a) => a.axis === "widget")!.subjectAppearance.point, 0);
});

test("absent and always-present prompts are named", () => {
  const samples = [
    draw("p1", 0, ["subject"]),
    draw("p1", 1, ["subject"]),
    draw("p2", 0, ["rival-a"]),
    draw("p2", 1, ["rival-a"]),
  ];

  const axes = computeAxisVisibility(CORPUS, computePromptVisibility(CORPUS, samples));
  const tools = axes.find((a) => a.axis === "tools")!;

  assert.deepEqual(tools.alwaysPresentPrompts, ["p1"]);
  assert.deepEqual(tools.absentPrompts, ["p2"]);
});

test('"ahead" requires non-overlapping intervals, not just a bigger number', () => {
  // RivalA 6/10, subject 4/10. Point estimates differ; intervals overlap
  // heavily, so nobody is measurably ahead of anybody.
  const close: Sample[] = [];
  for (let i = 0; i < 10; i += 1) {
    close.push(draw("p1", i, i < 6 ? (i < 4 ? ["rival-a", "subject"] : ["rival-a"]) : ["rival-b"]));
  }

  const axes = computeAxisVisibility(CORPUS, computePromptVisibility(CORPUS, close));
  assert.deepEqual(axes.find((a) => a.axis === "tools")!.ahead, [], "overlap means not ahead");

  // Now a gap wide enough to survive: rival-a 40/40, subject 2/40.
  const wide: Sample[] = [];
  for (let i = 0; i < 40; i += 1) {
    wide.push(draw("p1", i, i < 2 ? ["rival-a", "subject"] : ["rival-a"]));
  }

  const clear = computeAxisVisibility(CORPUS, computePromptVisibility(CORPUS, wide));
  assert.deepEqual(
    clear.find((a) => a.axis === "tools")!.ahead.map((c) => c.brandId),
    ["rival-a"],
  );
});

/* -------------------------------------------------------- share of voice */

test("share of voice is computed but carries an interval too", () => {
  const samples = [
    draw("p1", 0, ["rival-a", "subject"]),
    draw("p1", 1, ["rival-a"]),
  ];

  const sov = computeShareOfVoice(CORPUS, samples);
  const rivalA = sov.find((s) => s.brandId === "rival-a")!;
  const subject = sov.find((s) => s.brandId === "subject")!;

  assert.equal(rivalA.mentions, 2);
  assert.equal(subject.mentions, 1);
  // Three mentions total, so the subject holds one third of them.
  assert.ok(Math.abs(subject.share.point - 0.3333) < 0.001);
  assert.ok(subject.share.width > 0.5, "three mentions cannot support a precise share");
});

test("ambiguous mentions do not inflate anybody's share of voice", () => {
  const samples = [draw("p1", 0, ["rival-a", "subject"], { ambiguous: ["rival-a"] })];
  const sov = computeShareOfVoice(CORPUS, samples);
  assert.equal(sov.find((s) => s.brandId === "rival-a")!.mentions, 0);
  assert.equal(sov.find((s) => s.brandId === "subject")!.share.point, 1);
});
