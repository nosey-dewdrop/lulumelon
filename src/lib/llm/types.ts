/**
 * The model boundary.
 *
 * Every agent talks to this interface and nothing else. Three consequences,
 * each of which is the reason it exists:
 *
 *  1. The orchestration is testable with no network and no key. The `fake`
 *     provider is deterministic, so a test can assert what the workflow does
 *     with a given set of agent outputs instead of hoping a model cooperates.
 *
 *  2. Cost is a configuration decision, not a code change. Writers run once per
 *     variant per topic and are the volume; the judge and critic decide and are
 *     the ones worth paying for. Roles map to models in env.
 *
 *  3. It can be pointed at a free endpoint. Any OpenAI-compatible gateway works,
 *     including a local Ollama, so the pipeline can be run end to end at zero
 *     marginal cost.
 */
import type { z } from "zod";

export type AgentRole = "answer" | "sentiment";

export interface GenerateRequest<T> {
  role: AgentRole;
  /** Instructions that describe the contract and the grounding rules. */
  system: string;
  /** The task, including the derived data the agent is allowed to use. */
  user: string;
  /** The contract the response must satisfy. Enforced, not requested. */
  schema: z.ZodType<T>;
  /** Name used in error messages and the run trace. */
  schemaName: string;
  maxOutputTokens?: number;
}

export interface Usage {
  inputTokens: number;
  outputTokens: number;
}

export interface GenerateResult<T> {
  value: T;
  usage: Usage;
  model: string;
  /** How many attempts it took to get schema-valid output. */
  attempts: number;
}

export interface LlmProvider {
  readonly name: string;
  modelFor(role: AgentRole): string;
  generate<T>(request: GenerateRequest<T>): Promise<GenerateResult<T>>;
}

/**
 * Thrown when a model cannot produce output matching its contract.
 *
 * Fields are declared explicitly rather than as constructor parameter
 * properties: Node runs this TypeScript by stripping types, and parameter
 * properties are the one common construct that cannot be stripped because they
 * emit runtime assignments. Keeping to strippable syntax is what lets the whole
 * project run and test with no build step.
 */
export class SchemaViolationError extends Error {
  readonly schemaName: string;
  readonly attempts: number;
  readonly lastIssue: string;
  readonly lastRaw: string;

  constructor(schemaName: string, attempts: number, lastIssue: string, lastRaw: string) {
    super(`${schemaName} contract not satisfied after ${attempts} attempt(s): ${lastIssue}`);
    this.name = "SchemaViolationError";
    this.schemaName = schemaName;
    this.attempts = attempts;
    this.lastIssue = lastIssue;
    this.lastRaw = lastRaw;
  }
}
