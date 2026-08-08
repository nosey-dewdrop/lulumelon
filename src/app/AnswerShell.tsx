/**
 * The frame every answer page wears.
 *
 * Six pages, one shape: the question as the heading, the figure that answers it
 * directly underneath, and then the mechanism. The shape is here rather than
 * copied six times because the copies drift, and a reader who arrives on one of
 * these from a search result and then clicks to another should not feel they
 * changed sites.
 *
 * No emoji in these headings. The palette is six glyphs with a place each, all
 * of them spoken for on the home page, and spraying them across six more
 * headings would turn a placement into a decoration.
 */
import type { Answer } from "@/lib/answers";

import { Divider, Foot, Nav } from "./Frame";
import { Reveal } from "./Reveal";

export function AnswerShell({
  answer,
  children,
}: {
  answer: Answer;
  children: React.ReactNode;
}) {
  return (
    <main className="mx-auto max-w-[82rem] px-5 pb-14 pt-0 sm:px-10">
      <Nav here={answer.slug} />

      <header className="mx-auto mt-7 max-w-[58rem] text-center">
        <h1 className="text-[1.4rem] leading-tight tracking-tight sm:text-[1.7rem]">
          {answer.question}
        </h1>
        {/* The figure and the sentence that makes it checkable, centred, one
            above the other. A figure with its words beside it opens a second
            left edge in a centred block, which is the one thing the eye
            catches from across the room. */}
        <div className="mt-7">
          <div className="text-[2.2rem] leading-none tracking-tight text-pink">{answer.figure}</div>
          <p className="mx-auto mt-4 max-w-[46ch] text-[16px] leading-snug text-ink-soft">
            {answer.said}
          </p>
        </div>
      </header>

      <Divider />

      {children}

      <Foot back />
    </main>
  );
}

/** One block of the argument, at the width the rest of the site reads at. */
export function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Reveal className="mx-auto mt-10 max-w-[54rem]">
      <h2 className="text-[1.4rem] leading-snug">{title}</h2>
      <div className="mt-4 text-[16px] leading-snug text-ink-soft">{children}</div>
    </Reveal>
  );
}

/** A command, set the way the terminal sets one. */
export function Command({ children }: { children: React.ReactNode }) {
  return (
    <pre className="mt-5 min-w-0 overflow-x-auto text-[14px] leading-snug text-ink">{children}</pre>
  );
}
