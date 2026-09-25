/**
 * Check the reading of annotation geometry out of the SDK's Properties bridge.
 *
 * `state().points` is the one field the client parses by hand, because it
 * arrives as flat numeric strings with newline separators rather than as the
 * plain numbers every other vector field uses. If that format changes, these
 * fail instead of the viewer quietly showing a misplaced annotation.
 */

import { describe, expect, it } from 'vitest';
import type { MainModule } from '@imfusion/sdk';
import {
  annotationMaxPoints,
  parseAnnotationPoints,
  serializeAnnotationPoints,
  supportsAnnotationType,
} from './annotations';

describe('parseAnnotationPoints', () => {
  it('groups the flat string array into triples', () => {
    const state = {
      points: ['-39.58', '-43.94', '-40.22', '\n', '39.21', '33.53', '-40.22', '\n'],
    };
    expect(parseAnnotationPoints(state)).toEqual([
      [-39.58, -43.94, -40.22],
      [39.21, 33.53, -40.22],
    ]);
  });

  it('reads an annotation the user has not started yet as empty', () => {
    expect(parseAnnotationPoints({ points: [] })).toEqual([]);
    expect(parseAnnotationPoints({})).toEqual([]);
  });

  it('refuses a partial triple rather than truncating it', () => {
    expect(() => parseAnnotationPoints({ points: ['1', '2'] })).toThrow(/triples/);
  });

  it('refuses a coordinate that is not a number', () => {
    expect(() => parseAnnotationPoints({ points: ['1', 'nope', '3'] })).toThrow(/not a number/);
  });

  it('round-trips through the serializer', () => {
    const points = [
      [1, 2, 3],
      [4, 5, 6],
    ];
    expect(parseAnnotationPoints({ points: serializeAnnotationPoints(points) })).toEqual(points);
  });
});

describe('annotationMaxPoints', () => {
  it('reads the count the SDK reports for the shape', () => {
    expect(annotationMaxPoints({ maxPoints: 2 })).toBe(2);
    expect(annotationMaxPoints({ maxPoints: '3' })).toBe(3);
  });

  it('reports an unbounded or absent count as null', () => {
    expect(annotationMaxPoints({ maxPoints: 0 })).toBeNull();
    expect(annotationMaxPoints({ maxPoints: -1 })).toBeNull();
    expect(annotationMaxPoints({})).toBeNull();
  });
});

describe('supportsAnnotationType', () => {
  const bindings = {
    AnnotationType: { LineSegment: 0, Rectangle: 1, Angle: 2 },
  } as unknown as MainModule;

  it('accepts a type this build binds', () => {
    expect(supportsAnnotationType(bindings, 'Rectangle')).toBe(true);
  });

  it('rejects a type this build does not bind, before embind throws', () => {
    expect(supportsAnnotationType(bindings, 'Box')).toBe(false);
  });

  it('rejects everything when the enum itself is missing', () => {
    expect(supportsAnnotationType({} as MainModule, 'Rectangle')).toBe(false);
  });
});
