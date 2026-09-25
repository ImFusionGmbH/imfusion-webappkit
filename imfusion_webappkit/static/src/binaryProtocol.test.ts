import { describe, expect, it } from 'vitest';
import { decodeBinaryMessage, encodeBinaryMessage } from './binaryProtocol';

describe('binary WebSocket protocol', () => {
  it('round-trips metadata and raw IMF bytes', () => {
    const payload = Uint8Array.from({ length: 20_000 }, (_, index) => index % 251);

    const decoded = decodeBinaryMessage(encodeBinaryMessage(
      'data_loaded',
      { format: 'imf', names: ['First', 'Second'] },
      payload,
    ));

    expect(decoded.type).toBe('data_loaded');
    expect(decoded.data).toEqual({ format: 'imf', names: ['First', 'Second'] });
    expect(decoded.payload).toEqual(payload);
  });

  it('rejects truncated headers', () => {
    expect(() => decodeBinaryMessage(new Uint8Array([0, 0, 0, 8, 123]).buffer))
      .toThrow('invalid header length');
  });
});
