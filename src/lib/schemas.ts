/**
 * The data model.
 *
 * Two ideas separate this from the schema every tool in the category uses.
 *
 * First, a *sample* is the unit of storage, not a prompt. Asking a prompt once
 * gives you a sample; the metric is computed over many. A schema whose primary
 * record is "prompt -> result" has already thrown away the thing that makes the
 * number defensible.
 *
 * Second, every prompt carries an `axis`. One blended visibility score across a
 * person, two products and an infrastructure topic is a number about nothing.
 * Axes keep them apart.
 */
import { z } from "zod";

export const BrandSchema = z.object({
  id: z.string().regex(/^[a-z0-9-]+$/, "brand ids are lowercase kebab-case"),
  name: z.string().min(1),
  domain: z.string().min(1).optional(),
  /** Other spellings the same thing appears under. */
  aliases: z.array(z.string().min(1)).default([]),
  /**
   * Set when the name is also an ordinary English word, so a bare match is not
   * evidence. "Monday" the product versus "monday" the day; "Linear" the tracker
   * versus "linear" the adjective. Mentions matched only on such a name are
   * flagged rather than counted silently.
   */
  ambiguousName: z.boolean().default(false),
});
export type Brand = z.infer<typeof BrandSchema>;

export const IntentSchema = z.enum(["entity", "category", "solution", "competitor"]);
export type Intent = z.infer<typeof IntentSchema>;

export const TrackedPromptSchema = z.object({
  id: z.string().min(1),
  text: z.string().min(5),
  intent: IntentSchema,
  /** Which thing this prompt is about. Metrics never mix axes. */
  axis: z.string().min(1),
});
export type TrackedPrompt = z.infer<typeof TrackedPromptSchema>;

export const CorpusSchema = z.object({
  /** The thing being tracked. */
  subject: BrandSchema,
  /** Products or projects belonging to the subject, tracked separately. */
  projects: z.array(BrandSchema).default([]),
  /** Names expected to appear alongside, so rank means something. */
  competitors: z.array(BrandSchema).default([]),
  prompts: z.array(TrackedPromptSchema).min(1),
});
export type Corpus = z.infer<typeof CorpusSchema>;

/* ----------------------------------------------------------------- samples */

export const SentimentSchema = z.enum(["positive", "neutral", "negative"]);
export type Sentiment = z.infer<typeof SentimentSchema>;

export const MentionSchema = z.object({
  brandId: z.string().min(1),
  /** Order of first appearance in this answer; 1 is best. */
  rank: z.number().int().positive(),
  /** Character offset of the first match, which is what produced the rank. */
  charOffset: z.number().int().nonnegative(),
  /** The exact alias that matched, so a surprising mention can be traced. */
  matchedAlias: z.string().min(1),
  /** True when the only evidence was an ordinary-word name. */
  ambiguous: z.boolean(),
});
export type Mention = z.infer<typeof MentionSchema>;

/** One (prompt, provider, draw) observation. The atom of the whole system. */
export const SampleSchema = z.object({
  promptId: z.string().min(1),
  provider: z.string().min(1),
  model: z.string().min(1),
  /** 0-based draw index within this round. */
  drawIndex: z.number().int().nonnegative(),
  answer: z.string(),
  mentions: z.array(MentionSchema),
  latencyMs: z.number().nonnegative(),
  /** Set when the provider call failed; `answer` is then empty. */
  error: z.string().optional(),
});
export type Sample = z.infer<typeof SampleSchema>;

/* -------------------------------------------------- agent output contracts */

/**
 * Sentiment is the one part of extraction that needs a model, and therefore the
 * one part that can be quietly unstable. It is classified per mention, several
 * times, and the agreement ratio is reported.
 */
export const SentimentVoteSchema = z.object({
  sentiment: SentimentSchema,
  /** One sentence. Why this label and not a neighbouring one. */
  reason: z.string().min(5).max(300),
});
export type SentimentVote = z.infer<typeof SentimentVoteSchema>;
