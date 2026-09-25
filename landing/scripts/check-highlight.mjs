/**
 * Round-trip check for the snippet grammars: every tokenisation must join back
 * into the exact source, and the kinds are printed for eyeballing.
 *
 * The Python grammar adds call ranges to the ones the upstream tokeniser found,
 * and ranges are turned into tokens by a single forward walk — so a list left
 * out of order drops source text from the rendered block while the copy button
 * still yields the whole snippet. That is the failure this catches.
 *
 *   npm run check:highlight
 */
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { transformSync } from "esbuild";
import { pathToFileURL } from "node:url";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
/* Transpiled into the package rather than imported as a data: URL, so that the
   bare specifiers in highlight.ts still resolve to node_modules. */
const cache = resolve(here, "../node_modules/.cache/check-highlight");
mkdirSync(cache, { recursive: true });

async function load(relative) {
  const source = readFileSync(resolve(here, relative), "utf8");
  const { code } = transformSync(source, { loader: "ts", format: "esm" });
  const out = resolve(cache, relative.replace(/.*\//, "").replace(/\.ts$/, ".mjs"));
  writeFileSync(out, code);
  return import(pathToFileURL(out).href);
}

const { grammarFromLabel, highlighter } = await load("../src/highlight.ts");
const content = await load("../src/content.ts");

const CASES = [
  ["app.py", content.APP_PY],
  ["workflow.py", content.WORKFLOW_PY],
  ["shell", content.INSTALL_COMMANDS],
  ["shell", content.PIP_COMMANDS],
  ["shell", content.INIT_COMMANDS],
];

let failures = 0;
for (const [label, source] of CASES) {
  const grammar = grammarFromLabel(label);
  const { tokens } = highlighter.tokenize(source, { lang: grammar });
  const rejoined = tokens.map(token => token.value).join("");

  if (rejoined !== source) {
    failures += 1;
    console.error(`FAIL ${label}: tokens do not rejoin into the source`);
    console.error(JSON.stringify({ source, rejoined }, null, 2));
    continue;
  }

  const counts = {};
  for (const token of tokens) {
    if (token.className) counts[token.className] = (counts[token.className] ?? 0) + 1;
  }
  console.log(`ok   ${label.padEnd(12)} ${grammar.padEnd(7)} ${JSON.stringify(counts)}`);
  console.log(
    "     " +
      tokens
        .filter(token => token.className)
        .map(token => `${token.className}:${JSON.stringify(token.value)}`)
        .join(" ")
        .slice(0, 400)
  );
}

process.exit(failures === 0 ? 0 : 1);
