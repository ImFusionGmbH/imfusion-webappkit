import { useEffect, useRef } from 'react';
import { useLayoutMode, useViewVisibility } from '@imfusion/sdk-react';
import { PythonBridgeProvider, usePythonBridge } from './PythonBridge';
import { ContextMenuOverlay } from './ContextMenu';
import { DropZone } from './DropZone';
import { Header } from './Header';
import { Sidebar } from './Sidebar';
import { StatusIndicator } from './StatusIndicator';
import { DemoChrome } from './static-demo/DemoChrome';
import { WorkflowPanel } from './workflow/Panel';

/** Covers the page for the work that leaves nothing on it to look at. */
function LoadingOverlay() {
  const { busy } = usePythonBridge();
  if (!busy.blocking) return null;

  const percentage = busy.progress === null ? null : Math.round(busy.progress * 100);
  return (
    <div className="loading-overlay" role="status" aria-live="polite">
      <div className="loading-overlay__panel">
        <div className="landing-page__loading-spinner" />
        <strong>{busy.label}</strong>
        <span>{percentage === null ? busy.detail : `${percentage}%`}</span>
        {percentage !== null && (
          <span className="loading-overlay__progress" aria-hidden="true">
            <span style={{ width: `${percentage}%` }} />
          </span>
        )}
      </div>
    </div>
  );
}

/**
 * A line under the header for the work that does not take the page away.
 *
 * The status bar already names what is happening, but it is one quiet line at
 * the bottom of the window and a transfer can finish before anyone looks at it.
 * This sits where the eye already is, in the same place every time, so that
 * "something is going on" does not have to be read to be noticed.
 */
function BusyBar() {
  const { busy } = usePythonBridge();
  const determinate = busy.progress !== null;
  return (
    <div
      className="busy-bar"
      data-active={busy.active}
      data-determinate={determinate}
      role="progressbar"
      aria-hidden={!busy.active}
      aria-label={busy.label || 'Idle'}
      aria-valuemin={0}
      aria-valuemax={100}
      {...(determinate ? { 'aria-valuenow': Math.round((busy.progress ?? 0) * 100) } : {})}
    >
      <span
        className="busy-bar__fill"
        style={determinate ? { width: `${(busy.progress ?? 0) * 100}%` } : undefined}
      />
    </div>
  );
}

function InitialViewerLayout() {
  const bridge = usePythonBridge();
  const { setMode } = useLayoutMode();
  const display = bridge.imf.display;
  const { setHidden: set2dHidden } = useViewVisibility(display.main2dView());
  const { setHidden: setAxialHidden } = useViewVisibility(display.mainAxialView());
  const { setHidden: setCoronalHidden } = useViewVisibility(display.mainCoronalView());
  const { setHidden: setSagittalHidden } = useViewVisibility(display.mainSagittalView());
  const { setHidden: set3dHidden } = useViewVisibility(display.main3dView());
  const appliedLayout = useRef<string | null>(null);
  const appliedViews = useRef(false);

  useEffect(() => {
    const layout = bridge.config.layout.initial_view_layout;
    if (layout && appliedLayout.current !== layout) {
      setMode(layout);
      appliedLayout.current = layout;
    }
  }, [bridge.config.layout.initial_view_layout, setMode]);

  useEffect(() => {
    const views = bridge.config.layout.initial_visible_views;
    if (!views || !bridge.data.length || appliedViews.current) return;
    set2dHidden(!views.includes('2d'));
    const showMpr = views.includes('mpr');
    setAxialHidden(!showMpr && !views.includes('axial'));
    setCoronalHidden(!showMpr && !views.includes('coronal'));
    setSagittalHidden(!showMpr && !views.includes('sagittal'));
    set3dHidden(!views.includes('3d'));
    appliedViews.current = true;
  }, [
    bridge.config.layout.initial_visible_views,
    bridge.data.length,
    set2dHidden,
    setAxialHidden,
    setCoronalHidden,
    setSagittalHidden,
    set3dHidden,
  ]);

  return null;
}

function MainViewer() {
  const bridge = usePythonBridge();
  const busy = bridge.busy.active;

  // Styling the whole page from one class keeps the cue consistent across
  // chrome that has no idea the bridge exists.
  useEffect(() => {
    document.body.classList.toggle('is-busy', busy);
  }, [busy]);

  return (
    <>
      <InitialViewerLayout />
      <Header />
      <BusyBar />
      <Sidebar />
      <WorkflowPanel />
      <LoadingOverlay />
      {!bridge.data.length && !bridge.config.workflow_enabled && <DropZone />}
      <footer id="status-bar">
        <div id="message-area" className="message-area">{bridge.message}</div>
        <StatusIndicator className="status-bar__status" />
      </footer>
      <ContextMenuOverlay />
      <DemoChrome />
    </>
  );
}

export function App() {
  return (
    <PythonBridgeProvider>
      <MainViewer />
    </PythonBridgeProvider>
  );
}
