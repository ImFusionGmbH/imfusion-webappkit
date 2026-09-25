/**
 * Answer the client from a recording instead of a Python process.
 *
 * The recording is a graph: nodes are states the client can be in, edges are the
 * messages that move between them together with the frames the server replied
 * with. Replaying a graph rather than a transcript is what lets a visitor click
 * in their own order, go back, and repeat an action, instead of retracing the
 * path whoever built the demo happened to take.
 */

import type { ImFusion } from '@imfusion/sdk';
import type { AppConfig } from '../types';
import type { ServerFrame, Transport, TransportHandlers } from '../transport/types';
import { RECORDABLE_MESSAGE_TYPES, edgeKey } from './canonical';
import { demoHandlers, type HandlerRequest } from './handlers';
import type { DemoManifest, RecordedFrame } from './manifest';

/**
 * Messages the client waits on a reply to.
 *
 * These cannot be dropped the way bookkeeping can. The control that sent one
 * shows itself busy until the answer arrives, so silence here leaves it busy
 * for the rest of the visit.
 */
const AWAITED_MESSAGE_TYPES = new Set(['export_data']);

export class StaticTransport implements Transport {
  readonly recorded = true;

  private handlers: TransportHandlers | null = null;

  private manifest: DemoManifest | null = null;

  private pending: Promise<DemoManifest> | null = null;

  private node = '';

  /** Serializes delivery so one reply is fully applied before the next starts. */
  private queue: Promise<void> = Promise.resolve();

  private appOnlyActions: ReadonlySet<string> = new Set();

  private jobs = 0;

  private closed = false;

  constructor(
    private readonly url: string,
    private readonly imf: () => ImFusion,
  ) {}

  get notice(): string | undefined {
    return this.manifest?.notice;
  }

  private load(): Promise<DemoManifest> {
    this.pending ??= fetch(this.url).then(async (response) => {
      if (!response.ok) {
        throw new Error(`This demo's recording is missing (${response.status})`);
      }
      const manifest = await response.json() as DemoManifest;
      this.manifest = manifest;
      this.appOnlyActions = new Set(
        manifest.actions.filter((action) => action.is_app_only).map((action) => action.name),
      );
      return manifest;
    });
    return this.pending;
  }

  async loadConfig(): Promise<AppConfig> {
    return (await this.load()).config;
  }

  connect(handlers: TransportHandlers): void {
    this.handlers = handlers;
    this.load().then(
      (manifest) => {
        if (this.closed) return;
        this.node = manifest.initial_node;
        handlers.onOpen('Recorded demo — no server behind this page');
        this.enqueue(() => this.deliver(manifest.connect));
      },
      (error: unknown) => {
        handlers.onError(error instanceof Error ? error.message : String(error));
      },
    );
  }

  send(type: string, data: Record<string, unknown> = {}): boolean {
    const manifest = this.manifest;
    const handlers = this.handlers;
    if (!manifest || !handlers || this.closed) return false;

    if (type === 'selection_changed') {
      this.checkSelection(data.indices as number[] | undefined);
      return true;
    }
    // Everything else outside the recording is client-authoritative bookkeeping
    // the server would only mirror, so dropping it keeps the viewer usable.
    if (!RECORDABLE_MESSAGE_TYPES.has(type)) {
      if (AWAITED_MESSAGE_TYPES.has(type)) handlers.onUnavailable(manifest.notice);
      return true;
    }

    if (type === 'execute_action') {
      const handler = manifest.handlers[String(data.action)];
      if (handler) {
        this.enqueue(() => this.runHandler(handler, data as unknown as HandlerRequest));
        return true;
      }
    }

    const edge = manifest.nodes[this.node]?.edges[
      edgeKey(type, data, this.appOnlyActions)
    ];
    if (!edge) {
      handlers.onUnavailable(manifest.notice);
      return true;
    }
    // The state advances now, in the order the messages arrived, exactly as a
    // server would advance it; only delivering the reply is queued.
    this.node = edge.target;
    this.enqueue(() => this.deliver(edge.frames));
    return true;
  }

  sendBinary(type: string): boolean {
    this.handlers?.onUnavailable(
      this.manifest?.notice
      ?? 'This page is a recorded demo and cannot answer that interaction.',
    );
    // Binary messages carry data the visitor produced here — a loaded file or a
    // brush stroke — which no recording can have an answer for.
    void type;
    return true;
  }

  close(): void {
    // Nothing to report: closing is the client's own doing, and a recording has
    // no connection that could drop on its own.
    this.closed = true;
  }

  private enqueue(work: () => Promise<void>): void {
    this.queue = this.queue.then(work).catch((error: unknown) => {
      this.handlers?.onError(error instanceof Error ? error.message : String(error));
    });
  }

  private async deliver(frames: RecordedFrame[]): Promise<void> {
    for (const frame of frames) {
      if (this.closed) return;
      await this.handlers!.onFrame({
        type: frame.type,
        data: frame.data,
        payload: frame.payload ? await this.payload(frame.payload) : null,
      });
    }
  }

  private async payload(name: string): Promise<Uint8Array> {
    const response = await fetch(new URL(`payloads/${name}.bin`, new URL(this.url, window.location.href)));
    if (!response.ok) {
      throw new Error(`A recorded result is missing from this demo (${response.status})`);
    }
    return new Uint8Array(await response.arrayBuffer());
  }

  /**
   * Run an action in the browser and answer with the exchange the server would
   * have produced. The client turns busy the moment the button is pressed, so
   * every path here has to end in a message that closes the job.
   */
  private async runHandler(name: string, request: HandlerRequest): Promise<void> {
    const handler = demoHandlers[name];
    const job = {
      job_id: `demo-${(this.jobs += 1)}`,
      kind: 'action',
      label: request.action || 'Operation',
      status: 'running',
      progress: 0,
    };
    await this.frame('job_started', job);
    try {
      if (!handler) throw new Error(`This demo asks for an unknown handler: ${name}`);
      const result = handler(this.imf(), request);
      await this.frame(
        'data_add',
        { format: 'imf', name: result.name, index: result.index },
        result.payload,
      );
      await this.frame('job_result', {
        ...job,
        status: 'succeeded',
        result: { operation: job.label, outputs: 1 },
      });
    } catch (error: unknown) {
      await this.frame('job_failed', {
        ...job,
        status: 'failed',
        error: {
          code: 'operation_failed',
          message: error instanceof Error ? error.message : String(error),
          recoverable: true,
        },
      });
    }
  }

  private frame(
    type: string,
    data: Record<string, unknown>,
    payload: Uint8Array | null = null,
  ): Promise<void> {
    return this.handlers!.onFrame({ type, data, payload } as ServerFrame);
  }

  /**
   * Compare what the client is showing against what it was showing when this
   * state was recorded. A recorded result was computed with the selection the
   * recorder believed the client would have, and a workflow step can read that
   * selection, so a lasting disagreement means the two models of the client have
   * drifted apart. Changing visibility by hand also trips this, which is why it
   * only reaches the console.
   */
  private checkSelection(indices: number[] | undefined): void {
    const expected = this.manifest?.nodes[this.node]?.selection;
    if (!expected || !indices) return;
    if (expected.length === indices.length
      && expected.every((value, position) => value === indices[position])) {
      return;
    }
    console.warn(
      `Static demo: showing [${indices}] at ${this.node}, recorded as [${expected}]. `
      + 'Recorded results assume the latter.',
    );
  }
}
