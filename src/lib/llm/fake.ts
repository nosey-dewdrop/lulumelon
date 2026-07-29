/**
 * A deterministic stand-in for a provider that is nevertheless *unstable* across
 * draws.
 *
 * This is the important property, and it is not the usual reason for a stub. The
 * product's whole claim is that repeated draws of the same prompt disagree, so a
 * stub that returns one fixed answer cannot exercise any of it, the intervals,
 * the agreement ratio, the drift verdict would all be tested against a constant.
 *
 * So the answer is seeded by (prompt, provider, drawIndex): reproducible for a
 * given draw, different between draws. Ten draws against this provider produce a
 * spread that the statistics layer has to handle correctly, with no network and
 * no key.
 */
import { createHash } from "node:crypto";

import { SentimentVoteSchema, type SentimentVote } from "../schemas.ts";
import type { AgentRole, GenerateRequest, GenerateResult, LlmProvider } from "./types.ts";

export interface FakeProviderOptions {
  /** Names the stub may put in an answer, in the order it prefers them. */
  vocabulary?: string[];
  /** Make the given role throw, to exercise failure handling. */
  failRole?: AgentRole;
  /** Fail this fraction of draws deterministically, to exercise partial rounds. */
  failEveryNthDraw?: number;
}

/** Stable value in [0,1) from a string. No Math.random. */
function unit(seed: string): number {
  return createHash("sha256").update(seed).digest().readUInt32BE(0) / 0x1_0000_0000;
}

const DEFAULT_VOCABULARY = [
  "Langfuse",
  "LangSmith",
  "Braintrust",
  "Arize Phoenix",
  "Helicone",
  "rabadon",
];

/**
 * Builds one answer.
 *
 * Which names appear, and in what order, is a function of the seed, so the
 * same draw is reproducible while different draws genuinely differ. Roughly a
 * third of the vocabulary appears in any given answer, which is about how these
 * answers behave in practice.
 */
function answerFor(seed: string, vocabulary: string[]): string {
  const scored = vocabulary
    .map((name) => ({ name, score: unit(`${seed}:${name}`) }))
    .sort((a, b) => a.score - b.score);

  // Keep names whose score clears a seed-dependent threshold, always at least two.
  const cutoff = 0.35 + unit(`${seed}:cutoff`) * 0.3;
  const chosen = scored.filter((s) => s.score < cutoff).map((s) => s.name);
  const named = chosen.length >= 2 ? chosen : scored.slice(0, 2).map((s) => s.name);

  const opening = "For this kind of work, the tools people usually reach for are";
  const list =
    named.length === 1
      ? named[0]
      : `${named.slice(0, -1).join(", ")} and ${named[named.length - 1]}`;

  return [
    `${opening} ${list}.`,
    `${named[0]} is the one most teams start with, and ${named[named.length - 1]} comes up when the requirements get stricter.`,
    "Which one fits depends on how much of the pipeline you want to own yourself.",
  ].join(" ");
}

function sentimentFor(seed: string): SentimentVote {
  const roll = unit(`${seed}:sentiment`);
  const sentiment = roll < 0.45 ? "neutral" : roll < 0.8 ? "positive" : "negative";
  return {
    sentiment,
    reason: `Deterministic stub label for seed ${seed.slice(0, 16)}; a real classifier explains itself here.`,
  };
}

export function createFakeProvider(options: FakeProviderOptions = {}): LlmProvider {
  const vocabulary = options.vocabulary ?? DEFAULT_VOCABULARY;
  let draws = 0;

  return {
    name: "fake",
    modelFor: (role) => `fake-${role}`,

    async generate<T>(request: GenerateRequest<T>): Promise<GenerateResult<T>> {
      if (options.failRole === request.role) {
        throw new Error(`fake provider: forced failure for role "${request.role}"`);
      }

      draws += 1;
      if (options.failEveryNthDraw && draws % options.failEveryNthDraw === 0) {
        throw new Error(`fake provider: forced failure on draw ${draws}`);
      }

      // The seed is the whole user prompt, which carries the draw index, so
      // repeated draws of the same tracked prompt differ from one another.
      const seed = createHash("sha256").update(request.user).digest("hex");

      const raw: unknown =
        request.role === "answer" ? { text: answerFor(seed, vocabulary) } : sentimentFor(seed);

      // For the answer role the caller wants the prose, not an object; for
      // sentiment it wants the validated vote.
      if (request.role === "answer") {
        return {
          value: (raw as { text: string }).text as unknown as T,
          model: "fake-answer",
          attempts: 1,
          usage: {
            inputTokens: Math.ceil(request.user.length / 4),
            outputTokens: Math.ceil((raw as { text: string }).text.length / 4),
          },
        };
      }

      const parsed = SentimentVoteSchema.safeParse(raw);
      if (!parsed.success) {
        throw new Error(`fake provider produced an invalid vote: ${parsed.error.message}`);
      }

      return {
        value: parsed.data as unknown as T,
        model: "fake-sentiment",
        attempts: 1,
        usage: { inputTokens: 40, outputTokens: 30 },
      };
    },
  };
}
