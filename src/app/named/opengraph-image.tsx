/**
 * The card for the index of measured questions.
 *
 * Counted out of `data/published/` at build time rather than written down, so
 * publishing a round moves the picture along with the page.
 */
import { CONTENT_TYPE, SIZE, card } from "@/app/card";
import { publishedRounds } from "@/lib/published";

export const alt = "lulumelon: every recorded answer, and every company named in one";
/** Written to a file at build time, like every other route on this site. */
export const dynamic = "force-static";
export const size = SIZE;
export const contentType = CONTENT_TYPE;

/** English for a small count, because "1 questions" is a tell. */
const WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"];
const words = (count: number) => WORDS[count] ?? String(count);

export default function Image() {
  const rounds = publishedRounds();
  const draws = rounds.reduce((total, round) => total + round.draws, 0);
  const names = new Set(rounds.flatMap((round) => round.names.map((name) => name.name)));

  return card({
    figure: String(draws),
    said: `recorded answers to ${words(rounds.length)} questions, naming ${names.size} companies between them, none of which the questions asked for`,
    foot: "each answer written into a hash-chained file before anything was counted",
  });
}
