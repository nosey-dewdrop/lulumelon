/**
 * The documentation, on the site.
 *
 * It used to be a nav link that jumped to a markdown file in the repository,
 * which is a way of saying the docs are somebody else's problem. What a
 * stranger needs before they install anything is here, in the site's own type,
 * and every command on it exists in the build the page was made from.
 *
 * **It is a library, not a service.** There is no hosted api, no account and no
 * dashboard. You install a python package, you bring your own key, and the
 * rounds land on your disk. That answer belongs at the top of this page rather
 * than being left for somebody to work out from the absence of a sign up form.
 */
import type { Metadata } from "next";
import Link from "next/link";

import { Foot, Nav, Pm, REPO } from "@/app/Frame";
import { SITE_NAME, url } from "@/lib/site";

export const metadata: Metadata = {
  title: "docs",
  description:
    "lulumelon is a python library and a command line tool, MIT licensed, with no hosted service. Install it, bring your own key, and every round lands on your own disk in a hash-chained file.",
  alternates: { canonical: "/docs" },
  openGraph: {
    type: "article",
    url: url("/docs"),
    title: `docs · ${SITE_NAME}`,
    description:
      "Install, keys, the fifteen commands, the two layers, and the file a round is written into.",
  },
};

/** One command and what it does, set the way the terminal sets a line. */
function Command({ line, said }: { line: string; said: string }) {
  return (
    <div className="mt-2">
      <span className="text-ink">{line}</span>
      <span className="text-ink-soft">
        {"  "}
        <Pm /> {said}
      </span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-16 border-t border-rule pt-7">
      <h2 className="text-[1.15rem]">{title}</h2>
      <div className="mt-5 max-w-[80ch] text-[13px] leading-relaxed text-ink-soft">{children}</div>
    </section>
  );
}

export default function Docs() {
  return (
    <main className="mx-auto max-w-[82rem] px-5 pb-24 pt-5 sm:px-10 sm:pt-6">
      <Nav here="docs" />

      <header className="mx-auto mt-7 max-w-[58rem] text-center">
        <h1 className="text-[1.05rem] leading-tight tracking-tight sm:text-[1.3rem]">
          <span aria-hidden>🎀</span> a library, not a service.
        </h1>
        <p className="mx-auto mt-4 max-w-[62ch] text-[13px] leading-relaxed text-ink-soft">
          there is no hosted api here, no account and no dashboard. you install a python package,
          you bring your own key, and every round is written to your own disk in a file that
          re-derives. what that costs is printed before anything is spent.
        </p>
      </header>

      <Section title="how do you install it?">
        <p>
          python 3.11 or newer. two dependencies, both of them arithmetic; everything on the network
          path is standard library, because an http client is not worth a supply chain for one post.
        </p>
        <pre className="mt-5 overflow-x-auto text-[13px] leading-relaxed">
          <Command line="git clone https://github.com/nosey-dewdrop/lulumelon.git" said="" />
          <Command line="python3 -m venv .venv && source .venv/bin/activate" said="" />
          <Command line="pip install -e .          " said="puts `lulu` on the path" />
          <Command line='pip install -e ".[dev]"   ' said="pytest, to run the suite" />
          <Command line="python3 -m pytest lulumelon/tests" said="offline, spends no key" />
        </pre>
        <p className="mt-5">
          without the install the same commands run as{" "}
          <span className="text-ink">python3 -m lulumelon.cli</span>. building it as a package needs
          setuptools 77 or newer, which is not a preference: the licence field is the spdx string,
          and every backend before 77 reads that as a table and stops.
        </p>
      </Section>

      <Section title="where does the key go?">
        <p>
          into the os keychain, under the service <span className="text-ink">lulumelon</span> and
          the account name of the engine. one command, no questions asked, and it spends about a
          cent proving the key works and that a search actually comes back with pages.
        </p>
        <pre className="mt-5 overflow-x-auto text-[13px] leading-relaxed">
          <Command line="lulu setup   " said="paste the key, or pipe it: pbpaste | lulu setup" />
          <Command line="lulu doctor  " said="find the key, test it, price the call" />
          <Command line="lulu doctor --offline" said="everything except the call" />
        </pre>
        <p className="mt-5">
          where the keychain will not take it, a <span className="text-ink">.env</span> file beside
          you is written instead, created at 0600 rather than corrected to it afterwards. the
          environment variables it reads, in order, are{" "}
          <span className="text-ink">ANTHROPIC_API_KEY</span> then{" "}
          <span className="text-ink">LULU_ANTHROPIC_API_KEY</span>, and the same pair for
          perplexity. the key is never printed, never put in shell history and never written into
          the repository.
        </p>
        <p className="mt-4">
          two engines exist in this build, claude and perplexity sonar. that call is billed, so it
          is written down: it lands in <span className="text-ink">./ledger</span> under a name
          beginning <span className="text-ink">diagnostic__</span>, priced by{" "}
          <span className="text-ink">lulu usage</span> like any other spend and refused by
          everything that scores an answer.
        </p>
      </Section>

      <Section title="what are the commands?">
        <p>fifteen, and these are the six a first round goes through.</p>
        <pre className="mt-5 overflow-x-auto text-[13px] leading-relaxed">
          <Command line="lulu draft --site example.com " said="writes a question set from a site" />
          <Command line="lulu screened --draft FILE    " said="that round as a document, with a pdf" />
          <Command line="lulu rivals --snapshot ROUND  " said="who the answers named, uninvited" />
          <Command line="lulu collect --subject FILE   " said="asks each question k times" />
          <Command line="lulu report --snapshot ROUND  " said="one brand, with what it withholds" />
          <Command line="lulu verify                   " said="re-derive every chain on disk" />
        </pre>
        <p className="mt-5">
          the other nine. <span className="text-ink">plan</span> prices a round before it exists,{" "}
          <span className="text-ink">size</span> says how many prompts and draws a target width
          needs, <span className="text-ink">usage</span> prices what was spent from the
          provider&rsquo;s own figures, <span className="text-ink">ablate</span> and{" "}
          <span className="text-ink">lift</span> ask what one source was worth,{" "}
          <span className="text-ink">publish</span> writes the pages under{" "}
          <Link className="underline decoration-rule underline-offset-4 hover:decoration-pink" href="/named">
            measured questions
          </Link>
          , and <span className="text-ink">setup</span>, <span className="text-ink">init</span> and{" "}
          <span className="text-ink">doctor</span> handle the key.
        </p>
        <p className="mt-4">
          every command prints the most it can spend before it spends anything, and the guard stops
          a round rather than discovering the overrun afterwards. a ceiling is priced from the call
          it guards, which means the size of the prompt about to be sent and the cap the request
          carries, not from a constant.
        </p>
      </Section>

      <Section title="what is inside the library?">
        <p>
          two layers and a wall between them, and the wall is the product.{" "}
          <span className="text-ink">mirror</span> is pure arithmetic, reaches no network and does
          not import the other side, so an interval can be recomputed from a file with no key.{" "}
          <span className="text-ink">collect</span> is the only part allowed to reach a provider and
          it computes nothing.
        </p>
        <pre className="mt-5 overflow-x-auto text-[13px] leading-relaxed">
          <Command line="from lulumelon.mirror.intervals import wilson_interval" said="" />
          <Command line="wilson_interval(0, 10)" said="Interval(low=0.0, high=0.434)" />
          <Command line="wilson_interval(6, 6) " said="Interval(low=0.61, high=1.0)" />
        </pre>
        <p className="mt-5">
          <span className="text-ink">mirror</span> holds intervals, variance, stability, compare,
          sources, ablation, lift, report, screen, names and the types.{" "}
          <span className="text-ink">collect</span> holds ask, ledger, session, budget, detect,
          subject, audit, harvest, propose, replica and replay. 986 tests run over both with every
          socket closed.
        </p>
      </Section>

      <Section title="what does a round look like on disk?">
        <p>
          one file per round, append only, one json object per line, each line carrying the hash of
          the line before it. the round closes with a record saying how many calls it made and how
          they came out, hashed into the same chain, which is what makes a short file readable as
          short: a file somebody cut lines off the end of has lost the only sentence that said how
          long it was.
        </p>
        <p className="mt-4">
          the name of the file is the round: subject, engine, surface, timestamp and sequence. the
          surface is the arm, <span className="text-ink">api</span> when the model could search
          while answering and <span className="text-ink">api_unsearched</span> when it could not,
          and it is derived from the request rather than accepted from a caller so two arms cannot
          be filed under one name.
        </p>
        <p className="mt-4">
          a failed call is written down with the provider&rsquo;s own reason and never retried.
          asking again until the answer is good is a filter over model output, which is the thing
          this exists to refuse.
        </p>
      </Section>

      <Section title="what does it refuse to tell you?">
        <p>
          a ranking the sample cannot support, a comparison across a model version change, a rate
          computed from a round that does not re-derive, and a question set screened on your own
          name. each refusal is printed where the number would have been, with the reason.
        </p>
        <p className="mt-4">
          the licence is mit and the whole of it is on{" "}
          <a className="underline decoration-rule underline-offset-4 hover:decoration-pink" href={REPO}>
            github
          </a>
          . the key page in the repository goes further into what a call costs, with the figures
          read from the provider&rsquo;s own documentation and the date they were read on.
        </p>
      </Section>

      <Foot back />
    </main>
  );
}
