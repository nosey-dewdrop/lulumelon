/**
 * Give the exported cards the one thing a static host needs to serve them as
 * pictures.
 *
 * Next writes a metadata image route to a file with no extension: the home
 * card lands at `out/opengraph-image`, which is a valid PNG that GitHub Pages
 * hands over as `application/octet-stream`, because a static host has nothing
 * to guess a type from but the name. Measured, not assumed, on the live site
 * before this existed. A crawler that asks for a picture and is given an octet
 * stream does not draw a card, so the link went out bare with a perfectly good
 * image sitting behind it.
 *
 * So the export is finished here: every card gets its extension, every url
 * that pointed at the old name is moved with it, and the check at the bottom
 * refuses to let a build through with a reference to a file that is no longer
 * there. It runs after `next build`, from `npm run build`.
 */
import { readdirSync, readFileSync, renameSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const OUT = new URL("../out/", import.meta.url).pathname;
const NAME = "opengraph-image";

/** Files a url can be written into, as opposed to the pictures themselves. */
const TEXT = [".html", ".txt", ".json", ".xml"];

function walk(directory) {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

const files = walk(OUT);

const renamed = files.filter((path) => path.endsWith(`/${NAME}`));
for (const path of renamed) renameSync(path, `${path}.png`);

let moved = 0;
for (const path of files) {
  if (!TEXT.some((extension) => path.endsWith(extension))) continue;
  const before = readFileSync(path, "utf8");
  // The query is the hash Next puts on a card so a platform re-fetches it when
  // the picture changes. It is also what makes this token unambiguous: a bare
  // occurrence of the name is a route in a manifest, not a url a crawler will
  // follow.
  const after = before.replaceAll(`${NAME}?`, `${NAME}.png?`);
  if (after === before) continue;
  writeFileSync(path, after);
  moved += 1;
}

const left = files
  .filter((path) => TEXT.some((extension) => path.endsWith(extension)))
  .filter((path) => readFileSync(path, "utf8").includes(`${NAME}?`));
if (left.length) {
  console.error(`still pointing at a card with no extension: ${left.join(", ")}`);
  process.exit(1);
}

for (const path of renamed) {
  if (!statSync(`${path}.png`).isFile()) {
    console.error(`renamed away and not there: ${path}.png`);
    process.exit(1);
  }
}

console.log(`cards: ${renamed.length} given an extension, ${moved} files moved onto it`);
