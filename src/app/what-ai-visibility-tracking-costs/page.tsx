/**
 * The money page.
 *
 * Both halves of it are measured: what the software costs, which is nothing,
 * and what a round costs, which came off the provider's own figures for rounds
 * on this disk.
 */
import type { Metadata } from "next";
import Link from "next/link";

import { AnswerShell, Block, Command } from "@/app/AnswerShell";
import { Pm } from "@/app/Frame";
import { answerFor } from "@/lib/answers";
import { SITE_NAME, url } from "@/lib/site";

const ANSWER = answerFor("what-ai-visibility-tracking-costs")!;

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
      <Block title="the software is free and it stays that way">
        <p>
          There is no seat, no account and no invoice from here. The library is MIT licensed, you
          bring your own key, and the tokens are billed to you by the model provider at their own
          rates. <span className="text-ink">Nothing is taken on top.</span>
        </p>
        <p className="mt-4">
          That is a measurement decision before it is a commercial one. When the tool pays for the
          quota, every rival in a round is pushed towards a single draw, and at one draw the model
          rerolling and the question set moving cannot be told apart. Letting the token bill go
          straight to the person who wants the number is what makes depth affordable at all.
        </p>
      </Block>

      <Block title="what a round actually cost">
        <p>
          One paid round of twenty questions, four draws each, on 4 August 2026, came to{" "}
          <span className="text-ink">$2.46</span> against a ceiling of{" "}
          <span className="text-ink">$3.50 printed before it started</span>. A smaller round on this
          disk, twenty four answers with no search tool attached, priced out at{" "}
          <span className="text-ink">$0.045760</span>, which is $0.001907 a call.
        </p>
        <Command>{`lulu usage    # what the recorded rounds cost, from the provider's own figures`}</Command>
        <p className="mt-4">
          Three bases are kept apart and never merged: an amount the provider stated, a cost
          computed from tokens it reported, and a floor for calls it said nothing about. Failed
          calls are counted and priced at nothing, because no response says whether a rejected call
          is billed.
        </p>
      </Block>

      <Block title="the ceiling is checked before each call, not after the round">
        <p>
          A budget that is reconciled at the end is a receipt. This one is a gate: the price of the
          next call is computed and checked against what is left, and a round that would cross the
          line stops short, says so, and exits with a code of its own that is neither success nor
          failure. The file on disk is then a real round that is shorter than the design that bought
          it, so every interval computed from it is wider than the one you planned, and a caller
          that read it as complete would publish the wider bound as the planned one.
        </p>
      </Block>

      <Block title="before you spend anything">
        <p>
          <Link className="hover:text-lilac" href="/how-many-times-should-you-ask">
            how many draws the precision you want needs
          </Link>{" "}
          <Pm />{" "}
          <Link className="hover:text-lilac" href="/how-to-verify-an-ai-visibility-number">
            what you can prove afterwards
          </Link>
        </p>
      </Block>
    </AnswerShell>
  );
}
