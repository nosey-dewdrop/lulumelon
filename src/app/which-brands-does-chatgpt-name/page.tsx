/**
 * Who the model reaches for when the question names nobody.
 *
 * The figure is off the paid round of 4 August 2026, the same round the home
 * page quotes, and it is the one number in this product that surprises people
 * who have already bought a competitor: the list you declared is not the list
 * the model uses.
 */
import type { Metadata } from "next";
import Link from "next/link";

import { AnswerShell, Block, Command } from "@/app/AnswerShell";
import { Pm } from "@/app/Frame";
import { answerFor } from "@/lib/answers";
import { SITE_NAME, url } from "@/lib/site";

const ANSWER = answerFor("which-brands-does-chatgpt-name")!;

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
      <Block title="the list you declared is not the list the model uses">
        <p>
          A round is collected against the names you tracked, and every tool in this category
          reports on those names and stops there. The answers do not stop there. In one paid round
          of twenty questions, written from a customer&rsquo;s own site and asked four times each,
          the answers named <span className="text-ink">339 companies the declared list of thirteen
          never carried</span>, and eleven of the twenty questions named none of the thirteen at
          all.
        </p>
        <p className="mt-4">
          That second number is the one worth sitting with. More than half the questions a customer
          was measuring themselves on were questions where their whole competitive set was absent
          from the answer, and a report scored only against the declared list would have shown a
          clean sheet on all eleven.
        </p>
      </Block>

      <Block title="how does it decide something is a name?">
        <p>
          Two different jobs, kept apart. A tracked brand is matched by the literals you declared,
          with no model in the loop, so the thing being measured cannot be measured by a guess.
          Every other name in the answer is harvested afterwards by position in the sentence and by
          how the word is spelled in the rest of the corpus, and the round records which question
          and which arm each one arrived through.
        </p>
        <Command>
          {`lulu rivals --ledger ./ledger --snapshot ROUND --least 2`}
        </Command>
        <p className="mt-4">
          The result is a table of who came up and where, so the list you carry into the next round
          is corrected by what the model actually said rather than by what you remembered to type.
        </p>
      </Block>

      <Block title="what it will get wrong">
        <p>
          The harvest is positional, and two kinds of word slip through it. Type words like{" "}
          <span className="text-ink">API</span>, <span className="text-ink">AI</span> and{" "}
          <span className="text-ink">ML</span> sit where a company sits and are capitalised in the
          corpus the same way, so they appear in the table above real names and a reader strikes
          them out in a second. Going the other way, a name that never appears inside a sentence and
          leaves no trace in the surrounding spelling is dropped, which is how{" "}
          <span className="text-ink">Twelve Data</span> was lost from the round of 4 August 2026.
        </p>
        <p className="mt-4">
          Both are written down here rather than left for you to find, because a table that hides
          its two failure modes is a table you cannot use as evidence.
        </p>
      </Block>

      <Block title="see it on a real round">
        <p>
          Four questions are published with every name in every answer, asked six times each of one
          model with no search tool attached, and each name carries the interval its own sample
          supports rather than a bare percentage.
        </p>
        <p className="mt-4">
          <Link className="text-ink hover:text-lilac" href="/named">
            measured questions
          </Link>{" "}
          <Pm />{" "}
          <Link className="hover:text-lilac" href="/how-many-times-should-you-ask">
            why six draws and not one
          </Link>
        </p>
      </Block>
    </AnswerShell>
  );
}
