# youkiddingme

Measures what language models say about you, and reports how much of that is
actually known.

## how this started=

A company sent me a take-home case. It's extensions included multi-agent content pipeline, built as a
durable workflow, every agent its own step, real parallel fan-out with a
concurrency cap, a live external signal in the middle, a scoring judge, schema
contracts at every boundary, and a page showing the whole run trace. Forty-eight
hours. No boilerplate.

It was so detailed that finishing it cost $77.56, about 66 million tokens and
6,084 lines of code.

At which point I decided to scale the work up slightly and build one of the
company for myself.


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

---

Built by [nosey dewdrop](https://noseydewdrop.com). The case that started it is
not reproduced here, and the company is not named. The bug is in their data
either way.
