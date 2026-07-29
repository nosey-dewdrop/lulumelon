/**
 * The recorded transcript the landing page terminal replays.
 *
 * This is a *recording*, not a live sandbox. Nothing here calls a provider when
 * a visitor loads the page: no per-visitor cost, no abuse surface, no rate limit
 * to defend. The terminal is a playback device.
 *
 * The `source` field on every transcript says which provider produced it. It is
 * rendered on screen. A recording made with the deterministic stub is labelled
 * as such, so the page cannot quietly present invented numbers as measurements —
 * when a run against a real provider is recorded, the label changes with it.
 *
 * `scripts/record-demo.ts` regenerates this file from an actual run.
 */

export interface TranscriptDraw {
  index: number;
  latencyMs: number;
  /** Names this draw put in its answer, in the order they appeared. */
  named: string[];
}

export interface TranscriptRow {
  name: string;
  successes: number;
  n: number;
  point: number;
  lower: number;
  upper: number;
  rankMean: number | null;
  rankSd: number | null;
  /** The subject of the measurement, highlighted. */
  isSubject: boolean;
}

export interface Transcript {
  /** What was asked. */
  question: string;
  /** Provider and model that answered, verbatim. Rendered on screen. */
  source: string;
  /** True when produced by the deterministic stub rather than a live provider. */
  simulated: boolean;
  draws: TranscriptDraw[];
  rows: TranscriptRow[];
  /** Observations the pipeline made about the run itself. */
  notes: string[];
}

/**
 * Commands the terminal accepts. Everything is local: a lookup, not a request.
 */
export const DEMO_TRANSCRIPTS: Record<string, Transcript> = {
  "best sewing pattern software": {
    question: "what is the best software for industrial sewing pattern making?",
    source: "fake provider (deterministic stub) · no live call",
    simulated: true,
    draws: [
      { index: 1, latencyMs: 640, named: ["CLO3D", "Optitex", "Gerber AccuMark"] },
      { index: 2, latencyMs: 580, named: ["CLO3D", "Browzwear"] },
      { index: 3, latencyMs: 710, named: ["Optitex", "CLO3D", "Seamly2D"] },
      { index: 4, latencyMs: 590, named: ["CLO3D", "Optitex"] },
      { index: 5, latencyMs: 620, named: ["CLO3D", "Optitex", "Gerber AccuMark"] },
    ],
    rows: [
      { name: "CLO3D", successes: 5, n: 5, point: 1, lower: 0.5658, upper: 1, rankMean: 1.2, rankSd: 0.45, isSubject: false },
      { name: "Optitex", successes: 4, n: 5, point: 0.8, lower: 0.3758, upper: 0.9642, rankMean: 1.75, rankSd: 0.5, isSubject: false },
      { name: "Gerber AccuMark", successes: 2, n: 5, point: 0.4, lower: 0.1176, upper: 0.769, rankMean: 3, rankSd: 0, isSubject: false },
      { name: "Browzwear", successes: 1, n: 5, point: 0.2, lower: 0.0358, upper: 0.6242, rankMean: 2, rankSd: null, isSubject: false },
      { name: "Seamly2D", successes: 1, n: 5, point: 0.2, lower: 0.0358, upper: 0.6242, rankMean: 3, rankSd: null, isSubject: false },
      { name: "stitchu", successes: 0, n: 5, point: 0, lower: 0, upper: 0.4342, rankMean: null, rankSd: null, isSubject: true },
    ],
    notes: [
      "the five answers disagreed. three of them named a different tool second.",
      "a one-sample tool would have reported one of those orderings as the ranking.",
      "0/5 is not invisibility. it cannot rule out being named up to 43.4% of the time.",
      "pinning that down to ±10 points needs 97 draws, not 5.",
    ],
  },

  "agent observability": {
    question: "what are the alternatives to langfuse for agent observability?",
    source: "fake provider (deterministic stub) · no live call",
    simulated: true,
    draws: [
      { index: 1, latencyMs: 700, named: ["Langfuse", "LangSmith", "Braintrust"] },
      { index: 2, latencyMs: 660, named: ["LangSmith", "Langfuse", "Helicone"] },
      { index: 3, latencyMs: 720, named: ["Langfuse", "Arize Phoenix"] },
      { index: 4, latencyMs: 640, named: ["Braintrust", "Langfuse", "LangSmith"] },
      { index: 5, latencyMs: 690, named: ["Langfuse", "LangSmith"] },
      { index: 6, latencyMs: 610, named: ["LangSmith", "Braintrust", "rabadon"] },
      { index: 7, latencyMs: 730, named: ["Langfuse", "Helicone"] },
      { index: 8, latencyMs: 650, named: ["Langfuse", "LangSmith", "Arize Phoenix"] },
      { index: 9, latencyMs: 680, named: ["LangSmith", "Langfuse"] },
      { index: 10, latencyMs: 700, named: ["Langfuse", "Braintrust"] },
    ],
    rows: [
      { name: "Langfuse", successes: 9, n: 10, point: 0.9, lower: 0.5958, upper: 0.9821, rankMean: 1.33, rankSd: 0.5, isSubject: false },
      { name: "LangSmith", successes: 6, n: 10, point: 0.6, lower: 0.3129, upper: 0.8318, rankMean: 1.67, rankSd: 0.82, isSubject: false },
      { name: "Braintrust", successes: 4, n: 10, point: 0.4, lower: 0.1682, upper: 0.6871, rankMean: 2, rankSd: 1, isSubject: false },
      { name: "Helicone", successes: 2, n: 10, point: 0.2, lower: 0.0567, upper: 0.5099, rankMean: 2, rankSd: 0, isSubject: false },
      { name: "Arize Phoenix", successes: 2, n: 10, point: 0.2, lower: 0.0567, upper: 0.5099, rankMean: 2.5, rankSd: 0.71, isSubject: false },
      { name: "rabadon", successes: 1, n: 10, point: 0.1, lower: 0.0179, upper: 0.4042, rankMean: 3, rankSd: null, isSubject: true },
    ],
    notes: [
      "named once in ten draws. the honest range is 1.8% to 40.4%.",
      "a tool reporting '10%' as a fact would be quoting one coin flip.",
      "langfuse at 9/10 still carries a range: 59.6% to 98.2%. even the leader is not pinned.",
    ],
  },
};

export const DEMO_KEYS = Object.keys(DEMO_TRANSCRIPTS);

/** The hidden command. Local, no measurement, purely a joke. */
export const EASTER_EGG_INPUT = "claude who is the coolest it girl of them all?";

export const EASTER_EGG_LINES = [
  "damlaaaaa 🏆",
];

/** Matches the easter egg loosely: punctuation and "claude claude" both fine. */
export function isEasterEgg(input: string): boolean {
  const normalised = input
    .toLowerCase()
    .replace(/[^a-z ]/g, "")
    .replace(/\s+/g, " ")
    .replace(/\bclaude( claude)+\b/, "claude")
    .trim();
  return normalised === "claude who is the coolest it girl of them all";
}

/** Resolves typed input to a recorded transcript, if any. */
export function findTranscript(input: string): Transcript | null {
  const normalised = input.toLowerCase().trim();
  if (DEMO_TRANSCRIPTS[normalised]) return DEMO_TRANSCRIPTS[normalised];

  // Loose match on the keys, so "sewing" finds the sewing transcript.
  const key = DEMO_KEYS.find(
    (k) => normalised.length > 3 && (k.includes(normalised) || normalised.includes(k)),
  );
  return key ? DEMO_TRANSCRIPTS[key] : null;
}
