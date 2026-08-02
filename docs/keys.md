# Getting a key, and putting it where lulu will find it

This library asks you to bring your own key. That is what makes it cheap to
run, and it is also the only step where a new user can get stuck with nothing
to read. So this page is exact: the pages to open, the money involved, and the
one command that tells you what is wrong when it does not work.

Every figure below was read from Perplexity's own documentation on
**31 July 2026** and is linked to the page it came from. Nothing here is
estimated. Where their docs do not state something, this page says so instead
of filling the gap.

---

## 1. Get the key

1. Open **<https://console.perplexity.ai>** and sign in with your Perplexity
   account. This is the API portal, which is a different place from the
   chat product.
2. Open the **API Keys** tab and generate a new key.
   ([quickstart](https://docs.perplexity.ai/getting-started/quickstart):
   "Navigate to the **API Keys** tab in the API Portal and generate a new key.")
3. Copy it now. It is shown once.

Perplexity keys are reported to start with `pplx-`. That format is not stated
anywhere in their own documentation, so `lulu` treats it as a hint and warns
rather than refuses. If the key you are holding starts with `sk-`, it is an
OpenAI or Anthropic key and it will be rejected by the endpoint.

If you ever lose the page: Perplexity's own 401 response points at
<https://www.perplexity.ai/settings/api>, which is the same key list reached
from the account side.

## 2. Put credit on the account

Credits are bought in the console under the billing section.
Pricing is **pay as you go**: "Pay-as-you-go pricing for all APIs. No
subscription required."
([quickstart](https://docs.perplexity.ai/getting-started/quickstart))

**Perplexity's docs state no minimum purchase.** Guides elsewhere on the web
suggest starting with $5; that number is not from Perplexity, so it is not
repeated here as a requirement.

What the amount does change is your rate limit. A brand new account is Tier 0
and gets 50 sonar requests per minute, which is enough for everything in this
repository.
([rate limits](https://docs.perplexity.ai/docs/admin/rate-limits-usage-tiers))

| tier | total credits purchased | sonar requests per minute |
|---|---|---|
| 0 | $0 | 50 |
| 1 | $50+ | 150 |
| 2 | $250+ | 500 |
| 3 | $500+ | 1,000 |
| 4 | $1,000+ | 4,000 |
| 5 | $5,000+ | 4,000 |

## 3. Store it

```bash
pip install -e .
lulu setup
```

`lulu setup` asks nothing. It reads which engine the key belongs to off the key,
puts it in the safest place that will actually take it, and tells you where that
was. `lulu init` is the older wizard, for when you want to pick the place
yourself.

Three places, in the order `lulu` reads them:

| order | place | when to pick it |
|---|---|---|
| 1 | environment variable `PERPLEXITY_API_KEY` | CI, or one-off overrides |
| 2 | the OS keychain, service `lulumelon` | macOS: the key is not a file anywhere |
| 3 | `./.env`, then `~/.lulu/env` | when you want to see the file |

The first one that has a value wins, so an exported variable always overrides a
stored key. If you write the key into `./.env` inside a git repository,
`lulu init` adds `.env` to `.gitignore` first and says so.

**Row 3 is where `lulu setup` goes when row 2 refuses.** Being on a Mac is not
the same as having a keychain that will take a key: it can be locked, it can be
missing, and the authorisation dialog it puts up can be cancelled or never seen.
So `setup` offers the key to the keychain, and if the keychain does not take it,
writes `~/.lulu/env` instead, prints the reason the keychain gave, and names the
file. It never stores the key in no place at all, and it never ends in a stack
trace.

There is no search up the directory tree. `lulu` reads `./.env` and
`~/.lulu/env` and nothing else, so a run can never quietly pick up a key from a
directory you were not thinking about.

## 4. Check it

```bash
lulu doctor
```

It prints every place it looked, in order, whether or not it found something:

```
Looking for a perplexity key, in order:
  [empty] environment variable PERPLEXITY_API_KEY
  [empty] environment variable LULU_PERPLEXITY_API_KEY
  [empty] OS keychain (service lulumelon, account perplexity)
  [found] /Users/you/work/.env (PERPLEXITY_API_KEY)

Using the key from /Users/you/work/.env (PERPLEXITY_API_KEY).
Fingerprint: sha256:738bf347 (44 characters)
```

Then it spends one call to prove the key works, and prints what that call cost.
`lulu doctor --offline` does everything except the call, and spends nothing.

The fingerprint is a hash. It is there so you can tell two keys apart without
either of them ever being printed.

---

## What a call costs

From [Perplexity's pricing page](https://docs.perplexity.ai/getting-started/pricing),
read 31 July 2026:

| model | input / 1M tokens | output / 1M tokens | fee / 1K requests |
|---|---|---|---|
| sonar | $1 | $1 | $5 to $12 |
| sonar-pro | $3 | $15 | $6 to $14 |
| sonar-reasoning-pro | $2 | $8 | $6 to $14 |

The request fee is the part that matters, and it is why `lulu` reports a band
rather than a single number. A short `sonar` call costs a fraction of a cent in
tokens and between half a cent and just over one cent in fees, depending on the
search context size. Quoting one number would mean picking a context size on
your behalf and then presenting the guess as an invoice.

The fee range is why sample design is a cost decision and not a statistical
nicety. A measurement of 40 prompts asked 5 times each is 200 calls, which is
**$1.00 to $2.40 in request fees** plus a few cents of tokens.

### The other engine

`lulu` can also ask Claude, which searches through a tool and reports the pages
it retrieved. Token rates come from
[the model table](https://platform.claude.com/docs/en/about-claude/models/overview)
and the fee from
[the web search tool page](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool),
both read 1 August 2026:

| model | input / 1M tokens | output / 1M tokens | fee / 1K searches |
|---|---|---|---|
| claude-opus-5 | $5 | $25 | $10 |
| claude-sonnet-5 | $3 | $15 | $10 |
| claude-haiku-4-5 | $1 | $5 | $10 |

**That fee is charged per search, not per call, and the difference is the whole
point.** One question can send the model searching several times, and the
provider's own guidance says a comparative one can run ten or more, so an
uncapped call has no price anybody can know in advance. `lulu` caps it, and the
cap is also what keeps two rounds the same experiment: a round that searched
once and a round that searched nine times are two conditions, not one
measurement taken twice. A search that fails is not billed.

Get the key from **<https://console.anthropic.com/settings/keys>**, and note
that a subscription to the Claude assistant is not one. The API is billed
separately and issues its own key, and that is the step people miss.

When the API reports its own cost in the response, `lulu` prints that instead
and labels it as reported by the provider. The table above is only used when
the response is silent.

---

## When it does not work

`lulu doctor` names the state your account is in rather than a status code.

**The key was rejected (401).** The endpoint answered, so your network is fine.
The key was revoked, was copied incompletely, or belongs to another account.
Generate a fresh one and run `lulu init` again.

**No credit (402).** The key is valid, the account cannot be billed. Add credit
in the console.

**Rate limited (429).** Valid key, billable account, too many requests. A new
account is Tier 0 at 50 requests per minute. Wait and run it again.

**Nothing answered.** The key was never tested. That is a network path problem:
no route, DNS, or a proxy in the way.

**The endpoint is gone (404).** Our bug, not your setup. The provider moved it.

**The keychain would not take it.** `lulu setup` says so and writes
`~/.lulu/env` instead, so the key is stored and you can carry on. To use the
keychain after all, unlock it in Keychain Access, or create a login keychain if
the account has none, then run `lulu setup` again.

If the key is stored but malformed, `lulu doctor` says so before spending
anything: a pasted newline, a pair of shell quotes captured into the value, or
a key from the wrong provider all produce the same 401, and all three are
detectable locally for free.

---

## What is done with the key

- It is never printed. Not by `init`, not by `doctor`, not in an error.
  The tests place a known key and assert it does not appear on any output
  surface.
- It is never written to the ledger. Two separate guards, because they catch
  two different secrets. The provider boundary redacts our own key out of an
  error body, which it can do because it holds the key. The ledger redacts
  anything key-shaped out of every answer and every error it writes, which is
  what catches a key nobody here holds, quoted by a model out of a page that
  leaked it. That second pass runs before the card and phone rules, since those
  match digit runs anywhere and would otherwise take a key's digits and leave
  its prefix and issuer on disk.
- The provider object does not carry it in its `repr`, so a traceback or a
  debugger frame cannot spill it.
- Storing it in the keychain does not put it on a command line, where every
  other user of the machine could read it out of the process list.
- A file written by `lulu init` is created with permissions `600`, owner only.
- Running the test suite does not touch your keychain. The one test that
  exercises the real `security` binary creates a keychain of its own, never
  makes it the default, and deletes it afterwards.

The key is sent to exactly one place: the provider it belongs to.
