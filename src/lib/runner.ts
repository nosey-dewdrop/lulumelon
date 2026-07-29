/**
 * The runner: the loop that actually asks.
 *
 * Everything else in this repo consumes samples. This is the only thing that
 * produces them, and its design is settled by a measurement rather than by
 * taste.
 *
 * A variance decomposition of exactly this problem (arXiv:2607.13304, July 2026)
 * attributes the movement in a brand's appearance rate roughly like this:
 *
 *     repeated draws of the same prompt      ~35%
 *     the LANGUAGE the question is asked in  ~26-32%
 *     model identity                          ~1.6%
 *     paraphrase of the same intent           ~1.1% (main effect)
 *
 * and finds that past the fifth repeat, each extra draw buys almost nothing
 * (~0.0003 reduction in relative-error variance) while adding one more language
 * buys ~15x more (~0.00462).
 *
 * The category standardised on "five runs per prompt, in English". That is not
 * wrong so much as finished: it has already collected the cheap third of the
 * variance and stopped. So this runner spends its budget on the axes the field
 * ignores. Draws per cell stay small on purpose; the cells multiply across
 * language, paraphrase and surface.
 *
 * The word "surface" matters as much as the rest. Measured over 900 trials,
 * the same prompt on the same day swung 32 percentage points between a
 * logged-in session, a logged-out session and the API, and one brand went from
 * 15-18% in chat to 0% through the API. A number collected only through an API
 * is a number about the API.
 */
import pLimit from "p-limit";

import { extractMentions } from "./mentions.ts";
import type { LlmProvider } from "./llm/index.ts";
import { allBrands } from "./visibility.ts";
import type { Corpus, Sample, TrackedPrompt } from "./schemas.ts";
import { z } from "zod";

/**
 * One measurement condition. The cross product of these is the sampling plan,
 * and every sample records which cell it came from so the variance can later be
 * attributed rather than averaged away.
 */
export interface Cell {
  prompt: TrackedPrompt;
  /** BCP-47 tag. The single largest lever the field is not pulling. */
  language: string;
  /** Which rewording of the same intent this is. 0 is the original text. */
  paraphraseIndex: number;
  /** The exact question sent, after translation and rewording. */
  text: string;
  /** api | chat | chat-anonymous. Recorded because it dominates randomness. */
  surface: string;
  provider: string;
}

export interface RunPlan {
  cells: Cell[];
  drawsPerCell: number;
  /** cells x drawsPerCell. What the run will cost in calls. */
  totalCalls: number;
}

export interface PlanOptions {
  /**
   * Languages to ask in. Two is already better than five extra English draws.
   * Defaults to the language of the corpus only, so a caller has to opt into
   * the good axis deliberately and see the cost.
   */
  languages?: string[];
  /** Rewordings per prompt, including the original. */
  paraphrasesPerPrompt?: number;
  /** Surfaces available for this provider. */
  surfaces?: string[];
  /**
   * Draws per cell. Five is the knee of the curve; larger values are mostly
   * wasted and the planner says so rather than silently taking the money.
   */
  drawsPerCell?: number;
  providers?: string[];
}

export const DEFAULT_DRAWS_PER_CELL = 5;

/** Beyond this, extra draws per cell are not worth their cost. */
export const DRAWS_KNEE = 5;

/**
 * Builds the sampling plan without calling anything.
 *
 * Separated from execution so the cost of a run is inspectable before a single
 * token is spent, and so the plan itself can be tested.
 */
export function planRun(
  corpus: Corpus,
  options: PlanOptions = {},
): RunPlan & { warnings: string[] } {
  const languages = options.languages ?? ["en"];
  const paraphrases = Math.max(1, options.paraphrasesPerPrompt ?? 1);
  const surfaces = options.surfaces ?? ["api"];
  const providers = options.providers ?? ["default"];
  const drawsPerCell = Math.max(1, options.drawsPerCell ?? DEFAULT_DRAWS_PER_CELL);

  const cells: Cell[] = [];
  for (const prompt of corpus.prompts) {
    for (const language of languages) {
      for (let p = 0; p < paraphrases; p += 1) {
        for (const surface of surfaces) {
          for (const provider of providers) {
            cells.push({
              prompt,
              language,
              paraphraseIndex: p,
              // Translation and rewording happen at execution time; the plan
              // records the original so the cost can be computed up front.
              text: prompt.text,
              surface,
              provider,
            });
          }
        }
      }
    }
  }

  const warnings: string[] = [];

  if (drawsPerCell > DRAWS_KNEE) {
    warnings.push(
      `${drawsPerCell} draws per cell: past ${DRAWS_KNEE} each extra draw reduces error variance by ~0.0003, ` +
        `while one more language reduces it by ~0.00462. Spend the budget on languages instead.`,
    );
  }
  if (languages.length === 1) {
    warnings.push(
      "one language: query language accounts for roughly a quarter to a third of all variance, " +
        "and this run leaves that axis unmeasured.",
    );
  }
  if (surfaces.length === 1 && surfaces[0] === "api") {
    warnings.push(
      "api surface only: the same prompt has been measured swinging 32 points between api and chat. " +
        "This run describes the api, not what a person sees.",
    );
  }

  return { cells, drawsPerCell, totalCalls: cells.length * drawsPerCell, warnings };
}

/* ------------------------------------------------------------------ asking */

const AnswerSchema = z.string().min(1);

/** Instruction that makes the model answer as if a user had asked it. */
function askSystem(language: string): string {
  return [
    "You are answering a question a person typed into a chat assistant.",
    "Answer it directly and naturally, the way an assistant would.",
    "Name specific products or companies where they are relevant.",
    "Do not mention that you are being evaluated, sampled or tested.",
    `Answer in ${language}.`,
  ].join(" ");
}

export interface RunOptions {
  provider: LlmProvider;
  /** Model calls in flight. Small: this is the knob that melts a provider. */
  concurrency?: number;
  /** Called after each draw, for progress reporting. */
  onSample?: (sample: Sample, index: number, total: number) => void;
  nowMs?: () => number;
}

/**
 * Executes a plan, returning every sample including the failures.
 *
 * A failed draw is recorded with its error rather than dropped, because a
 * dropped failure silently shrinks the denominator and inflates the appearance
 * rate. Absence of an answer is not evidence of absence of a mention.
 */
export async function executeRun(
  corpus: Corpus,
  plan: RunPlan,
  options: RunOptions,
): Promise<Sample[]> {
  const limit = pLimit(options.concurrency ?? 4);
  const now = options.nowMs ?? (() => performance.now());
  const brands = allBrands(corpus);

  const jobs: (() => Promise<Sample>)[] = [];

  for (const cell of plan.cells) {
    for (let draw = 0; draw < plan.drawsPerCell; draw += 1) {
      jobs.push(async () => {
        const startedAt = now();
        // The draw index is part of the prompt so a deterministic provider still
        // varies between draws; a live provider ignores it as a trailing hint.
        const user = `${cell.text}\n\n<!-- draw ${draw} -->`;

        try {
          const result = await options.provider.generate({
            role: "answer",
            system: askSystem(cell.language),
            user,
            schema: AnswerSchema,
            schemaName: "Answer",
            maxOutputTokens: 700,
          });

          const answer = result.value;
          return {
            promptId: cell.prompt.id,
            provider: `${cell.provider}:${cell.surface}:${cell.language}:p${cell.paraphraseIndex}`,
            model: result.model,
            drawIndex: draw,
            answer,
            mentions: extractMentions(answer, brands),
            latencyMs: Math.round(now() - startedAt),
          };
        } catch (error) {
          return {
            promptId: cell.prompt.id,
            provider: `${cell.provider}:${cell.surface}:${cell.language}:p${cell.paraphraseIndex}`,
            model: options.provider.modelFor("answer"),
            drawIndex: draw,
            answer: "",
            mentions: [],
            latencyMs: Math.round(now() - startedAt),
            error: error instanceof Error ? `${error.name}: ${error.message}` : String(error),
          };
        }
      });
    }
  }

  const total = jobs.length;
  let completed = 0;

  return Promise.all(
    jobs.map((job) =>
      limit(async () => {
        const sample = await job();
        completed += 1;
        options.onSample?.(sample, completed, total);
        return sample;
      }),
    ),
  );
}

/** Rough call and token accounting for a plan, before spending anything. */
export function estimateRun(
  plan: RunPlan,
  perCallTokens = { input: 120, output: 500 },
): { calls: number; inputTokens: number; outputTokens: number } {
  return {
    calls: plan.totalCalls,
    inputTokens: plan.totalCalls * perCallTokens.input,
    outputTokens: plan.totalCalls * perCallTokens.output,
  };
}
