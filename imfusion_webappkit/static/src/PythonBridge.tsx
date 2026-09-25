import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import type { Annotation, Data, ImFusion, SharedImageSet } from '@imfusion/sdk';
import {
  useData,
  useDataLoader,
  useImFusion,
  useVisibleData,
} from '@imfusion/sdk-react';
import {
  defaultConfig,
  type ActionDescriptor,
  type AlgorithmInfo,
  type AppConfig,
  type BusyState,
  type ConnectionStatus,
  type ControllerStatus,
  type ExportFormat,
  type InputReference,
  type JobState,
  type SampleDataset,
  type ThemeConfig,
  type WorkflowState,
} from './types';
import {
  annotationMaxPoints,
  annotationStateColor,
  parseAnnotationPoints,
  serializeAnnotationPoints,
  supportsAnnotationType,
} from './annotations';
import {
  base64ToBytes,
  reconcileDataOrder,
  selectedDataIndices,
} from './protocol';
import {
  createTransport,
  type ServerFrame,
  type Transport,
} from './transport';

interface BridgeValue {
  imf: ImFusion;
  config: AppConfig;
  data: Data[];
  visibleData: Data[];
  status: ConnectionStatus;
  message: string;
  progress: number | null;
  algorithms: AlgorithmInfo[];
  controllers: ControllerStatus[];
  workflow: WorkflowState | null;
  activeJob: JobState | null;
  /** Every reason the client and the server are currently out of step. */
  busy: BusyState;
  isLoading: boolean;
  loadProgress: { received: number; total: number | null } | null;
  /** True when results are replayed from a recording rather than computed. */
  recorded: boolean;
  /** Set when an interaction has no recorded answer. */
  notice: string | null;
  dismissNotice(): void;
  /**
   * Explain and refuse, if this transport can never take an import.
   *
   * The load functions call this themselves; a control calls it to avoid
   * offering a dialog that has nothing behind it.
   */
  importUnavailable(): boolean;
  loadFile(file: File): Promise<void>;
  loadFiles(files: File[]): Promise<void>;
  loadSampleDataset(dataset: SampleDataset): Promise<void>;
  executeAction(
    name: string,
    inputs?: InputReference[],
    parameters?: Record<string, unknown>,
  ): void;
  discoverAlgorithms(inputs: InputReference[]): void;
  executeAlgorithm(id: string, parameters: Record<string, unknown>, inputs: InputReference[]): void;
  checkController(name: string, inputs: InputReference[]): void;
  executeController(name: string, parameters: Record<string, unknown>, inputs: InputReference[]): void;
  removeData(item: Data): void;
  setVisibleData(items: Data[]): void;
  exportAll(format?: ExportFormat): Promise<boolean>;
  sendWorkflowData(data: Record<string, unknown>): void;
  commitBrush(
    labelMap: Data,
    targetIndex: number | null,
  ): Promise<{ success: boolean; index?: number; message?: string }>;
  loadSnapshot(snapshot: Uint8Array, name: string): Promise<Data>;
  swapLocalData(stale: Data, replacement: Data): void;
  /**
   * Let the user draw an annotation the server did not ask for.
   *
   * For the sidebar panel. Workflow steps and action parameters get their
   * annotations from the server, which names them; here the client does, and
   * tells the server about it once the geometry exists.
   *
   * @returns The new annotation's id, or null when this SDK build cannot make
   * that shape.
   */
  createAnnotation(type: string, parent: Data): string | null;
  removeAnnotation(id: string): void;
  /** Annotations the client currently holds, newest last. */
  annotations: ClientAnnotation[];
  workflowNext(): void;
  workflowBack(): void;
  workflowRun(action?: string): void;
  cancelJob(): void;
}

/** An annotation the client is tracking, with what the panels need to show it. */
export interface ClientAnnotation {
  id: string;
  type: string;
  /** Index of the parent dataset, or -1 once the dataset has gone. */
  dataIndex: number;
  dataName: string;
  points: number[][];
  complete: boolean;
  /** True while the SDK is waiting for the user to place points. */
  editing: boolean;
  /** How the SDK's creation mode ended, or null while it has not.
   *
   *  Point counts cannot stand in for this. A rectangle reaches its last
   *  point while the drag is still going, and an aborted annotation looks
   *  exactly like one that has not been drawn yet, because the SDK clears its
   *  points. Anything waiting for a placement has to wait for the event. */
  creation: 'finished' | 'aborted' | null;
}

const PythonBridgeContext = createContext<BridgeValue | null>(null);

/** Loosest rate at which a drag on the canvas turns into WebSocket traffic. */
const MODIFIED_EVENT_INTERVAL_MS = 100;

/** Save a base64 payload from the server to the visitor's downloads. */
function downloadBuffer(encoded: string, filename: string, mediaType?: string) {
  const bytes = base64ToBytes(encoded);
  const blob = new Blob(
    [bytes.buffer as ArrayBuffer],
    { type: mediaType ?? 'application/octet-stream' },
  );
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

/** One unit of work the client is waiting on, feeding `BridgeValue.busy`. */
interface SyncTask {
  id: string;
  label: string;
  detail: string | null;
  blocking: boolean;
}

const newRequestId = () => crypto.randomUUID?.()
  ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;

/** Fixed, because the frame that ends this task carries no request of its own. */
const initialSyncTaskId = 'initial-sync';

/**
 * Resolve after the browser has had a chance to paint.
 *
 * Two frames, because the first only guarantees that the style and layout from
 * the pending state update have been computed; the second runs once they have
 * actually been put on screen.
 */
const nextPaint = () => new Promise<void>((resolve) => {
  requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
});

const idleBusy: BusyState = {
  active: false,
  blocking: false,
  label: '',
  detail: null,
  progress: null,
};

const themeVariables: Array<[keyof Omit<ThemeConfig, 'preset'>, string[]]> = [
  ['primary', ['--color-primary', '--accent-color']],
  ['primary_hover', ['--color-primary-hover', '--accent-color-hover']],
  ['secondary', ['--color-secondary']],
  ['background', ['--bg-primary']],
  ['surface', ['--bg-secondary']],
  ['surface_raised', ['--bg-tertiary']],
  ['surface_high', ['--bg-quaternary']],
  ['text', ['--text-primary']],
  ['text_muted', ['--text-secondary']],
  ['text_subtle', ['--text-tertiary']],
  ['on_primary', ['--text-on-primary']],
  ['border', ['--border-color']],
  ['success', ['--color-success', '--success-color']],
  ['danger', ['--color-danger', '--error-color']],
  ['warning', ['--color-warning']],
  ['info', ['--color-info']],
  ['font_family', ['--font-family']],
];

/** Ceiling on the palette built for an unconfigured label map, so that a
 *  segmentation with an unexpected value range cannot spin here. */
const MAX_AUTOMATIC_LABELS = 64;

/** Everything the configuration decides about the page rather than the state. */
function applyDocumentConfig(config: AppConfig) {
  applyTheme(config.theme);
  document.title = config.title;
  document.documentElement.style.setProperty(
    '--sidebar-width',
    `${config.layout.sidebar_width}px`,
  );
  document.documentElement.style.setProperty(
    '--workflow-panel-width',
    `${config.layout.workflow_panel_width}px`,
  );
  document.body.classList.toggle('workflow-active', config.workflow_enabled);
  document.body.classList.toggle(
    'workflow-with-sidebar',
    config.workflow_enabled && config.sidebar !== null,
  );
  document.body.classList.toggle(
    'workflow-right',
    config.layout.workflow_panel_position === 'right',
  );
  document.body.classList.toggle('sidebar-collapsed', Boolean(config.sidebar?.collapsed));
  document.body.classList.toggle(
    'sidebar-right',
    config.sidebar !== null && config.layout.sidebar_position === 'right',
  );
  document.body.classList.toggle(
    'header-title-center',
    config.layout.header_title_position === 'center',
  );
  document.body.classList.toggle(
    'header-title-right',
    config.layout.header_title_position === 'right',
  );
  document.body.classList.toggle('header-with-logo', Boolean(config.branding.logo_url));
  document.body.classList.toggle(
    'header-logo-right',
    config.layout.header_logo_position === 'right',
  );
  document.body.classList.toggle('status-hidden', !config.layout.show_status_bar);
  if (config.branding.favicon_url) {
    let favicon = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
    if (!favicon) {
      favicon = document.createElement('link');
      favicon.rel = 'icon';
      document.head.appendChild(favicon);
    }
    favicon.href = config.branding.favicon_url;
  }
}

function applyTheme(theme: ThemeConfig) {
  const root = document.documentElement;
  root.dataset.theme = theme.preset;
  // @imfusion/web-ui components read the browser/OS light-dark preference by
  // default; pin them to this app's own preset instead so they don't render
  // in a mismatched scheme (invisible text, unstyled inputs) against a page
  // that forces its own theme regardless of OS settings.
  root.dataset.imfUiColorScheme = theme.preset === 'light' ? 'light' : 'dark';
  themeVariables.forEach(([name, variables]) => {
    const value = theme[name];
    if (value) variables.forEach((variable) => root.style.setProperty(variable, value));
  });

  const rgb = theme.primary?.match(/^#([\da-f]{2})([\da-f]{2})([\da-f]{2})$/i);
  if (rgb) {
    root.style.setProperty(
      '--accent-color-rgb',
      `${parseInt(rgb[1], 16)}, ${parseInt(rgb[2], 16)}, ${parseInt(rgb[3], 16)}`,
    );
  }
}

export function PythonBridgeProvider({ children }: { children: ReactNode }) {
  const imf = useImFusion();
  const sdkData = useData();
  const sdkVisibleData = useVisibleData();
  const loader = useDataLoader();
  const sdkDataArray = useMemo(() => Array.from(sdkData), [sdkData]);
  const [dataOrder, setDataOrder] = useState<Data[]>(sdkDataArray);
  const data = useMemo(
    () => reconcileDataOrder(dataOrder, sdkDataArray),
    [dataOrder, sdkDataArray],
  );
  const visibleData = useMemo(() => Array.from(sdkVisibleData), [sdkVisibleData]);
  const dataRef = useRef(data);
  const visibleDataRef = useRef(visibleData);
  const transportRef = useRef<Transport | null>(null);
  const imfRef = useRef(imf);
  imfRef.current = imf;
  const messageQueueRef = useRef<Promise<void>>(Promise.resolve());
  const activeJobRef = useRef<JobState | null>(null);
  const pendingExportsRef = useRef(new Map<
    string,
    { resolve(value: boolean): void }
  >());
  const pendingBrushCommitsRef = useRef(new Map<
    string,
    { resolve(value: { success: boolean; index?: number; message?: string }): void }
  >());
  const pendingUploadsRef = useRef(new Map<string, { resolve(): void }>());
  const [config, setConfig] = useState<AppConfig>(defaultConfig);
  const [status, setStatus] = useState<ConnectionStatus>('disconnected');
  const [message, setMessage] = useState('Initializing application…');
  const [progress, setProgress] = useState<number | null>(null);
  const [algorithms, setAlgorithms] = useState<AlgorithmInfo[]>([]);
  const [controllers, setControllers] = useState<ControllerStatus[]>([]);
  const [workflow, setWorkflow] = useState<WorkflowState | null>(null);
  const [activeJob, setActiveJob] = useState<JobState | null>(null);
  const [dataRevision, setDataRevision] = useState(0);
  const [recorded, setRecorded] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [syncTasks, setSyncTasks] = useState<SyncTask[]>([]);

  const beginSync = useCallback((task: SyncTask) => {
    setSyncTasks((current) => [...current, task]);
  }, []);

  const endSync = useCallback((id: string) => {
    setSyncTasks((current) => current.filter((task) => task.id !== id));
  }, []);

  useEffect(() => {
    dataRef.current = data;
  }, [data]);

  useEffect(() => {
    visibleDataRef.current = visibleData;
  }, [visibleData]);

  useEffect(() => {
    activeJobRef.current = activeJob;
  }, [activeJob]);

  const send = useCallback((type: string, payload: Record<string, unknown> = {}) => (
    transportRef.current?.send(type, payload) ?? false
  ), []);

  const sendBinary = useCallback((
    type: string,
    payload: Record<string, unknown>,
    bytes: Uint8Array,
  ) => transportRef.current?.sendBinary(type, payload, bytes) ?? false, []);

  /**
   * Give an incoming label map colours for the values it holds.
   *
   * A label map crosses the socket as pixel values and a modality, with no
   * palette attached, and the renderer draws a value it has no configuration
   * for as nothing at all. The brush step already does this for the labels it
   * paints; a segmentation handed back by an action needs it too, or it lands
   * in the data list and never appears in the views.
   */
  const paletteLabelMap = useCallback(
    (item: Data) => {
      if (item.modality() !== 'LABEL') return;
      const labelMap = item as SharedImageSet;
      if (typeof labelMap.minmaxIntensityOriginal !== 'function') return;
      const highest = Math.min(
        Math.floor(labelMap.minmaxIntensityOriginal()[1]),
        MAX_AUTOMATIC_LABELS,
      );
      for (let value = 1; value <= highest; value += 1) {
        if (!imf.bindings.getLabelConfig(labelMap, value)) {
          imf.bindings.setDefaultLabelConfig(labelMap, value);
        }
      }
    },
    [imf],
  );

  const loadBuffer = useCallback(
    async (
      bytes: Uint8Array,
      options: { name?: string; selectOnly?: boolean; display?: boolean } = {},
    ): Promise<Data[]> => {
      const buffer = bytes.buffer.slice(
        bytes.byteOffset,
        bytes.byteOffset + bytes.byteLength,
      ) as ArrayBuffer;
      const loaded = Array.from(await imf.loadBuffer(buffer, `transfer-${Date.now()}.imf`));
      if (options.name && loaded[0]) loaded[0].name = options.name;
      loaded.forEach(paletteLabelMap);
      if (loaded.length && options.display !== false) {
        if (options.selectOnly) {
          const viewGroup = imf.display.viewGroup();
          viewGroup.setVisibleData(loaded);
          viewGroup.centerOnData(loaded[0]);
          imf.render();
        } else {
          imf.showAll(loaded);
        }
      }
      return loaded;
    },
    [imf, paletteLabelMap],
  );

  /**
   * Hand the server the datasets the browser just loaded, and wait for it.
   *
   * The wait is the point. Deserializing a volume costs the server as much as
   * loading it cost the browser, and for that whole window the data list on
   * screen is ahead of the model every index refers to. Resolving only on the
   * acknowledgement is what keeps the interface honest about it.
   */
  const notifyLoaded = useCallback(
    async (loaded: Data[], fallbackName: string) => {
      if (!loaded.length) return;
      const requestId = newRequestId();
      const name = loaded[0].name || fallbackName;
      // Clearing the task from the resolver means every path that drains the
      // pending map — the acknowledgement, a failure, a dropped connection —
      // releases the interface without having to remember to.
      const settled = new Promise<void>((resolve) => {
        pendingUploadsRef.current.set(requestId, {
          resolve: () => {
            endSync(requestId);
            resolve();
          },
        });
      });
      beginSync({
        id: requestId,
        label: 'Uploading…',
        detail: `Sending ${name} to the server`,
        blocking: false,
      });
      // Serializing is synchronous and holds the main thread for as long as the
      // volume is large, so the busy state has to reach the screen before it
      // starts. Without this the indicator appears only once the freeze ends,
      // which is most of the way through the wait it is there to explain.
      await nextPaint();
      const sent = sendBinary('data_loaded', {
        format: 'imf',
        request_id: requestId,
        name,
        names: loaded.map((item, index) => item.name || `${fallbackName} ${index + 1}`),
      }, imf.bindings.save(loaded));
      if (!sent) {
        pendingUploadsRef.current.delete(requestId);
        endSync(requestId);
        return;
      }
      await settled;
    },
    [beginSync, endSync, imf, sendBinary],
  );

  /**
   * Report a dataset arriving from the server for as long as it takes to decode.
   *
   * A result published by a job is covered by the job's own progress, but the
   * server can also push data from a callback or a background thread, and that
   * transfer would otherwise be silent however large it is.
   */
  const receiving = useCallback(
    async <T,>(name: string | undefined, work: () => Promise<T>): Promise<T> => {
      const taskId = newRequestId();
      beginSync({
        id: taskId,
        label: 'Receiving…',
        detail: name ? `Loading ${name}` : 'Loading data from the server',
        blocking: false,
      });
      try {
        return await work();
      } finally {
        endSync(taskId);
      }
    },
    [beginSync, endSync],
  );

  /**
   * Mirror the server's annotations into the SDK, and report back what the
   * user does to them.
   *
   * Ownership is the other way round from the data model: the browser holds
   * the geometry, because only it has the annotation and the handler that
   * turns clicks into points. The server keeps a shadow record, so an
   * `annotation_event` is the source of truth and a value pushed from Python
   * is only a starting point.
   */
  const annotationsRef = useRef(new Map<string, Annotation>());
  const [annotations, setAnnotations] = useState<ClientAnnotation[]>([]);
  const lastModifiedSentRef = useRef(new Map<string, number>());
  const creationRef = useRef(new Map<string, 'finished' | 'aborted'>());

  const annotationId = useCallback((annotation: Annotation): string | null => {
    for (const [id, tracked] of annotationsRef.current) {
      if (tracked === annotation || tracked.isAliasOf?.(annotation)) return id;
    }
    return null;
  }, []);

  /**
   * Which dataset owns `annotation`, as an index into the server's model.
   *
   * Asked of the annotation model rather than matched against the `Data` the
   * caller passed in: the SDK hands out a fresh handle per lookup, so a
   * dataset taken from `visibleData` is not reference-equal to the same
   * dataset in `data`. `dataAnnotations` compares the underlying objects.
   */
  const annotationDataIndex = useCallback(
    (annotation: Annotation): number => dataRef.current.findIndex(
      (item) => imf.annotationModel.dataAnnotations(item).includes(annotation),
    ),
    [imf],
  );

  const publishAnnotations = useCallback(() => {
    const items: ClientAnnotation[] = [];
    annotationsRef.current.forEach((annotation, id) => {
      let points: number[][] = [];
      let state: Record<string, unknown> = {};
      try {
        state = annotation.state();
        points = parseAnnotationPoints(state);
      } catch (error) {
        console.warn(`Could not read annotation ${id}`, error);
      }
      const dataIndex = annotationDataIndex(annotation);
      const maxPoints = annotationMaxPoints(state);
      items.push({
        id,
        type: annotation.type(),
        dataIndex,
        dataName: dataRef.current[dataIndex]?.name ?? '',
        points,
        complete: maxPoints !== null && points.length >= maxPoints,
        editing: maxPoints !== null && points.length < maxPoints,
        creation: creationRef.current.get(id) ?? null,
      });
    });
    setAnnotations(items);
  }, [annotationDataIndex]);

  const reportAnnotation = useCallback(
    (id: string, annotation: Annotation, event: string) => {
      let points: number[][] = [];
      let maxPoints: number | null = null;
      try {
        const state = annotation.state();
        points = parseAnnotationPoints(state);
        maxPoints = annotationMaxPoints(state);
      } catch (error) {
        console.warn(`Could not read annotation ${id}`, error);
      }
      send('annotation_event', { id, event, points, max_points: maxPoints });
    },
    [send],
  );

  useEffect(() => {
    const unsubscribe = imf.annotationModel.onAnnotationEvent((annotation, event) => {
      const id = annotationId(annotation);
      // An event for an annotation this client never registered is not an
      // error: the server may have removed it while the event was in flight.
      if (!id) return;
      if (event === 'Modified') {
        // Every handle drag signals, so this would otherwise be a stream.
        const now = Date.now();
        const last = lastModifiedSentRef.current.get(id) ?? 0;
        if (now - last < MODIFIED_EVENT_INTERVAL_MS) return;
        lastModifiedSentRef.current.set(id, now);
        reportAnnotation(id, annotation, 'points_changed');
        publishAnnotations();
        return;
      }
      lastModifiedSentRef.current.delete(id);
      if (event === 'CreationFinished') {
        creationRef.current.set(id, 'finished');
        reportAnnotation(id, annotation, 'editing_finished');
      } else if (event === 'CreationAborted') {
        creationRef.current.set(id, 'aborted');
        // Aborting clears the points and leaves the annotation in a mode the
        // SDK cannot re-arm, so the server replaces it rather than retrying.
        reportAnnotation(id, annotation, 'editing_aborted');
      }
      publishAnnotations();
    });
    return unsubscribe;
  }, [annotationId, imf, publishAnnotations, reportAnnotation]);

  const addAnnotation = useCallback(
    (
      id: string,
      type: string,
      parent: Data | undefined,
      options: {
        color?: number[];
        name?: string;
        label?: string;
        visible?: boolean;
        points?: number[][];
      } = {},
    ): Annotation | null => {
      if (!parent) {
        send('annotation_event', {
          id,
          event: 'unsupported',
          message: 'The annotation\'s dataset is not loaded in the browser',
        });
        return null;
      }
      if (!supportsAnnotationType(imf.bindings, type)) {
        send('annotation_event', {
          id,
          event: 'unsupported',
          message: `This browser's Web SDK does not support ${type} annotations`,
        });
        return null;
      }
      // `add()` returns null for a type it knows but cannot build, which is a
      // different failure from the guard above and needs the same answer.
      const annotation = imf.annotationModel.add(type as never, parent);
      if (!annotation) {
        send('annotation_event', {
          id,
          event: 'unsupported',
          message: `This browser's Web SDK could not create a ${type} annotation`,
        });
        return null;
      }
      annotationsRef.current.set(id, annotation);
      creationRef.current.delete(id);
      const state: Record<string, unknown> = {};
      if (options.color) {
        state.color = annotationStateColor(options.color);
        state.pointColor = annotationStateColor(options.color);
      }
      if (options.name) state.name = options.name;
      if (options.label !== undefined) state.labelText = options.label;
      if (options.visible !== undefined) state.visible = options.visible;
      if (options.points?.length) {
        state.points = serializeAnnotationPoints(options.points);
      }
      if (Object.keys(state).length) annotation.setState(state);
      imf.annotationModel.updateAnnotationVisibility();
      imf.render();
      return annotation;
    },
    [imf, send],
  );

  const createAnnotation = useCallback(
    (type: string, parent: Data): string | null => {
      const id = newRequestId();
      const annotation = addAnnotation(id, type, parent, {});
      if (!annotation) return null;
      send('annotation_created', {
        id,
        type,
        data_index: annotationDataIndex(annotation),
        points: [],
      });
      publishAnnotations();
      return id;
    },
    [addAnnotation, annotationDataIndex, publishAnnotations, send],
  );

  const removeAnnotation = useCallback(
    (id: string) => {
      const annotation = annotationsRef.current.get(id);
      if (!annotation) return;
      annotationsRef.current.delete(id);
      lastModifiedSentRef.current.delete(id);
      creationRef.current.delete(id);
      imf.annotationModel.remove(annotation);
      send('annotation_event', { id, event: 'removed' });
      publishAnnotations();
      imf.render();
    },
    [imf, publishAnnotations, send],
  );

  /**
   * Drop annotations on a dataset that is about to be destroyed.
   *
   * The SDK keys annotations by their parent `Data`, so removing the dataset
   * first would leave `updateAnnotationVisibility()` walking a freed pointer.
   * The server orders its own removals ahead of the dataset's for annotations
   * it created; this covers the ones the client originated and the paths where
   * the browser destroys a dataset on its own.
   */
  const forgetAnnotationsFor = useCallback(
    (item: Data | null) => {
      const doomed = item
        ? Array.from(imf.annotationModel.dataAnnotations(item))
        : null;
      let changed = false;
      annotationsRef.current.forEach((annotation, id) => {
        if (doomed && !doomed.some((candidate) => candidate.isAliasOf?.(annotation)
          || candidate === annotation)) {
          return;
        }
        if (doomed) imf.annotationModel.remove(annotation);
        annotationsRef.current.delete(id);
        lastModifiedSentRef.current.delete(id);
        creationRef.current.delete(id);
        changed = true;
      });
      if (changed) publishAnnotations();
    },
    [imf, publishAnnotations],
  );

  const applyFrame = useCallback(
    async ({ type, data, payload: binaryPayload }: ServerFrame) => {
      const payload = data ?? {};
      try {
        switch (type) {
          case 'actions':
            setConfig((current) => ({
              ...current,
              actions: (payload.actions ?? []).map((action: string | ActionDescriptor) =>
                typeof action === 'string'
                  ? {
                      name: action,
                      is_app_only: false,
                      inputs: [{ key: 'image', label: 'Image', required: true }],
                      parameters: {},
                    }
                  : { ...action, parameters: action.parameters ?? {} }),
            }));
            break;
          case 'job_started':
            activeJobRef.current = payload as JobState;
            setActiveJob(payload as JobState);
            setStatus('processing');
            setProgress(payload.progress ?? 0);
            setMessage(`Processing ${payload.label}…`);
            break;
          case 'job_progress':
            if (
              !activeJobRef.current
              || activeJobRef.current.job_id === payload.job_id
            ) {
              setActiveJob((current) => current
                ? { ...current, ...payload }
                : payload as JobState);
            }
            setProgress(payload.progress ?? 0);
            setMessage(payload.message ?? `Processing ${payload.label ?? 'operation'}…`);
            break;
          case 'job_result': {
            if (
              activeJobRef.current
              && activeJobRef.current.job_id !== payload.job_id
            ) {
              break;
            }
            const result = payload.result ?? {};
            if (result.algorithms) setAlgorithms(result.algorithms);
            if (result.controllers) {
              setControllers((current) => [
                ...current.filter(
                  (item) => !result.controllers.some(
                    (update: ControllerStatus) => update.name === item.name,
                  ),
                ),
                ...result.controllers,
              ]);
            }
            activeJobRef.current = null;
            setActiveJob(null);
            setMessage(`${payload.label ?? 'Operation'} completed`);
            setStatus('connected');
            setProgress(null);
            break;
          }
          case 'job_failed': {
            // A binary request that never got as far as becoming a job reports
            // its failure here, so whatever is waiting on it has to be let go.
            const requestId = String(payload.request_id ?? '');
            const failedUpload = pendingUploadsRef.current.get(requestId);
            if (failedUpload) {
              pendingUploadsRef.current.delete(requestId);
              failedUpload.resolve();
            }
            const current = activeJobRef.current;
            const terminatesCurrent = Boolean(
              payload.job_id && current?.job_id === payload.job_id,
            );
            if (terminatesCurrent || !current) {
              activeJobRef.current = null;
              setActiveJob(null);
              setStatus('error');
              setProgress(null);
            }
            setMessage(payload.error?.message ?? 'Operation failed');
            break;
          }
          case 'job_cancelled':
            if (activeJobRef.current?.job_id === payload.job_id) {
              activeJobRef.current = null;
              setActiveJob(null);
              setMessage(`${payload.label ?? 'Operation'} cancelled`);
              setStatus('connected');
              setProgress(null);
            }
            break;
          case 'data_add': {
            if (!binaryPayload) throw new Error('data_add is missing its binary payload');
            const loaded = await receiving(
              payload.name,
              () => loadBuffer(binaryPayload, { name: payload.name }),
            );
            const next = [...dataRef.current, ...loaded];
            dataRef.current = next;
            setDataOrder(next);
            break;
          }
          case 'data_update': {
            const previous = dataRef.current;
            const index = Number(payload.index);
            if (!binaryPayload) throw new Error('data_update is missing its binary payload');
            if (!Number.isInteger(index) || index < 0 || index >= previous.length) {
              throw new Error(`Invalid data_update index: ${payload.index}`);
            }
            const visibleIndices = selectedDataIndices(
              previous,
              visibleDataRef.current,
            );
            const loaded = await receiving(
              payload.name,
              () => loadBuffer(binaryPayload, { display: false }),
            );
            if (loaded.length !== 1) {
              throw new Error(`data_update expected one dataset, received ${loaded.length}`);
            }
            const replacement = loaded[0];
            if (payload.name) replacement.name = payload.name;
            const next = [...previous];
            next[index] = replacement;

            const nextVisible = visibleIndices
              .map((visibleIndex) => next[visibleIndex])
              .filter(Boolean);
            if (visibleIndices.length) {
              // Replace visible data while both handles are still in the model.
              // This prevents the auto-layouter from closing empty views.
              imf.display.viewGroup().setVisibleData(nextVisible);
              visibleDataRef.current = nextVisible;
            }
            // loadBuffer appended the replacement. Remove only the old item;
            // logical ordering remains aligned with server-side indices.
            forgetAnnotationsFor(previous[index]);
            imf.dataModel.remove(previous[index]);
            dataRef.current = next;
            setDataOrder(next);
            imf.render();
            break;
          }
          case 'data_reset': {
            // The whole model goes, so there is nothing to look at or act on
            // until the replacement is in: this one covers the page.
            const taskId = newRequestId();
            beginSync({
              id: taskId,
              label: 'Synchronizing…',
              detail: 'Reloading the datasets',
              blocking: true,
            });
            try {
              forgetAnnotationsFor(null);
              imf.dataModel.clear();
              imf.display.viewGroup().setVisibleData([]);
              const loaded = await loadBuffer(base64ToBytes(payload.image.buffer));
              if (payload.names) loaded.forEach((item: Data, index: number) => {
                if (payload.names[index]) item.name = payload.names[index];
              });
              dataRef.current = loaded;
              setDataOrder(loaded);
            } finally {
              endSync(taskId);
            }
            break;
          }
          case 'data_remove': {
            const item = dataRef.current[payload.index];
            if (item) {
              forgetAnnotationsFor(item);
              imf.dataModel.remove(item);
            }
            const next = dataRef.current.filter(
              (_item, index) => index !== payload.index,
            );
            dataRef.current = next;
            setDataOrder(next);
            break;
          }
          case 'data_metadata': {
            // Only the fields the SDK can write onto a live dataset travel
            // here; the server sends a full `data_update` for anything else.
            const item = dataRef.current[payload.index];
            if (item) {
              if (payload.name !== undefined) item.name = payload.name;
              if (payload.modality !== undefined) {
                (item as SharedImageSet).setModality(payload.modality);
              }
              setDataRevision((revision) => revision + 1);
              imf.render();
            }
            break;
          }
          case 'annotation_add': {
            const id = String(payload.id ?? '');
            if (!id || annotationsRef.current.has(id)) break;
            const annotation = addAnnotation(
              id,
              String(payload.type ?? ''),
              dataRef.current[Number(payload.data_index)],
              {
                color: payload.color,
                name: payload.name,
                label: payload.label,
                visible: payload.visible,
                points: payload.points,
              },
            );
            if (annotation) publishAnnotations();
            break;
          }
          case 'annotation_update': {
            // An unknown id is a no-op: a removal and an update legitimately
            // cross on the wire.
            const annotation = annotationsRef.current.get(String(payload.id ?? ''));
            if (!annotation) break;
            const state: Record<string, unknown> = {};
            if (payload.color) {
              state.color = annotationStateColor(payload.color);
              state.pointColor = annotationStateColor(payload.color);
            }
            if (payload.name !== undefined) state.name = payload.name;
            if (payload.label !== undefined) state.labelText = payload.label;
            if (payload.visible !== undefined) state.visible = payload.visible;
            if (payload.points !== undefined) {
              state.points = serializeAnnotationPoints(payload.points);
            }
            if (Object.keys(state).length) annotation.setState(state);
            publishAnnotations();
            imf.render();
            break;
          }
          case 'annotation_remove': {
            const id = String(payload.id ?? '');
            const annotation = annotationsRef.current.get(id);
            if (!annotation) break;
            annotationsRef.current.delete(id);
            lastModifiedSentRef.current.delete(id);
            creationRef.current.delete(id);
            imf.annotationModel.remove(annotation);
            publishAnnotations();
            imf.render();
            break;
          }
          case 'export_result': {
            const requestId = String(payload.request_id ?? '');
            const pending = pendingExportsRef.current.get(requestId);
            if (!pending) break;
            downloadBuffer(payload.buffer, payload.filename ?? 'export', payload.media_type);
            pendingExportsRef.current.delete(requestId);
            setStatus('connected');
            setProgress(null);
            setMessage(`Exported ${payload.filename ?? 'export'}`);
            pending.resolve(true);
            break;
          }
          case 'download_artifact':
            // Unlike `export_result` this one is unsolicited, so it resolves
            // no pending request.
            downloadBuffer(
              payload.buffer,
              payload.filename ?? 'download',
              payload.media_type,
            );
            setMessage(`Downloaded ${payload.filename ?? 'file'}`);
            break;
          case 'export_failed': {
            const requestId = String(payload.request_id ?? '');
            const pending = pendingExportsRef.current.get(requestId);
            const error = new Error(payload.message ?? 'Export failed');
            pendingExportsRef.current.delete(requestId);
            setStatus('error');
            setProgress(null);
            setMessage(error.message);
            pending?.resolve(false);
            break;
          }
          case 'workflow_brush_result': {
            const requestId = String(payload.request_id ?? '');
            const pending = pendingBrushCommitsRef.current.get(requestId);
            pendingBrushCommitsRef.current.delete(requestId);
            pending?.resolve({ success: true, index: payload.index });
            break;
          }
          case 'workflow_brush_failed': {
            const requestId = String(payload.request_id ?? '');
            const pending = pendingBrushCommitsRef.current.get(requestId);
            pendingBrushCommitsRef.current.delete(requestId);
            setMessage(payload.message ?? 'Brush commit failed');
            pending?.resolve({ success: false, message: payload.message });
            break;
          }
          case 'selection_update': {
            const selected = (payload.indices ?? [])
              .map((index: number) => dataRef.current[index])
              .filter(Boolean);
            const viewGroup = imf.display.viewGroup();
            viewGroup.setVisibleData(selected);
            if (selected[0]) viewGroup.centerOnData(selected[0]);
            // Annotations show in the views their parent dataset shows in, and
            // the SDK only works that out when asked.
            imf.annotationModel.updateAnnotationVisibility();
            imf.render();
            break;
          }
          case 'data_clear':
          case 'reset_views':
            forgetAnnotationsFor(null);
            imf.dataModel.clear();
            imf.display.viewGroup().setVisibleData([]);
            dataRef.current = [];
            setDataOrder([]);
            break;
          case 'initial_sync_complete':
            endSync(initialSyncTaskId);
            setMessage(
              payload.count
                ? `${payload.count} dataset(s) synchronized`
                : 'Ready — load a dataset to begin',
            );
            break;
          case 'data_sync_complete': {
            const requestId = String(payload.request_id ?? '');
            const pending = pendingUploadsRef.current.get(requestId);
            pendingUploadsRef.current.delete(requestId);
            pending?.resolve();
            break;
          }
          case 'workflow_state':
            setWorkflow(payload as WorkflowState);
            if (payload.current_step?.ui_config?.error) {
              setStatus('error');
              setProgress(null);
              setMessage(`Processing failed: ${payload.current_step.ui_config.error}`);
            } else {
              setStatus('connected');
              setProgress(null);
            }
            break;
          case 'workflow_error':
          case 'error':
            setMessage(payload.message ?? 'Unknown server error');
            setStatus('error');
            setProgress(null);
            break;
          default:
            console.warn('Unknown server message', type);
        }
      } catch (error) {
        console.error(`Failed to handle ${type}`, error);
        setMessage(error instanceof Error ? error.message : String(error));
        setStatus('connected');
      }
    },
    [
      addAnnotation,
      beginSync,
      endSync,
      forgetAnnotationsFor,
      imf,
      loadBuffer,
      publishAnnotations,
      receiving,
    ],
  );

  /** Apply frames one at a time: handling one can take a load and a render. */
  const handleFrame = useCallback((frame: ServerFrame) => {
    const applied = messageQueueRef.current.then(() => applyFrame(frame));
    messageQueueRef.current = applied.catch(() => undefined);
    return applied;
  }, [applyFrame]);

  useEffect(() => {
    const transport = createTransport(() => imfRef.current);
    transportRef.current = transport;
    setRecorded(transport.recorded);

    let cancelled = false;
    transport.loadConfig().then(
      (nextConfig) => {
        if (nextConfig.protocol_version !== 7) {
          throw new Error(
            `Unsupported server protocol ${nextConfig.protocol_version}; expected version 7`,
          );
        }
        if (cancelled) return;
        applyDocumentConfig(nextConfig);
        setConfig((current) => ({ ...nextConfig, actions: current.actions }));
      },
      (error: unknown) => {
        if (!cancelled) setMessage(error instanceof Error ? error.message : String(error));
      },
    );

    /** Release everything waiting on a reply that is no longer coming. */
    const abandonPending = (message: string) => {
      pendingExportsRef.current.forEach(({ resolve }) => resolve(false));
      pendingExportsRef.current.clear();
      pendingBrushCommitsRef.current.forEach(({ resolve }) => resolve({
        success: false,
        message,
      }));
      pendingBrushCommitsRef.current.clear();
      pendingUploadsRef.current.forEach(({ resolve }) => resolve());
      pendingUploadsRef.current.clear();
    };

    transport.connect({
      onOpen: (message) => {
        // The server streams its datasets straight after opening, and reports
        // them complete only at the end. Until then the page has nothing on it.
        beginSync({
          id: initialSyncTaskId,
          label: 'Synchronizing…',
          detail: 'Loading datasets from the server',
          blocking: true,
        });
        setStatus('connected');
        setMessage(message);
      },
      onClose: (message) => {
        abandonPending(message);
        endSync(initialSyncTaskId);
        setStatus('disconnected');
        setMessage(message);
      },
      onError: setMessage,
      onFrame: handleFrame,
      onUnavailable: (message) => {
        // The control that sent this already showed itself as busy, so the
        // interface has to be handed back along with the explanation.
        abandonPending(message);
        activeJobRef.current = null;
        setActiveJob(null);
        setStatus('connected');
        setProgress(null);
        setMessage('That interaction was not recorded');
        setNotice(message);
      },
    });

    return () => {
      cancelled = true;
      transportRef.current = null;
      transport.close();
    };
  }, [beginSync, endSync, handleFrame]);

  const selectedIndices = useMemo(
    () => selectedDataIndices(data, visibleData),
    [data, visibleData],
  );

  useEffect(() => {
    send('selection_changed', { indices: selectedIndices });
  }, [selectedIndices, send]);

  /**
   * Refuse an import the transport could never finish, before it starts.
   *
   * A recording has no process to hand the data to, but the browser would load
   * the file perfectly well and put it on screen, and only the notification
   * would fail. That leaves a dataset the recording does not know about sitting
   * in the model, shifting every index the recorded results were computed for.
   * Every way in — the dialog, the landing page, a dropped folder, a sample
   * card — arrives at one of the three functions below, so the refusal lives
   * here rather than on the controls.
   */
  const importUnavailable = useCallback(() => {
    const transport = transportRef.current;
    if (!transport?.recorded) return false;
    setNotice(
      transport.notice
      ?? 'This page is a recording, so there is nothing here to load data into.',
    );
    return true;
  }, []);

  const loadFile = useCallback(
    async (file: File) => {
      if (importUnavailable()) return;
      try {
        const loaded = Array.from(await loader.loadFile(file));
        if (!loaded.length) throw new Error(`No datasets found in ${file.name}`);
        imf.showAll(loaded);
        setMessage(`Loaded ${file.name}`);
        await notifyLoaded(loaded, file.name);
      } catch (error) {
        setMessage(error instanceof Error ? error.message : String(error));
      }
    },
    [imf, importUnavailable, loader, notifyLoaded],
  );

  const loadFiles = useCallback(
    async (files: File[]) => {
      if (!files.length || importUnavailable()) return;
      try {
        const loaded = Array.from(
          files.length === 1
            ? await loader.loadFile(files[0])
            : await loader.loadFolder(files),
        );
        if (!loaded.length) throw new Error('No datasets found in the selected files');
        imf.showAll(loaded);
        const fallbackName = files.length === 1 ? files[0].name : 'Selected folder';
        setMessage(
          files.length === 1
            ? `Loaded ${files[0].name}`
            : `Loaded ${files.length} files`,
        );
        await notifyLoaded(loaded, fallbackName);
      } catch (error) {
        setMessage(error instanceof Error ? error.message : String(error));
      }
    },
    [imf, importUnavailable, loader, notifyLoaded],
  );

  const loadSampleDataset = useCallback(
    async (dataset: SampleDataset) => {
      if (importUnavailable()) return;
      try {
        setMessage(`Loading ${dataset.name}…`);
        const loaded = Array.from(await loader.loadFileFromUrl(dataset.data_url));
        if (!loaded.length) throw new Error(`No datasets found in ${dataset.name}`);
        if (loaded.length === 1) loaded[0].name = dataset.name;
        imf.showAll(loaded);
        setMessage(`Loaded ${dataset.name}`);
        await notifyLoaded(loaded, dataset.name);
      } catch (error) {
        setMessage(error instanceof Error ? error.message : String(error));
      }
    },
    [imf, importUnavailable, loader, notifyLoaded],
  );

  const executeAction = useCallback(
    (
      name: string,
      inputs?: InputReference[],
      parameters?: Record<string, unknown>,
    ) => {
      setStatus('processing');
      setProgress(0);
      setMessage(`Processing ${name}…`);
      send('execute_action', {
        action: name,
        ...(inputs ? { inputs } : { indices: selectedIndices }),
        ...(parameters ? { parameters } : {}),
      });
    },
    [selectedIndices, send],
  );

  const discoverAlgorithms = useCallback(
    (inputs: InputReference[]) => send('discover_algorithms', { inputs }),
    [send],
  );

  const executeAlgorithm = useCallback(
    (id: string, parameters: Record<string, unknown>, inputs: InputReference[]) => {
      setStatus('processing');
      setProgress(0);
      setMessage(`Processing ${id}…`);
      send('execute_algorithm', { algorithm_id: id, inputs, parameters });
    },
    [send],
  );

  const checkController = useCallback(
    (name: string, inputs: InputReference[]) =>
      send('check_controller_compatibility', { controller_name: name, inputs }),
    [send],
  );

  const executeController = useCallback(
    (name: string, parameters: Record<string, unknown>, inputs: InputReference[]) => {
      if (!inputs.length) return;
      setStatus('processing');
      setProgress(0);
      setMessage(`Processing ${name}…`);
      send('execute_controller', {
        controller_name: name,
        inputs,
        parameters,
      });
    },
    [send],
  );

  const removeData = useCallback(
    (item: Data) => {
      const index = data.indexOf(item);
      if (index < 0) return;
      send('data_removed', { index, name: item.name });
      forgetAnnotationsFor(item);
      imf.dataModel.remove(item);
    },
    [data, forgetAnnotationsFor, imf, send],
  );

  const setVisibleData = useCallback(
    (items: Data[]) => {
      imf.display.viewGroup().setVisibleData(items);
      if (items[0]) imf.display.viewGroup().centerOnData(items[0]);
      imf.annotationModel.updateAnnotationVisibility();
    },
    [imf],
  );

  const exportAll = useCallback(async (format: ExportFormat = 'imf') => {
    if (!data.length) return false;
    if (format === 'imf') {
      const saved = imf.bindings.save(data);
      const blob = new Blob([new Uint8Array(saved).buffer], { type: 'application/octet-stream' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'export.imf';
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
      return true;
    }

    const requestId = newRequestId();
    setStatus('processing');
    setProgress(0);
    setMessage(`Exporting ${format === 'dicom' ? 'DICOM' : 'NIfTI'}…`);
    const result = new Promise<boolean>((resolve) => {
      pendingExportsRef.current.set(requestId, {
        resolve: (value: boolean) => {
          endSync(requestId);
          resolve(value);
        },
      });
    });
    beginSync({
      id: requestId,
      label: 'Exporting…',
      detail: 'Preparing the download on the server',
      blocking: false,
    });
    const sent = send('export_data', {
      request_id: requestId,
      format,
      indices: data.map((_item, index) => index),
    });
    if (!sent) {
      pendingExportsRef.current.delete(requestId);
      endSync(requestId);
      setStatus('error');
      setProgress(null);
      setMessage('Cannot export while disconnected');
      return false;
    }
    return result;
  }, [beginSync, data, endSync, imf, send]);

  const sendWorkflowData = useCallback(
    (workflowData: Record<string, unknown>) =>
      send('workflow_step_data', { data: workflowData }),
    [send],
  );

  const commitBrush = useCallback(
    (labelMap: Data, targetIndex: number | null) => {
      const requestId = newRequestId();
      const result = new Promise<{ success: boolean; index?: number; message?: string }>(
        (resolve) => {
          pendingBrushCommitsRef.current.set(requestId, {
            resolve: (value) => {
              endSync(requestId);
              resolve(value);
            },
          });
        },
      );
      beginSync({
        id: requestId,
        label: 'Saving…',
        detail: 'Sending the segmentation to the server',
        blocking: false,
      });
      const sent = sendBinary(
        'workflow_brush_commit',
        { format: 'imf', request_id: requestId, target_index: targetIndex },
        imf.bindings.save([labelMap]),
      );
      if (!sent) {
        pendingBrushCommitsRef.current.delete(requestId);
        endSync(requestId);
        return Promise.resolve({ success: false, message: 'Cannot save while disconnected.' });
      }
      return result;
    },
    [beginSync, endSync, imf, sendBinary],
  );

  const loadSnapshot = useCallback(
    async (snapshot: Uint8Array, name: string): Promise<Data> => {
      const buffer = snapshot.buffer.slice(
        snapshot.byteOffset,
        snapshot.byteOffset + snapshot.byteLength,
      ) as ArrayBuffer;
      const [restored] = Array.from(await imf.loadBuffer(buffer, `reset-${Date.now()}.imf`));
      if (!restored) throw new Error('Failed to reload the snapshot.');
      restored.name = name;
      return restored;
    },
    [imf],
  );

  const swapLocalData = useCallback(
    (stale: Data, replacement: Data) => {
      // The caller must unbind anything still referencing `stale` (e.g. an
      // active brush) before calling this, otherwise removing it here leaves
      // a dangling reference in the WASM module.
      const currentVisible = visibleDataRef.current;
      if (currentVisible.some((item) => item === stale)) {
        const nextVisible = currentVisible.map((item) => (item === stale ? replacement : item));
        imf.display.viewGroup().setVisibleData(nextVisible);
        visibleDataRef.current = nextVisible;
      }
      imf.dataModel.remove(stale);
      imf.render();
    },
    [imf],
  );

  /**
   * Collapse every reason the client is waiting into one answer.
   *
   * Ordered by how much of the interface the work takes away: reading a file
   * and rebuilding the model leave nothing to do, a job leaves the viewer alone
   * but owns the progress bar, and a transfer is the quietest of the three.
   */
  const busy = useMemo<BusyState>(() => {
    if (loader.isLoading) {
      const received = loader.progress?.received;
      const total = loader.progress?.total;
      return {
        active: true,
        blocking: true,
        label: 'Loading…',
        detail: 'Reading and processing the selected files',
        progress: total ? (received ?? 0) / total : null,
      };
    }
    const blocking = syncTasks.find((task) => task.blocking);
    if (blocking) {
      return {
        active: true,
        blocking: true,
        label: blocking.label,
        detail: blocking.detail,
        progress: null,
      };
    }
    // `status` turns to processing when a job is requested, which is before the
    // server has answered with one, so the gap between the two has to count.
    if (status === 'processing' || activeJob) {
      return {
        active: true,
        blocking: false,
        label: 'Processing…',
        detail: message,
        progress,
      };
    }
    const task = syncTasks[0];
    if (task) {
      return {
        active: true,
        blocking: false,
        label: task.label,
        detail: task.detail,
        progress: null,
      };
    }
    return idleBusy;
  }, [
    activeJob,
    loader.isLoading,
    loader.progress,
    message,
    progress,
    status,
    syncTasks,
  ]);

  const value = useMemo<BridgeValue>(
    () => ({
      imf,
      config,
      data,
      visibleData,
      status,
      message,
      progress,
      busy,
      algorithms,
      controllers,
      workflow,
      activeJob,
      isLoading: loader.isLoading,
      loadProgress: loader.progress,
      recorded,
      notice,
      dismissNotice: () => setNotice(null),
      importUnavailable,
      loadFile,
      loadFiles,
      loadSampleDataset,
      executeAction,
      discoverAlgorithms,
      executeAlgorithm,
      checkController,
      executeController,
      removeData,
      setVisibleData,
      exportAll,
      sendWorkflowData,
      commitBrush,
      loadSnapshot,
      swapLocalData,
      createAnnotation,
      removeAnnotation,
      annotations,
      workflowNext: () => send('workflow_next'),
      workflowBack: () => send('workflow_back'),
      workflowRun: (action?: string) =>
        send('workflow_run', action ? { action } : {}),
      cancelJob: () => {
        if (activeJob) send('cancel_job', { job_id: activeJob.job_id });
      },
    }),
    [
      algorithms,
      activeJob,
      annotations,
      busy,
      config,
      controllers,
      createAnnotation,
      data,
      dataRevision,
      executeAction,
      discoverAlgorithms,
      executeAlgorithm,
      checkController,
      commitBrush,
      executeController,
      exportAll,
      imf,
      importUnavailable,
      loadFile,
      loadFiles,
      loadSampleDataset,
      loader.isLoading,
      loader.progress,
      loadSnapshot,
      message,
      notice,
      progress,
      recorded,
      removeAnnotation,
      removeData,
      send,
      sendWorkflowData,
      setVisibleData,
      swapLocalData,
      status,
      visibleData,
      workflow,
    ],
  );

  return <PythonBridgeContext.Provider value={value}>{children}</PythonBridgeContext.Provider>;
}

export function usePythonBridge(): BridgeValue {
  const value = useContext(PythonBridgeContext);
  if (!value) throw new Error('usePythonBridge must be used inside PythonBridgeProvider');
  return value;
}
