/**
 * The landing page.
 *
 * One idea, spent everywhere: doubt. The product's whole argument is that a
 * single reading of a language model is not a measurement, so the page's motif
 * is the ± that every honest number carries. It appears in the wordmark, as the
 * list marker, and beside every figure quoted.
 *
 * Hierarchy is by size. No cards, no pills, no gradients, no icons, no
 * three-column feature grid. The terminal is the only ornament and it is also
 * the demo.
 */
import { Terminal } from "./Terminal";

function Pm() {
  return <span className="text-ink-soft">±</span>;
}

export default function Page() {
  return (
    <main className="mx-auto max-w-[68rem] px-5 pb-24 pt-10 sm:px-8 sm:pt-16">
      {/* ------------------------------------------------------------ hero */}
      <header>
        <div className="flex items-baseline gap-2 text-[13px] text-ink-soft">
          <span className="text-ink">youkiddingme</span>
          <Pm />
          <span>measurement, not vibes</span>
        </div>

        <h1 className="mt-8 max-w-[36ch] text-[2rem] leading-[1.15] tracking-tight sm:text-[2.9rem]">
          every tool in this category reports one number.
          <br />
          <span className="text-ink-soft">it asked once.</span>
        </h1>

        <p className="mt-7 max-w-[62ch] text-[15px] leading-relaxed text-ink-soft">
          language models are not deterministic. ask the same question twice and you get different
          brands, in a different order. so &ldquo;your visibility is 18.5%&rdquo; is not a
          measurement, it is one draw from a distribution nobody characterised. this asks n times
          and reports what the sample can actually support.
        </p>
      </header>

      {/* -------------------------------------------------------- terminal */}
      <section className="mt-12" aria-label="recorded measurement">
        <Terminal />
        <p className="mt-3 text-[12px] text-ink-soft">
          a recording. typing here calls nothing and costs nothing.
        </p>
      </section>

      {/* ---------------------------------------------------- the argument */}
      <section className="mt-20 grid gap-x-12 gap-y-10 sm:grid-cols-2">
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
            did the content work, or did the <span className="text-ink-soft">dice</span> move?
          </h2>
          <p className="mt-4 text-[14.5px] leading-relaxed text-ink-soft">
            publish something, measure again. if the two intervals overlap, the honest verdict is
            inconclusive and the report says how many draws it would take to settle it. going from
            2 of 10 to 4 of 10 looks like a doubling and means nothing.
          </p>
        </div>

        <div>
          <h2 className="text-[1.35rem] leading-tight">
            or did the <span className="text-ink-soft">model</span> move?
          </h2>
          <p className="mt-4 text-[14.5px] leading-relaxed text-ink-soft">
            providers ship new versions without telling anyone, and everybody&rsquo;s numbers shift
            at once. the same fixed prompt set, run on a schedule, separates &ldquo;you dropped&rdquo;
            from &ldquo;the model changed underneath you&rdquo;.
          </p>
        </div>
      </section>

      {/* ------------------------------------------------------ what it does */}
      <section className="mt-20">
        <h2 className="text-[1.35rem]">what it measures</h2>
        <dl className="mt-6 max-w-[70ch] text-[14.5px] leading-relaxed">
          {[
            [
              "appearance rate",
              "of the n times this prompt was asked, in how many were you named. a property of you alone, so it does not move when a competitor moves. reported with an interval.",
            ],
            [
              "rank, separately",
              "average position across the draws where you appeared, with its spread. appearing twice at rank 1 is a different position from appearing nine times at rank 5, and one blended number hides which you are.",
            ],
            [
              "sentiment, with agreement",
              "classified several times per mention. the label ships with how unanimous the vote was, because a single classification is a coin whose bias nobody measured.",
            ],
            [
              "per axis, never blended",
              "your name, each product, each topic. one score across four different markets is a number about nothing.",
            ],
            [
              "withheld evidence",
              "a name that is also an ordinary word does not count as a mention. “we ship on monday” is not monday.com. those matches are reported separately rather than folded into someone’s share of voice.",
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
      </section>

      {/* ---------------------------------------------------------- footer */}
      <footer className="mt-24 border-t border-rule pt-6 text-[12.5px] text-ink-soft">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-2">
          <span className="text-ink">youkiddingme</span>
          <Pm />
          <a
            className="underline decoration-rule underline-offset-4 hover:decoration-ink"
            href="https://github.com/nosey-dewdrop/youkiddingme"
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
