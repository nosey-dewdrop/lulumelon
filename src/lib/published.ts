/**
 * The rounds this site is allowed to serve.
 *
 * Read from `data/published/` at build time and nowhere else. A ledger is the
 * customer's own record and is not in this repository at all, so the only way
 * a measurement reaches the web is `lulu publish` writing it here by hand and
 * somebody committing it. There is no path from a round to a url that nobody
 * chose.
 */
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { join } from "node:path";

export interface PublishedName {
  name: string;
  /** Draws of this question that named it. */
  draws: number;
  /** Draws the question was asked. */
  of: number;
  rate: number;
  low: number;
  high: number;
}

export interface PublishedRound {
  slug: string;
  question: string;
  snapshot: string;
  prompt_id: string;
  engine: string;
  model: string;
  /** `api` when the model could search while answering, `api_unsearched` when not. */
  arm: string;
  asked_at: string;
  draws: number;
  names: PublishedName[];
  /** Names a person removed by hand, kept so the page can say it happened. */
  dropped?: string[];
}

const DIRECTORY = join(process.cwd(), "data", "published");

export function publishedRounds(): PublishedRound[] {
  if (!existsSync(DIRECTORY)) return [];
  return readdirSync(DIRECTORY)
    .filter((name) => name.endsWith(".json"))
    .map((name) => JSON.parse(readFileSync(join(DIRECTORY, name), "utf8")) as PublishedRound)
    .sort((a, b) => a.question.localeCompare(b.question));
}

export function publishedRound(slug: string): PublishedRound | undefined {
  return publishedRounds().find((round) => round.slug === slug);
}

/** `api_unsearched` said in words, because the arm is the whole condition. */
export function armInWords(arm: string): string {
  return arm === "api_unsearched"
    ? "answering from its own weights, with no search tool"
    : "answering with the search tool on";
}

export function percent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}
