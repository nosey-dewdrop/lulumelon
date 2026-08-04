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
import { CountUp, Reveal } from "./Reveal";
import { Terminal } from "./Terminal";

function Pm() {
  return <span className="text-lilac">±</span>;
}

/** A figure and the words that make it checkable. Never a figure alone. */
function Figure({ value, of }: { value: string; of: string }) {
  return (
    <div className="flex items-baseline gap-3">
      <span className="min-w-[7.5rem] text-[1.6rem] leading-none tracking-tight text-pink">
        <CountUp value={value} />
      </span>
      <span className="text-[13px] leading-snug text-ink-soft">{of}</span>
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
    <Reveal delay={delay} className="border-t border-rule pt-5">
      <h2 className="text-[1.35rem] leading-tight">{heading}</h2>
      <p className="mt-4 text-[14.5px] leading-relaxed text-ink-soft">{children}</p>
    </Reveal>
  );
}

export default function Page() {
  return (
    <main className="mx-auto max-w-[82rem] px-5 pb-24 pt-10 sm:px-10 sm:pt-14">
      {/* ------------------------------------------------------------ hero
          The terminal is the first thing on the page and it is running before
          a visitor has read a word, because the argument here is a thing that
          happens rather than a claim. Six lines in, somebody who has never
          heard of this has watched the same question return different
          companies, which is the whole product. Everything under it is
          evidence for what they have already seen. */}
      <header>
        <div className="flex items-baseline gap-2 text-[13px] text-ink-soft">
          <span className="text-ink">lulumelon</span>
          <Pm />
          <span>measurement, not vibes</span>
        </div>

        <h1 className="mt-7 max-w-[46ch] text-[1.7rem] leading-[1.16] tracking-tight sm:text-[2.4rem]">
          every tool in this category reports one number.{" "}
          <span className="text-ink-soft">it asked once.</span>
        </h1>
      </header>

      <section className="mt-8" aria-label="recorded measurement">
        <Terminal />
        <div className="mt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1 text-[12px] text-ink-soft">
          <span>a recording. typing here calls nothing and costs nothing.</span>
          <Pm />
          <span>ask the same question ten times and count, or read a number somebody asked once.</span>
        </div>
      </section>

      <section className="mt-12 grid gap-x-14 gap-y-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <p className="max-w-[58ch] text-[15px] leading-relaxed text-ink-soft">
          language models are not deterministic. ask the same question twice and you get different
          companies, in a different order. so &ldquo;your visibility is 18.5%&rdquo; is not a
          measurement, it is one draw from a distribution nobody characterised. this asks n times,
          writes every answer into a hash-chained file, and reports what the sample can actually
          support.
        </p>

        {/* Four figures off one paid round, each with the sentence that makes
            it checkable. Proof, not decoration. */}
        <div className="border-t border-rule pt-6 lg:border-l lg:border-t-0 lg:pl-12 lg:pt-0">
          <p className="text-[12px] uppercase tracking-[0.14em] text-ink-soft">
            one round, 4 august 2026
          </p>
          <div className="mt-5 flex flex-col gap-4">
            <Figure value="20" of="questions written from one customer site, then measured four times each" />
            <Figure value="11" of="of them named none of the thirteen rivals that had been declared" />
            <Figure value="339" of="companies the same answers did name, that the declared list never carried" />
            <Figure value="$2.46" of="the whole round, against a ceiling of $3.50 printed before it started" />
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------- the argument
          Six questions the category answers wrong, each arriving as it is
          scrolled to. A heading that asks something ends in a question mark,
          every time, on every surface. */}
      <section className="mt-20 grid gap-x-14 gap-y-10 sm:grid-cols-2 lg:grid-cols-3">
        <Card
          delay={0}
          heading={
            <>
              is 0 of 10 <span className="text-lilac">zero</span>?
            </>
          }
        >
          never being named in ten draws is compatible with being named up to{" "}
          <span className="text-ink">43.4%</span> of the time. the textbook interval collapses to
          nothing here and lets a tool claim certainty of absence after ten samples. wilson keeps
          the real bound, so the report says what it does not know.
        </Card>

        <Card
          delay={60}
          heading={
            <>
              when is a competitor <span className="text-lilac">ahead</span>?
            </>
          }
        >
          a competitor at 6 of 10 against your 4 of 10 is not ahead of you. those ranges overlap
          almost entirely. this refuses to print a ranking the sample cannot support, which is the
          one thing every dashboard in the category does anyway.
        </Card>

        <Card
          delay={120}
          heading={
            <>
              does the model that <span className="text-lilac">searches</span> answer with the same
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
              did the content work, or did the <span className="text-lilac">dice</span> move?
            </>
          }
        >
          publish something, measure again. if the two intervals overlap, the honest verdict is
          inconclusive and the report says how many draws it would take to settle it. going from 2
          of 10 to 4 of 10 looks like a doubling and means nothing. that round&rsquo;s own noise
          floor was <span className="text-ink">12.6 points</span>, read off the draws that were
          already bought.
        </Card>

        <Card
          delay={60}
          heading={
            <>
              or did the <span className="text-lilac">model</span> move?
            </>
          }
        >
          providers ship new versions without telling anyone, and everybody&rsquo;s numbers shift at
          once. the same fixed question set, run on a schedule, separates &ldquo;you dropped&rdquo;
          from &ldquo;the model changed underneath you&rdquo;, and a round whose model moved is
          refused rather than compared.
        </Card>

        <Card
          delay={120}
          heading={
            <>
              what is the most this <span className="text-lilac">can</span> cost?
            </>
          }
        >
          every command prints that figure before it spends anything, and the guard stops the round
          rather than discovering the overrun afterwards. the first version of that guard printed{" "}
          <span className="text-ink">$0.0440</span> and paid <span className="text-ink">$0.0467</span>
          , because it priced a call nobody was making. it is priced from the request now.
        </Card>
      </section>

      {/* ------------------------------------------------------ what it does */}
      <section className="mt-20 grid gap-x-14 gap-y-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Reveal>
          <h2 className="text-[1.35rem]">what does it measure?</h2>
          <dl className="mt-6 text-[14.5px] leading-relaxed">
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
                  <dt className="text-ink">{term}</dt>
                  <dd className="mt-1 text-ink-soft">{body}</dd>
                </div>
              </div>
            ))}
          </dl>
        </Reveal>

        <Reveal delay={80}>
          <h2 className="text-[1.35rem]">what does it refuse?</h2>
          <dl className="mt-6 text-[14.5px] leading-relaxed">
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
                  <dt className="text-ink">{term}</dt>
                  <dd className="mt-1 text-ink-soft">{body}</dd>
                </div>
              </div>
            ))}
          </dl>
        </Reveal>
      </section>

      {/* ------------------------------------------------------------ proof */}
      <Reveal className="mt-20 border-t border-rule pt-8">
        <h2 className="text-[1.35rem]">can you check any of it?</h2>
        <p className="mt-4 max-w-[70ch] text-[14.5px] leading-relaxed text-ink-soft">
          yes, and that is the design. the measurement core is pure arithmetic and reaches no network, the collector reaches the
          network and computes nothing, and the wall between them is why a number here can be
          reproduced from the file it came from. the suite runs offline with every socket closed
          and spends no key.
        </p>
        <div className="mt-7 flex flex-wrap gap-x-12 gap-y-5">
          <Figure value="979" of="python tests, offline, on the measurement core and the collector" />
          <Figure value="45" of="node tests on the sampling maths behind the demo above" />
          <Figure value="0" of="answers rewritten, retried, or dropped from any round" />
        </div>
      </Reveal>

      {/* ---------------------------------------------------------- footer */}
      <footer className="mt-24 border-t border-rule pt-6 text-[12.5px] text-ink-soft">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-2">
          <span className="text-ink">lulumelon</span>
          <Pm />
          <a
            className="underline decoration-rule underline-offset-4 hover:decoration-ink"
            href="https://github.com/nosey-dewdrop/lulumelon"
          >
            source
          </a>
          <Pm />
          <span>built by nosey dewdrop</span>
        </div>
      </footer>
    </main>
  );
}
