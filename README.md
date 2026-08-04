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

Asks n times, and reports what the sample supports. Below is a real round, not
an illustration. Four hundred live calls against one engine on 1 August 2026,
two arms, $3.695558 of a prepaid account, written to a sealed ledger that
re-derives.

    APPEARANCE
      Ornek is named in 11.1% of answers
      honest range 0.0% to 33.3%  (95% confidence, prompt-clustered)

    WHAT IS CONTRIBUTING TO YOUR INTERVAL WIDTH?
      the model answering differently   0.0%
      which questions you chose to ask  100.0%
      noise floor  +/-25.8 points  (icc 1.00)

The second arm asked the same nine questions with no search tool attached, and
the brand was named in 0.0% of a hundred and eighty answers. So this engine does
not carry it and finds it only when it goes looking.

**The repeats bought nothing, and the arithmetic says how much nothing.** Every
question returned the same answer on all twenty asks, so the correlation inside
a question came out at 1.000. The design effect is then the cluster size, and
a hundred and twenty five answers over nine questions carry an effective sample
of 9.00. Exactly the number of questions.

**0 of 20 is not 0%.** Eight of the nine questions never named the brand, and
never being named still leaves a real upper bound rather than certainty of
absence. The textbook normal approximation collapses to [0, 0] there, so this
uses the Wilson score interval, which keeps a bound at the edges.

**One question was excluded and the report says so on its own line.** It asked
what the brand's own domain is, so every answer repeated the name, including the
ones stating the model had never heard of it. A question carrying the name is
answered with it whatever the model knows.

**Rank is kept separate from rate**, because appearing twice at rank 1 is a
different position from appearing nine times at rank 5.

**Ahead means the intervals do not overlap.** A competitor at 6 of 10 against
your 4 of 10 is not ahead of you, so no ranking is printed that the sample
cannot support.

The round behind those figures is on the machine that collected it and is not
published here, because it is a measurement of somebody else's brand. What is
published is the command that reproduces one, and the chain hash that lets a
reader check any report against the ledger it came from.

## layout

```
lulumelon/
  cli.py          `lulu init` / `doctor` / `plan` / `collect` / `report` / `rivals` / `usage` / `verify` / `ablate` / `lift`
  keys.py         where a key is looked for, in order, and how it is kept quiet
  prices.py       what a call costs, from the provider's page, with the date read
  mirror/         the measurement core, calls no model
    types.py      a run is the atom, and one run is never enough for a number
    intervals.py  Wilson and a clustered bootstrap that resamples prompts
    variance.py   splits the wobble into the model rerolling vs the prompt set
    stability.py  decides whether an ordering repeats enough to report a rank
    compare.py    before / after, and no verdict when the model moved underneath
    sources.py    which pages were cited, and whether a name travels with them
    ablation.py   whether a replica may stand in for the surface it replaces
    lift.py       what one source was worth, and the name that has to be earned
    report.py     one brand, with the refusals kept
    screen.py     the gates a question passes, and the draws that decide it
    names.py      who the model named when nobody suggested anybody
  collect/        the part that asks, and the part that writes it down
    ask.py        provider boundary; Perplexity Sonar and a deterministic stub
    subject.py    the tracked names and the questions, refused rather than repaired
    session.py    one round: k asks per prompt, failures recorded not retried
    budget.py     a ceiling checked before each call, so a round stops short
    ledger.py     append-only, hash-chained, and each round states its length
    detect.py     brand matching by declared literals, no model in the loop
    audit.py      whether the answer engines are allowed to read the site
    harvest.py    the customer's own site, read once, with the gaps named
    propose.py    one paid call for candidate questions, and no trust in the reply
    replica.py    the same question with the source list supplied, on purpose
    replay.py     ledger back into runs, handing back what it excluded
  usage.py        what a recorded round cost, from the provider's own figures
  plan.py         how many calls a target precision needs, before spending any
  panel.py        the surface a customer reads
  latex.py        the same surface as a document, with the ledger it came from
  text.py         one counted noun, agreeing, so every screen can count to one
  demo.py         one recorded round, so the output above can be reproduced

src/lib/          the TypeScript layer behind the demo terminal
  stats.ts        Wilson intervals and the sampling math; calls no model
  mentions.ts     extracts brand mentions and ranks from a model answer
  visibility.ts   turns samples into per-brand rates, intervals and ranks
```

The measurement engine lives in Python and only in Python. A sampling plan that
answers differently depending on which language you asked it in is not an
instrument, so there is one implementation of it rather than two that agree
until they do not.

One page under two urls is read once. Which two urls those are is the site's
own answer, from the tag the standard exists for, and where a site declares
nothing the words decide: a page whose text is already in the corpus to the
character is the same document under a second name, and it would otherwise
spend a second slot of the handful the model is shown. Both are recorded, with
the url that was kept, because a corpus of thirteen pages that started as
fifteen is a different object from one that started as thirteen.

`mirror/` and `stats.ts` are pure: given successes and n they return an interval,
so the claim this makes can be checked without spending a token. `collect/` is
the only part allowed to reach the network, and it computes nothing.

    python3 -m pytest lulumelon/tests   # 968 tests, offline
    npm test                            # 45 tests, offline

Offline and self contained: the suite closes every socket for the length of a
run, and the one test that drives the OS keychain makes a keychain of its own,
uses it, and deletes it. Running these tests does not change the machine that
ran them.

## install

Python 3.11 or newer, and nothing else to decide. The two dependencies are the
arithmetic; everything on the network path is standard library, because an HTTP
client is not worth a supply chain for one POST.

    git clone https://github.com/nosey-dewdrop/lulumelon.git
    cd lulumelon
    python3 -m venv .venv && source .venv/bin/activate
    pip install -e .

That puts `lulu` on the path. Without the install the same commands run as
`python3 -m lulumelon.cli`, and the tests run either way.

    pip install -e ".[dev]"     # pytest, to run the suite
    python3 lulumelon/demo.py   # the argument this exists for, no key, no network

Building it as a package needs setuptools 77 or newer, which is stated in
`pyproject.toml` and is not a preference: the licence field here is the SPDX
string, and every backend before 77 reads that as a table and stops.

## getting started

You bring your own key, so the first command is about the key and nothing else.
[docs/keys.md](docs/keys.md) is the long version, with the exact pages and the
published prices.

    lulu setup     # paste the key when it asks, or pipe it in: pbpaste | lulu setup

That is the whole of it. One command, no questions. It reads which engine the
key belongs to off the key, offers it to the OS keychain, falls back to a file
with owner-only permissions when the keychain will not take it, says which of
the two happened and why, and then spends about a cent proving that the key
works, that the search tool is switched on for your account, and that a search
actually comes back with pages.

The fallback is not decoration. A Mac whose default keychain is locked or
missing answers the store request with a dialog and then with nothing, so
"macOS" and "a key can be stored right now" are two different facts and this
command only believes the second one after it has asked. Whichever way it goes
it prints the place and the command to read the key back yourself.

That call is billed, so it is written down. It lands in `./ledger` under a name
beginning `diagnostic__`, and the command says the path on the way past. A round
of its own, because a call made to test an account is not a measurement of a
brand: it is priced by `lulu usage` like any other spend, and refused by
everything that scores an answer.

The key is never printed, never put in shell history, and never written into the
repository. Nothing is asked, because every question in a setup step is a place
to get stuck, and this one had three.

    lulu doctor    # why is it not working, on one screen
    lulu init      # the older wizard, when you want to choose where it goes

`lulu doctor` prints every place it looked, in order, whether or not it found
anything. `lulu doctor --offline` does all of that and spends nothing.

## what a measurement costs

    lulu plan --prompts 40 --brands 5 --half-width 5

sizes the round before it is bought. With no pilot it will not hand back a
single number: for a yes-or-no outcome the total per-draw variance is p(1-p)
and cannot exceed a quarter, which is arithmetic, but how that splits between
the model answering differently and the questions you picked is not, and the
split is what decides whether repeats or prompts buy your precision. So it
prints the range, the icc above which no number of repeats reaches the target
at all, and the price of both ends. Point it at a recorded round with
`--pilot` and every one of those is replaced by a measured value.

## what a design you set costs

    lulu size --prompts 24 --runs 5 --engines perplexity,anthropic

is the other direction, for when the design is already decided. You fix the
prompts, the repeats and the engines; it returns the bill and the precision that
design actually buys. The key is yours, so the spend lands on your account, and
a figure you are asked to approve has to be answerable before the round rather
than after it.

Two things it will not round off. At one run per prompt it prints no interval at
all, because the model's rerun noise and the prompt-to-prompt spread are then the
same quantity and no split can be identified; a round of that shape returns a
reading, and a reading is not a measurement. And a second engine does not narrow
the first, since engine answers are never pooled into one proportion, so what
more engines buy is coverage across systems, each carrying its own interval and
its own bill.

## drafting a question set from a domain

    lulu draft --site https://ornek.com --floor 0.5 --budget 5.00 \
               --rivals Numerai --out data/subjects/ornek.json

reads the customer's own site, asks a model for candidate questions, and keeps
only the ones that survive. Nothing else is typed: the pages that get read are
ranked by what the site itself links to and lists, and every question arrives
carrying the page it came from and a quote from that page, checked as a literal
substring of that page before anything is asked for real.

`--floor` sets what a kept question has to beat, and the number of draws follows
from it rather than from a constant here. At a floor of 0.5 a clean sweep needs
four draws before its lower bound clears the floor, so four is what it buys; at
0.75 it buys twelve, and the bill is printed before the money moves.

The gate measures how often an answer names a **rival**, never the customer.
Screening a question set on the customer's own mentions keeps the questions they
scored well on and drops the rest, which raises the published number by deleting
the evidence against it, so with no rival declared the paid round is refused
rather than run on the one name available.

`--harvest-only` stops after reading the site and spends nothing. `--dry-run`
adds the proposal call and the free gates and stops before the draws. Either
way, every candidate that died is written to `<out>.draft.json` with the gate
that stopped it, because a set of nine questions that started as forty is a
different object from one that started as nine.

## collecting a round

    lulu collect --subject data/subjects/ornek.json --k 5 --budget 5.00 \
                 --provider anthropic --model claude-opus-5 --max-searches 3

asks every question in the subject file k times, writes each answer to the
ledger as it comes back, and seals the round when it closes. The subject file is
where the tracked names and the questions live. A prompt id in it is permanent
identity, because that is what every comparison groups by, so a file with two
prompts under one id is refused rather than renumbered, and so is one with no
prompts, an empty brand, or a key this build does not read.

`--budget` is a hard ceiling in dollars and it has no default. This is the
command that spends real money on a prepaid account, and a default ceiling is a
default amount of somebody else's. It is built from the published price of the
model that will actually answer, so a model with no price on file is refused
rather than collected unpriced, and the worst case at that ceiling is printed
before the first call rather than reported after the last one. Nothing is asked
along the way: every question in a step is a place to get stuck.

A round the ceiling stops is a shorter round rather than a failed one. It says
how many questions were never asked, seals itself at the length it reached, and
comes back with a non-zero code so nothing downstream reads it as the design
that was bought.

    lulu collect --subject data/subjects/ornek.json --k 5 --budget 5.00 --no-search

collects the other arm: the same questions with no search tool attached at all,
which is the difference between a brand the model knows from its weights and one
it finds by retrieval. That arm records itself under its own surface, so the two
are two files and two conditions, and comparing them is refused by the same rule
that refuses a comparison between a logged-in browser and an API. On a fee
charged per search it owes nothing, and `lulu usage` prices it that way instead
of charging the one-search floor for a search it was never able to run.

## reading a round

    lulu report --ledger ./ledger --snapshot ROUND \
                --subject data/subjects/ornek.json --brand Ornek

prints what that round measured: the design it was collected under, the rate
with its interval, where the width of that interval came from, and every place
the round refuses to give a number. The chain is re-derived first, because a
number computed from a round that does not re-derive is not a number.

It also prints what it asked and what it asked it under, which is the half of
this category a buyer is normally not shown. An independent critique lists what
these products keep back as "prompt list, runs per prompt, geography, model,
account state, and scoring formula", and the advice given to buyers is to ask to
see the prompts for their category and run the round again themselves. So the
report ends with every question, in the order the subject file states them, each
with how many of its asks came back usable and a mark where it is left out of
the rate. The rate is not balanced across them: the round in `./ledger` asked
twenty of each and kept between seven and twenty, and a design line that divides
answers by questions prints an average that no question was asked at.

Above the questions it says where the round asked from, which is nowhere: no
location is sent on any call, and a report silent about that reads as a report
that chose somewhere. The cap on how many searches one call may run is stated as
not recoverable, because no field of a record carries it; on the arm collected
with no search tool at all it is recoverable, and that is what is printed
instead. Under the rate are the two lines that produce it: the mean of the
per-prompt means, and the clustered percentile bootstrap named with the draws
and the seed it was run at, so the arithmetic can be repeated rather than
believed.

The subject file is passed rather than a list of questions, because one rule is
applied here that needs it. **A question that names the brand cannot measure
that brand.** Detection matches declared literals, so a question carrying one of
the brand's own forms is answered with that form whatever the model knows, and
the answer scores as a mention. Which questions those are is computable from the
file that states them, so it is derived rather than labelled by hand. Such a
prompt is left out of the rate and its interval and named on its own line: a
number that quietly got smaller is its own defect.

That rule was written against this repo's first real round. One question in ten
asked what the brand's own domain was. Every answer to it named the brand, and
every one of those answers was the model saying it had never heard of it. It was
worth ten points of headline visibility on the arm collected with no search
tool, which reads 0.0% over the nine questions that remain.

    lulu report --ledger ./ledger --snapshot ROUND \
                --subject data/subjects/ornek.json --brand Ornek \
                --pdf ornek.pdf

writes the same report as a document, and adds to it the file the numbers came
from: the snapshot id, how many records are on it, what the round's own seal
says it did, the hash the chain ends on, the model as the response reported it,
the surface, the dates and what the round cost. A number in a PDF with no way
back to its evidence is the thing this repo exists against.

The document prints every question and the terminal stops at a screenful. That
is the one place the two surfaces differ, and it is that way round because the
document is the copy somebody checks a claim against, and a list of questions
with some of them missing cannot be checked against anything.

`--tex PATH` stops after the LaTeX and needs no TeX installed to get there.
`--pdf PATH` writes that document beside the PDF and runs `tectonic` over it.
Where there is no engine on the PATH the document is still written, the binary
that was looked for is named, and the command exits 7, which is outside the
range the refusals use: a machine with no typesetter on it is not a round that
could not be scored, and no script should read it as one.

    lulu usage     # what the rounds on disk cost, from the provider's figures
    lulu verify    # re-derive every chain, and say what that check does not cover

The questions in a screening round carry no company in them, so the names in
the answers are the model's own. `lulu rivals` reads them back off a round that
has already been paid for, and reports each name with the questions it turned up
in and how many draws of each named it. A name in every draw of one question and
a name in one draw of every question are opposite findings, and a single total
would print them the same.

    lulu rivals --ledger ./ledger --snapshot ROUND --least 2

Which of those names is a competitor is the one judgement it does not make. A
name is printed when the round wrote it inside a sentence at least once, or when
it is spelled the way no ordinary word is, and never when the same round also
wrote it in lower case. Every name printed appears in a recorded answer character
for character, which is the rule a quote is held to everywhere else here.

`lulu draft` prints its screening round once, while it is spending, and then that
round is a scrollback and two files of JSON. `lulu screened` reads it back and
turns it into the document, with every question it measured printed beside its
verdict and the names the same draws reached for underneath.

    lulu screened --draft data/subjects/ornek.draft.json --pdf screened.pdf

A question that named nobody is printed in full rather than summarised away. On
the first paid screening round this library ran, eleven of twenty questions came
back with none of the declared rivals named in any draw, which is a larger
statement about a market than the one score that round produced, and it had
nowhere to be read until this command existed.

That round also showed why a barren verdict is a statement about a list. Its
rivals were read off the arm that answers from its own weights and the round was
collected on the arm that searches, and the two arms reach for different
companies. So both surfaces print the names the answers used that the declared
list never mentioned, off the same draws, at no extra cost.

Every round closes with a record saying how many calls it made and how they
came out, hashed into the same chain as the answers. That is what makes a short
file readable as short: a round somebody has cut lines off the end of has lost
the only sentence that said how long it was, and `lulu verify` says so. It also
says which rounds the check does not reach, which is any collected before the
seal existed, because a file that never stated its length cannot be shown to be
missing anything.

    lulu ablate --live ROUND --replica ROUND --brand ornek --margin 5

asks the question the causal claim rests on. A live engine chooses its own
sources, so what it retrieves and what it says cannot be held apart; a replica
is the same model asked the same questions with the source list supplied, which
makes the list something you can change. That is only worth anything if the
replica behaves like the surface it stands in for, so this is an equivalence
test rather than an overlap test: it asks whether the difference is provably
smaller than the margin you plan at. Overlap would reward not looking, since two
rates measured with too few calls overlap with everything. So there are three
outcomes, and `this design cannot tell` is one of them, printed with the number
of calls that would settle it and a non-zero exit code.

    lulu lift --live ROUND --held ROUND --dropped ROUND --brand ornek \
              --source https://b.example/list \
              --sources https://a.example/guide \
              --sources https://b.example/list \
              --sources https://c.example/review

measures what that one page was worth: the appearance rate with the list held
whole, the rate with the page taken out, and the paired gap between them with
its interval. The sentence it exists to print reads `37.5% without it, 62.5%
with it, +25.0 points`.

The word `lift` is not the name of that number, it is a name it has to be
granted. The contrast is causal either way, since the list is ours and one
thing moved; what a passing gate buys is somewhere to carry it. Without
`--live` there is no gate, the same arithmetic prints as an `arm difference`,
and the exit code is not zero. With one, the levels are restated with the
gate's own margin added on top, because a laboratory rate quoted as a
customer's rate is uncertain by both.

The source list is not taken on trust either. A replica round records the
digest of the exact material it was shown, so the list given on the command
line is checked against the evidence file, and a reordered list, a swapped pair
of arms or an edited instruction is refused by name rather than measured.

Neither command scores a round whose answers did not all come from one engine.
A round is one engine and one surface, so a file holding two was not written by
one round: keyed by the question alone one engine's answers replace the other's,
and keyed by the sample the two sides pair on nothing they share. Both are
numbers about the collector, so such a round is refused and the engines it
holds are named.

`lulu usage` keeps three bases apart and never merges them: an amount the
provider stated, a cost computed from tokens it reported, and a floor for calls
it said nothing about. Failed calls are counted and priced at nothing, because
no response says whether a rejected call is billed.

---

Built by [nosey dewdrop](https://noseydewdrop.com).

