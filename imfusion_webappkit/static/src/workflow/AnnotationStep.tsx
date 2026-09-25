import { useCallback, useEffect, useRef } from 'react';
import { useViewVisibility } from '@imfusion/sdk-react';
import { Button } from '@imfusion/web-ui';
import { usePythonBridge } from '../PythonBridge';
import { AnnotationList } from '../AnnotationList';
import type { AnnotationRole, WorkflowStep } from '../types';

type ViewName = '2d' | 'mpr' | 'axial' | 'coronal' | 'sagittal' | '3d';

/**
 * Keep the views the step allows, and only those, on screen while armed.
 *
 * The Web SDK attaches a new annotation to every view and works out its
 * visibility from its parent dataset, so there is no per-view targeting to ask
 * for. Hiding the rest is what turns the step's `views` list into a constraint
 * rather than a hint, and the previous layout is put back on exit — losing the
 * other views' context is the cost, which is why the server's defaults are
 * generous.
 */
function useAllowedViews(views: ViewName[] | undefined, active: boolean) {
  const bridge = usePythonBridge();
  const display = bridge.imf.display;
  const twoD = useViewVisibility(display.main2dView());
  const axial = useViewVisibility(display.mainAxialView());
  const coronal = useViewVisibility(display.mainCoronalView());
  const sagittal = useViewVisibility(display.mainSagittalView());
  const threeD = useViewVisibility(display.main3dView());
  const restoreRef = useRef<boolean[] | null>(null);

  const setters = [twoD, axial, coronal, sagittal, threeD];
  const allowed = views
    ? [
      views.includes('2d'),
      views.includes('mpr') || views.includes('axial'),
      views.includes('mpr') || views.includes('coronal'),
      views.includes('mpr') || views.includes('sagittal'),
      views.includes('3d'),
    ]
    : null;

  useEffect(() => {
    if (!active || !allowed || allowed.every(Boolean)) return undefined;
    restoreRef.current = setters.map((view) => view.hidden);
    setters.forEach((view, index) => {
      if (!allowed[index]) view.setHidden(true);
    });
    return () => {
      const previous = restoreRef.current;
      restoreRef.current = null;
      if (previous) setters.forEach((view, index) => view.setHidden(previous[index]));
    };
    // The setters are stable per view; re-running on `hidden` changing would
    // capture the layout this effect itself just imposed as the one to restore.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, views?.join('|')]);
}

function RolePanel({
  role,
  showMeasurements,
  armedId,
}: {
  role: AnnotationRole;
  showMeasurements: boolean;
  armedId: string | null;
}) {
  const [red, green, blue] = role.color;
  return (
    <div className="workflow-step-annotation__role">
      {role.labelled && (
        <h4 className="workflow-step-annotation__role-title">
          <span
            className="workflow-step-annotation__swatch"
            style={{
              backgroundColor: `rgb(${red * 255}, ${green * 255}, ${blue * 255})`,
            }}
          />
          {role.role}
          {role.data_name && (
            <span className="workflow-step-annotation__role-data">{role.data_name}</span>
          )}
        </h4>
      )}
      <AnnotationList
        annotations={role.annotations}
        showMeasurements={showMeasurements}
        activeId={armedId}
      />
    </div>
  );
}

export function WorkflowAnnotationStep({ step }: { step: WorkflowStep }) {
  const bridge = usePythonBridge();
  const config = step.ui_config;
  const roles = config.roles ?? [];
  const armedId = config.armed_id ?? null;
  const pendingId = config.pending_id ?? null;
  const placed = config.placed ?? 0;
  const total = config.total ?? 0;
  const armed = Boolean(armedId);

  useAllowedViews(config.views as ViewName[] | undefined, armed);

  // A crosshair is the only cue that the app is waiting for a click on the
  // canvas rather than in the panel.
  useEffect(() => {
    if (!armed) return undefined;
    const canvas = bridge.imf.canvas;
    const previous = canvas.style.cursor;
    canvas.style.cursor = 'crosshair';
    return () => { canvas.style.cursor = previous; };
  }, [armed, bridge.imf]);

  const place = useCallback(
    () => bridge.sendWorkflowData({ action: 'place' }),
    [bridge],
  );
  const clear = useCallback(
    () => bridge.sendWorkflowData({ action: 'clear' }),
    [bridge],
  );
  const redo = useCallback(
    () => bridge.sendWorkflowData({ action: 'redo' }),
    [bridge],
  );

  const activePrompt = roles
    .flatMap((role) => role.annotations)
    .find((annotation) => annotation.id === (armedId ?? pendingId))
    ?.prompt;

  return (
    <div className="workflow-step-annotation">
      <p className="workflow-step-annotation__message">
        {config.message ?? 'Press Place, then draw the annotation in the viewer.'}
      </p>
      {total > 1 && (
        <p className="workflow-step-annotation__progress" role="status">
          {placed} of {total} placed
          {activePrompt ? ` — now the ${activePrompt}` : ''}
        </p>
      )}
      {roles.map((role) => (
        <RolePanel
          key={role.role}
          role={role}
          showMeasurements={Boolean(config.show_measurements)}
          armedId={armedId}
        />
      ))}
      {config.error && (
        <p className="workflow-step-annotation__error" role="alert">{config.error}</p>
      )}
      <div className="workflow-step-annotation__actions">
        {/* Dropped once everything is placed, rather than left disabled: Redo
            and Clear are the only things left to offer. */}
        {placed < total && (
          <Button
            size="sm"
            variant="primary"
            startIcon={<i className={`bi ${armed ? 'bi-hourglass-split' : 'bi-vector-pen'}`} />}
            aria-pressed={armed}
            disabled={armed || Boolean(config.error)}
            onClick={place}
          >
            {armed ? 'Click in the viewer…' : placed ? 'Place Next' : 'Place'}
          </Button>
        )}
        {placed > 0 && (
          <Button
            size="sm"
            variant="secondary"
            startIcon={<i className="bi bi-arrow-counterclockwise" />}
            disabled={armed}
            onClick={redo}
            title="Discard the last annotation and place it again"
          >
            Redo
          </Button>
        )}
        {placed > 0 && (
          <Button
            size="sm"
            variant="secondary"
            startIcon={<i className="bi bi-trash" />}
            disabled={armed}
            onClick={clear}
          >
            Clear
          </Button>
        )}
      </div>
      {config.required === false && placed < total && (
        <p className="workflow-step-annotation__hint">This step can be skipped.</p>
      )}
    </div>
  );
}
