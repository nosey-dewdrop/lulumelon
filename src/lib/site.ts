/**
 * What the site calls itself, and where it lives.
 *
 * The url is read from the environment rather than written here, because a
 * canonical tag pointing at the wrong host is worse than none at all: it tells
 * a crawler that the page it just read is a copy of a page somewhere else. Set
 * `NEXT_PUBLIC_SITE_URL` at build time on whichever host is serving it.
 */
export const SITE_NAME = "lulumelon";

export const TAGLINE = "measure what language models say about you";

export const SITE_URL = (
  process.env.NEXT_PUBLIC_SITE_URL ?? "https://nosey-dewdrop.github.io/lulumelon"
).replace(/\/$/, "");

export const REPO_URL = "https://github.com/nosey-dewdrop/lulumelon";

/** Written out rather than left as the handle, on every surface. */
export const AUTHOR = "Damla Su Bilge";
export const AUTHOR_URL = "https://noseydewdrop.com";
export const AUTHOR_HANDLE = "nosey dewdrop";

/**
 * Absolute url for a path, for canonicals and the sitemap.
 *
 * With the trailing slash the export writes, because `/named/x` and
 * `/named/x/` are two urls to a crawler and a sitemap that lists one while the
 * page declares the other is a site arguing with itself about which page is
 * canonical.
 */
export function url(path = "/"): string {
  const clean = path.startsWith("/") ? path : `/${path}`;
  // A file keeps its name. `sitemap.xml/` is a directory that does not exist,
  // and it was pointed at from robots.txt, which is the one line a crawler
  // reads before it decides how much of the site to bother with.
  const isFile = /\.[a-z0-9]+$/i.test(clean);
  const withSlash = isFile || clean.endsWith("/") ? clean : `${clean}/`;
  return `${SITE_URL}${withSlash}`;
}
