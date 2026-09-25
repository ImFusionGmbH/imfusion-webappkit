import {
  useEffect,
  useRef,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react';
import { usePythonBridge } from './PythonBridge';

const PANEL_MIN_WIDTH = 180;
const PANEL_MAX_WIDTH = 640;
const PANEL_KEYBOARD_STEP = 16;
const MAIN_MIN_WIDTH = 240;

export function PanelResizer({ panel, variable, label, defaultWidth, growsLeftwards }: {
  panel: 'sidebar' | 'workflow-panel';
  variable: string;
  label: string;
  defaultWidth: number;
  growsLeftwards: boolean;
}) {
  const bridge = usePythonBridge();
  const frameRef = useRef(0);
  const stopDragRef = useRef<() => void>(() => {});

  useEffect(() => () => {
    window.cancelAnimationFrame(frameRef.current);
    stopDragRef.current();
  }, []);

  const currentWidth = () => {
    const value = getComputedStyle(document.documentElement).getPropertyValue(variable);
    return Number.parseFloat(value) || defaultWidth;
  };

  const applyWidth = (width: number) => {
    const current = currentWidth();
    // Growing is additionally capped by the space left for the viewer, which
    // matters when a sidebar and a workflow panel share the window.
    const mainWidth = document.getElementById('main-canvas-area')?.getBoundingClientRect().width
      ?? window.innerWidth;
    const maxWidth = Math.max(
      PANEL_MIN_WIDTH,
      Math.min(PANEL_MAX_WIDTH, current + mainWidth - MAIN_MIN_WIDTH),
    );
    const clamped = Math.round(Math.min(maxWidth, Math.max(PANEL_MIN_WIDTH, width)));
    document.documentElement.style.setProperty(variable, `${clamped}px`);
    window.cancelAnimationFrame(frameRef.current);
    frameRef.current = window.requestAnimationFrame(() => bridge.imf.updateSize());
  };

  const startDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = currentWidth();
    const handle = event.currentTarget;
    const onMove = (move: PointerEvent) => {
      const delta = move.clientX - startX;
      applyWidth(startWidth + (growsLeftwards ? -delta : delta));
    };
    const stop = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', stop);
      window.removeEventListener('pointercancel', stop);
      handle.classList.remove('panel-resizer--active');
      document.body.classList.remove('panel-resizing');
      stopDragRef.current = () => {};
      bridge.imf.updateSize();
    };
    stopDragRef.current = stop;
    handle.classList.add('panel-resizer--active');
    document.body.classList.add('panel-resizing');
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', stop);
    window.addEventListener('pointercancel', stop);
  };

  const onKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    const step = growsLeftwards ? -PANEL_KEYBOARD_STEP : PANEL_KEYBOARD_STEP;
    if (event.key === 'ArrowLeft') applyWidth(currentWidth() - step);
    else if (event.key === 'ArrowRight') applyWidth(currentWidth() + step);
    else if (event.key === 'Home' || event.key === 'Enter') applyWidth(defaultWidth);
    else return;
    event.preventDefault();
  };

  return (
    <div
      className={`panel-resizer panel-resizer--${panel}`}
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      tabIndex={0}
      onPointerDown={startDrag}
      onDoubleClick={() => applyWidth(defaultWidth)}
      onKeyDown={onKeyDown}
    />
  );
}
