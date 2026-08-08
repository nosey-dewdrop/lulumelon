/**
 * The refusals, collected in one place.
 *
 * Every other page here says what the tool reports. This one says what it will
 * not, which is the half a buyer is normally not shown.
 */
import type { Metadata } from "next";
import Link from "next/link";

import { AnswerShell, Block } from "@/app/AnswerShell";
import { Pm } from "@/app/Frame";
import { answerFor } from "@/lib/answers";
import { SITE_NAME, url } from "@/lib/site";

const ANSWER = answerFor("when-a-visibility-number-is-not-real")!;

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
      <Block title="zero is not zero">
        <p>
          Never being named in five draws is compatible with an appearance rate of{" "}
          <span className="text-ink">43.4%</span>. In ten draws it is 27.8%. The textbook normal
          approximation collapses to a point at the edges and hands back a confident nothing, so
          this uses the Wilson score interval, which keeps a bound where the evidence is thinnest.
          A dashboard that prints 0% for a brand that was asked about five times is not reporting
          absence, it is reporting that nobody looked hard enough to tell.
        </p>
      </Block>

      <Block title="no rank where the ordering does not repeat">
        <p>
          Appearing twice at position one is a different fact from appearing nine times at position
          five, so rate and rank are kept apart and never blended into one score. And a rank is only
          printed where the ordering repeats across draws. Where it does not, the ordering was
          noise, and a number computed from noise reads exactly like a number computed from
          evidence.
        </p>
      </Block>

      <Block title="no ahead where the intervals overlap">
        <p>
          A competitor at six of ten against your four of ten is not ahead of you. Both of those
          samples support a wide range of true rates and those ranges sit on top of each other, so
          the ordering is not supported and no ranking is printed. The word ahead has to be earned
          by non-overlapping intervals, not by a bigger number.
        </p>
      </Block>

      <Block title="undecided is a verdict, and it is not a pass">
        <p>
          Where an interval spans the base rate the result is recorded as undecided, and undecided
          is not a quiet pass. The gate opened at the place the evidence was thinnest is a gate that
          never closed. A question that carries the brand&rsquo;s own name is thrown out of the rate
          entirely for the same reason, because a question with the name in it is answered with the
          name whatever the model knows.
        </p>
      </Block>

      <Block title="and the comparison it will not make">
        <p>
          Two rounds collected from two different engines are not one round, so a file holding both
          is refused and the engines it holds are named. A before and after taken across a model
          version change gets no verdict either, because the thing underneath the measurement moved.
        </p>
        <p className="mt-4">
          <Link className="hover:text-lilac" href="/how-many-times-should-you-ask">
            how many draws it takes to say anything
          </Link>{" "}
          <Pm />{" "}
          <Link className="hover:text-lilac" href="/did-my-change-move-ai-visibility">
            the word a causal claim has to earn
          </Link>
        </p>
      </Block>
    </AnswerShell>
  );
}
