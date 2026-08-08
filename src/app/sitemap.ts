import type { MetadataRoute } from "next";

import { ANSWERS } from "@/lib/answers";
import { publishedRounds } from "@/lib/published";
import { url } from "@/lib/site";

/**
 * Every url this site serves, generated from the same files the pages are.
 *
 * Written from `publishedRounds()` rather than by hand, so a round that was
 * published and a round that is in the sitemap cannot drift apart. A sitemap
 * listing a page that does not exist is the fastest way to teach a crawler to
 * stop trusting the rest of it.
 */

/** Written once at build time. A static export has nowhere to run this later. */
export const dynamic = "force-static";

export default function sitemap(): MetadataRoute.Sitemap {
  const rounds = publishedRounds();
  const newest = rounds.map((round) => round.asked_at).sort().at(-1);

  return [
    { url: url("/"), changeFrequency: "monthly", priority: 1 },
    { url: url("/docs"), changeFrequency: "monthly", priority: 0.9 },
    // The six question pages, off the same list the navigation row reads, so a
    // page the site serves cannot be missing from the file that tells a crawler
    // the site has it.
    ...ANSWERS.map((answer) => ({
      url: url(`/${answer.slug}`),
      changeFrequency: "monthly" as const,
      priority: 0.9,
    })),
    {
      url: url("/named"),
      lastModified: newest ? new Date(newest) : undefined,
      changeFrequency: "weekly",
      priority: 0.9,
    },
    ...rounds.map((round) => ({
      url: url(`/named/${round.slug}`),
      lastModified: new Date(round.asked_at),
      changeFrequency: "monthly" as const,
      priority: 0.8,
    })),
  ];
}
