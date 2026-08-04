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
import { Terminal } from "./Terminal";

function Pm() {
  return <span className="text-ink-soft">±</span>;
}

/** A figure and the words that make it checkable. Never a figure alone. */
function Figure({ value, of }: { value: string; of: string }) {
  return (
    <div className="flex items-baseline gap-3">
      <span className="min-w-[7.5rem] text-[1.6rem] leading-none tracking-tight">{value}</span>
      <span className="text-[13px] leading-snug text-ink-soft">{of}</span>
    </div>
  );
}

export default function Page() {
  return (
    <main className="mx-auto max-w-[82rem] px-5 pb-24 pt-10 sm:px-10 sm:pt-14">
      {/* ------------------------------------------------------------ hero */}
      <header className="grid gap-x-14 gap-y-10 lg:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)]">
        <div>
          <div className="flex items-baseline gap-2 text-[13px] text-ink-soft">
            <span className="text-ink">lulumelon</span>
            <Pm />
            <span>measurement, not vibes</span>
          </div>

          <h1 className="mt-8 max-w-[34ch] text-[2rem] leading-[1.15] tracking-tight sm:text-[3rem]">
            every tool in this category reports one number.
            <br />
            <span className="text-ink-soft">it asked once.</span>
          </h1>

          <p className="mt-7 max-w-[58ch] text-[15px] leading-relaxed text-ink-soft">
            language models are not deterministic. ask the same question twice and you get
            different companies, in a different order. so &ldquo;your visibility is 18.5%&rdquo; is
            not a measurement, it is one draw from a distribution nobody characterised. this asks n
            times, writes every answer into a hash-chained file, and reports what the sample can
            actually support.
          </p>
        </div>

        {/* The right column is the proof, not decoration. Four figures off one
            paid round, each with the sentence that makes it checkable. */}
        <div className="self-end border-t border-rule pt-6 lg:border-l lg:border-t-0 lg:pl-10 lg:pt-0">
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
      </header>

      {/* -------------------------------------------------------- terminal */}
      <section className="mt-14" aria-label="recorded measurement">
        <Terminal />
        <p className="mt-3 text-[12px] text-ink-soft">
          a recording. typing here calls nothing and costs nothing.
        </p>
      </section>

      {/* ---------------------------------------------------- the argument */}
      <section className="mt-20 grid gap-x-14 gap-y-10 sm:grid-cols-2 lg:grid-cols-3">
        <div>
          <h2 className="text-[1.35rem] leading-tight">
            0 of 10 is not <span className="text-ink-soft">zero</span>.
          </h2>
          <p className="mt-4 text-[14.5px] leading-relaxed text-ink-soft">
            never being named in ten draws is compatible with being named up to{" "}
            <span className="text-ink">43.4%</span> of the time. the textbook interval collapses to
            nothing here and lets a tool claim certainty of absence after ten samples. wilson keeps
            the real bound, so the report says what it does not know.
          </p>
        </div>

        <div>
          <h2 className="text-[1.35rem] leading-tight">
            ahead means the intervals <span className="text-ink-soft">do not touch</span>.
          </h2>
          <p className="mt-4 text-[14.5px] leading-relaxed text-ink-soft">
            a competitor at 6 of 10 against your 4 of 10 is not ahead of you. those ranges overlap
            almost entirely. this refuses to print a ranking the sample cannot support, which is the
            one thing every dashboard in the category does anyway.
          </p>
        </div>

        <div>
          <h2 className="text-[1.35rem] leading-tight">
            the model that <span className="text-ink-soft">searches</span> answers with other
            companies.
          </h2>
          <p className="mt-4 text-[14.5px] leading-relaxed text-ink-soft">
            the same questions, asked with the search tool on and with it off, come back naming
            different markets. a rival list read off one arm and measured against the other reports
            an empty category. that is a fact about the list, and this says so on the screen before
            the money moves.
          </p>
        </div>

        <div>
          <h2 className="text-[1.35rem] leading-tight">
            did the content work, or did the <span className="text-ink-soft">dice</span> move?
          </h2>
          <p className="mt-4 text-[14.5px] leading-relaxed text-ink-soft">
            publish something, measure again. if the two intervals overlap, the honest verdict is
            inconclusive and the report says how many draws it would take to settle it. going from 2
            of 10 to 4 of 10 looks like a doubling and means nothing. that round&rsquo;s own noise
            floor was <span className="text-ink">12.6 points</span>, read off the draws that were
            already bought.
          </p>
        </div>

        <div>
          <h2 className="text-[1.35rem] leading-tight">
            or did the <span className="text-ink-soft">model</span> move?
          </h2>
          <p className="mt-4 text-[14.5px] leading-relaxed text-ink-soft">
            providers ship new versions without telling anyone, and everybody&rsquo;s numbers shift
            at once. the same fixed question set, run on a schedule, separates &ldquo;you
            dropped&rdquo; from &ldquo;the model changed underneath you&rdquo;, and a round whose
            model moved is refused rather than compared.
          </p>
        </div>

        <div>
          <h2 className="text-[1.35rem] leading-tight">
            the ceiling is priced from the <span className="text-ink-soft">call</span>.
          </h2>
          <p className="mt-4 text-[14.5px] leading-relaxed text-ink-soft">
            every command prints the most it can spend before it spends anything, and the guard
            stops the round rather than discovering the overrun afterwards. the first version of
            that guard printed <span className="text-ink">$0.0440</span> and paid{" "}
            <span className="text-ink">$0.0467</span>, because it priced a call nobody was making.
            it is priced from the request now.
          </p>
        </div>
      </section>

      {/* ------------------------------------------------------ what it does */}
      <section className="mt-20 grid gap-x-14 gap-y-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div>
          <h2 className="text-[1.35rem]">what it measures</h2>
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
        </div>

        <div>
          <h2 className="text-[1.35rem]">what it refuses</h2>
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
        </div>
      </section>

      {/* ------------------------------------------------------------ proof */}
      <section className="mt-20 border-t border-rule pt-8">
        <h2 className="text-[1.35rem]">it is checkable</h2>
        <p className="mt-4 max-w-[70ch] text-[14.5px] leading-relaxed text-ink-soft">
          the measurement core is pure arithmetic and reaches no network, the collector reaches the
          network and computes nothing, and the wall between them is why a number here can be
          reproduced from the file it came from. the suite runs offline with every socket closed
          and spends no key.
        </p>
        <div className="mt-7 flex flex-wrap gap-x-12 gap-y-5">
          <Figure value="979" of="python tests, offline, on the measurement core and the collector" />
          <Figure value="45" of="node tests on the sampling maths behind the demo above" />
          <Figure value="0" of="answers rewritten, retried, or dropped from any round" />
        </div>
      </section>

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
