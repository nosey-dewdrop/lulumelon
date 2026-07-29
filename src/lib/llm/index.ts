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
  planner: "claude-sonnet-4-6",
  writer: "claude-haiku-4-5-20251001",
  judge: "claude-sonnet-4-6",
  critic: "claude-sonnet-4-6",
};

const OPENAI_DEFAULTS: Record<AgentRole, string> = {
  planner: "gpt-4o-mini",
  writer: "gpt-4o-mini",
  judge: "gpt-4o",
  critic: "gpt-4o",
};

function resolveModels(defaults: Record<AgentRole, string>): Record<AgentRole, string> {
  return {
    planner: process.env.LLM_MODEL_PLANNER || defaults.planner,
    writer: process.env.LLM_MODEL_WRITER || defaults.writer,
    judge: process.env.LLM_MODEL_JUDGE || defaults.judge,
    critic: process.env.LLM_MODEL_CRITIC || defaults.critic,
  };
}

/**
 * Failure-path switches for the stub, driven by env so the demo can be run
 * end to end without editing code:
 *
 *   LLM_FAKE_FABRICATE_INDEX=0  the first writer emits fabricated claims, and
 *                               the grounding gate disqualifies it before the
 *                               judge ever scores it
 *   LLM_FAKE_FAIL_ROLE=judge    that agent throws, so the topic degrades to a
 *                               partial result while the other topics finish
 */
function fakeOptionsFromEnv(): FakeProviderOptions {
  const index = process.env.LLM_FAKE_FABRICATE_INDEX;
  const failRole = process.env.LLM_FAKE_FAIL_ROLE as FakeProviderOptions["failRole"];
  return {
    fabricateAtIndex: index === undefined || index === "" ? undefined : Number(index),
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
