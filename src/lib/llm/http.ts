/**
 * The live providers.
 *
 * Two transports, one enforcement path. Whatever the endpoint, the response is
 * parsed and validated against the agent's Zod contract, and a violation is fed
 * back to the model as a repair instruction rather than propagated downstream.
 *
 * The OpenAI transport deliberately uses `response_format: json_object` and the
 * schema in the prompt, not the stricter `json_schema` mode. That mode is not
 * implemented consistently across the gateways this needs to run on, and a
 * local Ollama does not support it at all. Since the Zod loop is the real
 * enforcement, using the lowest common denominator costs nothing and keeps the
 * pipeline runnable at zero marginal cost.
 */
import { z } from "zod";

import {
  SchemaViolationError,
  type AgentRole,
  type GenerateRequest,
  type GenerateResult,
  type LlmProvider,
} from "./types.ts";

/** How many times to ask a model to repair contract-violating output. */
const MAX_ATTEMPTS = 3;

export interface HttpProviderConfig {
  apiKey: string;
  baseUrl: string;
  models: Record<AgentRole, string>;
  /** Abort a single model call after this long. */
  timeoutMs?: number;
}

const DEFAULT_TIMEOUT_MS = 60_000;

function contractInstruction(schemaName: string, schema: z.ZodType<unknown>): string {
  const json = JSON.stringify(z.toJSONSchema(schema), null, 2);
  return [
    `Respond with a single JSON object and nothing else. No prose, no code fence.`,
    `It must satisfy this JSON Schema (${schemaName}):`,
    json,
  ].join("\n");
}

/** Pulls a JSON object out of a response that may still be wrapped in prose. */
function extractJson(text: string): string {
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (fenced) return fenced[1].trim();

  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start !== -1 && end > start) return text.slice(start, end + 1);
  return text.trim();
}

/**
 * Shared validate-and-repair loop. `call` performs one round trip.
 * Exported so the enforcement can be tested without a network transport.
 */
export async function runWithContract<T>(
  request: GenerateRequest<T>,
  model: string,
  call: (system: string, user: string) => Promise<{ text: string; usage: GenerateResult<T>["usage"] }>,
): Promise<GenerateResult<T>> {
  const system = `${request.system}\n\n${contractInstruction(request.schemaName, request.schema)}`;

  let user = request.user;
  let lastIssue = "";
  let lastRaw = "";
  let totalIn = 0;
  let totalOut = 0;

  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1) {
    const { text, usage } = await call(system, user);
    totalIn += usage.inputTokens;
    totalOut += usage.outputTokens;
    lastRaw = text;

    let candidate: unknown;
    try {
      candidate = JSON.parse(extractJson(text));
    } catch (error) {
      lastIssue = `response was not valid JSON: ${(error as Error).message}`;
      user = `${request.user}\n\nYour previous reply could not be parsed as JSON. ${lastIssue}\nReturn only the JSON object.`;
      continue;
    }

    const parsed = request.schema.safeParse(candidate);
    if (parsed.success) {
      return {
        value: parsed.data,
        model,
        attempts: attempt,
        usage: { inputTokens: totalIn, outputTokens: totalOut },
      };
    }

    // Feed the exact validation failure back. This is why the contract is worth
    // having: the repair instruction is precise instead of "try again".
    lastIssue = parsed.error.issues
      .map((i) => `${i.path.join(".") || "<root>"}: ${i.message}`)
      .join("; ");
    user = `${request.user}\n\nYour previous reply did not satisfy the contract:\n${lastIssue}\nReturn a corrected JSON object.`;
  }

  throw new SchemaViolationError(request.schemaName, MAX_ATTEMPTS, lastIssue, lastRaw);
}

/* ----------------------------------------------------------- OpenAI-compatible */

export function createOpenAiCompatibleProvider(config: HttpProviderConfig): LlmProvider {
  const timeoutMs = config.timeoutMs ?? DEFAULT_TIMEOUT_MS;

  return {
    name: "openai-compatible",
    modelFor: (role) => config.models[role],

    async generate<T>(request: GenerateRequest<T>): Promise<GenerateResult<T>> {
      const model = config.models[request.role];

      return runWithContract(request, model, async (system, user) => {
        const response = await fetch(`${config.baseUrl.replace(/\/$/, "")}/chat/completions`, {
          method: "POST",
          headers: {
            "content-type": "application/json",
            authorization: `Bearer ${config.apiKey}`,
          },
          body: JSON.stringify({
            model,
            temperature: 0.7,
            max_tokens: request.maxOutputTokens ?? 2000,
            response_format: { type: "json_object" },
            messages: [
              { role: "system", content: system },
              { role: "user", content: user },
            ],
          }),
          signal: AbortSignal.timeout(timeoutMs),
        });

        if (!response.ok) {
          throw new Error(`${model} returned ${response.status}: ${await response.text()}`);
        }

        const body = (await response.json()) as {
          choices: { message: { content: string } }[];
          usage?: { prompt_tokens?: number; completion_tokens?: number };
        };

        return {
          text: body.choices[0]?.message?.content ?? "",
          usage: {
            inputTokens: body.usage?.prompt_tokens ?? 0,
            outputTokens: body.usage?.completion_tokens ?? 0,
          },
        };
      });
    },
  };
}

/* -------------------------------------------------------------------- Anthropic */

export function createAnthropicProvider(config: HttpProviderConfig): LlmProvider {
  const timeoutMs = config.timeoutMs ?? DEFAULT_TIMEOUT_MS;

  return {
    name: "anthropic",
    modelFor: (role) => config.models[role],

    async generate<T>(request: GenerateRequest<T>): Promise<GenerateResult<T>> {
      const model = config.models[request.role];

      return runWithContract(request, model, async (system, user) => {
        const response = await fetch(`${config.baseUrl.replace(/\/$/, "")}/v1/messages`, {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "x-api-key": config.apiKey,
            "anthropic-version": "2023-06-01",
          },
          body: JSON.stringify({
            model,
            max_tokens: request.maxOutputTokens ?? 2000,
            temperature: 0.7,
            system,
            messages: [{ role: "user", content: user }],
          }),
          signal: AbortSignal.timeout(timeoutMs),
        });

        if (!response.ok) {
          throw new Error(`${model} returned ${response.status}: ${await response.text()}`);
        }

        const body = (await response.json()) as {
          content: { type: string; text?: string }[];
          usage?: { input_tokens?: number; output_tokens?: number };
        };

        return {
          text: body.content
            .filter((block) => block.type === "text")
            .map((block) => block.text ?? "")
            .join(""),
          usage: {
            inputTokens: body.usage?.input_tokens ?? 0,
            outputTokens: body.usage?.output_tokens ?? 0,
          },
        };
      });
    },
  };
}
