/**
 * Extraction is where a silent bug becomes a wrong metric, so the awkward cases
 * are tested rather than assumed: names inside other names, names that are also
 * ordinary words, names inside code blocks and URLs.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { extractMentions, isOrdinaryWord, maskNonProse, withheldMentions } from "../src/lib/mentions.ts";
import { BrandSchema, type Brand } from "../src/lib/schemas.ts";

const brand = (input: Partial<Brand> & { id: string; name: string }): Brand =>
  BrandSchema.parse(input);

const BRANDS: Brand[] = [
  brand({ id: "rabadon", name: "rabadon" }),
  brand({ id: "langfuse", name: "Langfuse" }),
  brand({ id: "langsmith", name: "LangSmith", aliases: ["LangChain LangSmith"] }),
  brand({ id: "monday", name: "Monday.com", aliases: ["Monday"], ambiguousName: true }),
  brand({ id: "linear", name: "Linear", ambiguousName: true }),
  brand({ id: "clo3d", name: "CLO3D", aliases: ["CLO 3D", "CLO"] }),
];

test("rank follows order of first appearance in the text", () => {
  const answer = "Most teams use Langfuse first, then look at LangSmith, and rabadon is newer.";
  const mentions = extractMentions(answer, BRANDS);

  assert.deepEqual(
    mentions.map((m) => [m.brandId, m.rank]),
    [
      ["langfuse", 1],
      ["langsmith", 2],
      ["rabadon", 3],
    ],
  );
  // The offset is the evidence behind the rank, so it is kept.
  assert.ok(mentions[0].charOffset < mentions[1].charOffset);
});

test("a repeated name is ranked by its first appearance, not its last", () => {
  const answer = "rabadon is worth a look. Langfuse is popular. rabadon again.";
  const mentions = extractMentions(answer, BRANDS);
  assert.deepEqual(
    mentions.map((m) => m.brandId),
    ["rabadon", "langfuse"],
  );
});

test("ranks are dense, so a rank of 2 always means one name came first", () => {
  const answer = "Only LangSmith and rabadon here.";
  const mentions = extractMentions(answer, BRANDS);
  assert.deepEqual(
    mentions.map((m) => m.rank),
    [1, 2],
  );
});

/* ------------------------------------------------------- overlapping names */

test("the longest alias wins, so Monday.com is not counted as bare Monday", () => {
  const answer = "Teams comparing Monday.com and Langfuse.";
  const mentions = extractMentions(answer, BRANDS);

  const monday = mentions.find((m) => m.brandId === "monday");
  assert.ok(monday, "Monday.com should be counted");
  assert.equal(monday.matchedAlias, "Monday.com");
  assert.equal(monday.ambiguous, false, "the full product name is not ambiguous");
});

test("a short alias does not match inside a longer unrelated word", () => {
  // "CLO" must not fire inside "CLO3D", and neither may fire inside "CLOSE".
  const inside = extractMentions("We evaluated CLO3D for grading.", BRANDS);
  assert.deepEqual(
    inside.map((m) => [m.brandId, m.matchedAlias]),
    [["clo3d", "CLO3D"]],
  );

  const unrelated = extractMentions("CLOSE the file and CLOTHING is unrelated.", BRANDS);
  assert.deepEqual(unrelated, [], "no tracked name appears here");
});

test("word boundaries are not fooled by punctuation or possessives", () => {
  const mentions = extractMentions("(Langfuse), rabadon's docs, and LangSmith.", BRANDS);
  assert.deepEqual(
    mentions.map((m) => m.brandId),
    ["langfuse", "rabadon", "langsmith"],
  );
});

/* --------------------------------------------------------- ordinary words */

test("a name that is also an ordinary word is withheld, not counted", () => {
  const answer = "We ship every Monday and growth has been linear so far.";

  const counted = extractMentions(answer, BRANDS);
  assert.deepEqual(counted, [], "neither is evidence of a product mention");

  // But the evidence is surfaced rather than thrown away.
  const withheld = withheldMentions(answer, BRANDS);
  assert.deepEqual(
    withheld.map((m) => m.brandId).sort(),
    ["linear", "monday"],
  );
  assert.ok(withheld.every((m) => m.ambiguous));
});

test("an ordinary-word brand is counted when a strong alias appears too", () => {
  // Bare "Monday" first, the real product name later. Evidence quality wins
  // over position: the mention is counted and not flagged.
  const answer = "On Monday we compared tools. Monday.com came out ahead.";
  const mentions = extractMentions(answer, BRANDS);

  const monday = mentions.find((m) => m.brandId === "monday");
  assert.ok(monday);
  assert.equal(monday.ambiguous, false);
  assert.equal(monday.matchedAlias, "Monday.com");
});

test("includeAmbiguous is an explicit opt-in, never the default", () => {
  const answer = "Growth was linear.";
  assert.deepEqual(extractMentions(answer, BRANDS), []);

  const permissive = extractMentions(answer, BRANDS, { includeAmbiguous: true });
  assert.deepEqual(
    permissive.map((m) => [m.brandId, m.ambiguous]),
    [["linear", true]],
  );
});

test("the ordinary-word list covers the names it needs to", () => {
  assert.equal(isOrdinaryWord("Monday"), true);
  assert.equal(isOrdinaryWord("linear"), true);
  assert.equal(isOrdinaryWord("Langfuse"), false);
  assert.equal(isOrdinaryWord("rabadon"), false);
});

/* --------------------------------------------------------- non-prose spans */

test("code fences, inline code, URLs and emails are not prose", () => {
  const answer = [
    "Use the client as follows:",
    "```ts",
    "import Langfuse from 'langfuse'",
    "```",
    "See https://langfuse.com/docs or mail team@langfuse.com.",
    "In practice rabadon is the one we shipped.",
  ].join("\n");

  const mentions = extractMentions(answer, BRANDS);
  assert.deepEqual(
    mentions.map((m) => m.brandId),
    ["rabadon"],
    "Langfuse appeared only in code, a link and an address",
  );
});

test("masking preserves offsets so ranks stay correct", () => {
  const answer = "`Langfuse` then rabadon.";
  const masked = maskNonProse(answer);
  assert.equal(masked.length, answer.length, "offsets must not shift");
  assert.equal(masked.indexOf("rabadon"), answer.indexOf("rabadon"));
});

test("inline code does not swallow the rest of the line", () => {
  const answer = "Run `npm i` and then Langfuse works.";
  const mentions = extractMentions(answer, BRANDS);
  assert.deepEqual(
    mentions.map((m) => m.brandId),
    ["langfuse"],
  );
});

/* ------------------------------------------------------------------ basics */

test("an answer naming nothing tracked yields no mentions", () => {
  assert.deepEqual(extractMentions("A general answer about software.", BRANDS), []);
  assert.deepEqual(extractMentions("", BRANDS), []);
});

test("matching is case-insensitive but reports the alias as configured", () => {
  const mentions = extractMentions("langfuse and LANGSMITH both.", BRANDS);
  assert.deepEqual(
    mentions.map((m) => [m.brandId, m.matchedAlias]),
    [
      ["langfuse", "Langfuse"],
      ["langsmith", "LangSmith"],
    ],
  );
});

test("extraction is reproducible", () => {
  const answer = "Langfuse, then rabadon, then Monday.com.";
  assert.deepEqual(extractMentions(answer, BRANDS), extractMentions(answer, BRANDS));
});
