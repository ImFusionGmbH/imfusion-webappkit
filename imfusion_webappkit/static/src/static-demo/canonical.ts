/**
 * Canonical keys for the client messages that drive a recorded demo.
 *
 * The recording is keyed by the message that caused each transition, so the key
 * computed here has to match the one the recorder wrote character for character.
 * Both sides apply the same two rules: reduce the payload to the part the server
 * actually reads, then serialize it with sorted keys.
 * `imfusion_webappkit/static_demo/canonical.py` is the other half of this pair,
 * and `tests/test_static_demo_canonical.py` checks they still agree.
 */

/**
 * Messages that change server state, and so appear in the recording. Everything
 * else the client sends is bookkeeping the server only mirrors.
 */
export const RECORDABLE_MESSAGE_TYPES = new Set([
  'execute_action',
  'workflow_next',
  'workflow_back',
  'workflow_run',
  'workflow_step_data',
  'annotation_event',
  'annotation_created',
]);

function withSortedKeys(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(withSortedKeys);
  if (value !== null && typeof value === 'object') {
    const source = value as Record<string, unknown>;
    const sorted: Record<string, unknown> = {};
    for (const key of Object.keys(source).sort()) {
      sorted[key] = withSortedKeys(source[key]);
    }
    return sorted;
  }
  return value;
}

export function canonicalJson(value: unknown): string {
  return JSON.stringify(withSortedKeys(value));
}

interface InputReferencePayload {
  role?: unknown;
  index?: unknown;
}

/** Return the part of a client message that determines the server's reply. */
export function normalizeMessage(
  type: string,
  data: Record<string, unknown> = {},
  appOnlyActions: ReadonlySet<string> = new Set(),
): Record<string, unknown> {
  if (type === 'execute_action') {
    const action = data.action;
    const normalized: Record<string, unknown> = { action };
    if (!appOnlyActions.has(String(action))) {
      const references: InputReferencePayload[] = Array.isArray(data.inputs)
        ? data.inputs as InputReferencePayload[]
        // `executeAction` falls back to the current viewer selection when the
        // caller passes no explicit roles.
        : ((data.indices ?? []) as number[]).map((index, position) => ({
          role: String(position),
          index,
        }));
      normalized.inputs = references
        .map((reference) => ({ role: String(reference.role), index: reference.index }))
        .sort((first, second) => (first.role < second.role ? -1 : first.role > second.role ? 1 : 0));
    }
    // An app-only action ignores inputs entirely, and the selection the client
    // would attach to it changes with every click.
    const parameters = data.parameters as Record<string, unknown> | undefined;
    if (parameters && Object.keys(parameters).length) normalized.parameters = parameters;
    return normalized;
  }

  if (type === 'workflow_run') {
    return data.action === undefined || data.action === null ? {} : { action: data.action };
  }

  if (type === 'workflow_step_data') {
    return { data: (data.data ?? {}) as Record<string, unknown> };
  }

  if (type === 'annotation_event') {
    // `points` and `max_points` are deliberately dropped. A recorded demo is
    // replayed by someone who drags somewhere slightly different from whoever
    // recorded it, so keying on the geometry would make every annotation
    // interaction miss its edge and dead-end the demo. Without them the demo
    // replays the recorded outcome for any placement, which is the honest
    // behaviour for something canned.
    return { event: data.event };
  }

  if (type === 'annotation_created') {
    return { type: data.type };
  }

  if (type === 'workflow_next' || type === 'workflow_back') return {};

  throw new Error(`Message type cannot be recorded: ${type}`);
}

/** Return the graph key for one client message. */
export function edgeKey(
  type: string,
  data: Record<string, unknown> = {},
  appOnlyActions: ReadonlySet<string> = new Set(),
): string {
  return canonicalJson({ type, data: normalizeMessage(type, data, appOnlyActions) });
}
