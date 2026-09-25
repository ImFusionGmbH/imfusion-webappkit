/**
 * Check the TypeScript half of the canonical key against the shared table.
 *
 * The recorder writes edge keys and this side looks them up, so the two
 * implementations have to agree character for character. `canonical.py` is
 * checked against the same fixture by `tests/test_static_demo_canonical.py`, so
 * a change to either one that the other does not follow fails here.
 */

import { describe, expect, it } from 'vitest';
import { canonicalJson, edgeKey } from './canonical';
import cases from './edgeKeys.fixture.json';

describe('edgeKey', () => {
  it.each(cases)('$name', ({ type, data, app_only: appOnly, key }) => {
    expect(edgeKey(type, data, new Set(appOnly))).toBe(key);
  });

  it('refuses a message the recorder never writes an edge for', () => {
    expect(() => edgeKey('selection_changed', { indices: [0] })).toThrow(/cannot be recorded/);
  });
});

describe('canonicalJson', () => {
  it('sorts keys at every depth', () => {
    expect(canonicalJson({ b: 1, a: [2, { d: 4, c: 3 }] })).toBe('{"a":[2,{"c":3,"d":4}],"b":1}');
  });
});
