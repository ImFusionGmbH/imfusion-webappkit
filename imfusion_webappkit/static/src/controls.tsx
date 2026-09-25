import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Button, Checkbox, Field, Input, Select, Slider as SliderPrimitive } from '@imfusion/web-ui';
import type { Data } from '@imfusion/sdk';
import { usePythonBridge } from './PythonBridge';
import { AnnotationList } from './AnnotationList';
import { areAliases } from './protocol';
import { recordedHint, snapToRecorded } from './static-demo/snapping';
import type { InputReference, InputSpec, Parameter } from './types';

export function useInputSelection(specs: InputSpec[]) {
  const bridge = usePythonBridge();
  const [values, setValues] = useState<Record<string, number>>({});
  const specKey = specs.map((spec) => spec.key).join('|');

  useEffect(() => {
    setValues((current) => {
      const visible = bridge.visibleData
        .map((item) => bridge.data.findIndex((candidate) => areAliases(candidate, item)))
        .filter((index) => index >= 0);
      const candidates = [...visible, ...bridge.data.map((_, index) => index)]
        .filter((index, position, all) => all.indexOf(index) === position);
      const next: Record<string, number> = {};
      specs.forEach((spec, position) => {
        const existing = current[spec.key];
        next[spec.key] = specs.length === 1 && visible.length
          ? visible[0]
          : existing >= 0 && existing < bridge.data.length
            ? existing
            : candidates[position] ?? -1;
      });
      return next;
    });
  }, [bridge.data, bridge.visibleData, specKey]);

  const references: InputReference[] = specs
    .filter((spec) => values[spec.key] >= 0)
    .map((spec) => ({ role: spec.key, index: values[spec.key] }));
  const complete = specs.every((spec) => !spec.required || values[spec.key] >= 0)
    && new Set(references.map((ref) => ref.index)).size === references.length;
  return { values, setValues, references, complete };
}

/** A single-choice dropdown built from the web-ui Select primitives, shared by
 *  dataset pickers and choice-type parameters so each call site only supplies
 *  its options. */
export function OptionSelect({
  value,
  onChange,
  placeholder,
  options,
  'aria-label': ariaLabel,
}: {
  value: string;
  onChange(value: string): void;
  placeholder: string;
  options: Array<{ value: string; label: string }>;
  'aria-label'?: string;
}) {
  return (
    // `items` lets the trigger show the option label: without it the closed
    // select renders the raw value, e.g. a dataset index instead of its name.
    <Select.Root value={value} items={options} onValueChange={(next) => onChange(String(next))}>
      <Select.Trigger aria-label={ariaLabel}>
        <Select.Value placeholder={placeholder} />
        <Select.Icon><i className="bi bi-chevron-down" aria-hidden="true" /></Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Positioner sideOffset={4}>
          <Select.Popup>
            <Select.List>
              {options.map((option) => (
                // The indicator comes first: web-ui lays an item out as a
                // narrow column for the tick and a wide one for the label, so
                // the other order squeezes the label into the narrow column
                // and drops the tick onto a second line.
                <Select.Item key={option.value} value={option.value}>
                  <Select.ItemIndicator><i className="bi bi-check" aria-hidden="true" /></Select.ItemIndicator>
                  <Select.ItemText>{option.label}</Select.ItemText>
                </Select.Item>
              ))}
            </Select.List>
          </Select.Popup>
        </Select.Positioner>
      </Select.Portal>
    </Select.Root>
  );
}

export function InputSelectors({
  specs,
  values,
  onChange,
}: {
  specs: InputSpec[];
  values: Record<string, number>;
  onChange(values: Record<string, number>): void;
}) {
  const bridge = usePythonBridge();
  return (
    <div className="operation-inputs">
      {specs.map((spec) => (
        <Field.Root className="operation-input" key={spec.key}>
          <Field.Label>{spec.label}</Field.Label>
          <OptionSelect
            value={values[spec.key] >= 0 ? String(values[spec.key]) : ''}
            onChange={(next) => onChange({ ...values, [spec.key]: Number(next) })}
            placeholder="Select dataset…"
            options={bridge.data.map((item, index) => ({
              value: String(index),
              label: item.name || `Data ${index + 1}`,
            }))}
          />
        </Field.Root>
      ))}
    </div>
  );
}

/**
 * Whether every annotation parameter has geometry behind it.
 *
 * Kept next to the field it gates so the Run button and the field agree on
 * what "filled in" means. Other parameter types always have a value.
 */
export function parametersComplete(
  parameters: Record<string, Parameter>,
  values: Record<string, unknown>,
): boolean {
  return Object.entries(parameters).every(
    ([name, parameter]) => parameter.type !== 'annotation' || Boolean(values[name]),
  );
}

/**
 * One annotation an action asks the user to draw before it runs.
 *
 * The client owns the annotation here, unlike in a workflow step: it creates
 * it, and reports the id as the parameter's value once the placement is
 * complete. The server exchanges the id for the annotation when the action
 * runs.
 *
 * Drawing happens in the viewer, which the dialog is sitting on top of, so
 * placing has to ask for the dialog to step aside through `onPlacingChange`
 * and wait for the annotation to come back complete.
 */
function AnnotationParameterField({
  annotationType,
  prompt,
  target: requested,
  value,
  onChange,
  onPlacingChange,
}: {
  annotationType: string;
  prompt: string;
  target?: Data;
  value: string;
  onChange(value: string): void;
  onPlacingChange?(placing: boolean): void;
}) {
  const bridge = usePythonBridge();
  // Whatever is on screen, for the callers that have no input selection to
  // name a dataset with.
  const target = requested ?? bridge.visibleData[0] ?? bridge.data[0];
  // The annotation being drawn, which is not the parameter's value yet: an
  // id only becomes the value once there is geometry behind it, so Run cannot
  // fire on a half-drawn annotation.
  const [placing, setPlacing] = useState<string | null>(null);
  const drawn = bridge.annotations.find((annotation) => annotation.id === placing);
  const chosen = bridge.annotations.find((annotation) => annotation.id === value);

  const finish = useRef(onChange);
  finish.current = onChange;
  const report = useRef(onPlacingChange);
  report.current = onPlacingChange;

  const stop = useCallback((id: string | null) => {
    setPlacing(null);
    report.current?.(false);
    if (id) finish.current(id);
  }, []);

  useEffect(() => {
    if (!placing || !drawn) return;
    // Abandoned placement leaves an annotation the SDK will not re-arm, so it
    // goes rather than sitting in the list as something that cannot be drawn.
    if (drawn.creation === 'aborted') {
      bridge.removeAnnotation(placing);
      stop(null);
    } else if (drawn.creation === 'finished') {
      stop(placing);
    }
  }, [bridge, drawn?.creation, placing, stop]);

  const place = () => {
    if (!target) return;
    // An annotation is only drawn in its own dataset's views, so asking for
    // one on a dataset the user cannot see gives them nothing to draw on.
    // Shown on its own rather than added to what is already there: a single
    // input follows the visible dataset, so leaving another one in front of it
    // would pull the action's own choice away from the annotation.
    if (!bridge.visibleData.some((item) => areAliases(item, target))) {
      bridge.setVisibleData([target]);
    }
    const id = bridge.createAnnotation(annotationType, target);
    if (!id) return;
    onChange('');
    setPlacing(id);
    report.current?.(true);
  };

  const cancel = () => {
    if (placing) bridge.removeAnnotation(placing);
    stop(null);
  };

  return (
    <div className="parameter-annotation">
      {chosen && (
        <AnnotationList
          annotations={[{
            id: chosen.id,
            type: chosen.type,
            name: prompt,
            label: '',
            points: chosen.points,
            max_points: null,
            complete: chosen.complete,
            editing: chosen.editing,
            error: '',
            length: null,
            angle: null,
          }]}
        />
      )}
      <div className="parameter-annotation__actions">
        <Button
          size="sm"
          variant="primary"
          startIcon={<i className="bi bi-vector-pen" />}
          disabled={!target || Boolean(placing)}
          onClick={place}
        >
          {chosen ? 'Place Again' : 'Place'}
        </Button>
      </div>
      {!target && (
        <Field.Description>Load a dataset to place this annotation.</Field.Description>
      )}
      {placing && (
        <PlacementPrompt
          prompt={prompt}
          target={target?.name ?? ''}
          points={drawn?.points.length ?? 0}
          onCancel={cancel}
        />
      )}
    </div>
  );
}

/**
 * What the user sees while the dialog is out of the way.
 *
 * Rendered at the document root: the dialog that owns this field is hidden
 * while placing, so a prompt inside it would be hidden too.
 */
function PlacementPrompt({
  prompt,
  target,
  points,
  onCancel,
}: {
  prompt: string;
  target: string;
  points: number;
  onCancel(): void;
}) {
  return createPortal(
    (
      <div className="placement-prompt" role="status">
        <i className="bi bi-vector-pen" aria-hidden="true" />
        <span className="placement-prompt__text">
          Draw <strong>{prompt}</strong>
          {target ? ` on ${target}` : ''}
          {/* Placing a shape takes several clicks, and the count is how the
              user can tell the viewer is registering them. */}
          {points > 0 ? ` — ${points} point${points === 1 ? '' : 's'} so far` : ''}
        </span>
        <Button size="sm" variant="secondary" onClick={onCancel}>Cancel</Button>
      </div>
    ),
    document.body,
  );
}

export function ParameterFields({
  parameters,
  values,
  onChange,
  annotationTarget,
  onPlacingChange,
}: {
  parameters: Record<string, Parameter>;
  values: Record<string, unknown>;
  onChange(values: Record<string, unknown>): void;
  /** Dataset a new annotation attaches to, which for an action is the one it
   *  is about to run on rather than whichever happens to be on screen. */
  annotationTarget?: Data;
  /** Raised while the user is drawing, so a dialog can step out of the way. */
  onPlacingChange?(placing: boolean): void;
}) {
  // What is being typed, before it is snapped. Committing on every keystroke
  // would snap "1" on the way to "150", so a snapped field commits on blur.
  const [drafts, setDrafts] = useState<Record<string, string>>({});

  return (
    <div className="algorithm-parameters">
      {Object.entries(parameters).map(([name, parameter]) => {
        const allowed = parameter.allowed_values;
        const commit = (value: unknown) => onChange({
          ...values,
          [name]: allowed ? snapToRecorded(value, allowed) : value,
        });
        // An explicit empty label, e.g. for a field named by a placeholder
        // instead, omits the label rather than falling back to the name.
        const label = parameter.label
          ? `${parameter.label}${parameter.unit ? ` (${parameter.unit})` : ''}`
          : null;
        return (
          <Field.Root className="parameter-item" key={name} title={parameter.description}>
            {label && <Field.Label>{label}</Field.Label>}
            {parameter.type === 'annotation' ? (
              <AnnotationParameterField
                annotationType={parameter.annotation_type ?? ''}
                prompt={parameter.label || name}
                target={annotationTarget}
                value={String(values[name] ?? '')}
                onChange={commit}
                onPlacingChange={onPlacingChange}
              />
            ) : parameter.type === 'bool' ? (
              <Checkbox.Root
                checked={Boolean(values[name])}
                disabled={allowed?.length === 1}
                onCheckedChange={commit}
              >
                <Checkbox.Indicator><i className="bi bi-check" aria-hidden="true" /></Checkbox.Indicator>
              </Checkbox.Root>
            ) : parameter.type === 'choice' ? (
              <OptionSelect
                value={String(values[name] ?? '')}
                onChange={commit}
                placeholder="Select…"
                options={(parameter.options ?? [])
                  .filter((option) => !allowed || allowed.includes(option))
                  .map((option) => ({ value: option, label: option }))}
              />
            ) : (
              <Input
                type={parameter.type === 'string' ? 'text' : 'number'}
                value={drafts[name] ?? String(values[name] ?? '')}
                placeholder={parameter.placeholder}
                min={parameter.min}
                max={parameter.max}
                step={parameter.step ?? (
                  parameter.type === 'int' ? 1 : parameter.type === 'float' ? 0.01 : undefined
                )}
                onChange={(event) => {
                  const text = event.target.value;
                  if (allowed) {
                    setDrafts((current) => ({ ...current, [name]: text }));
                    return;
                  }
                  commit(parameter.type === 'string' ? text : Number(text));
                }}
                onBlur={(event) => {
                  if (!allowed) return;
                  const text = event.target.value;
                  commit(parameter.type === 'string' ? text : Number(text));
                  setDrafts(({ [name]: _dropped, ...rest }) => rest);
                }}
              />
            )}
            {allowed && <Field.Description>{recordedHint(allowed)}</Field.Description>}
          </Field.Root>
        );
      })}
    </div>
  );
}

export function Slider({
  label,
  value,
  min,
  max,
  step = 1,
  decimals,
  unit,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  /** Digits after the decimal point in the readout. Defaults from `step`. */
  decimals?: number;
  /** Appended to the readout, e.g. "mm". */
  unit?: string;
  onChange(value: number): void;
}) {
  const digits = decimals ?? (step < 1 ? 2 : 0);
  return (
    <div className="windowing__control-group">
      <SliderPrimitive.Root
        value={value}
        min={min}
        max={max}
        step={step}
        onValueChange={(next) => onChange(Array.isArray(next) ? next[0] : next)}
      >
        <SliderPrimitive.Label className="control-label">{label}</SliderPrimitive.Label>
        <div className="windowing__slider-group">
          <SliderPrimitive.Control className="windowing__slider-control">
            <SliderPrimitive.Track>
              <SliderPrimitive.Indicator />
              <SliderPrimitive.Thumb />
            </SliderPrimitive.Track>
          </SliderPrimitive.Control>
          <SliderPrimitive.Value className="windowing__slider-value">
            {() => `${value.toFixed(digits)}${unit ? ` ${unit}` : ''}`}
          </SliderPrimitive.Value>
        </div>
      </SliderPrimitive.Root>
    </div>
  );
}
