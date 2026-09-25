/**
 * The handful of presentational pieces the sections share: a code block, the
 * brand's generative motif, and the two icons the page needs.
 */
import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Button, Code } from "@imfusion/web-ui";
import { renderTokens, type HighlightRenderNode } from "@tanstack/highlight/core";
import { grammarFromLabel, highlighter } from "./highlight";

function toElements(nodes: readonly HighlightRenderNode[]): ReactNode {
  return nodes.map((node, index) =>
    node.type === "text" ? (
      <Fragment key={index}>{node.value}</Fragment>
    ) : (
      <span key={index} className={node.classNames.join(" ")}>
        {toElements(node.children)}
      </span>
    )
  );
}

interface CodeBlockProps {
  /** Must stay a string: it is also the value the block's copy button yields. */
  children: string;
  /** Label for the corner notch, which also decides the grammar. */
  language: string;
  className?: string;
}

async function copyText(value: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      return;
    } catch {
      // The API can still reject when the page is not in a secure context.
    }
  }

  const textarea = document.createElement("textarea");
  const previouslyFocused = document.activeElement;
  textarea.value = value;
  textarea.readOnly = true;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();

  try {
    if (!document.execCommand("copy")) throw new Error("Clipboard copy failed");
  } finally {
    textarea.remove();
    if (previouslyFocused instanceof HTMLElement) previouslyFocused.focus();
  }
}

/**
 * `Code.Block` with tokens in its `highlighted` slot. The library's own
 * code-highlight integration takes one prop for both the grammar and the notch
 * label, which would cost us the filenames, so the tokens are rendered here
 * from the same upstream grammars it uses. The `th-` classes they carry are
 * styled globally by the library's stylesheet.
 */
export function CodeBlock({ children, language, className }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);
  const resetTimer = useRef<number>(undefined);
  const highlighted = useMemo(() => {
    const grammar = grammarFromLabel(language);
    if (!grammar) return undefined;
    const { tokens } = highlighter.tokenize(children, { lang: grammar });
    return toElements(renderTokens(tokens));
  }, [children, language]);

  useEffect(() => () => window.clearTimeout(resetTimer.current), []);

  const copy = useCallback(async () => {
    try {
      await copyText(children);
      setCopied(true);
      window.clearTimeout(resetTimer.current);
      resetTimer.current = window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }, [children]);

  return (
    <div className={`landing-code-block${className ? ` ${className}` : ""}`}>
      <Code.Block language={language} hideCopy highlighted={highlighted}>
        {children}
      </Code.Block>
      <Button
        className="landing-code-block__copy"
        variant="secondary"
        size="sm"
        radius="sm"
        aria-label={copied ? "Copied" : "Copy"}
        data-copied={copied || undefined}
        onClick={copy}
      >
        {copied ? <CheckIcon /> : <CopyIcon />}
      </Button>
    </div>
  );
}

function CopyIcon() {
  return (
    <svg viewBox="0 0 24 24" width="12" height="12" aria-hidden="true">
      <rect x="8" y="8" width="14" height="14" rx="2" fill="none" stroke="currentColor" strokeWidth="2" />
      <path d="M16 4a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2" fill="none" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg viewBox="0 0 24 24" width="12" height="12" aria-hidden="true">
      <path d="m20 6-11 11-5-5" fill="none" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}

/* The Perspective Layer — the brand's generative motif. One skewed plane,
   repeatedly rotated and shrunk, builds the rosette; the overlapping
   translucent fills turn the intersections into the shapes of the identity
   system. Kept low-contrast and behind content, never foreground decoration. */

const PLANE: ReadonlyArray<readonly [number, number]> = [
  [-232, -60],
  [232, -104],
  [232, 60],
  [-232, 104],
];

const POINTS = PLANE.map(point => point.join(",")).join(" ");

interface PerspectiveLayersProps {
  /** How many copies of the plane make up the rosette. */
  count: number;
  /** Total rotation, in degrees, spread across those copies. */
  sweep: number;
  /** Per-copy scale factor; below 1 the rosette spirals inward. */
  decay: number;
  /** Seconds for one full revolution. Omit to hold the rosette still. */
  spin?: number;
  /**
   * How far the innermost plane fades out, 0–1. The fade lives here rather than
   * in a CSS `mask-image`: a masked element becomes its own composited layer,
   * and Chrome rasterises that layer with a slightly different colour transform,
   * which bleeds a visible rectangle over whatever it overlaps — through an
   * ancestor's `overflow: hidden`, and even while `visibility: hidden`.
   * Fading per plane also thins the centre, where every plane would otherwise
   * stack its fill into a solid disc.
   */
  fade?: number;
}

export function PerspectiveLayers({
  count,
  sweep,
  decay,
  spin,
  fade = 0.82,
}: PerspectiveLayersProps) {
  const step = sweep / count;
  const last = Math.max(1, count - 1);

  return (
    <svg
      className="layers"
      viewBox="-260 -260 520 520"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
      focusable="false"
    >
      <g className="layers__spin" style={spin ? { animationDuration: `${spin}s` } : undefined}>
        {Array.from({ length: count }, (_, index) => {
          const scale = decay ** index;
          return (
            <polygon
              key={index}
              points={POINTS}
              // Divided by the scale so every ring keeps the same visual weight.
              strokeWidth={(0.9 / scale).toFixed(2)}
              opacity={(1 - fade * (index / last)).toFixed(3)}
              transform={`rotate(${(index * step).toFixed(2)}) scale(${scale.toFixed(4)})`}
            />
          );
        })}
      </g>
    </svg>
  );
}

/* Icons are inline so the page carries no icon dependency of its own; web-ui
   bundles lucide-react for its own internals, which isn't ours to import from. */

export function GitHubMark() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
      <path
        fill="currentColor"
        d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38
           0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01
           1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-2.92-.88-2.92-2.79
           0-.82.29-1.49.77-2.01-.08-.2-.34-1 .07-2.08 0 0 .63-.2 2.06.77a5.6 5.6 0 0 1 1.5-.2c.51 0
           1.02.07 1.5.2 1.43-.97 2.06-.77 2.06-.77.41 1.08.15 1.88.07 2.08.48.52.77 1.19.77
           2.01 0 1.92-1.15 2.59-2.93 2.79.3.26.56.76.56 1.54 0 1.11-.01 2.01-.01 2.29 0
           .21.15.46.55.38A8 8 0 0 0 16 8c0-4.42-3.58-8-8-8Z"
      />
    </svg>
  );
}

export function ArrowRight() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
      <path
        d="M2 8h11M9 4l4 4-4 4"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
