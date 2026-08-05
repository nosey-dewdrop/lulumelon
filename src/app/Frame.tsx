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

import { AUTHOR, AUTHOR_URL, SITE_NAME } from "@/lib/site";

export const REPO = "https://github.com/nosey-dewdrop/lulumelon";

export function Pm() {
  return <span className="text-lilac">±</span>;
}

export function Nav({ here }: { here?: "named" | "docs" }) {
  return (
    <nav className="flex flex-wrap items-baseline justify-center gap-x-5 gap-y-2 text-[13px] text-ink-soft">
      {here ? (
        <Link className="text-ink hover:text-lilac" href="/">
          {SITE_NAME}
        </Link>
      ) : (
        <span className="text-ink">{SITE_NAME}</span>
      )}
      <Pm />
      {here === "named" ? (
        <span className="underline decoration-rule underline-offset-[6px]">measured questions</span>
      ) : (
        <Link className="hover:text-lilac" href="/named">
          measured questions
        </Link>
      )}
      <Pm />
      {here === "docs" ? (
        <span className="underline decoration-rule underline-offset-[6px]">docs</span>
      ) : (
        <Link className="hover:text-lilac" href="/docs">
          docs
        </Link>
      )}
      <Pm />
      <a className="hover:text-lilac" href={REPO}>
        source
      </a>
    </nav>
  );
}

export function Foot({ back }: { back?: boolean }) {
  return (
    <footer className="mt-10 text-[12px] text-ink-soft">
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
