import type { ActionDescriptor, AppConfig } from '../types';

/** A recorded server message. `payload` names a file under `payloads/`. */
export interface RecordedFrame {
  type: string;
  data: Record<string, any>;
  payload?: string;
}

/** One client message and the reply it produced while recording. */
export interface RecordedEdge {
  message: { type: string; data: Record<string, unknown> };
  frames: RecordedFrame[];
  target: string;
}

/** One state the client can be in, and the ways out of it. */
export interface RecordedNode {
  id: string;
  selection: number[];
  edges: Record<string, RecordedEdge>;
}

export interface DemoManifest {
  protocol_version: number;
  /** Shown when the visitor reaches an interaction nobody recorded. */
  notice: string;
  config: AppConfig;
  actions: ActionDescriptor[];
  /** Action name to the client-side handler that recomputes it here. */
  handlers: Record<string, string>;
  initial_node: string;
  connect: RecordedFrame[];
  nodes: Record<string, RecordedNode>;
}

export const MANIFEST_META_NAME = 'imfusion-static-demo';

/**
 * The manifest URL a recorded build writes into its own `index.html`, or null
 * when the page is served by Python. Reading a tag rather than probing for the
 * file keeps a live deployment from making a request that always fails.
 */
export function manifestUrl(): string | null {
  const meta = document.querySelector<HTMLMetaElement>(
    `meta[name="${MANIFEST_META_NAME}"]`,
  );
  return meta?.content || null;
}
