# lulumelon

Measures what language models say about a brand, and reports how much of that a
sample actually supports.

## why it exists?

I was working on a multi-agent content pipeline and spent a while inside a
dataset of what language models had answered about a set of brands. Working
with it left me with a question I could not put down, and this repo is me
trying to answer it.

## the problem

A visibility number usually looks like this:

    your visibility: 18.5%

A language model is not a deterministic function. Ask the same question twice
and you can get different brands, in a different order, with a different tone.
So one reading is one draw from a distribution, and 18.5% and 24% may be the
same underlying reality sampled twice.

Refresh frequency and sample size are also different quantities, and it is easy
to conflate them. Running a one-shot reading every morning gives you thirty
one-shot readings, not a sample of thirty.

This is a hard problem rather than a careless one. Sampling n times costs n
times as much, the variance is real and inconvenient, and an interval is harder
to read than a single number. This repo is one attempt at it, not a verdict on
anyone else's.

## what this does

Asks n times, and reports what the sample supports.

    name                seen     rate        interval             rank
    CLO3D               5/5    100.0%      56.6% – 100.0%      1.2 ± 0.45
    Optitex             4/5     80.0%      37.6% –  96.4%      1.8 ± 0.50
    Gerber AccuMark     2/5     40.0%      11.8% –  76.9%      3.0 ± 0.00
    Seamly2D            1/5     20.0%       3.6% –  62.4%      3.0
  ▸ stitchu             0/5      0.0%       0.0% –  43.4%      never named

**0 of 5 is not 0%.** Never being named in five draws is compatible with being
named 43% of the time. The textbook normal approximation collapses to [0, 0]
here, which would state certainty of absence after five samples, so this uses
the Wilson score interval, which keeps a real bound at the edges.

**100% is not certainty either.** Five for five gives a lower bound of 56.6%.

**Rank is kept separate from rate**, because appearing twice at rank 1 is a
different position from appearing nine times at rank 5.

**Ahead means the intervals do not overlap.** A competitor at 6 of 10 against
your 4 of 10 is not ahead of you, so no ranking is printed that the sample
cannot support.

## layout

```
lulumelon/
  cli.py          `lulu init` and `lulu doctor`: the key path, before anything runs
  keys.py         where a key is looked for, in order, and how it is kept quiet
  prices.py       what a call costs, from the provider's page, with the date read
  mirror/         the measurement core, calls no model
    intervals.py  Wilson and a clustered bootstrap that resamples prompts
    variance.py   splits the wobble into the model rerolling vs the prompt set
    stability.py  decides whether an ordering repeats enough to report a rank
    compare.py    before / after, and no verdict when the model moved underneath
    sources.py    which pages were cited, and whether a name travels with them
    report.py     one brand, with the refusals kept
  collect/        the part that asks, and the part that writes it down
    ask.py        provider boundary; Perplexity Sonar and a deterministic stub
    session.py    one round: k asks per prompt, failures recorded not retried
    ledger.py     append-only, hash-chained, nothing edited in place
    detect.py     brand matching by declared literals, no model in the loop
    audit.py      whether the answer engines are allowed to read the site
    replay.py     ledger back into runs, handing back what it excluded
  panel.py        the surface a customer reads

  prices.py       published rates, with the date each was read
  usage.py        what a recorded round cost, from the provider's own figures
  plan.py         how many calls a target precision needs, before spending any

src/lib/          the TypeScript layer behind the demo terminal
  stats.ts        Wilson intervals and the sampling math; calls no model
  mentions.ts     extracts brand mentions and ranks from a model answer
  visibility.ts   turns samples into per-brand rates, intervals and ranks
```

The measurement engine lives in Python and only in Python. A sampling plan that
answers differently depending on which language you asked it in is not an
instrument, so there is one implementation of it rather than two that agree
until they do not.

`mirror/` and `stats.ts` are pure: given successes and n they return an interval,
so the claim this makes can be checked without spending a token. `collect/` is
the only part allowed to reach the network, and it computes nothing.

    python3 -m pytest lulumelon/tests   # 212 tests, offline
    npm test                            # 45 tests, offline

## getting started

You bring your own key, so the first command is about the key and nothing else.
[docs/keys.md](docs/keys.md) is the long version, with the exact pages and the
published prices.

    pip install -e .
    lulu init      # asks for a key, stores it, says exactly where it put it
    lulu doctor    # finds it, tests it with one call, and prices that call

`lulu doctor` prints every place it looked, in order, whether or not it found
anything. `lulu doctor --offline` does all of that and spends nothing.

---

Built by [nosey dewdrop](https://noseydewdrop.com).

