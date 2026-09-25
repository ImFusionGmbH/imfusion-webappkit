import { describe, expect, it } from 'vitest';
import { recordedHint, snapToRecorded } from './snapping';

describe('snapToRecorded', () => {
  it('leaves a recorded value alone', () => {
    expect(snapToRecorded(100, [50, 100, 200])).toBe(100);
  });

  it('moves a number to the nearest recorded one', () => {
    expect(snapToRecorded(120, [50, 100, 200])).toBe(100);
    expect(snapToRecorded(160, [50, 100, 200])).toBe(200);
    expect(snapToRecorded(-5, [50, 100, 200])).toBe(50);
  });

  it('breaks a tie towards the lower value, as reduce reaches it first', () => {
    expect(snapToRecorded(75, [50, 100])).toBe(50);
  });

  it('falls back to the first value when nearness means nothing', () => {
    expect(snapToRecorded('sobel', ['gaussian', 'median'])).toBe('gaussian');
    expect(snapToRecorded(true, [false])).toBe(false);
    expect(snapToRecorded(Number.NaN, [50, 100])).toBe(50);
  });

  it('accepts anything when nothing was recorded', () => {
    expect(snapToRecorded(3.5, [])).toBe(3.5);
  });
});

describe('recordedHint', () => {
  it('names a single value, lists a few, and counts many', () => {
    expect(recordedHint([100])).toBe('Recorded at 100');
    expect(recordedHint([50, 100, 200])).toBe('Recorded: 50, 100, 200');
    expect(recordedHint([1, 2, 3, 4, 5, 6, 7])).toBe('7 recorded values');
  });
});
