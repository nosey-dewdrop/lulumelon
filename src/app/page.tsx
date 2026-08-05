/**
 * The landing page.
 *
 * One idea, spent everywhere: doubt. The product's whole argument is that a
 * single reading of a language model is not a measurement, so the page's motif
 * is the ± that every honest number carries. It appears in the wordmark, as the
 * list marker, and beside every figure quoted.
 *
 * **Every number on this page came off a real round.** The measurements below
 * were paid for on 4 August 2026 and are on disk in a hash-chained ledger. A
 * landing page for a measurement tool that quotes invented figures is the
 * defect the tool exists to name, so nothing here is illustrative.
 *
 * Hierarchy is by size. No cards, no pills, no gradients, no icons, no
 * three-column feature grid. The terminal is the only ornament and it is also
 * the demo.
 */
import Link from "next/link";

import { Divider, Foot, Nav, Pm, REPO } from "./Frame";
import { AUTHOR, AUTHOR_URL, SITE_NAME, url } from "@/lib/site";
import { CountUp, Reveal } from "./Reveal";
import { Terminal } from "./Terminal";

/**
 * `**like this**` becomes bold, so the sentence beside a figure can carry the
 * word it turns on without the markup swallowing the copy.
 */
function emphasised(text: string) {
  return text.split(/\*\*(.+?)\*\*/g).map((part, i) =>
    i % 2 ? (
      <strong key={i} className="font-bold text-ink">
        {part}
      </strong>
    ) : (
      part
    ),
  );
}

/** A figure and the words that make it checkable. Never a figure alone. */
function Figure({ value, of }: { value: string; of: string }) {
  return (
    <div className="flex items-baseline gap-4">
      {/* A fixed column, not a minimum. `$2.46` is wider than `11`, so a
          minimum let the widest figure push its own sentence to the right and
          the four rows stopped lining up with each other. */}
      {/* Both sides carry the same line height, so the baseline the flex box
          aligns on is the same one the eye reads. `leading-none` on the figure
          shortened its line box and dropped the number below the sentence it
          belongs to. */}
      <span className="w-[4.2rem] shrink-0 text-[1.4rem] leading-snug tracking-tight text-pink">
        <CountUp value={value} />
      </span>
      <span className="text-[14px] leading-snug text-ink-soft">{emphasised(of)}</span>
    </div>
  );
}

/**
 * The same figure, stacked, for the strip that closes the page.
 *
 * Three of them centred read as one statement about the whole thing. Side by
 * side with the words to the right of the number, they turned into three more
 * lines of a list with a hole down the middle of it.
 */
function Stacked({ value, of }: { value: string; of: string }) {
  return (
    <div className="max-w-[24ch]">
      <div className="text-[1.85rem] leading-snug tracking-tight text-pink">
        <CountUp value={value} />
      </div>
      <p className="mt-3 text-[14px] leading-snug text-ink-soft">{of}</p>
    </div>
  );
}

/** One block of the argument, arriving as it is scrolled to. */
function Card({
  heading,
  delay,
  children,
}: {
  heading: React.ReactNode;
  delay: number;
  children: React.ReactNode;
}) {
  return (
    <Reveal delay={delay}>
      <h2 className="text-[1.25rem] leading-tight">{heading}</h2>
      <p className="mt-4 text-[14px] leading-snug text-ink-soft">{children}</p>
    </Reveal>
  );
}

export default function Page() {
  return (
    <main className="mx-auto max-w-[82rem] px-5 pb-14 pt-0 sm:px-10">
      {/* What this is and who wrote it, in the form a search engine reads as
          an entity rather than as a sentence. The name is written out because
          a handle is not a person to an index. */}
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            "@context": "https://schema.org",
            "@type": "SoftwareApplication",
            name: SITE_NAME,
            applicationCategory: "DeveloperApplication",
            operatingSystem: "macOS, Linux",
            url: url("/"),
            license: "https://opensource.org/licenses/MIT",
            isAccessibleForFree: true,
            programmingLanguage: "Python",
            softwareRequirements: "Python 3.11 or newer",
            codeRepository: REPO,
            description:
              "A python library and command line tool that measures what language models say about a brand, asking each question many times and reporting the interval the sample supports.",
            author: { "@type": "Person", name: AUTHOR, url: AUTHOR_URL },
            creator: { "@type": "Person", name: AUTHOR, url: AUTHOR_URL },
          }),
        }}
      />

      {/* ------------------------------------------------------------- hero
          The terminal is the first thing on the page. Not the first thing
          under a headline, the first thing: it is already running when the
          page paints, and six lines in somebody who has never heard of this
          has watched the same question come back with different companies in
          it. That is the product, and no sentence above it would do the job
          the thing itself does. The wordmark and the claim sit underneath,
          where they read as a caption on something already seen.

          The brand still arrives first, because the terminal's own opening
          line says it. */}
      <Nav />

      {/* Two columns, and the terminal is one of them. Centred on its own it
          sat as a lump with the page left open either side of it. Against the
          right edge it reads as a window, and the width it stops taking now
          carries the line that says what this is, what the terminal is, and
          the round that paid for the figures under it. */}
      <section className="mt-7 grid items-start gap-x-10 gap-y-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <div>
          <h1 className="text-[1.15rem] leading-tight tracking-tight sm:text-[1.4rem]">
            lulumelon <span aria-hidden>🍉</span> measures what language models say about you.
          </h1>

          <div className="mt-4 text-[14px] leading-snug text-ink-soft">
            <p>
              <span aria-hidden>✨</span> a recording. typing there calls nothing and costs nothing.
            </p>
            <p className="mt-2 flex gap-3">
              <Pm />
              <span>
                ask the same question ten times and count, or read a number somebody asked once.
              </span>
            </p>
          </div>

          {/* Four figures off one paid round, each with the sentence that
              makes it checkable. Proof, not decoration, and it sits beside the
              demo rather than under it because it is what the demo produced. */}
          <div className="mt-9">
            <p className="text-[14px] uppercase tracking-[0.14em] text-ink-soft">
              <span aria-hidden>💘</span> one round, 4 august 2026
            </p>
            <div className="mt-5 flex flex-col gap-4">
              <Figure value="20" of="questions written from one customer site, then measured four times each" />
              <Figure value="11" of="of them named **none** of the thirteen rivals that had been declared" />
              <Figure value="339" of="companies the same answers **did** name, that the declared list never carried" />
              <Figure value="$2.46" of="the whole round, against a ceiling of $3.50 **printed before it started**" />
            </div>
          </div>
        </div>

        <section aria-label="recorded measurement" className="w-full lg:justify-self-end">
          <Terminal />
        </section>
      </section>

      <Divider />

      <header className="text-center">
        <p className="mx-auto max-w-[44ch] text-[1.25rem] leading-snug">
          every tool in this category reports one number.{" "}
          <span className="text-ink-soft">it asked once.</span>
        </p>
      </header>

      <section className="mt-9 grid gap-x-10 gap-y-7 lg:grid-cols-2">
        <p className="text-[15.5px] leading-snug text-ink-soft">
          language models are not deterministic. ask the same question twice and you get different
          companies, in a different order. so &ldquo;your visibility is 18.5%&rdquo; is not a
          measurement, it is one draw from a distribution nobody characterised. this asks n times,
          writes every answer into a hash-chained file, and reports what the sample can actually
          support.
        </p>

        {/* The commercial position, where the figures used to sit. Every
            product in this category rents a seat and bills for calls it makes
            on your behalf; this hands over the software and lets the money go
            straight to the provider. It belongs this high on the page because
            it is the first question anybody has after the demo. */}
        <div className="lg:pl-8">
          <h2 className="text-[1.25rem] leading-snug">
            <span aria-hidden>💐</span> what does it cost to use?
          </h2>
          <p className="mt-4 text-[15.5px] leading-snug text-ink-soft">
            <strong className="font-bold text-ink">nothing.</strong> the library is free, mit
            licensed, and it stays that way. bring your own key, pay the provider for your own
            tokens, and{" "}
            <strong className="font-bold text-ink">the software takes nothing on top</strong>. no
            account, no seat, no invoice from here.
          </p>
          <p className="mt-4 text-[15.5px] leading-snug text-ink-soft">
            the round above cost <strong className="font-bold text-ink">$2.46</strong>, paid
            straight to the model provider, and that was the whole bill.
          </p>
        </div>
      </section>

      <Divider />

      {/* --------------------------------------------------------- the thing
          What a stranger can install, and the commands that exist. Without
          this the page is an argument about measurement rather than a library
          somebody can run tonight, and every figure above came out of these
          fifteen commands. */}
      <Reveal className="mt-12">
        {/* The heading and the line under it sit as a centred column. What
            follows keeps the width it had, because a command list set to a
            reading measure wraps where a command should not wrap. */}
        <div className="mx-auto max-w-[54rem]">
          <h2 className="text-[1.25rem]">how do you run it?</h2>
          <p className="mt-4 text-[14px] leading-snug text-ink-soft">
          python 3.11 and two dependencies, both of them arithmetic. everything on the network path
          is standard library, because an http client is not worth a supply chain for one post.
            the suite runs offline and spends no key.
          </p>
        </div>

        <div className="mt-7 grid gap-x-12 gap-y-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div>
            {/* No border and no fill. This page has one box in it and that box
                is the terminal at the top; a second one made of a lighter
                colour would be a card by another name. The type is already
                monospace, so a command reads as a command on its own. */}
            <pre className="min-w-0 overflow-x-auto text-[14px] leading-snug">
{[
                ["pip install -e .", ""],
                ["lulu setup", "your key, into the OS keychain"],
                ["lulu draft --site example.com", "writes the question set from a site"],
                ["lulu collect --subject FILE", "asks each question k times"],
                ["lulu report --snapshot ROUND", "the number, with what it withholds"],
                ["lulu verify", "re-derive every chain on disk"],
              ].map(([command, said]) => (
                <div key={command}>
                  <span className="text-ink">{command}</span>
                  {said ? (
                    <span className="text-ink-soft">
                      {"  ".repeat(1)}
                      <span className="text-lilac">±</span> {said}
                    </span>
                  ) : null}
                </div>
              ))}
            </pre>
            <p className="mt-3 text-[13px] text-ink-soft">
              fifteen commands in all. `lulu screened` turns a round into a pdf, `lulu rivals`
              reads the names off it, `lulu publish` writes the pages under{" "}
              <Link className="underline decoration-rule underline-offset-4 hover:decoration-pink" href="/named">
                measured questions
              </Link>
              , and `lulu usage` prices what was spent from the provider&rsquo;s own figures.
            </p>
          </div>

          <div className="text-[14px] leading-snug text-ink-soft">
            <p>
              <span className="text-ink">the library is the product.</span> `mirror` is pure
              arithmetic and reaches no network, so an interval can be recomputed from a file
              without a key. `collect` is the only part allowed to reach a provider and it computes
              nothing. that wall is why a number here is checkable rather than quotable.
            </p>
            <p className="mt-4">
              a round lands in an append-only file, hash-chained, each line carrying the hash of
              the one before it, and the round states its own length so a file somebody cut lines
              off the end of stops verifying.
            </p>
            <p className="mt-4">
              mit licensed, on{" "}
              <a className="underline decoration-rule underline-offset-4 hover:decoration-pink" href={REPO}>
                github
              </a>
              , with the key setup written out in{" "}
              <a
                className="underline decoration-rule underline-offset-4 hover:decoration-pink"
                href={`${REPO}/blob/main/docs/keys.md`}
              >
                docs/keys.md
              </a>
              .
            </p>
          </div>
        </div>
      </Reveal>

      <Divider />

      {/* ---------------------------------------------------- the argument
          Six questions the category answers wrong, each arriving as it is
          scrolled to. A heading that asks something ends in a question mark,
          every time, on every surface. */}
      <section className="mt-8 grid gap-x-10 gap-y-7 sm:grid-cols-2 lg:grid-cols-3">
        <Card
          delay={0}
          heading={
            <>
              is 0 of 10 zero?
            </>
          }
        >
          never being named in ten draws is compatible with being named up to{" "}
          <strong className="font-bold text-ink">43.4% of the time</strong>. the textbook interval
          collapses to nothing here and lets a tool{" "}
          <strong className="font-bold text-ink">claim certainty of absence</strong> after ten
          samples. wilson keeps the real bound, so the report says what it does not know.
        </Card>

        <Card
          delay={60}
          heading={
            <>
              when is a competitor ahead?{" "}
              <span aria-hidden>💞</span>
            </>
          }
        >
          a competitor at <strong className="font-bold text-ink">6 of 10 against your 4 of 10 is not
          ahead of you</strong>. those ranges overlap
          almost entirely. this refuses to print a ranking the sample cannot support, which is the
          one thing every dashboard in the category does anyway.
        </Card>

        <Card
          delay={120}
          heading={
            <>
              does the model that searches answer with the same
              companies?
            </>
          }
        >
          it does not. the same questions, asked with the search tool on and with it off, come back
          naming different markets. a rival list read off one arm and measured against the other
          reports an empty category, which is a fact about the list, and this says so on the screen
          before the money moves.
        </Card>

        <Card
          delay={0}
          heading={
            <>
              did the content work, or did the dice move?{" "}
              <span aria-hidden>💫</span>
            </>
          }
        >
          publish something, measure again. if the two intervals overlap, the honest verdict is
          inconclusive and the report says how many draws it would take to settle it. going from 2
          of 10 to 4 of 10 looks like a doubling and means nothing. that round&rsquo;s own noise floor was{" "}
          <strong className="font-bold text-ink">12.6 points</strong>, read off the draws that were
          already bought.
        </Card>

        <Card
          delay={60}
          heading={
            <>
              or did the model move?
            </>
          }
        >
          providers ship new versions without telling anyone, and everybody&rsquo;s numbers shift at
          once. the same fixed question set, run on a schedule, separates{" "}
          <strong className="font-bold text-ink">&ldquo;you dropped&rdquo; from &ldquo;the model
          changed underneath you&rdquo;</strong>, and a round whose model moved is
          refused rather than compared.
        </Card>

        <Card
          delay={120}
          heading={
            <>
              what is the most this can cost?
            </>
          }
        >
          every command prints that figure before it spends anything, and the guard stops the round
          rather than discovering the overrun afterwards. the first version of that guard{" "}
          <strong className="font-bold text-ink">printed $0.0440 and paid $0.0467</strong>, because it
          priced a call nobody was making. it is priced from the request now.
        </Card>
      </section>

      <Divider />

      {/* ------------------------------------------------------ what it does */}
      <section className="mt-8 grid gap-x-10 gap-y-7 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Reveal>
          <h2 className="text-[1.25rem]">what does it measure?</h2>
          <dl className="mt-6 text-[14px] leading-snug">
            {[
              [
                "appearance rate",
                "of the n times this question was asked, in how many were you named. a property of you alone, so it does not move when a competitor moves. reported with an interval.",
              ],
              [
                "rank, separately",
                "average position across the draws where you appeared, with its spread, and withheld entirely when the leader does not repeat often enough for a position to describe anything but the sampling.",
              ],
              [
                "who else got named",
                "counted off the same answers, with no list supplied. a name counts when the round wrote it inside a sentence, or spelled it the way no ordinary word is spelled, and never when the same round also wrote it in lower case.",
              ],
              [
                "which questions discriminate",
                "before the paid round, each candidate question is drawn against the rivals and kept only if the lower bound of its interval clears the floor. undecided is not a pass.",
              ],
              [
                "what the answers cited",
                "the pages the provider itself reported, never scraped out of the prose, with whether your name travels with them stated as an association rather than an effect.",
              ],
            ].map(([term, body]) => (
              <div key={term} className="mt-5 flex gap-3">
                <Pm />
                <div>
                  <dt className="font-bold text-ink">{term}</dt>
                  <dd className="mt-1 text-ink-soft">{body}</dd>
                </div>
              </div>
            ))}
          </dl>
        </Reveal>

        <Reveal delay={80}>
          <h2 className="text-[1.25rem]">
            what does it refuse? <span aria-hidden>🎀</span>
          </h2>
          <dl className="mt-6 text-[14px] leading-snug">
            {[
              [
                "a round it cannot re-derive",
                "every answer is hash-chained to the one before it and the round states its own length. a file somebody cut lines off the end of no longer verifies, and nothing is computed from it.",
              ],
              [
                "a question set screened on your own name",
                "keeping the questions you scored well on and dropping the rest raises the published number by deleting the evidence against it. rivals are what the gate measures, and with none declared the paid round does not run.",
              ],
              [
                "a comparison across a model change",
                "two rounds collected on different model versions are two experiments, so the verdict is withheld rather than printed with a caveat under it.",
              ],
              [
                "an answer that stopped early",
                "a reply cut off mid sentence, by a paused search or by its own token cap, is a fragment. recorded as a failure, never as a draw where your name happened not to come up.",
              ],
              [
                "a retry until it works",
                "a failed call is written down with the provider's own reason and never repeated. asking again until the answer is good is a filter over model output, which is the thing this exists to refuse.",
              ],
            ].map(([term, body]) => (
              <div key={term} className="mt-5 flex gap-3">
                <Pm />
                <div>
                  <dt className="font-bold text-ink">{term}</dt>
                  <dd className="mt-1 text-ink-soft">{body}</dd>
                </div>
              </div>
            ))}
          </dl>
        </Reveal>
      </section>

      <Divider />

      {/* ------------------------------------------------------------ proof */}
      <Reveal className="mt-8 text-center">
        <h2 className="text-[1.25rem]">can you check any of it?</h2>
        <p className="mx-auto mt-4 max-w-[64ch] text-[14px] leading-snug text-ink-soft">
          yes, and that is the design. the measurement core is pure arithmetic and reaches no
          network, the collector reaches the network and computes nothing, and the wall between
          them is why a number here can be reproduced from the file it came from. the suite runs
          offline with every socket closed and spends no key.
        </p>
        <div className="mt-10 flex flex-wrap items-start justify-center gap-x-16 gap-y-6 text-left">
          <Stacked value="979" of="python tests, offline, on the measurement core and the collector" />
          <Stacked value="45" of="node tests on the sampling maths behind the demo above" />
          <Stacked value="0" of="answers rewritten, retried, or dropped from any round" />
        </div>
      </Reveal>

      <Foot back />
    </main>
  );
}
