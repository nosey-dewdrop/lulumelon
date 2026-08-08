/**
 * The record, and what checking it does and does not cover.
 *
 * The figure is the ledger on this disk as `lulu verify` reports it, and the
 * page says out loud what a re-derivation proves and what it cannot.
 */
import type { Metadata } from "next";
import Link from "next/link";

import { AnswerShell, Block, Command } from "@/app/AnswerShell";
import { Pm } from "@/app/Frame";
import { answerFor } from "@/lib/answers";
import { SITE_NAME, url } from "@/lib/site";

const ANSWER = answerFor("how-to-verify-an-ai-visibility-number")!;

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
      <Block title="every answer is written down before anything is counted">
        <p>
          A round is an append-only file, one record per call, each record carrying the hash of the
          one before it. Every report re-derives the chain before it computes a single figure,
          because a number computed from a round that no longer re-derives is not a number. A
          failed call is written down with its status and the provider&rsquo;s own reason rather
          than retried, since repeating a request until it succeeds is a filter, and a filter
          applied to evidence is a thumb on the scale.
        </p>
        <Command>{`lulu verify    # re-derive every chain on disk, and say what the check does not cover`}</Command>
      </Block>

      <Block title="what a re-derivation proves">
        <p>
          Every record present was checked against its own hash and against the one before it, so
          altering a single answer costs a rewrite of every record after it. A sealed round is also
          checked against its own length, because it ends with a record saying how many calls it
          made, which is what turns records deleted from the end into something reported rather than
          silently lost.
        </p>
        <p className="mt-4">
          On the rounds this repository was built from, that check reads{" "}
          <span className="text-ink">6 of 6 rounds re-derive from their own contents</span>.
        </p>
      </Block>

      <Block title="what it does not prove">
        <p>
          It does not prove the provider said what the file says it said. A hash chain makes a
          record tamper-evident to everyone downstream of it, including you, and it cannot reach
          back to the other end of the wire. The command prints that limit in its own output rather
          than leaving the word verified to do work it has not earned.
        </p>
      </Block>

      <Block title="and the number on a page">
        <p>
          A round reaches the web only when somebody runs <span className="text-ink">lulu publish</span>{" "}
          and commits the file it writes, so no measurement is on this site that a person did not
          choose to put there. Each published page carries the model, the arm, the date and the
          draw count beside the figure.
        </p>
        <p className="mt-4">
          <Link className="text-ink hover:text-lilac" href="/named">
            measured questions
          </Link>{" "}
          <Pm />{" "}
          <Link className="hover:text-lilac" href="/when-a-visibility-number-is-not-real">
            when it refuses to print one
          </Link>
        </p>
      </Block>
    </AnswerShell>
  );
}
