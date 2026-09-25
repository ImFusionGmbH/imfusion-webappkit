import { useEffect, useState, type ReactNode } from 'react';
import { Button, Field } from '@imfusion/web-ui';
import { usePythonBridge } from '../PythonBridge';
import { DropZone, SampleDatasets } from '../DropZone';
import { PanelResizer } from '../PanelResizer';
import { OptionSelect, ParameterFields } from '../controls';
import { exportFormatLabel } from '../formatting';
import type { ExportFormat, WorkflowStep } from '../types';
import { WorkflowAnnotationStep } from './AnnotationStep';
import { WorkflowBrushStep } from './BrushStep';
import { WorkflowCustomStep } from './elements';

function WorkflowParameterStep({ step }: { step: WorkflowStep }) {
  const bridge = usePythonBridge();
  const parameters = step.ui_config.parameters ?? [];
  const descriptors = Object.fromEntries(parameters.map((parameter) => [parameter.name, parameter]));
  const [values, setValues] = useState<Record<string, unknown>>(
    Object.fromEntries(parameters.map((parameter) => [parameter.name, parameter.value ?? parameter.default ?? ''])),
  );

  return (
    <ParameterFields
      parameters={descriptors}
      values={values}
      onChange={(next) => {
        setValues(next);
        bridge.sendWorkflowData({ parameters: next });
      }}
    />
  );
}

function WorkflowStage({
  number,
  title,
  pending = false,
  children,
}: {
  number: number;
  title: string;
  pending?: boolean;
  children: ReactNode;
}) {
  return (
    <section className={`workflow-step-stage ${pending ? 'workflow-step-stage--pending' : ''}`}>
      <h3 className="workflow-step-stage__title">
        <span className="workflow-step-stage__number">{number}</span>
        {title}
      </h3>
      {children}
    </section>
  );
}

function WorkflowInputSelectionStep({ step }: { step: WorkflowStep }) {
  const bridge = usePythonBridge();
  const config = step.ui_config;
  const specs = config.inputs ?? [];
  const datasets = config.datasets ?? [];
  const [values, setValues] = useState<Record<string, number>>(config.values ?? {});

  useEffect(() => setValues(config.values ?? {}), [step.id, config.values]);

  const options = datasets.map((dataset) => ({
    value: String(dataset.index),
    label: dataset.name || `Data ${dataset.index + 1}`,
  }));
  const selectors = datasets.length ? (
    specs.map((spec) => (
      <Field.Root className="operation-input" key={spec.key}>
        <Field.Label>{spec.label}</Field.Label>
        <OptionSelect
          value={options.some((option) => option.value === String(values[spec.key]))
            ? String(values[spec.key])
            : ''}
          onChange={(next) => {
            const nextValues = { ...values, [spec.key]: Number(next) };
            setValues(nextValues);
            bridge.sendWorkflowData({ inputs: nextValues });
          }}
          placeholder="Select dataset…"
          options={options}
        />
      </Field.Root>
    ))
  ) : (
    // Without data the pickers would only offer an empty list, so name the
    // missing prerequisite instead. The server owns this list, so it is also
    // empty for as long as an upload is in flight — and by then the visitor can
    // see their data in the viewer, so being told nothing is loaded reads as a
    // bug rather than as an instruction.
    <p className="workflow-step-stage__hint">
      {bridge.busy.active
        ? bridge.busy.detail ?? bridge.busy.label
        : 'Nothing is loaded yet.'}
    </p>
  );

  // Loading and assigning are two separate moves, and the assignment half is
  // useless until the first one happened: number them so the order is obvious.
  const showSamples = config.allow_sample_datasets && bridge.config.sample_datasets.length > 0;
  if (!config.allow_upload && !showSamples) {
    return <div className="workflow-step-inputs">{selectors}</div>;
  }

  return (
    <div className="workflow-step-inputs">
      <WorkflowStage number={1} title="Load data">
        {config.allow_upload && (
          <DropZone compact message={config.message ?? 'Load datasets, then assign each input role.'} />
        )}
        {showSamples && <SampleDatasets compact />}
      </WorkflowStage>
      <WorkflowStage
        number={2}
        title={specs.length > 1 ? 'Assign inputs' : 'Select input'}
        pending={!datasets.length}
      >
        {selectors}
      </WorkflowStage>
    </div>
  );
}

function WorkflowExportStep({ step }: { step: WorkflowStep }) {
  const bridge = usePythonBridge();
  const formats = (step.ui_config.formats ?? bridge.config.export_formats) as ExportFormat[];
  const [format, setFormat] = useState<ExportFormat>(formats[0] ?? 'imf');

  useEffect(() => {
    if (!formats.includes(format)) setFormat(formats[0] ?? 'imf');
  }, [format, formats.join('|')]);

  return (
    <div className="workflow-step-export">
      <p className="workflow-step-export__message">
        {step.ui_config.message ?? 'Export your results'}
      </p>
      <div className="workflow-step-export__format">
        <OptionSelect
          aria-label="Export format"
          value={format}
          onChange={(value) => setFormat(value as ExportFormat)}
          placeholder="Select a format…"
          options={formats.map((value) => ({ value, label: exportFormatLabel(value) }))}
        />
      </div>
      <Button
        size="sm"
        variant="primary"
        onClick={async () => {
          if (await bridge.exportAll(format)) bridge.sendWorkflowData({ exported: true });
        }}
      >
        {step.ui_config.exported ? 'Export Again' : 'Export'}
      </Button>
      {step.ui_config.exported && (
        <p className="workflow-step-export__confirmation" role="status">
          <i className="bi bi-check-circle" /> Export complete. Your download has started.
        </p>
      )}
    </div>
  );
}

function WorkflowContent({ step }: { step: WorkflowStep }) {
  const bridge = usePythonBridge();
  const config = step.ui_config;
  switch (config.type) {
    case 'data_selection':
      return <WorkflowInputSelectionStep step={step} />;
    case 'parameters':
      return <WorkflowParameterStep step={step} />;
    case 'brush':
      return <WorkflowBrushStep step={step} />;
    case 'annotation':
      return <WorkflowAnnotationStep step={step} />;
    case 'processing': {
      const manual = config.auto_run === false;
      const running = manual && bridge.status === 'processing' && !config.completed && !config.error;
      const stateClass = config.error
        ? 'workflow-step-processing--error'
        : config.completed
          ? 'workflow-step-processing--complete'
          : '';
      return (
        <div className={`workflow-step-processing ${stateClass}`}>
          {(!manual || running) && <div className="workflow-step-processing__spinner" />}
          <p className="workflow-step-processing__text">
            {config.error
              ? `Processing failed: ${config.error}`
              : running
                ? 'Processing…'
                : config.message ?? 'Processing…'}
          </p>
          {manual && !config.completed && !running && (
            <Button
              size="sm"
              variant="primary"
              onClick={() => bridge.workflowRun()}
            >
              {config.run_label ?? 'Run'}
            </Button>
          )}
          {config.error && !manual && (
            <p className="workflow-step-processing__guidance">Go back, adjust the settings, and try again.</p>
          )}
        </div>
      );
    }
    case 'validation': {
      const hasDecision = config.accepted === true || config.accepted === false;
      return (
        <div className="workflow-step-validation">
          <p>{config.message ?? 'Is this result acceptable?'}</p>
          <div className="workflow-step-validation__buttons">
            <Button
              size="sm"
              variant="negative"
              className={config.accepted === false ? 'button--selected' : hasDecision ? 'button--unselected' : ''}
              aria-pressed={config.accepted === false}
              onClick={() => bridge.sendWorkflowData({ accepted: false })}
            >
              Reject
            </Button>
            <Button
              size="sm"
              variant="positive"
              className={config.accepted === true ? 'button--selected' : hasDecision ? 'button--unselected' : ''}
              aria-pressed={config.accepted === true}
              onClick={() => bridge.sendWorkflowData({ accepted: true })}
            >
              Accept
            </Button>
          </div>
        </div>
      );
    }
    case 'export':
      return <WorkflowExportStep step={step} />;
    case 'custom':
      return <WorkflowCustomStep step={step} />;
    default:
      return <div className="workflow-step-message">{config.message}</div>;
  }
}

export function WorkflowPanel() {
  const bridge = usePythonBridge();
  const workflow = bridge.workflow;
  if (!bridge.config.workflow_enabled || !workflow?.current_step) return null;
  const percent = ((workflow.current_index + 1) / Math.max(1, workflow.total_steps)) * 100;

  return (
    <>
      {bridge.config.layout.workflow_panel_resizable && (
        <PanelResizer
          panel="workflow-panel"
          variable="--workflow-panel-width"
          label="Resize workflow panel"
          defaultWidth={bridge.config.layout.workflow_panel_width}
          growsLeftwards={bridge.config.layout.workflow_panel_position === 'right'}
        />
      )}
      <aside className="workflow-panel">
        <div className="workflow-panel__progress">
          <div className="workflow-panel__progress-bar"><div className="workflow-panel__progress-fill" style={{ width: `${percent}%` }} /></div>
          <div className="workflow-panel__progress-text">Step {workflow.current_index + 1} of {workflow.total_steps}</div>
        </div>
        <div className="workflow-panel__step">
          <h2 className="workflow-panel__step-title">{workflow.current_step.title}</h2>
          <div className="workflow-panel__step-content"><WorkflowContent step={workflow.current_step} /></div>
        </div>
        <div className="workflow-panel__nav">
          <Button
            size="sm"
            variant="secondary"
            className="button--workflow-nav button--workflow-back"
            disabled={!workflow.can_go_back || bridge.busy.active}
            onClick={bridge.workflowBack}
          >
            Back
          </Button>
          <div className="workflow-panel__nav-spacer" />
          <Button
            size="sm"
            variant="primary"
            className="button--workflow-nav button--workflow-next"
            disabled={!workflow.can_proceed || bridge.busy.active}
            onClick={bridge.workflowNext}
          >
            {workflow.is_last_step ? 'Finish' : 'Next'}
          </Button>
        </div>
        <div className="workflow-panel__indicators">
          {workflow.steps.map((step, index) => (
            <span
              key={step.id}
              className={`workflow-panel__indicator ${index === workflow.current_index ? 'workflow-panel__indicator--active' : step.completed ? 'workflow-panel__indicator--completed' : ''}`}
            />
          ))}
        </div>
      </aside>
    </>
  );
}
