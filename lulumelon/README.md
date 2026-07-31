# mirror

A measurement engine for non-deterministic answer engines.

Ask ChatGPT who the best running shoe brand is. Ask again. You will often get a
different list. Every product in the AI-visibility category asks once a day and
prints the resulting number as a score. This library asks k times and reports
the distribution, the interval, and whether the movement you are looking at
could have been the dice.

No model is called anywhere in this package. Given recorded runs it is pure
arithmetic, reproducible from a seed. That is the property that makes it an
instrument rather than a dashboard.

## What it computes

| module | question it answers |
|---|---|
| `intervals` | how wide is the uncertainty, with the prompt as the resampling unit |
| `variance` | is the wobble the model rerolling, or genuine prompt-to-prompt difference |
| `stability` | does the answer agree with itself enough for a rank to mean anything |
| `compare` | did it change, or did it wobble, and was the model swapped underneath |
| `report` | all of the above for one brand, with a refusal when a number would mislead |

## Run it

```bash
python3 -m pytest mirror/tests -q     # 68 tests, no network, no API key
python3 mirror/demo.py                # side by side: one run vs twelve
```

## The three refusals

These are the product, not error handling.

**k=1 is rejected.** With one run per prompt, model rerun noise and real
prompt-to-prompt difference are algebraically indistinguishable, so any
confidence interval printed from such a design is decoration. `decompose`
raises rather than returning a number.

**A rank is withheld when the ordering does not repeat.** If the leading brand
changes between reruns, an average position describes the sampling, not the
brand. Published measurement finds identical ordered brand lists in well under
one pair of runs in a hundred.

**A comparison across a model version change gets no verdict.** Providers
update hosted models without changelogs. When the recorded model version
differs between two snapshots, `Verdict.significant` is false regardless of how
large the gap is, and the text says why.

## Who else publishes an interval, and what is wrong with it

"Nobody reports uncertainty" would be an overstatement, so it is not the claim.
Of the vendors surveyed, one publishes a formal confidence interval and one
publishes its sample count. The rest publish neither.

The published interval is the interesting one. Verbatim from the vendor's own
methodology post, all three quotes fetched directly rather than taken from a
summary:

- `n >= (0.98 / MoE)^2`
- "The default configuration (10 topics, 8 personas, 10 models) produces 800
  observations per run"
- "a single run yields an overall visibility estimate within +/-5 pp at 95%
  confidence"

The constant is the worst-case binomial half-width at p=0.5 and the arithmetic
is correct. The assumption is not: it counts all n observations as independent
when they are k repeats of n/k prompts, and repeats of one prompt are
correlated. `published_binomial_moe` exists in this package so the size of that
error is measured rather than asserted.

**Coverage.** 300 simulated snapshots, 25 prompts, 8 repeats each, known true
rate:

```
published formula (0.98/sqrt(n))   covers 76.0%   claims 95%
cluster bootstrap                  covers 92.0%   claims 95%
```

Ours lands slightly under its nominal 95% too, which is what a percentile
bootstrap does at 25 clusters, and is stated rather than rounded up.

**The sharper consequence.** The same post says, verbatim: "Ten related prompts
run 39 times each, or fifty prompts run 8 times each, both get you to +/-5 pp."
Under the published formula those designs are interchangeable, since both land
near 400 observations. Measured in the same simulated world:

```
design                observations   true half-width   coverage   claimed
10 prompts x 39 runs           390            12.7pp        89%     5.0pp
50 prompts x 8 runs            400             7.0pp        92%     4.9pp
```

They are not interchangeable, they differ by roughly a factor of two, and the
first is understated by two and a half times. A customer following that advice
buys repeats when they needed prompts. `tests/test_intervals.py` pins this.

## On the "just run it more times" argument

An incumbent in this category published a test of 753 prompts across 7 engines
comparing once-daily sampling against ten-times-daily, and found portfolio-level
scores differing by about a quarter of a point. That result is real and this
library does not argue with it.

It is also why the answer here is not a fixed k. `runs_needed` returns
*unreachable, add prompts* in exactly the regime where extra repeats buy
nothing, and `BrandReport.advice` reads the variance split before recommending
anything. The claim was never that everyone needs more runs. It is that nobody
currently measures which regime they are in, so a portfolio average can be
perfectly stable while every per-prompt and every rank claim built on it is
noise.

## Layout

```
mirror/          the arithmetic, no I/O, no model calls
tests/           68 tests including a Monte Carlo coverage check
demo.py          runnable comparison against the single-run design
conftest.py      path shim so the suite runs from the repo root
```

## Status

Engine only. There is no collection layer yet: this package consumes recorded
runs and says nothing about how to obtain them. That is the next and harder
half.
