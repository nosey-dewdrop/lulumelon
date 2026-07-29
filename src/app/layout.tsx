import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "youkiddingme — measure what language models say about you",
  description:
    "Ask the same question many times, because the answer changes. Appearance rates with confidence intervals, not one-shot guesses.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full">{children}</body>
    </html>
  );
}
