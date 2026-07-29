# youkiddingme

Measures what language models say about you, and reports how much of that is
actually known.

## how this started

A company sent me a take-home case. Multi-agent content pipeline, built as a
durable workflow, every agent its own step, real parallel fan-out with a
concurrency cap, a live external signal in the middle, a scoring judge, schema
contracts at every boundary, and a page showing the whole run trace. Forty-eight
hours. No boilerplate.

It was so detailed that finishing it cost $77.56, about 66 million tokens and
6,084 lines of code.

At which point I decided to scale the work up slightly and build one of the
company for myself.

## the part that made me do it

The brief was strict about one thing above all others: every factual claim in
generated content must trace back to the supplied data, and a fabricated number
is an automatic fail.

So I did not read their precomputed summary. I recomputed it from the raw
answers, and wrote a test asserting my figures reproduced theirs.

They did not.

One brand's sentiment tally in the shipped summary disagrees with the shipped
raw data it was supposedly computed from. Everything else matched to the digit,
which is how I knew it was a real defect and not my arithmetic.

A brief that forbids unsourced numbers, shipped alongside an export containing
one. I did not build this out of spite. I built it because that is the exact
failure the tool catches, and once you have seen it in the category's own data
you cannot look at the category's dashboards the same way.

## what the category sells

Every product in AI visibility reports a number like this:

    your visibility: 18.5%

That number came from asking each tracked prompt **once**.

Language models are not deterministic functions. Ask the same question twice and
you get different brands, in a different order, with a different tone. So 18.5%
is not a measurement. It is one draw from a distribution nobody characterised,
printed in a large font next to a green arrow.

Over a hundred products, two hundred million dollars of funding, and as far as I
can find, not one of them publishes an error bar. There are methodology pages
that explain which platforms are covered and how pretty the charts are. There are
none that say how many times a prompt is run.

## what this does instead

Asks n times. Reports what the sample supports.

    name                seen     rate        honest range          rank
    CLO3D               5/5    100.0%      56.6% – 100.0%      1.2 ± 0.45
    Optitex             4/5     80.0%      37.6% –  96.4%      1.8 ± 0.50
    Gerber AccuMark     2/5     40.0%      11.8% –  76.9%      3.0 ± 0.00
    Seamly2D            1/5     20.0%       3.6% –  62.4%      3.0
  ▸ stitchu             0/5      0.0%       0.0% –  43.4%      never named

Five things in that table that the category will not print:

**0 of 5 is not zero.** Never being named in five draws is entirely compatible
with being named 43% of the time. The textbook normal-approximation interval
collapses to [0, 0] here, which would let a tool announce certainty of absence
after five samples. Wilson keeps the real bound. Absence of evidence gets
reported as absence of evidence.

**100% is not certainty either.** Five for five gives a lower bound of 56.6%.
Even the leader is not pinned.

**Rank is separate from rate.** Appearing twice at rank 1 is a different
position from appearing nine times at rank 5. Blending them into one "average
rank" hides which one you are.

**Ahead means the intervals do not overlap.** A competitor at 6 of 10 against
your 4 of 10 is not ahead of you; those ranges sit almost on top of each other.
This refuses to print a ranking the sample cannot support.

**Nothing is blended across axes.** Your name, each product, each topic get
their own number. One score spanning four different markets is a number about
nothing.

## the two questions it exists to answer

**Did my content do anything?** Measure, publish, measure again. If the
intervals overlap, the verdict is `inconclusive` and the report says how many
draws it would take to settle it. Going from 2 of 10 to 4 of 10 looks like a
doubling and means nothing at all. `inconclusive` is a first-class answer here,
not a failure. Reporting a change the sample cannot support is how these tools
manufacture confident nonsense.

**Or did the model move?** Providers ship new versions without announcing them
and everyone's numbers shift at once. The same fixed prompt set, run on a
schedule, separates "you dropped" from "the ground moved".

## the parts that are not statistics

**Mention extraction is deterministic.** Rank is the order of first appearance
measured by character offset, not a model's opinion about who was recommended.
Longest alias wins, so `Monday.com` is not counted as a bare `Monday`. Code
fences, inline code, URLs and email addresses are masked out, because a brand
name inside a code block is not the model naming a product to a reader.

**Names that are ordinary English words do not count.** "We ship every Monday"
is not a mention of Monday.com. "Growth was linear" is not a mention of Linear.
Counting those silently inflates a competitor's share of voice and leaves no
trace for anyone to notice. Here they are extracted, withheld from the number,
and reported separately so a human decides.

**Sentiment is the only part that needs a model**, so it is classified several
times per mention and ships with its agreement ratio. A single classification is
a coin whose bias nobody measured. It is also, not coincidentally, the exact
field that was wrong in the export that started this.

## status

Honest inventory, because a README that overstates its repo is the same crime as
a dashboard that overstates its sample.

Built and tested, no network required:

- `src/lib/stats.ts`, Wilson intervals, sample sizing, rank summary, classifier
  agreement, drift verdicts
- `src/lib/mentions.ts`, deterministic extraction, alias resolution,
  ordinary-word withholding, non-prose masking
- `src/lib/visibility.ts`, appearance rate, per-axis pooling, overlap-aware
  comparison, share of voice kept as a secondary read
- `src/lib/llm/`, provider interface, live transports, and a stub that is
  deterministic per draw yet disagrees between draws, which is the only way to
  test any of the above offline
- `src/app/`, the landing page and its terminal

Not built yet: the scheduled runner, persistence, the report surface, auth.

`npm test` runs the suite. It needs no key and touches no network.

## running it

    npm install
    cp .env.example .env.local     # LLM_PROVIDER=fake needs no key
    npm test
    npm run dev

## the name

It is what you say when a dashboard shows you one number to three decimal places
and no sample size.

---

Built by [nosey dewdrop](https://noseydewdrop.com). The case that started it is
not reproduced here, and the company is not named. The bug is in their data
either way.
