/**
 * The docs card.
 *
 * Fifteen is counted, not remembered: `test_docs.py` already fails if a command
 * exists that the documentation does not, so the figure on this card moves when
 * the tool does.
 */
import { CONTENT_TYPE, SIZE, card } from "@/app/card";

export const alt = "lulumelon documentation: fifteen commands, and no service behind any of them";
/** Written to a file at build time, like every other route on this site. */
export const dynamic = "force-static";
export const size = SIZE;
export const contentType = CONTENT_TYPE;

export default function Image() {
  return card({
    figure: "15",
    said: "commands, run on your own machine against your own key, with no account and no hosted api anywhere behind them",
    foot: "python 3.11 and two dependencies, both of them arithmetic",
  });
}
