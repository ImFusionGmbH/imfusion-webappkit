/**
 * The grammars the snippets on this page are tokenised with: the library's own
 * upstream ones, with Python adjusted twice.
 *
 * TanStack's Python grammar tags only decorators and `def` names as functions,
 * which leaves the workflow snippet — a list of constructor calls and nothing
 * else — almost entirely uncoloured. Call sites are added back here, and
 * decorators move to `meta` so the two can be told apart in the stylesheet.
 */
import {
  createHighlighter,
  defineLanguage,
  type TokenRange,
} from "@tanstack/highlight/core";
import { plaintext } from "@tanstack/highlight/languages/plaintext";
import { python } from "@tanstack/highlight/languages/python";
import { shell } from "@tanstack/highlight/languages/shell";

/** A name immediately followed by an opening parenthesis. */
const CALL = /\b[A-Za-z_]\w*(?=\s*\()/g;

/* Registered under its own name so the wrapper below can reach it by name
   through the tokenizer context and still answer to "python" itself. */
const upstream = defineLanguage({ name: "python-upstream", tokenize: python.tokenize });

const pythonWithCalls = defineLanguage({
  name: "python",
  aliases: ["py"],
  tokenize(code, context) {
    const ranges: Array<TokenRange> = context
      .tokenize(code, "python-upstream")
      .map(range =>
        code[range.start] === "@" ? { ...range, className: "meta" as const } : range
      );

    // Claimed offsets, so a call is only added where the upstream grammar found
    // nothing — the name in `def foo(` is already tagged, and `foo(` inside a
    // string or comment must not be pulled back out of it.
    const claimed = new Uint8Array(code.length);
    for (const range of ranges) claimed.fill(1, range.start, range.end);

    for (const match of code.matchAll(CALL)) {
      const start = match.index;
      const end = start + match[0].length;
      if (claimed.subarray(start, end).some(Boolean)) continue;
      ranges.push({ className: "function", start, end });
      claimed.fill(1, start, end);
    }

    /* Ranges are turned into tokens by a single forward walk that emits the gap
       before each one, so an out-of-order list silently drops source text from
       the block. Sorting is what keeps the render equal to the input. */
    return ranges.sort((a, b) => a.start - b.start);
  },
});

export const highlighter = createHighlighter({
  languages: [upstream, pythonWithCalls, shell, plaintext],
  fallbackLanguage: "plaintext",
});

/**
 * Pick a grammar from the label shown in the block's corner notch, so call
 * sites keep passing one thing ("app.py", "shell") rather than two. Returning
 * `undefined` leaves the block unhighlighted rather than falling back to
 * plaintext, which would wrap every character in markup for nothing.
 */
export function grammarFromLabel(label: string): string | undefined {
  if (label.endsWith(".py")) return "python";
  if (["shell", "bash", "sh", "console"].includes(label)) return "shell";
  return undefined;
}
