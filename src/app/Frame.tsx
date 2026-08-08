/**
 * The doors and the sign-off, in one place.
 *
 * Every page on this site wears these, and it is one component rather than
 * three copies because the copies drifted: the question pages ended up with a
 * thin breadcrumb where the home page had a nav, a headline twice the size of
 * the one it linked from, and no way back that read like a way back. A visitor
 * who lands on a measured question from a search result has to be able to see
 * that it belongs to something, and to walk into it.
 */
import Link from "next/link";

import { ANSWERS } from "@/lib/answers";
import { AUTHOR, AUTHOR_URL, SITE_NAME } from "@/lib/site";

export const REPO = "https://github.com/nosey-dewdrop/lulumelon";

export function Pm() {
  return <span className="text-lilac">±</span>;
}

/** The current page, so the bar can mark where the reader is standing. */
export type Here = "named" | "docs" | (string & {});

function Standing({ children }: { children: React.ReactNode }) {
  return <span className="underline decoration-rule underline-offset-[6px]">{children}</span>;
}

/**
 * Two rows, and the second one is the product.
 *
 * The first row is the site. The second is what the tool answers, one link per
 * question, because a reader who has not decided anything yet is not going to
 * find `lulu lift` inside a paragraph on the docs page. The labels are short
 * enough to sit in a row; the urls they point at are the long sentences
 * somebody actually types, and they are written out in `lib/answers.ts` once
 * for the bar, the sitemap and the test that keeps them in step.
 */
export function Nav({ here }: { here?: Here }) {
  return (
    // Sticky, and solid rather than blurred. The page scrolls under it and
    // the paper hides what passes, so there is no rule to draw and nothing to
    // float. `-mx` reaches back through the padding of the page it sits in, so
    // the bar is the width of the window rather than of the column.
    <nav className="sticky top-0 z-20 -mx-5 bg-paper px-5 py-3 text-ink-soft sm:-mx-10 sm:px-10">
      <div className="flex flex-wrap items-baseline justify-center gap-x-5 gap-y-2 text-[15px]">
        {here ? (
          <Link className="text-ink hover:text-lilac" href="/">
            {SITE_NAME}
          </Link>
        ) : (
          <span className="text-ink">{SITE_NAME}</span>
        )}
        <Pm />
        {here === "named" ? (
          <Standing>measured questions</Standing>
        ) : (
          <Link className="hover:text-lilac" href="/named">
            measured questions
          </Link>
        )}
        <Pm />
        {here === "docs" ? (
          <Standing>docs</Standing>
        ) : (
          <Link className="hover:text-lilac" href="/docs">
            docs
          </Link>
        )}
        <Pm />
        <a className="hover:text-lilac" href={REPO}>
          source
        </a>
      </div>

      {/* A step down in size, so the row reads as what is inside the site
          rather than as a second site. */}
      <div className="mt-2 flex flex-wrap items-baseline justify-center gap-x-4 gap-y-1 text-[13.5px]">
        {ANSWERS.map((answer, i) => (
          <span key={answer.slug} className="flex items-baseline gap-x-4">
            {i > 0 ? <Pm /> : null}
            {here === answer.slug ? (
              <Standing>{answer.label}</Standing>
            ) : (
              <Link className="hover:text-lilac" href={`/${answer.slug}`}>
                {answer.label}
              </Link>
            )}
          </span>
        ))}
      </div>
    </nav>
  );
}

/**
 * What separates two blocks here.
 *
 * A plain rule was tried and thrown out. This is the same three glyphs every
 * time, from the palette, centred and spaced out, so a reader learns it as the
 * mark of a break rather than reading it as content. Hidden from a screen
 * reader, which hears the heading that follows instead.
 */
export function Divider() {
  return (
    <div className="my-10 text-center text-[14px] tracking-[0.7em] select-none" aria-hidden>
      ✨🍉✨
    </div>
  );
}

export function Foot({ back }: { back?: boolean }) {
  return (
    <footer className="mt-10 text-[13px] text-ink-soft">
      <div className="flex flex-wrap items-baseline justify-center gap-x-3 gap-y-2">
        <Link className="text-ink hover:text-lilac" href="/">
          {SITE_NAME}
        </Link>
        <Pm />
        <a className="underline decoration-rule underline-offset-4 hover:decoration-pink" href={REPO}>
          source
        </a>
        <Pm />
        <span>
          built by{" "}
          <a className="underline decoration-rule underline-offset-4 hover:decoration-pink" href={AUTHOR_URL}>
            {AUTHOR}
          </a>
        </span>
        {back ? (
          <>
            <Pm />
            <Link className="hover:text-lilac" href="/named">
              every measured question
            </Link>
          </>
        ) : null}
      </div>
    </footer>
  );
}
