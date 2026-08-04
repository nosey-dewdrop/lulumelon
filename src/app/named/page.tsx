/**
 * The index of measured questions.
 *
 * The hub every question page links back to, and the page a crawler reaches
 * them through. It carries the leading name and the round behind each question
 * rather than a list of links, because a list of links is a page that says
 * nothing until you click it.
 */
import type { Metadata } from "next";
import Link from "next/link";

import { armInWords, percent, publishedRounds } from "@/lib/published";
import { SITE_NAME, url } from "@/lib/site";

export const metadata: Metadata = {
  title: "measured questions",
  description:
    "Questions that name no company, asked of a language model many times, with every company it reached for counted per draw and reported with the interval the sample supports.",
  alternates: { canonical: "/named" },
  openGraph: {
    type: "website",
    url: url("/named"),
    title: `measured questions · ${SITE_NAME}`,
    description:
      "Who a language model names when the question mentions nobody, counted per draw, with intervals.",
  },
};

export default function NamedIndex() {
  const rounds = publishedRounds();

  return (
    <main className="mx-auto max-w-[82rem] px-5 pb-24 pt-10 sm:px-10 sm:pt-14">
      <div className="flex items-baseline gap-2 text-[12px] text-ink-soft">
        <Link
          href="/"
          className="text-ink underline decoration-rule underline-offset-4 hover:decoration-pink"
        >
          {SITE_NAME}
        </Link>
        <span className="text-lilac">±</span>
        <span>measured questions</span>
      </div>

      <h1 className="mt-8 max-w-[30ch] text-[1.35rem] leading-[1.18] tracking-tight sm:text-[1.85rem]">
        who does the model name when the question names nobody?
      </h1>
      <p className="mt-6 max-w-[62ch] text-[13.5px] leading-relaxed text-ink-soft">
        each question below was asked of one model several times over, and every answer was written
        into a hash-chained file before anything was counted. the pages report what the sample
        supports and refuse what it does not.
      </p>

      {rounds.length === 0 ? (
        <p className="mt-14 text-[13.5px] text-ink-soft">
          no round has been published yet. `lulu publish` writes them, and they are committed by
          hand.
        </p>
      ) : (
        <ul className="mt-14 border-t border-rule">
          {rounds.map((round) => {
            const leader = round.names[0];
            return (
              <li key={round.slug} className="border-b border-rule py-6">
                <Link href={`/named/${round.slug}`} className="group block">
                  <div className="grid gap-x-10 gap-y-3 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
                    <h2 className="text-[1rem] leading-snug group-hover:text-lilac">
                      {round.question}
                    </h2>
                    <div className="text-[12px] leading-relaxed text-ink-soft">
                      {leader ? (
                        <span>
                          <span className="text-ink">{leader.name}</span> in {leader.draws} of{" "}
                          {leader.of} draws, {percent(leader.low)} to {percent(leader.high)}
                        </span>
                      ) : (
                        <span>no name was repeated often enough to report</span>
                      )}
                      <br />
                      {round.model}, {armInWords(round.arm)}
                    </div>
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}
