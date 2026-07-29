/**
 * Provider selection.
 *
 * Roles map to models here rather than at the call site, because the cost
 * answer in NOTES.md depends on it: writers are the volume (variants x topics)
 * and get the cheap model, the judge and critic decide and get the strong one.
 * Changing that trade-off is an env edit, not a code change.
 */
import { createFakeProvider, type FakeProviderOptions } from "./fake.ts";
import { createAnthropicProvider, createOpenAiCompatibleProvider } from "./http.ts";
import type { AgentRole, LlmProvider } from "./types.ts";

export type { LlmProvider, AgentRole } from "./types.ts";
export { SchemaViolationError } from "./types.ts";
export { createFakeProvider } from "./fake.ts";

const ANTHROPIC_DEFAULTS: Record<AgentRole, string> = {
  // The answer role impersonates what a user would actually be asking, so it
  // should be the model people actually ask. The sentiment role only classifies.
  answer: "claude-sonnet-4-6",
  sentiment: "claude-haiku-4-5",
};

const OPENAI_DEFAULTS: Record<AgentRole, string> = {
  answer: "gpt-4o",
  sentiment: "gpt-4o-mini",
};

function resolveModels(defaults: Record<AgentRole, string>): Record<AgentRole, string> {
  return {
    answer: process.env.LLM_MODEL_ANSWER || defaults.answer,
    sentiment: process.env.LLM_MODEL_SENTIMENT || defaults.sentiment,
  };
}

/**
 * Failure-path switches for the stub, driven by env so a degraded round can be
 * demonstrated end to end without editing code:
 *
 *   LLM_FAKE_FAIL_EVERY_NTH_DRAW=4   every fourth draw throws, so a round
 *                                    completes with fewer samples than requested
 *                                    and the intervals widen accordingly
 *   LLM_FAKE_FAIL_ROLE=sentiment     that role throws entirely
 */
function fakeOptionsFromEnv(): FakeProviderOptions {
  const nth = process.env.LLM_FAKE_FAIL_EVERY_NTH_DRAW;
  const failRole = process.env.LLM_FAKE_FAIL_ROLE as FakeProviderOptions["failRole"];
  return {
    failEveryNthDraw: nth ? Number(nth) : undefined,
    failRole: failRole || undefined,
  };
}

export function createProviderFromEnv(fakeOptions?: FakeProviderOptions): LlmProvider {
  const kind = (process.env.LLM_PROVIDER ?? "fake").toLowerCase();

  if (kind === "fake") return createFakeProvider(fakeOptions ?? fakeOptionsFromEnv());

  const apiKey = process.env.LLM_API_KEY;
  if (!apiKey) {
    throw new Error(
      `LLM_PROVIDER=${kind} requires LLM_API_KEY. Set LLM_PROVIDER=fake to run without a key.`,
    );
  }

  if (kind === "anthropic") {
    return createAnthropicProvider({
      apiKey,
      baseUrl: process.env.LLM_BASE_URL || "https://api.anthropic.com",
      models: resolveModels(ANTHROPIC_DEFAULTS),
    });
  }

  if (kind === "openai") {
    return createOpenAiCompatibleProvider({
      apiKey,
      baseUrl: process.env.LLM_BASE_URL || "https://api.openai.com/v1",
      models: resolveModels(OPENAI_DEFAULTS),
    });
  }

  throw new Error(`unknown LLM_PROVIDER "${kind}"; expected fake, anthropic or openai`);
}
