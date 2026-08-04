import type { MetadataRoute } from "next";

import { url } from "@/lib/site";

/**
 * What a crawler may read, and where the list of pages is.
 *
 * Everything here is public and meant to be indexed. The one thing this site
 * never serves is a customer's round, and that is kept out by not being in the
 * repository at all rather than by a line in this file.
 */

/** Written once at build time, like the sitemap it points at. */
export const dynamic = "force-static";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", allow: "/" }],
    sitemap: url("/sitemap.xml"),
    host: url("/"),
  };
}
