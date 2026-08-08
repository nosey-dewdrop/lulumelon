/**
 * The navigation row, the pages and the sitemap, held to one list.
 *
 * Three places name these urls and none of them may name a different set. A
 * label in the bar pointing at a page that is not there is a 404 the first
 * visitor finds; a page that is there and missing from the sitemap is a page a
 * crawler is never told about, which for six pages written to be found is the
 * whole point of writing them.
 *
 * Both directions, because only one of them catches a page added without being
 * listed, which is the direction a hurry goes in.
 */
import assert from "node:assert/strict";
import { existsSync, readdirSync, statSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { ANSWERS } from "../src/lib/answers.ts";

const APP = fileURLToPath(new URL("../src/app/", import.meta.url));

/** Route folders that are not one of the six, and are not meant to be. */
const NOT_AN_ANSWER = new Set(["docs", "named"]);

test("every listed answer has a page on disk", () => {
  for (const answer of ANSWERS) {
    assert.ok(
      existsSync(`${APP}${answer.slug}/page.tsx`),
      `${answer.slug} is in the navigation row and has no page`,
    );
  }
});

test("every question page on disk is in the list", () => {
  const listed = new Set(ANSWERS.map((answer) => answer.slug));
  const onDisk = readdirSync(APP)
    .filter((entry) => statSync(`${APP}${entry}`).isDirectory())
    .filter((entry) => !entry.startsWith("[") && !entry.startsWith("_"))
    .filter((entry) => !NOT_AN_ANSWER.has(entry))
    .filter((entry) => existsSync(`${APP}${entry}/page.tsx`));

  for (const entry of onDisk) {
    assert.ok(listed.has(entry), `${entry} is a page and is in no navigation row or sitemap`);
  }
});

test("the urls read like the question somebody types", () => {
  for (const answer of ANSWERS) {
    assert.match(answer.slug, /^[a-z][a-z0-9-]+$/, `${answer.slug} is not a clean url`);
    assert.ok(answer.slug.includes("-"), `${answer.slug} is one word, which is not a search`);
    // The heading is a question and the site's rule is that a question ends
    // with a mark, on every surface.
    assert.ok(answer.question.endsWith("?"), `${answer.slug}: the heading is not asked`);
    assert.ok(answer.label.length <= 18, `${answer.label} is too long to sit in the bar`);
  }
});

test("no two answers share a url or a label", () => {
  assert.equal(new Set(ANSWERS.map((a) => a.slug)).size, ANSWERS.length);
  assert.equal(new Set(ANSWERS.map((a) => a.label)).size, ANSWERS.length);
});
