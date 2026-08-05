/**
 * The picture that goes out with a link.
 *
 * A tool that exists to say where a number came from cannot advertise itself
 * with a number from nowhere, so every figure printed on a card here is one the
 * page under it also carries: the paid round of 4 August 2026 for the home
 * page, and `data/published/` for the question pages. Nothing on a card is
 * illustrative, and nothing on a card is rounder than the measurement.
 *
 * The type is DejaVu Sans Mono, vendored beside this file. The site sets no
 * font at all and lets a machine use its own monospace, which on the machine
 * these screenshots came from is Menlo; Menlo descends from Bitstream Vera and
 * so does DejaVu, so this is the same letter shape the page renders in, in a
 * file that can legally travel with the repository. A picture has to carry its
 * own font, and this is the closest true one.
 *
 * The palette is the stylesheet's, to the hex.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { ImageResponse } from "next/og";

import { SITE_NAME, SITE_URL, TAGLINE } from "@/lib/site";

/** What every platform crops to, and what `summary_large_image` promises. */
export const SIZE = { width: 1200, height: 630 };
export const CONTENT_TYPE = "image/png";

const PAPER = "#f7f0fa";
const RULE = "#dcc9e6";
const INK = "#241029";
const INK_SOFT = "#6b4f78";
const PINK = "#c8286f";
const LILAC = "#7b3fa8";

const MONO = readFileSync(join(process.cwd(), "src", "fonts", "DejaVuSansMono.ttf"));

/** The host, without the part a reader would not type. */
const HOST = SITE_URL.replace(/^https?:\/\//, "");

/** An interval, drawn the way the page draws it: a band, and a point in it. */
const BAR = 640;

export interface Interval {
  low: number;
  high: number;
  rate: number;
  /** The bounds in words, because a bar alone is a shape rather than a claim. */
  caption: string;
}

export interface Card {
  /** The line above the figure, when the figure needs a subject. */
  note?: string;
  /** The measurement, and the only thing on the card in pink. */
  figure: string;
  /** What the figure is of. A figure alone is not a card either. */
  said: string;
  interval?: Interval;
  /** Where the figure came from, along the bottom. */
  foot: string;
}

export function card({ note, figure, said, interval, foot }: Card) {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          background: PAPER,
          color: INK,
          fontFamily: "DejaVu Sans Mono",
          padding: "64px 72px",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
          <div style={{ fontSize: 32 }}>{SITE_NAME}</div>
          <div style={{ fontSize: 22, color: INK_SOFT }}>{TAGLINE}</div>
        </div>

        {/* The measurement takes the middle of the card rather than sitting
            under the wordmark, because at the size a feed shows this in, the
            figure is the only thing with a chance of being read. */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            flexGrow: 1,
            justifyContent: "center",
          }}
        >
          {note ? (
            <div style={{ fontSize: 24, color: INK_SOFT, marginBottom: 18, maxWidth: 1000 }}>
              {note}
            </div>
          ) : null}
          <div style={{ fontSize: 104, color: PINK, lineHeight: 1 }}>{figure}</div>
          <div style={{ fontSize: 32, lineHeight: 1.35, marginTop: 22, maxWidth: 900 }}>{said}</div>
          {interval ? (
            <div style={{ display: "flex", flexDirection: "column", marginTop: 30 }}>
              <div style={{ display: "flex", position: "relative", width: BAR, height: 6 }}>
                {/* The whole scale, drawn. On the page the track is the next
                    shade of paper because the reader is a foot away; in a feed
                    that shade disappears and the band becomes a line starting
                    from nowhere, so the track here is the rule colour and the
                    band is visibly a part of a whole. */}
                <div
                  style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    width: BAR,
                    height: 6,
                    background: RULE,
                  }}
                />
                <div
                  style={{
                    position: "absolute",
                    top: 0,
                    height: 6,
                    left: Math.round(BAR * interval.low),
                    width: Math.max(2, Math.round(BAR * (interval.high - interval.low))),
                    background: LILAC,
                  }}
                />
                <div
                  style={{
                    position: "absolute",
                    top: -4,
                    height: 14,
                    left: Math.min(BAR - 4, Math.round(BAR * interval.rate)),
                    width: 4,
                    background: PINK,
                  }}
                />
              </div>
              <div style={{ fontSize: 22, color: INK_SOFT, marginTop: 16 }}>{interval.caption}</div>
            </div>
          ) : null}
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
          <div style={{ fontSize: 22, color: INK_SOFT, maxWidth: 620 }}>{foot}</div>
          {/* The address is one word to a reader and breaking it in half is the
              fastest way to make a card look automatic. */}
          <div style={{ fontSize: 22, color: INK_SOFT, flexShrink: 0, marginLeft: 40 }}>{HOST}</div>
        </div>
      </div>
    ),
    {
      ...SIZE,
      fonts: [{ name: "DejaVu Sans Mono", data: MONO, style: "normal", weight: 400 }],
    },
  );
}
