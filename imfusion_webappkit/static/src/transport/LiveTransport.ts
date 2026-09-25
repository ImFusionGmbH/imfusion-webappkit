import { decodeBinaryMessage, encodeBinaryMessage } from '../binaryProtocol';
import type { AppConfig, ServerMessage } from '../types';
import type { ServerFrame, Transport, TransportHandlers } from './types';

/** Talks to the Python process that serves the page. */
export class LiveTransport implements Transport {
  readonly recorded = false;

  private socket: WebSocket | null = null;

  /** Orders decoding, which is asynchronous for a payload arriving as a Blob. */
  private incoming: Promise<void> = Promise.resolve();

  async loadConfig(): Promise<AppConfig> {
    const response = await fetch('/config');
    if (!response.ok) {
      throw new Error(`Configuration request failed (${response.status})`);
    }
    return await response.json() as AppConfig;
  }

  connect(handlers: TransportHandlers): void {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const socket = new WebSocket(`${protocol}//${window.location.host}/ws`);
    socket.binaryType = 'arraybuffer';
    this.socket = socket;

    socket.onopen = () => handlers.onOpen('Connected to Python server');
    socket.onclose = () => handlers.onClose('Disconnected from Python server');
    socket.onerror = () => handlers.onError('WebSocket connection error');
    socket.onmessage = (event: MessageEvent) => {
      this.incoming = this.incoming
        .then(async () => {
          await handlers.onFrame(await decode(event.data));
        })
        .catch((error: unknown) => {
          handlers.onError(error instanceof Error ? error.message : String(error));
        });
    };
  }

  send(type: string, data: Record<string, unknown> = {}): boolean {
    if (this.socket?.readyState !== WebSocket.OPEN) return false;
    this.socket.send(JSON.stringify({ type, data }));
    return true;
  }

  sendBinary(
    type: string,
    data: Record<string, unknown>,
    bytes: Uint8Array,
  ): boolean {
    if (this.socket?.readyState !== WebSocket.OPEN) return false;
    this.socket.send(encodeBinaryMessage(type, data, bytes));
    return true;
  }

  close(): void {
    const socket = this.socket;
    this.socket = null;
    socket?.close();
  }
}

async function decode(data: unknown): Promise<ServerFrame> {
  if (typeof data === 'string') {
    const parsed = JSON.parse(data) as ServerMessage<any>;
    return { type: parsed.type, data: parsed.data ?? {}, payload: null };
  }
  const buffer = data instanceof ArrayBuffer
    ? data
    : await (data as Blob).arrayBuffer();
  const binary = decodeBinaryMessage<any>(buffer);
  return { type: binary.type, data: binary.data, payload: binary.payload };
}
