import type { ImFusion } from '@imfusion/sdk';
import { StaticTransport } from '../static-demo/StaticTransport';
import { manifestUrl } from '../static-demo/manifest';
import { LiveTransport } from './LiveTransport';
import type { Transport } from './types';

export type { ServerFrame, Transport, TransportHandlers } from './types';
export { LiveTransport } from './LiveTransport';

/**
 * Choose how this page reaches its results.
 *
 * A recorded build declares its manifest in `index.html`; anything else is
 * served by Python and talks to it over a WebSocket.
 */
export function createTransport(imf: () => ImFusion): Transport {
  const url = manifestUrl();
  return url ? new StaticTransport(url, imf) : new LiveTransport();
}
