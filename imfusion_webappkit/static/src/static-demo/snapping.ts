/**
 * Keep a parameter control on the values a recording can answer for.
 *
 * A recorded action holds only the results it was built with, so a control that
 * accepted anything else would lead somewhere the demo cannot go. The control
 * the application declared is kept as it is, and the value it produces is moved
 * onto the nearest recorded one instead.
 *
 * `_restrict` in `imfusion_webappkit/static_demo/recorder.py` is the other half:
 * it publishes the recorded values and makes sure the control opens on one of
 * them, so a visitor who presses the button without touching anything also
 * reaches a recorded result.
 */

export type Recordable = boolean | number | string;

export function snapToRecorded(value: unknown, allowed: readonly Recordable[]): unknown {
  if (!allowed.length || allowed.includes(value as Recordable)) return value;
  const numbers = allowed.filter(
    (candidate): candidate is number => typeof candidate === 'number',
  );
  if (typeof value === 'number' && Number.isFinite(value) && numbers.length) {
    return numbers.reduce((best, candidate) => (
      Math.abs(candidate - value) < Math.abs(best - value) ? candidate : best
    ));
  }
  return allowed[0];
}

/** What the field says about itself, beneath its label. */
export function recordedHint(allowed: readonly Recordable[]): string {
  if (allowed.length === 1) return `Recorded at ${allowed[0]}`;
  if (allowed.length <= 6) return `Recorded: ${allowed.join(', ')}`;
  return `${allowed.length} recorded values`;
}
