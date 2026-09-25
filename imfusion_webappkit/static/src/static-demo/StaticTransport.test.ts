import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ImFusion } from '@imfusion/sdk';
import type { ServerFrame, Transport, TransportHandlers } from '../transport/types';
import { edgeKey } from './canonical';
import type { DemoManifest } from './manifest';
import { StaticTransport } from './StaticTransport';

const threshold = { action: 'Threshold', inputs: [{ role: 'image', index: 0 }] };

function manifest(): DemoManifest {
  return {
    protocol_version: 7,
    notice: 'Only the recorded interactions work here.',
    config: { title: 'Recorded' } as DemoManifest['config'],
    actions: [{ name: 'Threshold', is_app_only: false } as DemoManifest['actions'][number]],
    handlers: {},
    initial_node: 'n0',
    connect: [
      { type: 'actions', data: { actions: ['Threshold'] } },
      { type: 'data_add', data: { name: 'Sample' }, payload: 'abc' },
    ],
    nodes: {
      n0: {
        id: 'n0',
        selection: [0],
        edges: {
          [edgeKey('execute_action', threshold)]: {
            message: { type: 'execute_action', data: threshold },
            frames: [{ type: 'data_add', data: { name: 'Mask' }, payload: 'def' }],
            target: 'n1',
          },
        },
      },
      n1: { id: 'n1', selection: [1], edges: {} },
    },
  };
}

/** Serve the manifest and its payloads the way a static host would. */
function serve(document: DemoManifest = manifest()) {
  const fetched: string[] = [];
  // Payload URLs are resolved against the page, which vitest does not have.
  vi.stubGlobal('window', { location: { href: 'https://example.test/demo/' } });
  vi.stubGlobal('fetch', vi.fn(async (input: unknown) => {
    const url = String(input);
    fetched.push(url);
    if (url.endsWith('manifest.json')) {
      return { ok: true, status: 200, json: async () => document } as Response;
    }
    return {
      ok: true,
      status: 200,
      arrayBuffer: async () => new Uint8Array([1, 2, 3]).buffer,
    } as Response;
  }));
  return fetched;
}

function collect() {
  const frames: ServerFrame[] = [];
  const unavailable: string[] = [];
  const handlers: TransportHandlers = {
    onOpen: vi.fn(),
    onClose: vi.fn(),
    onError: vi.fn(),
    onFrame: async (frame) => { frames.push(frame); },
    onUnavailable: (message) => { unavailable.push(message); },
  };
  return { frames, handlers, unavailable };
}

/** Let the transport's delivery queue drain. */
const settle = () => new Promise((resolve) => { setTimeout(resolve, 0); });

/** Typed as the interface, so the tests exercise what the client calls. */
function transport(): Transport {
  return new StaticTransport('./fixtures/manifest.json', () => ({} as ImFusion));
}

afterEach(() => vi.unstubAllGlobals());

describe('StaticTransport', () => {
  it('serves the configuration out of the recording', async () => {
    serve();
    expect((await transport().loadConfig()).title).toBe('Recorded');
  });

  it('replays the connect frames, payloads and all', async () => {
    serve();
    const { frames, handlers } = collect();
    const subject = transport();
    subject.connect(handlers);
    await settle();

    expect(frames.map((frame) => frame.type)).toEqual(['actions', 'data_add']);
    expect(frames[0].payload).toBeNull();
    expect(frames[1].payload).toEqual(new Uint8Array([1, 2, 3]));
    expect(handlers.onOpen).toHaveBeenCalledOnce();
  });

  it('follows a recorded edge and answers from the state it reaches', async () => {
    serve();
    const { frames, handlers, unavailable } = collect();
    const subject = transport();
    subject.connect(handlers);
    await settle();
    frames.length = 0;

    expect(subject.send('execute_action', threshold)).toBe(true);
    await settle();
    expect(frames.map((frame) => frame.data.name)).toEqual(['Mask']);

    // n1 has no edges, so the same action is now outside the recording.
    subject.send('execute_action', threshold);
    await settle();
    expect(unavailable).toEqual(['Only the recorded interactions work here.']);
  });

  it('explains itself rather than hanging on an interaction nobody recorded', async () => {
    serve();
    const { handlers, unavailable } = collect();
    const subject = transport();
    subject.connect(handlers);
    await settle();

    subject.send('execute_action', { action: 'Threshold', inputs: [{ role: 'image', index: 9 }] });
    subject.sendBinary('load_data', {}, new Uint8Array([0]));
    expect(unavailable).toHaveLength(2);
  });

  it('accepts the bookkeeping a server would only mirror', async () => {
    serve();
    const { frames, handlers, unavailable } = collect();
    const subject = transport();
    subject.connect(handlers);
    await settle();
    frames.length = 0;

    expect(subject.send('data_removed', { index: 0 })).toBe(true);
    expect(subject.send('selection_changed', { indices: [0] })).toBe(true);
    await settle();
    expect(frames).toEqual([]);
    expect(unavailable).toEqual([]);
  });

  it('speaks up for a message the client is waiting on a reply to', async () => {
    serve();
    const { handlers, unavailable } = collect();
    const subject = transport();
    subject.connect(handlers);
    await settle();

    // Dropping this one the way bookkeeping is dropped would leave the export
    // pending, and the interface busy, for the rest of the visit.
    subject.send('export_data', { request_id: 'r1', format: 'dicom', indices: [0] });
    expect(unavailable).toEqual(['Only the recorded interactions work here.']);
  });

  it('offers its notice so a caller can refuse before it starts', async () => {
    serve();
    const subject = transport();
    expect(subject.notice).toBeUndefined();
    await subject.loadConfig();
    expect(subject.notice).toBe('Only the recorded interactions work here.');
  });

  it('reads each payload from a URL beside the manifest', async () => {
    const fetched = serve();
    const { handlers } = collect();
    const subject = transport();
    subject.connect(handlers);
    await settle();

    expect(fetched.some((url) => url.endsWith('/payloads/abc.bin'))).toBe(true);
  });

  it('reports a recording it cannot read instead of failing silently', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 404 } as Response)));
    const { handlers } = collect();
    transport().connect(handlers);
    await settle();
    expect(handlers.onError).toHaveBeenCalledWith(expect.stringContaining('404'));
  });
});
