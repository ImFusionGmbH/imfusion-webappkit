import { describe, expect, it } from 'vitest';
import {
  base64ToBytes,
  bytesToBase64,
  reconcileDataOrder,
  resultDataName,
  selectedDataIndices,
} from './protocol';

describe('IMF transport helpers', () => {
  it('round-trips binary payloads larger than one conversion chunk', () => {
    const input = Uint8Array.from({ length: 20_000 }, (_, index) => index % 251);
    expect(base64ToBytes(bytesToBase64(input))).toEqual(input);
  });
});

describe('selectedDataIndices', () => {
  it('uses object identity and ignores unknown datasets', () => {
    const first = { name: 'first' };
    const second = { name: 'second' };
    expect(selectedDataIndices([first, second], [second, { name: 'missing' }, first])).toEqual([1, 0]);
  });

  it('matches separate handles that alias the same SDK dataset', () => {
    const dataset = { id: 7, isAliasOf(other: { id?: number }) { return other.id === this.id; } };
    const alias = { id: 7, isAliasOf(other: { id?: number }) { return other.id === this.id; } };
    expect(selectedDataIndices([dataset], [alias])).toEqual([0]);
  });
});

describe('reconcileDataOrder', () => {
  it('preserves logical ordering while filtering removals and appending additions', () => {
    const first = { name: 'first' };
    const second = { name: 'second' };
    const replacement = { name: 'replacement' };
    expect(
      reconcileDataOrder(
        [first, replacement, second],
        [first, second, replacement],
      ),
    ).toEqual([first, replacement, second]);
  });

  it('matches alias handles when reconciling SDK data', () => {
    const preferred = { id: 7, isAliasOf(other: { id?: number }) { return other.id === this.id; } };
    const actual = { id: 7, isAliasOf(other: { id?: number }) { return other.id === this.id; } };
    expect(reconcileDataOrder([preferred], [actual])).toEqual([preferred]);
  });
});

describe('resultDataName', () => {
  it('combines the source data and a readable operation name', () => {
    expect(resultDataName('Sample Image', 'Base.MorphologicalOperations')).toBe(
      'Sample Image — Morphological Operations',
    );
  });
});
