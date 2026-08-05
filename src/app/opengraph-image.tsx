/**
 * The home card.
 *
 * The figure is the one the page leads with, off the round of 4 August 2026,
 * and `tests/copy.test.ts` holds the two files to the same numbers so a new
 * round cannot leave an old figure travelling around inside a picture.
 */
import { CONTENT_TYPE, SIZE, card } from "./card";

export const alt =
  "lulumelon: 11 of 20 measured questions named none of the thirteen rivals that had been declared";
/** Written to a file at build time, like every other route on this site. */
export const dynamic = "force-static";
export const size = SIZE;
export const contentType = CONTENT_TYPE;

export default function Image() {
  return card({
    figure: "11 of 20",
    said: "questions written from one customer site, and the answers named none of the thirteen rivals that had been declared",
    foot: "one round, four draws each, 4 august 2026, $2.46 paid straight to the provider",
  });
}
