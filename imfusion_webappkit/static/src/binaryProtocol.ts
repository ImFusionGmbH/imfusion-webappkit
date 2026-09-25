export interface BinaryMessage<T = Record<string, unknown>> {
  type: string;
  data: T;
  payload: Uint8Array;
}

const encoder = new TextEncoder();
const decoder = new TextDecoder();

export function encodeBinaryMessage(
  type: string,
  data: Record<string, unknown>,
  payload: Uint8Array,
): ArrayBuffer {
  const header = encoder.encode(JSON.stringify({ type, data }));
  const frame = new Uint8Array(4 + header.length + payload.length);
  new DataView(frame.buffer).setUint32(0, header.length, false);
  frame.set(header, 4);
  frame.set(payload, 4 + header.length);
  return frame.buffer;
}

export function decodeBinaryMessage<T = Record<string, unknown>>(
  frame: ArrayBuffer,
): BinaryMessage<T> {
  if (frame.byteLength < 4) throw new Error('Binary message is missing its header length');
  const headerLength = new DataView(frame).getUint32(0, false);
  const payloadOffset = 4 + headerLength;
  if (!headerLength || payloadOffset > frame.byteLength) {
    throw new Error('Binary message has an invalid header length');
  }

  const header = JSON.parse(
    decoder.decode(new Uint8Array(frame, 4, headerLength)),
  ) as { type?: unknown; data?: T };
  if (typeof header.type !== 'string' || !header.type) {
    throw new Error('Binary message is missing its type');
  }
  return {
    type: header.type,
    data: header.data ?? ({} as T),
    payload: new Uint8Array(frame, payloadOffset),
  };
}
