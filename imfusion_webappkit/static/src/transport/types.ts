import type { AppConfig } from '../types';

/** One decoded server message, with its binary payload if it had one. */
export interface ServerFrame {
  type: string;
  data: Record<string, any>;
  payload: Uint8Array | null;
}

export interface TransportHandlers {
  onOpen(message: string): void;
  onClose(message: string): void;
  onError(message: string): void;
  /**
   * Deliver one frame. The returned promise settles once the client has finished
   * acting on it, which a transport replaying a recording awaits so it does not
   * run ahead of the viewer.
   */
  onFrame(frame: ServerFrame): Promise<void>;
  /** An interaction this transport cannot answer at all. */
  onUnavailable(message: string): void;
}

/**
 * The client's whole dependency on a server.
 *
 * There are exactly two touchpoints — the configuration fetched on start-up and
 * the message stream — so naming them as an interface is what lets the same
 * bundle run against a Python process or against a recording of one.
 */
export interface Transport {
  /** True when answers come from a recording rather than a running server. */
  readonly recorded: boolean;
  /** Why an interaction may go unanswered, for a transport that has such a limit. */
  readonly notice?: string;
  loadConfig(): Promise<AppConfig>;
  connect(handlers: TransportHandlers): void;
  send(type: string, data?: Record<string, unknown>): boolean;
  sendBinary(type: string, data: Record<string, unknown>, bytes: Uint8Array): boolean;
  close(): void;
}
