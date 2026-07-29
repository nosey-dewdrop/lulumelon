/**
 * Mention extraction: given an answer, which tracked names appear, in what
 * order, and how much can we trust each match.
 *
 * Deterministic. No model, no network. Every visibility number downstream is
 * built on this function, so it is the one place a silent error becomes a wrong
 * metric — which is precisely what a hand-inspected export of this category's
 * data turned out to contain.
 *
 * Four decisions worth defending:
 *
 *  1. Rank is the order of first appearance, measured by character offset. Not
 *     "which is discussed most", not "which the model recommends" — the
 *     positional fact, which is the only part that is objectively in the text.
 *
 *  2. Longest alias wins. "Monday.com" and "Monday" both match the same string;
 *     taking the longer one keeps the evidence as strong as the text allows.
 *
 *  3. Names that are ordinary English words are flagged, not silently counted.
 *     "We ship on Monday" is not a mention of Monday.com, and "linear growth" is
 *     not a mention of Linear. Counting those inflates a competitor's share of
 *     voice and there is no way to notice it after the fact.
 *
 *  4. Code blocks and URLs are excluded from the searched text. A brand name
 *     inside a code fence or a link path is not the model naming a product to
 *     the reader.
 */
import type { Brand, Mention } from "./schemas.ts";

/** Escapes a literal for use inside a regular expression. */
function escapeRegex(literal: string): string {
  return literal.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Builds a matcher for one alias.
 *
 * Word boundaries are asserted with lookarounds rather than `\b`, because `\b`
 * is defined against `\w` and gets the edges wrong for names containing dots or
 * hyphens: `\bmonday.com\b` fails to anchor after "com" the way you would
 * expect, and `\bCLO\b` inside "CLO3D" matches when it should not.
 */
function aliasPattern(alias: string): RegExp {
  const escaped = escapeRegex(alias);
  // A match may not be preceded or followed by a letter or digit. Punctuation,
  // whitespace and string edges are all acceptable boundaries.
  return new RegExp(`(?<![\\p{L}\\p{N}])${escaped}(?![\\p{L}\\p{N}])`, "giu");
}

/**
 * Words common enough in English prose that a bare match is not evidence.
 * Deliberately short: this list only needs to cover names a tracked brand might
 * actually collide with.
 */
const ORDINARY_WORDS = new Set([
  "monday", "linear", "notion", "figma", "arc", "slack", "stripe", "square",
  "sage", "canvas", "atlas", "prism", "beacon", "compass", "anchor", "shift",
]);

export function isOrdinaryWord(name: string): boolean {
  return ORDINARY_WORDS.has(name.trim().toLowerCase());
}

/**
 * Blanks out spans that are not the model addressing the reader: fenced and
 * inline code, and URLs. Replaced with spaces rather than removed so that every
 * character offset in the result still refers to the original string.
 */
export function maskNonProse(text: string): string {
  const blank = (match: string) => " ".repeat(match.length);
  return text
    .replace(/```[\s\S]*?```/g, blank)
    .replace(/`[^`\n]*`/g, blank)
    .replace(/https?:\/\/\S+/g, blank)
    .replace(/\b[\w.-]+@[\w.-]+\.\w+\b/g, blank);
}

interface Candidate {
  brand: Brand;
  alias: string;
  offset: number;
  length: number;
  /** True when this alias is an ordinary English word. */
  weak: boolean;
}

/** Every alias hit for every brand, before overlap resolution. */
function collectCandidates(masked: string, brands: Brand[]): Candidate[] {
  const out: Candidate[] = [];

  for (const brand of brands) {
    // The name itself is always a candidate alias.
    const aliases = [brand.name, ...brand.aliases];
    const seen = new Set<string>();

    for (const alias of aliases) {
      const key = alias.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);

      const weak = brand.ambiguousName && isOrdinaryWord(alias);

      for (const match of masked.matchAll(aliasPattern(alias))) {
        out.push({
          brand,
          alias,
          offset: match.index,
          length: match[0].length,
          weak,
        });
      }
    }
  }

  return out;
}

/**
 * Drops candidates swallowed by a longer overlapping match.
 *
 * Without this, "Monday.com" produces two hits — one for the full name and one
 * for the bare "Monday" inside it — and the bare one would be flagged ambiguous,
 * dragging an unambiguous mention into the doubtful bucket.
 */
function resolveOverlaps(candidates: Candidate[]): Candidate[] {
  const byLengthDesc = [...candidates].sort(
    (a, b) => b.length - a.length || a.offset - b.offset,
  );

  const kept: Candidate[] = [];
  for (const candidate of byLengthDesc) {
    const end = candidate.offset + candidate.length;
    const swallowed = kept.some((k) => {
      const kEnd = k.offset + k.length;
      return candidate.offset >= k.offset && end <= kEnd;
    });
    if (!swallowed) kept.push(candidate);
  }
  return kept;
}

export interface ExtractionOptions {
  /**
   * Keep mentions whose only evidence is an ordinary-word name. Off by default:
   * counting them inflates share of voice, and the flag exists so a human can
   * decide, not so the pipeline can quietly include them.
   */
  includeAmbiguous?: boolean;
}

/**
 * Extracts ranked mentions from one answer.
 *
 * Rank is assigned over the brands that survive filtering, so ranks are always
 * a dense 1..n sequence — a rank of 3 means two other tracked names came first
 * in the text, with no gaps to interpret.
 */
export function extractMentions(
  answer: string,
  brands: Brand[],
  options: ExtractionOptions = {},
): Mention[] {
  const masked = maskNonProse(answer);
  const resolved = resolveOverlaps(collectCandidates(masked, brands));

  // Earliest surviving hit per brand, preferring a strong match over a weak one
  // even when the weak one appears first: evidence quality outranks position.
  const firstPerBrand = new Map<string, Candidate>();
  for (const candidate of resolved) {
    const current = firstPerBrand.get(candidate.brand.id);
    if (!current) {
      firstPerBrand.set(candidate.brand.id, candidate);
      continue;
    }
    const strongerThanCurrent = current.weak && !candidate.weak;
    const sameStrengthButEarlier = current.weak === candidate.weak && candidate.offset < current.offset;
    if (strongerThanCurrent || sameStrengthButEarlier) {
      firstPerBrand.set(candidate.brand.id, candidate);
    }
  }

  const surviving = [...firstPerBrand.values()]
    .filter((c) => options.includeAmbiguous || !c.weak)
    .sort((a, b) => a.offset - b.offset || a.brand.id.localeCompare(b.brand.id));

  return surviving.map((candidate, index) => ({
    brandId: candidate.brand.id,
    rank: index + 1,
    charOffset: candidate.offset,
    matchedAlias: candidate.alias,
    ambiguous: candidate.weak,
  }));
}

/**
 * The mentions that were found but withheld, and why.
 *
 * Surfaced rather than dropped. A tool that silently discards evidence is a tool
 * whose numbers cannot be argued with, and the report needs to be able to say
 * "Monday appeared, but only as the day of the week".
 */
export function withheldMentions(answer: string, brands: Brand[]): Mention[] {
  const all = extractMentions(answer, brands, { includeAmbiguous: true });
  const counted = new Set(extractMentions(answer, brands).map((m) => m.brandId));
  return all.filter((m) => !counted.has(m.brandId));
}
