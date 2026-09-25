import type { Annotation as SdkAnnotation, MainModule } from '@imfusion/sdk';

/** One annotation as the server describes it, for panels and parameter fields. */
export interface AnnotationDescriptor {
  id: string;
  type: string;
  name: string;
  label: string;
  /** What this annotation is for, when a step collects several in sequence. */
  prompt?: string;
  points: number[][];
  max_points: number | null;
  complete: boolean;
  editing: boolean;
  error: string;
  length: number | null;
  angle: number | null;
}

/**
 * Read an annotation's control points out of its state.
 *
 * The Properties bridge serializes a `vector<vec3>` as a flat array of numeric
 * *strings* with `'\n'` separators — unlike `color` or `xAxis`, which arrive as
 * plain numbers — so this is the only place in the client that knows the shape.
 * A leftover partial triple means the format changed and is reported rather
 * than truncated, because silently dropping a coordinate would look like a
 * misplaced annotation.
 */
export function parseAnnotationPoints(state: Record<string, unknown>): number[][] {
  const raw = state.points;
  if (!Array.isArray(raw)) return [];
  const numbers = raw
    .filter((token) => typeof token !== 'string' || token.trim() !== '')
    .map((token) => Number(token));
  if (numbers.some((value) => !Number.isFinite(value))) {
    throw new Error('Annotation points contain a value that is not a number');
  }
  if (numbers.length % 3 !== 0) {
    throw new Error(`Annotation points do not group into triples (${numbers.length} values)`);
  }
  const points: number[][] = [];
  for (let index = 0; index < numbers.length; index += 3) {
    points.push(numbers.slice(index, index + 3));
  }
  return points;
}

/** Write points back in the form `state()` reports them. */
export function serializeAnnotationPoints(points: number[][]): string[] {
  return points.flatMap((point) => [...point.map((value) => String(value)), '\n']);
}

export function annotationMaxPoints(state: Record<string, unknown>): number | null {
  const value = Number(state.maxPoints);
  return Number.isInteger(value) && value > 0 ? value : null;
}

/**
 * Whether this SDK build can create `type`.
 *
 * Embind resolves an enum argument by string lookup and throws a `TypeError`
 * for one it does not know, so an unsupported type has to be caught before
 * `add()` rather than after. This is what lets the server offer annotation
 * types that only newer SDK builds bind.
 */
export function supportsAnnotationType(bindings: MainModule, type: string): boolean {
  const known = bindings.AnnotationType as unknown as Record<string, string> | undefined;
  return Boolean(known && type in known);
}

/** Round a world point for display, in the millimetres the SDK works in. */
export function formatPoint(point: number[]): string {
  return point.map((value) => value.toFixed(1)).join(', ');
}

export function annotationStateColor(color: readonly number[]): number[] {
  return color.length === 3 ? [...color, 1] : [...color];
}

export type { SdkAnnotation };
