import { copyFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { defineConfig } from "vite";

/**
 * MV3 content scripts are injected as classic scripts and cannot use ESM
 * `import` statements. Building each entry separately (CCB_TARGET) guarantees
 * a self-contained bundle per entry with no shared chunks.
 */

const root = __dirname;
const outDir = resolve(root, "dist");

const ENTRIES = {
  content: { name: "content/content", input: resolve(root, "src/content/content.ts") },
  background: {
    name: "background/service-worker",
    input: resolve(root, "src/background/service-worker.ts"),
  },
} as const;

type TargetKey = keyof typeof ENTRIES;

const target = (process.env.CCB_TARGET ?? "content") as TargetKey;
const entry = ENTRIES[target] ?? ENTRIES.content;
const isFirst = target === "content";

export default defineConfig({
  // The panel ships hand-written plain CSS injected into the shadow root. Pin an
  // inline (empty) PostCSS config so Vite stops searching parent directories and
  // never picks up an unrelated project's postcss.config.mjs.
  css: { postcss: { plugins: [] } },
  build: {
    outDir,
    // Only the first build clears dist so the second entry is preserved.
    emptyOutDir: isFirst,
    target: "chrome114",
    minify: false,
    rollupOptions: {
      input: entry.input,
      output: {
        format: "iife",
        entryFileNames: `${entry.name}.js`,
        inlineDynamicImports: true,
      },
    },
  },
  plugins: [
    {
      name: "ccb-copy-manifest",
      closeBundle() {
        mkdirSync(outDir, { recursive: true });
        copyFileSync(resolve(root, "manifest.json"), resolve(outDir, "manifest.json"));
      },
    },
  ],
});
