/**
 * Why the draw count is derived rather than chosen.
 *
 * The figure is the effective sample of the round the front page quotes, and it
 * is the cheapest way to show what repeats are actually worth: a hundred and
 * twenty five answers that carry nine.
 */
import type { Metadata } from "next";
import Link from "next/link";

import { AnswerShell, Block, Command } from "@/app/AnswerShell";
import { Pm } from "@/app/Frame";
import { answerFor } from "@/lib/answers";
import { SITE_NAME, url } from "@/lib/site";

const ANSWER = answerFor("how-many-times-should-you-ask")!;

export const metadata: Metadata = {
  title: ANSWER.question,
  description: ANSWER.description,
  alternates: { canonical: `/${ANSWER.slug}` },
  openGraph: {
    type: "article",
    url: url(`/${ANSWER.slug}`),
    title: `${ANSWER.question} · ${SITE_NAME}`,
    description: ANSWER.description,
  },
};

export default function Page() {
  return (
    <AnswerShell answer={ANSWER}>
      <Block title="thirty daily readings are not a sample of thirty">
        <p>
          A language model is not a deterministic function, so one reading is one draw from a
          distribution nobody characterised. Refresh frequency and sample size get conflated here
          constantly. Asking a question once every morning for a month gives you thirty one-shot
          readings taken under thirty different conditions, not thirty draws of today&rsquo;s
          answer, and the model moved underneath you somewhere in the middle of it.
        </p>
      </Block>

      <Block title="what the repeats bought, as a number">
        <p>
          In the round the front page quotes, every question came back with the same answer on all
          twenty asks, so the correlation inside a question was{" "}
          <span className="text-ink">1.000</span>. When that happens the design effect is the
          cluster size, and a hundred and twenty five answers over nine questions carry an{" "}
          <span className="text-ink">effective sample of 9.00</span>. Exactly the number of
          questions. The repeats bought nothing, and the arithmetic says how much nothing.
        </p>
        <p className="mt-4">
          That is not an argument against repeating. It is the reason the split is reported: the
          interval width is decomposed into the model answering differently and the question set you
          picked, so you know which of the two is worth spending the next dollar on.
        </p>
      </Block>

      <Block title="the number of draws follows the rate, it is not a setting">
        <p>
          A rate near a half needs more draws than a rate near an edge to reach the same precision,
          so the draw count is derived from the base rather than typed in. The floors this build
          uses are 2 draws at 0.3, 4 at 0.5, 6 at 0.6 and 12 at 0.75.
        </p>
        <Command>
          {`lulu plan --prompts 40 --brands 5 --half-width 5
lulu size --prompts 24 --runs 5 --engines perplexity,anthropic`}
        </Command>
        <p className="mt-4">
          The first sizes the round before it is bought. With no pilot it refuses to hand back a
          single number, because how the variance splits between the model and the question set is
          not something arithmetic can know in advance. The second goes the other way and prices a
          design you already set.
        </p>
      </Block>

      <Block title="where this bites hardest">
        <p>
          At one draw a day there is no noise floor, and without a noise floor no claim that a
          change moved anything can be separated from the model rerolling.
        </p>
        <p className="mt-4">
          <Link className="hover:text-lilac" href="/when-a-visibility-number-is-not-real">
            what a thin sample cannot support
          </Link>{" "}
          <Pm />{" "}
          <Link className="hover:text-lilac" href="/what-ai-visibility-tracking-costs">
            what the draws cost
          </Link>
        </p>
      </Block>
    </AnswerShell>
  );
}
