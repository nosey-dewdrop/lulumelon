import type { NextConfig } from "next";

/**
 * Static, and served from a path.
 *
 * `export` because the site is four pages and a table, and nothing on it needs
 * a server: every figure is baked in at build time out of `data/published/`.
 * That also means a crawler and a visitor read the identical html.
 *
 * `basePath` because GitHub Pages serves a project repository under its own
 * name. It is read from the environment rather than written here so the same
 * build works on a bare domain, and it has to agree with `NEXT_PUBLIC_SITE_URL`
 * or every canonical on the site points at a page that is not there.
 */
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

const nextConfig: NextConfig = {
  output: "export",
  basePath: basePath || undefined,
  trailingSlash: true,
  images: { unoptimized: true },
};

export default nextConfig;
