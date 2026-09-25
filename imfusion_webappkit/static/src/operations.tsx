import { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Field } from '@imfusion/web-ui';
import { Modal } from './Modal';
import { usePythonBridge } from './PythonBridge';
import {
  InputSelectors,
  OptionSelect,
  ParameterFields,
  parametersComplete,
  useInputSelection,
} from './controls';
import type { ActionDescriptor, InputReference, InputSpec } from './types';

/** Ask the server once per input selection, after the client is idle.
 *
 *  Waiting for idle is what keeps a probe from naming an index the server
 *  does not hold yet. Remembering the last key is what keeps the probe's own
 *  completion from looking like a reason to ask again. */
function useIdleProbe(busy: boolean, key: string | null, probe: () => void) {
  const sentKey = useRef<string | null>(null);
  const probeRef = useRef(probe);
  probeRef.current = probe;
  useEffect(() => {
    if (key === null) {
      sentKey.current = null;
      return;
    }
    if (busy) return;
    if (sentKey.current === key) return;
    sentKey.current = key;
    probeRef.current();
  }, [busy, key]);
}

function selectionProbeKey(
  complete: boolean,
  references: InputReference[],
): string | null {
  return complete && references.length
    ? references.map((ref) => ref.index).join('|')
    : null;
}

export function ActionControl({ action }: { action: ActionDescriptor }) {
  const bridge = usePythonBridge();
  const selection = useInputSelection(action.inputs);
  const [dialogOpen, setDialogOpen] = useState(false);
  const defaults = useMemo(
    () => Object.fromEntries(
      Object.entries(action.parameters).map(([name, parameter]) => [
        name,
        parameter.default ?? parameter.value,
      ]),
    ),
    [action.parameters],
  );
  const [parameterValues, setParameterValues] = useState<Record<string, unknown>>(defaults);
  const hasParameters = Object.keys(action.parameters).length > 0;
  const usesDialog = action.inputs.length > 1 || hasParameters;
  const parametersReady = parametersComplete(action.parameters, parameterValues);
  // An annotation is drawn in the viewer, which the dialog covers, so the
  // dialog hides itself for the duration instead of closing: closing would
  // take the dataset choice and the other parameters with it.
  const [placing, setPlacing] = useState(false);
  // Annotations belong to a dataset, and this action's is one of its inputs
  // rather than whichever happens to be on screen.
  //
  // TODO: let a parameter name the input it belongs to. Taking the first is
  // right for the single-input actions that ask for a region of their own
  // image, but an action over two images cannot say which one it means, and
  // `AnnotationParameter` has no field for it.
  const annotationTarget = bridge.data[selection.values[action.inputs[0]?.key ?? '']];

  useEffect(() => setParameterValues(defaults), [defaults]);

  if (action.is_app_only && !hasParameters) {
    return (
      <Button
        size="sm"
        variant="outline"
        startIcon={<i className="bi bi-gear" />}
        disabled={bridge.busy.active}
        onClick={() => bridge.executeAction(action.name)}
      >
        {action.name}
      </Button>
    );
  }
  if (usesDialog) {
    return (
      <>
        <Button
          size="sm"
          variant="outline"
          startIcon={<i className="bi bi-gear" />}
          disabled={(action.inputs.length > 0 && !bridge.data.length) || bridge.busy.active}
          onClick={() => setDialogOpen(true)}
        >
          {action.name}
        </Button>
        {dialogOpen && (
          <Modal
            title={action.name}
            hidden={placing}
            onClose={() => setDialogOpen(false)}
            footer={(
              <>
                <Button size="sm" variant="secondary" onClick={() => setDialogOpen(false)}>Cancel</Button>
                {hasParameters && (
                  <Button size="sm" variant="secondary" onClick={() => setParameterValues(defaults)}>
                    Reset
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="primary"
                  startIcon={<i className="bi bi-play-fill" />}
                  disabled={!selection.complete || !parametersReady || bridge.busy.active}
                  onClick={() => {
                    bridge.executeAction(action.name, selection.references, parameterValues);
                    setDialogOpen(false);
                  }}
                >
                  Run
                </Button>
              </>
            )}
          >
            {action.inputs.length > 0 && (
              <>
                <p>Select the datasets to use for each input.</p>
                <InputSelectors
                  specs={action.inputs}
                  values={selection.values}
                  onChange={selection.setValues}
                />
              </>
            )}
            {hasParameters && (
              <ParameterFields
                parameters={action.parameters}
                values={parameterValues}
                onChange={setParameterValues}
                annotationTarget={annotationTarget}
                onPlacingChange={setPlacing}
              />
            )}
            {action.inputs.length > 0 && !selection.complete && (
              <div className="modal__error">
                Select a different dataset for every required input.
              </div>
            )}
            {selection.complete && !parametersReady && (
              <div className="modal__error">
                Place every annotation this action needs.
              </div>
            )}
          </Modal>
        )}
      </>
    );
  }
  return (
    <Button
      size="sm"
      variant="outline"
      startIcon={<i className="bi bi-gear" />}
      disabled={!selection.complete || bridge.busy.active}
      onClick={() => bridge.executeAction(action.name, selection.references)}
    >
      {action.name}
    </Button>
  );
}

export function AlgorithmPanel({ onExecute }: { onExecute?: () => void } = {}) {
  const bridge = usePythonBridge();
  const [inputCount, setInputCount] = useState(1);
  const inputSpecs = useMemo<InputSpec[]>(
    () => Array.from({ length: inputCount }, (_, index) => ({
      key: `input${index + 1}`,
      label: `Input ${index + 1}`,
      required: true,
    })),
    [inputCount],
  );
  const inputSelection = useInputSelection(inputSpecs);
  const [selectedId, setSelectedId] = useState('');
  const selected = bridge.algorithms.find((algorithm) => algorithm.id === selectedId);
  const [values, setValues] = useState<Record<string, unknown>>({});

  useEffect(() => {
    if (!selected) return;
    setValues(Object.fromEntries(Object.entries(selected.parameters).map(([name, parameter]) => [name, parameter.value])));
  }, [selected]);

  // These indices are positions in the server's data model, and a dataset the
  // browser has finished loading does not have one until the upload lands.
  const busy = bridge.busy.active;
  useIdleProbe(
    busy,
    selectionProbeKey(inputSelection.complete, inputSelection.references),
    () => bridge.discoverAlgorithms(inputSelection.references),
  );

  if (!bridge.visibleData.length) {
    return (
      <div className="sidebar__empty">
        <i className="bi bi-cpu" aria-hidden="true" />
        <span>Load data to discover algorithms</span>
      </div>
    );
  }

  return (
    <div className="sidebar__widget-content">
      <InputSelectors
        specs={inputSpecs}
        values={inputSelection.values}
        onChange={inputSelection.setValues}
      />
      <div className="operation-inputs__actions">
        {inputCount > 1 && (
          <button
            className="icon-button"
            title="Remove input"
            aria-label="Remove input"
            onClick={() => setInputCount((count) => count - 1)}
          >
            <i className="bi bi-dash-lg" />
          </button>
        )}
        <button
          className="icon-button"
          title="Add input"
          aria-label="Add input"
          onClick={() => setInputCount((count) => count + 1)}
        >
          <i className="bi bi-plus-lg" />
        </button>
      </div>
      <div className="operation-section">
        <Field.Root>
          <Field.Label>Algorithm</Field.Label>
          <OptionSelect
            value={selectedId}
            onChange={setSelectedId}
            placeholder="Select an algorithm…"
            options={bridge.algorithms.map((algorithm) => ({ value: algorithm.id, label: algorithm.name }))}
          />
        </Field.Root>
        {selected && <ParameterFields parameters={selected.parameters} values={values} onChange={setValues} />}
        <Button
          size="sm"
          variant="primary"
          className="button--compute"
          startIcon={<i className="bi bi-play-fill" />}
          disabled={!selected || !inputSelection.complete || bridge.busy.active}
          onClick={() => {
            if (!selected) return;
            bridge.executeAlgorithm(selected.id, values, inputSelection.references);
            onExecute?.();
          }}
        >
          Compute
        </Button>
      </div>
    </div>
  );
}

export function AlgorithmControl() {
  const bridge = usePythonBridge();
  const [dialogOpen, setDialogOpen] = useState(false);

  return (
    <>
      <Button
        size="sm"
        variant="outline"
        startIcon={<i className="bi bi-gear" />}
        disabled={!bridge.data.length || bridge.busy.active}
        onClick={() => setDialogOpen(true)}
      >
        Algorithms
      </Button>
      {dialogOpen && (
        <Modal
          title="Algorithms"
          className="modal--wide"
          onClose={() => setDialogOpen(false)}
        >
          <AlgorithmPanel onExecute={() => setDialogOpen(false)} />
        </Modal>
      )}
    </>
  );
}

export function ControllerContent({ name, onExecute }: { name: string; onExecute?: () => void }) {
  const bridge = usePythonBridge();
  const descriptor = bridge.config.algorithm_controllers.find((item) => item.name === name);
  const inputSelection = useInputSelection(descriptor?.inputs ?? []);
  const controller = bridge.controllers.find((item) => item.name === name);
  const [values, setValues] = useState<Record<string, unknown>>({});

  useEffect(() => {
    if (!controller) return;
    setValues(Object.fromEntries(Object.entries(controller.parameters).map(([key, parameter]) => [key, parameter.value])));
  }, [controller]);

  // As in AlgorithmPanel: the indices only mean something to the server once
  // it holds the data, so this waits out the sync rather than asking early.
  const busy = bridge.busy.active;
  const selectionKey = selectionProbeKey(
    inputSelection.complete,
    inputSelection.references,
  );
  useIdleProbe(
    busy,
    selectionKey === null ? null : `${name}:${selectionKey}`,
    () => bridge.checkController(name, inputSelection.references),
  );

  if (!controller?.compatible) {
    return (
      <>
        {descriptor && (
          <InputSelectors specs={descriptor.inputs} values={inputSelection.values} onChange={inputSelection.setValues} />
        )}
        <div className="sidebar__empty">
          <i
            className={`bi ${bridge.data.length ? 'bi-exclamation-triangle' : 'bi-cpu'}`}
            aria-hidden="true"
          />
          <span>
            {bridge.data.length
              ? 'Algorithm is not compatible with the selected inputs'
              : 'Load data to use this algorithm'}
          </span>
        </div>
      </>
    );
  }
  return (
    <div className="sidebar__widget-content">
      {descriptor && (
        <InputSelectors specs={descriptor.inputs} values={inputSelection.values} onChange={inputSelection.setValues} />
      )}
      <ParameterFields parameters={controller.parameters} values={values} onChange={setValues} />
      <Button
        size="sm"
        variant="primary"
        className="button--compute"
        startIcon={<i className="bi bi-play-fill" />}
        disabled={!inputSelection.complete || bridge.busy.active}
        onClick={() => {
          bridge.executeController(name, values, inputSelection.references);
          onExecute?.();
        }}
      >
        Compute
      </Button>
    </div>
  );
}

export function AlgorithmControllerControl({ name, title }: { name: string; title: string }) {
  const bridge = usePythonBridge();
  const [dialogOpen, setDialogOpen] = useState(false);
  return (
    <>
      <Button
        size="sm"
        variant="outline"
        startIcon={<i className="bi bi-gear" />}
        disabled={!bridge.data.length || bridge.busy.active}
        onClick={() => setDialogOpen(true)}
      >
        {title}
      </Button>
      {dialogOpen && (
        <Modal title={title} className="modal--wide" onClose={() => setDialogOpen(false)}>
          <ControllerContent name={name} onExecute={() => setDialogOpen(false)} />
        </Modal>
      )}
    </>
  );
}
