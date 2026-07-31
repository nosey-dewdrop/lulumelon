# youkiddingme

A measurement library for what language models say about a brand, and for how
much of that a sample actually supports.

## why it exists?

A company sent me a take-home case: a multi-agent content pipeline as a durable
workflow, every agent its own step, real parallel fan-out with a concurrency
cap, a live external signal mid-flow, a scoring judge, schema contracts at every
boundary, and a page showing the whole run trace, in 48 hours.

It was detailed enough to be worth doing properly, and doing it properly cost me
$77.56, about 66 million tokens and 6,084 lines of code.

It also came with a data export shaped like a real product's database, and
working inside that shape is what raised the question this library answers. Each
tracked prompt had exactly one recorded run. There was no field anywhere for
which model version produced it. And the summary on top of it reported numbers
to two decimal places.

So I started reading how this measurement is done, and the question I could not
answer from any public methodology page was a simple one: how many times is a
prompt asked before the number is printed?

## the problem

A visibility number usually looks like this:

    your visibility: 18.5%

A language model is not a deterministic function. Ask the same question twice
and you can get different brands, in a different order, with a different tone.
So a single reading is one draw from a distribution, and 18.5% and 24% may be
the same underlying reality sampled twice.

This is a hard problem rather than a careless one. Sampling n times costs n
times as much, the variance is real and inconvenient, and an interval is harder
to sell than a single number going up. None of that makes the single number
mean more than it does.

## what this does

Asks n times, and reports what the sample supports.

    name                seen     rate        interval             rank
    CLO3D               5/5    100.0%      56.6% – 100.0%      1.2 ± 0.45
    Optitex             4/5     80.0%      37.6% –  96.4%      1.8 ± 0.50
    Gerber AccuMark     2/5     40.0%      11.8% –  76.9%      3.0 ± 0.00
    Seamly2D            1/5     20.0%       3.6% –  62.4%      3.0
  ▸ stitchu             0/5      0.0%       0.0% –  43.4%      never named

Five properties that follow from reporting it this way:

**0 of 5 is not 0%.** Never being named in five draws is compatible with being
named 43% of the time. The textbook normal approximation collapses to [0, 0]
here, which would state certainty of absence after five samples, so the library
uses the Wilson score interval, which stays inside [0, 1] and keeps a real bound
at the edges. Absence of evidence is reported as absence of evidence.

**100% is not certainty either.** Five for five gives a lower bound of 56.6%.
Even the leader is not pinned.

**Rank is kept separate from rate.** Appearing twice at rank 1 is a different
position from appearing nine times at rank 5, and averaging them into one number
hides which one you are.

**Ahead means the intervals do not overlap.** A competitor at 6 of 10 against
your 4 of 10 is not ahead of you, because those ranges sit almost on top of each
other, so no ranking is printed that the sample cannot support.

**Nothing is blended across axes.** Each brand, product and topic keeps its own
number. One score spanning four different markets is a number about nothing.

## layout

```
src/lib/
  stats.ts        Wilson intervals and the sampling math; calls no model
  mentions.ts     extracts brand mentions and ranks from a model answer
  visibility.ts   turns samples into per-brand rates, intervals and ranks
  runner.ts       plan / estimate / execute a sampled run
  llm/            provider interface, deterministic stub, live transport
tests/            45 tests, no network and no API key
```

`stats.ts` is the core and is pure: given successes and n it returns an
interval, so the claim the library makes can be checked without spending a
token. `npm test` runs everything offline.

---

Built by [nosey dewdrop](https://noseydewdrop.com). The case that started this is
not reproduced here.
