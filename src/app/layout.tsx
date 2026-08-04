import type { Metadata } from "next";

import { SITE_NAME, SITE_URL, TAGLINE } from "@/lib/site";

import "./globals.css";

/**
 * The site's metadata, in one place, so a page added later cannot ship without
 * a canonical url or a social card. `metadataBase` is what makes every relative
 * canonical below resolve to an absolute one, which is the single most common
 * way a static export ends up telling search engines that every page is the
 * home page.
 */
export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: `${SITE_NAME}, ${TAGLINE}`,
    template: `%s · ${SITE_NAME}`,
  },
  description:
    "Ask a language model the same question many times, because the answer changes. Appearance rates with confidence intervals, a hash-chained record of every answer, and a refusal where the sample cannot support a number.",
  applicationName: SITE_NAME,
  keywords: [
    "llm visibility measurement",
    "ai search visibility",
    "answer engine optimisation",
    "brand mentions in llm answers",
    "confidence interval",
    "wilson interval",
    "generative engine optimisation",
    "chatgpt brand monitoring",
  ],
  authors: [{ name: "nosey dewdrop", url: "https://noseydewdrop.com" }],
  creator: "nosey dewdrop",
  alternates: { canonical: "/" },
  openGraph: {
    type: "website",
    url: SITE_URL,
    siteName: SITE_NAME,
    title: `${SITE_NAME}, ${TAGLINE}`,
    description:
      "One reading of a language model is one draw from a distribution. This asks n times and reports what the sample supports.",
    locale: "en",
  },
  twitter: {
    card: "summary_large_image",
    title: `${SITE_NAME}, ${TAGLINE}`,
    description:
      "One reading of a language model is one draw from a distribution. This asks n times and reports what the sample supports.",
  },
  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true, "max-snippet": -1, "max-image-preview": "large" },
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="h-full antialiased">
      <head>
        {/*
          A block that arrives on scroll starts at zero opacity, and a reader
          whose scripts never ran would be looking at a page with the argument
          missing. The markup carries every word either way; this is the one
          line that makes sure they are painted.
        */}
        <noscript>
          <style>{".reveal{opacity:1;transform:none}"}</style>
        </noscript>
      </head>
      <body className="min-h-full">{children}</body>
    </html>
  );
}
