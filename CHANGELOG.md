# Changelog

Versions are what a reader can install and point at. A number in `pyproject.toml`
with no tag behind it does not answer "which one am I running", which is the
first question anybody asks a library that is still moving.

## 0.1.0, 5 August 2026

The first tagged build. Everything below runs on your own machine against your
own key, and nothing here bills through anybody.

### the measurement

- Wilson score intervals rather than the normal approximation, so 0 of 20 is an
  upper bound instead of certainty of absence.
- A clustered percentile bootstrap that resamples prompts, because repeats
  inside one question are not independent draws of the thing being measured.
- Interval width split into the model answering differently and the question set
  chosen, since only one of those two is worth spending more money on.
- No rank printed where the ordering does not repeat, and no "ahead" where the
  intervals overlap.
- A round is one engine and one surface. A file holding two is refused and the
  engines it holds are named.
- The screening gate counts rivals and never the customer, because filtering a
  question set by the customer's own score raises the published number by
  deleting the evidence against it.

### the record

- An append-only, hash-chained ledger. Every report re-derives the chain before
  it computes anything, and `lulu verify` re-derives every chain on disk.
- Failed calls are written down with `status="error"` rather than retried, so a
  round is what happened rather than what happened often enough.
- A ceiling checked before each call. A round that hits it stops short, says so,
  and exits with its own code rather than pretending to be complete.

### the commands

Fifteen, from `lulu setup` to `lulu publish`. Prices come from the provider's
own published page with the date they were read, and `lulu usage` keeps an
amount the provider stated, a cost computed from reported tokens, and a floor
for calls it said nothing about as three separate bases that never merge.

### the surfaces

- A static site with four routes, every figure on it off a measured round, and
  a social card per route generated from that round's own numbers.
- `lulu publish` writes a round out as pages, by hand, so nothing reaches the
  web that somebody did not choose to put there.

### the gates

- 988 python tests and 52 node tests, all offline, no key spent.
- ruff over 78 python files, eslint and tsc over the site.
- Every push runs all of it on python 3.11 and 3.13, installs the wheel into an
  empty environment and runs `lulu --help` out of it, and the site deploys only
  behind those gates.

### known limits

Written out in the README under "what does it not do?", and held to the code by
a test: two engines rather than four, a rival list still typed in by hand, and a
name counter that drops a name nothing in a round spells.
