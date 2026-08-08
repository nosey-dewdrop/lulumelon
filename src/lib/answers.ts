/**
 * The six questions this site answers, each on its own url.
 *
 * The home page is a shop window and a shop window has room for one sentence.
 * Everything the tool actually does for somebody was underneath it, in a
 * paragraph, or in the docs, which is where the founder herself did not know
 * `lulu lift` existed. So each capability gets a page of its own, at a url
 * written the way the question is typed.
 *
 * Two reasons for separate pages rather than a longer home page. A single page
 * competes with itself for six different searches, and each of these has its
 * own title, canonical and card. And an answer engine cites the page that
 * answers one question rather than the page that covers a subject, which for a
 * tool that measures what answer engines cite is not a marketing detail.
 *
 * The label is short because it sits in a navigation row. The url is long
 * because it is the sentence somebody types. Nav, sitemap and the test that
 * holds the two together all read this list rather than repeating it.
 */

export interface Answer {
  /** The url, and the search it is written for. */
  slug: string;
  /** What the navigation row shows, which has to stay short. */
  label: string;
  /** The page's own question, and its `h1`. */
  question: string;
  /** The figure the page is built around, off a measured round. */
  figure: string;
  /** What that figure is of, in one line. */
  said: string;
  description: string;
}

export const ANSWERS: Answer[] = [
  {
    slug: "did-my-change-move-ai-visibility",
    label: "did it move?",
    question: "did my change move anything?",
    // No figure here yet, and the reason is the site's own rule. The numbers
    // this command is known by, `37.5% without it, 62.5% with it, +25.0
    // points`, come out of `test_lift.py`, which is a fixture rather than a
    // round somebody paid for. Every other page on this site leads with a
    // measurement, and this one leads with the gate until a lift round is
    // collected and published.
    figure: "no verdict",
    said: "is what a gap gets when the arms are not comparable, whatever the arithmetic says",
    description:
      "Change one thing, ask again, and read the gap with the interval it carries. The word for a causal claim has to be earned here: without a passing gate the same arithmetic prints as an arm difference and the command exits non-zero.",
  },
  {
    slug: "which-brands-does-chatgpt-name",
    label: "who gets named?",
    question: "who does the model name when nobody suggests anybody?",
    figure: "339",
    said: "companies one round of answers named that the declared rival list never carried",
    description:
      "A round records every company the answers reached for, not only the names you tracked. One paid round of twenty questions named 339 the declared list had never heard of.",
  },
  {
    slug: "how-many-times-should-you-ask",
    label: "how many draws?",
    question: "how many times do you have to ask?",
    figure: "9.00",
    said: "the effective sample inside 125 answers, because the repeats bought nothing",
    description:
      "Asking once is one draw from a distribution. The number of draws is derived from the base rate rather than picked, and a hundred and twenty five answers over nine questions can carry an effective sample of nine.",
  },
  {
    slug: "what-ai-visibility-tracking-costs",
    label: "what it costs",
    question: "what does a round cost?",
    figure: "$2.46",
    said: "the whole round, against a ceiling of $3.50 printed before it started",
    description:
      "The software is free and MIT licensed. You bring your own key, the tokens are billed to you by the provider, and the ceiling is printed before the first call and enforced during the round.",
  },
  {
    slug: "how-to-verify-an-ai-visibility-number",
    label: "can you prove it?",
    question: "can the number be proved?",
    figure: "6 of 6",
    said: "rounds on disk that re-derive from their own contents",
    description:
      "Every answer is written into an append-only hash-chained file, every report re-derives the chain before it computes anything, and a round states its own length so records removed from the end are reported rather than lost.",
  },
  {
    slug: "when-a-visibility-number-is-not-real",
    label: "when it refuses",
    question: "when does it refuse to give you a number?",
    figure: "0 of 5",
    said: "is not zero, it is anything up to 43.4%, and the report says so",
    description:
      "Never being named in five draws is compatible with 43.4%. No rank where the ordering does not repeat, no ahead where the intervals overlap, and undecided where the interval spans the base.",
  },
];

export function answerFor(slug: string): Answer | undefined {
  return ANSWERS.find((answer) => answer.slug === slug);
}
