/**
 * One measured question, as a page.
 *
 * This is the part of the site that grows: one url per question a round was
 * asked, each carrying who the model named and how often, with the interval
 * the sample supports. Every figure comes out of `data/published/`, which is
 * written by `lulu publish` from a hash-chained round and committed by hand.
 *
 * Nothing here is generated text. The page is a table and the sentences around
 * it are the same refusals the product prints in a terminal, because a page
 * that softened them would be advertising a different product.
 */
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Divider, Foot, Nav, Pm } from "@/app/Frame";
import { armInWords, percent, publishedRound, publishedRounds } from "@/lib/published";
import { REPO_URL, SITE_NAME, url } from "@/lib/site";

export const dynamicParams = false;

export function generateStaticParams() {
  return publishedRounds().map((round) => ({ slug: round.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const round = publishedRound(slug);
  if (!round) return {};

  const leader = round.names[0];
  const description = leader
    ? `Asked ${round.draws} times of ${round.model}. ${leader.name} was named in ${leader.draws} of ${round.draws} answers, which the sample puts between ${percent(leader.low)} and ${percent(leader.high)}. Every answer is on record.`
    : `Asked ${round.draws} times of ${round.model}, with every answer on record.`;

  return {
    title: round.question,
    description,
    alternates: { canonical: `/named/${round.slug}` },
    openGraph: {
      type: "article",
      url: url(`/named/${round.slug}`),
      title: round.question,
      description,
      siteName: SITE_NAME,
    },
    twitter: { card: "summary_large_image", title: round.question, description },
  };
}

function Bar({ low, high, rate }: { low: number; high: number; rate: number }) {
  return (
    <span
      className="interval mt-2 block w-full"
      style={
        {
          "--low": `${low * 100}%`,
          "--high": `${high * 100}%`,
          "--point": `${rate * 100}%`,
        } as React.CSSProperties
      }
      aria-hidden
    />
  );
}

export default async function NamedPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const round = publishedRound(slug);
  if (!round) notFound();

  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "Dataset",
    name: round.question,
    description: `Which companies ${round.model} named when asked "${round.question}" ${round.draws} times, with Wilson intervals.`,
    url: url(`/named/${round.slug}`),
    dateCreated: round.asked_at,
    creator: { "@type": "Organization", name: SITE_NAME, url: url("/") },
    license: "https://opensource.org/licenses/MIT",
    isAccessibleForFree: true,
    measurementTechnique:
      "Repeated sampling of one prompt, appearance counted per draw, Wilson score interval at 95%",
    variableMeasured: round.names.slice(0, 20).map((one) => ({
      "@type": "PropertyValue",
      name: one.name,
      value: one.draws,
      maxValue: one.of,
      unitText: "draws naming this company",
    })),
  };

  return (
    <main className="mx-auto max-w-[82rem] px-5 pb-14 pt-0 sm:px-10">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />

      <Nav here="named" />

      {/* The same measure and the same size as the line at the top of the home
          page, because they are the same kind of line. A visitor who lands here
          from a search result has to meet the site, not a stray table. */}
      <header className="mx-auto mt-7 max-w-[58rem] text-center">
        <h1 className="text-[1.4rem] leading-tight tracking-tight sm:text-[1.7rem]">
          <span aria-hidden>💘</span> {round.question}
        </h1>
        <p className="mx-auto mt-4 max-w-[62ch] text-[16px] leading-snug text-ink-soft">
          asked {round.draws} times of {round.model}, {armInWords(round.arm)}. the question names no
          company. what follows is who the model reached for on its own, counted per draw, with the
          range the sample supports beside each one.
        </p>
        <p className="mt-4 flex flex-wrap items-baseline justify-center gap-x-3 gap-y-1 text-[14.5px] text-ink-soft">
          <span>{round.asked_at}</span>
          <Pm />
          <span>
            {round.engine} {round.model}
          </span>
          <Pm />
          <span className="break-all">{round.snapshot}</span>
          <Pm />
          <a className="underline decoration-rule underline-offset-4 hover:decoration-pink" href={REPO_URL}>
            lulu verify
          </a>
        </p>
      </header>

      <section className="mt-8" aria-label="who was named">
        <div className="grid gap-x-10 gap-y-7 sm:grid-cols-2 lg:grid-cols-3">
          {round.names.map((one) => (
            <div key={one.name}>
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-[16px]">{one.name}</span>
                <span className="text-[16px] text-ink-soft">
                  {one.draws}/{one.of}
                </span>
              </div>
              <Bar low={one.low} high={one.high} rate={one.rate} />
              <p className="mt-2 text-[11.5px] text-ink-soft">
                {percent(one.rate)} of draws, and the sample puts it between {percent(one.low)} and{" "}
                {percent(one.high)}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* Centred as a column, left aligned inside it. Long copy set flush to
          the page edge on one side and open on the other reads as a leftover
          rather than as a section. */}
      <Divider />

      {/* No arrival on this page. A result page is read after a search,
          not scrolled through, and a block that fades in under somebody
          already looking for a number reads as the page being slow. */}
      <div className="mx-auto mt-10 max-w-[54rem]">
        <h2 className="text-[1.4rem]">what does this not say?</h2>
        <div className="mt-5 grid gap-6 text-[16px] leading-snug text-ink-soft sm:grid-cols-2">
          <p>
            a name at {round.draws} of {round.draws} is not a certainty. six draws put the honest
            range at 61% to 100%, and a page that printed 100% would be quoting a sample it does
            not have. the bar under every name is that range, drawn.
          </p>
          <p>
            two names whose ranges overlap are not ranked. this is one engine on one day under one
            arm, and the same questions asked with the search tool on come back naming other
            companies entirely.
          </p>
          <p>
            a name counts when the round wrote it inside a sentence, or spelled it the way no
            ordinary word is spelled, and never when the same round also wrote it in lower case.
            nothing was matched against a list of companies, because the question this answers is
            who the model names when nobody suggested anybody.
          </p>
          {round.dropped?.length ? (
            <p>
              {round.dropped.length} entries were removed by hand as genre words rather than
              companies: {round.dropped.join(", ")}. they are named here rather than deleted
              quietly.
            </p>
          ) : (
            <p>
              nothing was removed from this table by hand. what the extraction produced is what is
              printed, including anything it got wrong.
            </p>
          )}
        </div>
      </div>

      <Foot back />
    </main>
  );
}
