/**
 * A card for one measured question.
 *
 * The leading name of that round, its rate, and the interval drawn the way the
 * page draws it. All four come out of the round's own published file, so a card
 * cannot say something the page does not.
 */
import { CONTENT_TYPE, SIZE, card } from "@/app/card";
import { armInWords, percent, publishedRound, publishedRounds } from "@/lib/published";

export const alt =
  "the name a language model reached for most in this question, and the interval its sample supports";
/** Written to a file at build time, like every other route on this site. */
export const dynamic = "force-static";
export const size = SIZE;
export const contentType = CONTENT_TYPE;

export function generateStaticParams() {
  return publishedRounds().map((round) => ({ slug: round.slug }));
}

export default async function Image({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const round = publishedRound(slug);
  if (!round) throw new Error(`no published round for ${slug}`);

  const leader = round.names[0];
  const foot = `${round.draws} draws of ${round.model}, ${armInWords(round.arm)}`;

  if (!leader) {
    return card({
      note: round.question,
      figure: `0 of ${round.draws}`,
      said: "answers named a company, and a page that reported one anyway would be reporting nothing",
      foot,
    });
  }

  return card({
    note: round.question,
    figure: `${leader.draws} of ${round.draws}`,
    said: `answers named ${leader.name}`,
    interval: {
      low: leader.low,
      high: leader.high,
      rate: leader.rate,
      caption: `95% interval, ${percent(leader.low)} to ${percent(leader.high)}`,
    },
    foot,
  });
}
