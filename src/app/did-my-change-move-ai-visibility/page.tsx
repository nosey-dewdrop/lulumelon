/**
 * The gap between two rounds, and the word it has to earn.
 *
 * This is the only page on the site without a paid measurement at the top of
 * it, and that is stated on the page rather than papered over. The figures this
 * command is known by come out of the suite's own fixtures, and the site's
 * standing rule is that a figure on a page came off a round somebody bought. So
 * the page leads with the gate instead, which is the part that is real, tested
 * and unusual, and the measured example lands here the day a lift round is
 * collected and published.
 */
import type { Metadata } from "next";
import Link from "next/link";

import { AnswerShell, Block, Command } from "@/app/AnswerShell";
import { Pm } from "@/app/Frame";
import { answerFor } from "@/lib/answers";
import { SITE_NAME, url } from "@/lib/site";

const ANSWER = answerFor("did-my-change-move-ai-visibility")!;

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
      <Block title="the number on its own answers nothing">
        <p>
          Knowing you are named in eleven percent of answers tells you to do exactly nothing. The
          question with money attached to it is the next one. You changed a page, or earned a
          mention on somebody else&rsquo;s, and you want to know whether the answers moved, by how
          much, and whether that gap is bigger than the model rerolling on its own.
        </p>
        <p className="mt-4">
          That question needs a noise floor, and a noise floor needs draws. It is the one claim in
          this category that a single daily reading structurally cannot support, whatever the
          dashboard puts next to it.
        </p>
      </Block>

      <Block title="two arms, paired, with the gap carrying its own interval">
        <p>
          One round is collected with the source in the list the model was shown, one without, and
          the same questions run through both. The difference is paired prompt by prompt rather than
          taken between two averages, and it is reported with an interval of its own, because a gap
          between two uncertain numbers is more uncertain than either of them.
        </p>
        <Command>
          {`lulu ablate --live ROUND --replica ROUND --brand ornek --margin 5
lulu lift --live ROUND --held ROUND --dropped ROUND --brand ornek \\
          --source https://b.example/list \\
          --sources https://a.example/guide \\
          --sources https://b.example/list \\
          --sources https://c.example/review`}
        </Command>
      </Block>

      <Block title="the word lift is granted, never assumed">
        <p>
          Without a passing gate the same arithmetic prints as an{" "}
          <span className="text-ink">arm difference</span> and the command exits non-zero. The
          contrast is causal either way, since the list is yours and one thing moved, but what a
          gate buys is somewhere to carry that claim: with one, the levels are restated with the
          gate&rsquo;s own margin added on top, because a laboratory rate quoted as a
          customer&rsquo;s rate is uncertain twice over.
        </p>
        <p className="mt-4">
          The source list is not taken on trust either. A replica round records the digest of the
          exact material it was shown, so the list you pass on the command line is checked against
          the evidence file, and a reordered list, a swapped pair of arms or an edited instruction
          is refused by name rather than measured.
        </p>
      </Block>

      <Block title="what is not on this page yet">
        <p>
          A measured lift. The figures this command is usually shown with come out of the
          suite&rsquo;s fixtures, and every figure on this site comes off a round somebody paid for,
          so they are not printed here as though they were one. A lift round on this project&rsquo;s
          own brand costs a few dollars and lands on this page when it is collected.
        </p>
        <p className="mt-4">
          <Link className="hover:text-lilac" href="/how-many-times-should-you-ask">
            why a noise floor needs draws
          </Link>{" "}
          <Pm />{" "}
          <Link className="hover:text-lilac" href="/when-a-visibility-number-is-not-real">
            the verdicts it withholds
          </Link>
        </p>
      </Block>
    </AnswerShell>
  );
}
