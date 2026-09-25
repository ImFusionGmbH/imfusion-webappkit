import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { HERO_LEAD } from "./src/content";

export default defineConfig({
  plugins: [
    react(),
    {
      name: "inject-copy",
      transformIndexHtml(html) {
        return html.replaceAll("__HERO_LEAD__", HERO_LEAD);
      },
    },
  ],
  // `src/content.ts` reads these to decide where the page links; the bundle has
  // no `process`, so the lookups are replaced with literals here. An empty
  // string leaves the canonical defaults in place.
  define: {
    "process.env.WEBAPPKIT_REPO_URL": JSON.stringify(process.env.WEBAPPKIT_REPO_URL ?? ""),
    "process.env.WEBAPPKIT_DOCS_URL": JSON.stringify(process.env.WEBAPPKIT_DOCS_URL ?? ""),
  },
  // Relative asset URLs so the built page works from a subdirectory or from disk.
  base: "./",
  build: {
    outDir: "dist",
    assetsInlineLimit: 0,
  },
  server: { port: 5173 },
});
