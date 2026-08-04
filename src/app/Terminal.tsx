"use client";

/**
 * The landing page's one signature interaction.
 *
 * It is a playback device, not a sandbox. Every line it can ever print is
 * already in the bundle: typing something fires no request, spends no tokens and
 * cannot be abused. Unrecognised input is answered honestly and turned into the
 * call to action rather than faked.
 *
 * The chrome deliberately quotes the terminal the product is about, the same
 * markers, the same status bar, the same coral working line. Real text in real
 * DOM, so it is selectable and readable by a screen reader; nothing here is an
 * image of a terminal.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  DEMO_KEYS,
  DEMO_TRANSCRIPTS,
  EASTER_EGG_LINES,
  findTranscript,
  isEasterEgg,
  type Transcript,
} from "@/lib/demo-transcript";

/* ------------------------------------------------------------------- lines */

type Line =
  | { kind: "said"; text: string; dim?: boolean }
  | { kind: "asked"; text: string }
  | { kind: "working"; text: string; right?: string }
  | { kind: "tool"; name: string; args: string }
  | { kind: "result"; text: string; accent?: "coral" | "lilac" | "muted" }
  | { kind: "row"; label: string; count: string; rate: string; range: string; rank: string; subject: boolean }
  | { kind: "head"; text: string }
  | { kind: "blank" };

const pctText = (value: number) => `${(value * 100).toFixed(1)}%`;

/** Turns a transcript into the exact sequence of lines the terminal prints. */
function transcriptLines(t: Transcript): Line[] {
  const lines: Line[] = [
    { kind: "asked", text: t.question },
    { kind: "blank" },
    {
      kind: "working",
      text: `sampling · ${t.draws.length} draws · ${t.source}`,
      right: "0 tokens spent here",
    },
    { kind: "blank" },
  ];

  for (const draw of t.draws) {
    lines.push({
      kind: "result",
      text: `draw ${String(draw.index).padStart(2)} of ${t.draws.length}   ${draw.named.join(", ")}`,
      accent: "muted",
    });
  }

  lines.push({ kind: "blank" });
  lines.push({ kind: "tool", name: "Measure", args: "appearance rate · wilson 95%" });
  lines.push({
    kind: "head",
    text: `${"name".padEnd(18)}${"seen".padStart(6)}${"rate".padStart(9)}${"honest range".padStart(20)}${"rank".padStart(14)}`,
  });

  for (const row of t.rows) {
    lines.push({
      kind: "row",
      label: row.name,
      count: `${row.successes}/${row.n}`,
      rate: pctText(row.point),
      range: `${pctText(row.lower)} to ${pctText(row.upper)}`,
      rank:
        row.rankMean === null
          ? "never named"
          : row.rankSd === null
            ? `${row.rankMean.toFixed(1)}`
            : `${row.rankMean.toFixed(1)} ± ${row.rankSd.toFixed(2)}`,
      subject: row.isSubject,
    });
  }

  lines.push({ kind: "blank" });
  for (const note of t.notes) lines.push({ kind: "said", text: note });
  lines.push({ kind: "blank" });

  return lines;
}

const OPENING: Line[] = [
  { kind: "said", text: "lulumelon measures what language models say about you." },
  {
    kind: "said",
    text: "it asks the same question many times, because the answer keeps changing.",
    dim: true,
  },
  { kind: "blank" },
];

/* --------------------------------------------------------------- rendering */

function LineView({ line }: { line: Line }) {
  switch (line.kind) {
    case "blank":
      return <div className="h-[0.9em]" aria-hidden />;

    case "said":
      return (
        <div className="flex gap-2">
          <span className="text-term-muted select-none">●</span>
          <span className={line.dim ? "text-term-muted" : "text-term-text"}>{line.text}</span>
        </div>
      );

    case "asked":
      return (
        <div className="-mx-3 flex gap-2 bg-term-input px-3 py-[2px]">
          <span className="text-term-muted select-none">›</span>
          <span className="text-term-bright">{line.text}</span>
        </div>
      );

    case "working":
      return (
        <div className="flex items-baseline gap-2">
          <span className="text-term-coral select-none">*</span>
          <span className="text-term-coral">{line.text}</span>
          {line.right && (
            <span className="ml-auto text-term-muted hidden sm:inline">{line.right}</span>
          )}
        </div>
      );

    case "tool":
      return (
        <div className="flex gap-2">
          <span className="text-term-green select-none">●</span>
          <span>
            <span className="font-bold text-term-bright">{line.name}</span>
            <span className="text-term-muted">({line.args})</span>
          </span>
        </div>
      );

    case "head":
      return (
        <div className="flex gap-2">
          <span className="text-term-rule select-none">└</span>
          <span className="whitespace-pre text-term-muted">{line.text}</span>
        </div>
      );

    case "result":
      return (
        <div className="flex gap-2">
          <span className="select-none text-term-rule">{line.accent === "muted" ? " " : "└"}</span>
          <span
            className={
              line.accent === "coral"
                ? "text-term-coral"
                : line.accent === "lilac"
                  ? "text-term-lilac"
                  : "whitespace-pre text-term-muted"
            }
          >
            {line.text}
          </span>
        </div>
      );

    case "row":
      return (
        <div className="flex gap-2">
          <span className="select-none text-term-rule"> </span>
          <span
            className={`whitespace-pre ${line.subject ? "text-term-lilac" : "text-term-text"}`}
          >
            {line.subject ? "▸ " : "  "}
            {line.label.padEnd(16)}
            {line.count.padStart(6)}
            {line.rate.padStart(9)}
            {line.range.padStart(20)}
            {line.rank.padStart(14)}
          </span>
        </div>
      );
  }
}

/* ---------------------------------------------------------------- terminal */

const REPLAY_DELAY_MS = 62;

export function Terminal() {
  const opening = useMemo(
    () => [...OPENING, ...transcriptLines(DEMO_TRANSCRIPTS[DEMO_KEYS[0]])],
    [],
  );

  const [printed, setPrinted] = useState<Line[]>([]);
  const [queue, setQueue] = useState<Line[]>(opening);
  const [typed, setTyped] = useState("");
  const [focused, setFocused] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);

  // Drain the queue one line at a time. A real terminal fills downward; this is
  // the only animation on the page.
  useEffect(() => {
    if (queue.length === 0) return;
    const timer = setTimeout(() => {
      setPrinted((p) => [...p, queue[0]]);
      setQueue((q) => q.slice(1));
    }, REPLAY_DELAY_MS);
    return () => clearTimeout(timer);
  }, [queue]);

  useEffect(() => {
    const body = bodyRef.current;
    if (body) body.scrollTop = body.scrollHeight;
  }, [printed]);

  const submit = useCallback(() => {
    const input = typed.trim();
    if (!input) return;
    setTyped("");

    if (isEasterEgg(input)) {
      setQueue((q) => [
        ...q,
        { kind: "asked", text: input },
        { kind: "blank" },
        ...EASTER_EGG_LINES.map((text): Line => ({ kind: "result", text, accent: "lilac" })),
        { kind: "blank" },
      ]);
      return;
    }

    const transcript = findTranscript(input);
    if (transcript) {
      setQueue((q) => [...q, ...transcriptLines(transcript)]);
      return;
    }

    // Honest answer, which doubles as the offer.
    setQueue((q) => [
      ...q,
      { kind: "asked", text: input },
      { kind: "blank" },
      {
        kind: "said",
        text: "not measured. this terminal replays recordings, it does not call a model.",
      },
      {
        kind: "said",
        text: "measuring that properly means many draws against several providers.",
        dim: true,
      },
      { kind: "blank" },
      { kind: "tool", name: "Recorded", args: DEMO_KEYS.join(" · ") },
      { kind: "blank" },
    ]);
  }, [typed]);

  return (
    <div className="w-full border border-term-rule bg-term-bg text-[12.5px] leading-[1.55] sm:text-[13px]">
      {/* title bar */}
      <div className="flex items-center gap-2 border-b border-term-rule bg-term-bar px-3 py-[6px]">
        <span className="flex gap-[6px]" aria-hidden>
          <span className="h-[11px] w-[11px] rounded-full bg-light-red" />
          <span className="h-[11px] w-[11px] rounded-full bg-light-yellow" />
          <span className="h-[11px] w-[11px] rounded-full bg-light-green" />
        </span>
        <span className="truncate pl-2 text-term-text">
          lulumelon, · what do the models actually say, ± recording
        </span>
      </div>

      {/* body */}
      <div
        ref={bodyRef}
        className="h-[26rem] overflow-y-auto px-3 py-3 sm:h-[30rem]"
        onClick={() => inputRef.current?.focus()}
      >
        {printed.map((line, i) => (
          <div key={i} className="arrive">
            <LineView line={line} />
          </div>
        ))}
        {queue.length > 0 && (
          <div className="flex gap-2">
            <span className="text-term-coral select-none">*</span>
            <span className="text-term-coral">working…</span>
          </div>
        )}
      </div>

      {/* input row */}
      <div className="border-t border-term-rule bg-term-input">
        <label className="flex cursor-text items-center gap-2 px-3 py-[6px]">
          <span className="text-term-muted select-none">›</span>
          <span className="relative flex-1">
            <input
              ref={inputRef}
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              onFocus={() => setFocused(true)}
              onBlur={() => setFocused(false)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  submit();
                }
              }}
              spellCheck={false}
              autoComplete="off"
              aria-label="type a recorded question"
              className="w-full bg-transparent text-term-bright caret-transparent outline-none placeholder:text-term-muted"
              placeholder={
                queue.length > 0 ? "" : "try: agent observability   ·   or ask something else"
              }
            />
            <span
              className={`pointer-events-none absolute top-0 ${focused ? "caret" : "opacity-40"}`}
              style={{ left: `${typed.length}ch` }}
              aria-hidden
            >
              <span className="inline-block h-[1.15em] w-[0.6ch] translate-y-[0.15em] bg-term-text" />
            </span>
          </span>
        </label>
      </div>

      {/* status bar */}
      <div className="border-t border-term-rule px-3 py-[6px] text-[11.5px]">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <span className="text-term-muted">lulumelon</span>
          <span className="text-term-rule">·</span>
          <span className="text-term-muted">wilson 95%</span>
          <span className="text-term-lilac">*</span>
          <span className="text-term-lilac">rabadon</span>
        </div>
        <div className="text-term-pink">
          ▸▸ recording · no live calls <span className="text-term-muted">(nothing to abuse)</span>
        </div>
        <div className="mt-1 flex items-baseline justify-between gap-4">
          <span className="font-bold text-term-bright">● main</span>
          <span className="text-term-muted hidden sm:inline">enter to run · recordings only</span>
        </div>
        <div className="flex items-baseline justify-between gap-4">
          <span className="truncate text-term-muted">
            ○ measure (+2) &nbsp;appearance rate · rank · drift
          </span>
          <span className="shrink-0 text-term-muted">↓ 0 tokens</span>
        </div>
      </div>
    </div>
  );
}
