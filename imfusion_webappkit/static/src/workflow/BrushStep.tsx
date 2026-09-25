import { useCallback, useEffect, useRef, useState } from 'react';
import type { SharedImageSet } from '@imfusion/sdk';
import { Button, Field } from '@imfusion/web-ui';
import { usePythonBridge } from '../PythonBridge';
import { OptionSelect, Slider } from '../controls';
import type { WorkflowStep } from '../types';

export function WorkflowBrushStep({ step }: { step: WorkflowStep }) {
  const bridge = usePythonBridge();
  const config = step.ui_config;
  const imageIndex = config.image_index;
  const labelMapIndex = config.label_map_index ?? null;
  const labelValues = config.labels ?? [1];
  const entryToken = config.entry_token ?? 0;
  const initialRadius = config.radius_mm ?? 10;
  const initialAdaptiveness = config.adaptiveness ?? 0.5;

  const [radius, setRadius] = useState(initialRadius);
  const [radiusRange, setRadiusRange] = useState<[number, number]>([1, 50]);
  const [adaptiveness, setAdaptiveness] = useState(initialAdaptiveness);
  const [selectedLabel, setSelectedLabel] = useState(labelValues[0] ?? 1);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(Boolean(config.committed));
  const [active, setActive] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [canReset, setCanReset] = useState(false);

  const imageRef = useRef<SharedImageSet | null>(null);
  const labelMapRef = useRef<SharedImageSet | null>(null);
  const targetIndexRef = useRef<number | null>(labelMapIndex);
  const snapshotRef = useRef<Uint8Array | null>(null);
  const activeRef = useRef(false);
  const errorRef = useRef('');
  const committingRef = useRef(false);
  const resettingRef = useRef(false);
  activeRef.current = active;
  errorRef.current = error;
  committingRef.current = committing;
  resettingRef.current = resetting;

  const applyLabelSelection = useCallback(
    (value: number, labelMap: SharedImageSet) => {
      let labelConfig = bridge.imf.bindings.getLabelConfig(labelMap, value);
      if (!labelConfig) {
        bridge.imf.bindings.setDefaultLabelConfig(labelMap, value);
        labelConfig = bridge.imf.bindings.getLabelConfig(labelMap, value);
      }
      bridge.imf.brush.setLabel(value);
      if (labelConfig) bridge.imf.brush.setPreviewColor(labelConfig.color);
      return labelConfig;
    },
    [bridge.imf],
  );

  useEffect(() => {
    const image = typeof imageIndex === 'number'
      ? bridge.data[imageIndex] as SharedImageSet | undefined
      : undefined;
    const existingLabelMap = typeof labelMapIndex === 'number'
      ? bridge.data[labelMapIndex] as SharedImageSet | undefined
      : undefined;
    if (!image) {
      setError('The brush source image is not available.');
      return undefined;
    }

    const brush = bridge.imf.brush;
    try {
      const before = new Set(Array.from(bridge.imf.dataModel));
      brush.setData(image, existingLabelMap ?? null);
      const labelMap = existingLabelMap
        ?? Array.from(bridge.imf.dataModel)
          .find((item) => !before.has(item)) as SharedImageSet | undefined;
      if (!labelMap) throw new Error('The brush did not create a label map.');
      labelMap.name = config.label_map_name ?? 'Label Map';
      imageRef.current = image;
      labelMapRef.current = labelMap;
      targetIndexRef.current = existingLabelMap ? labelMapIndex : null;
      // Snapshot the label map as it stood on entry so Reset can restore it
      // later, whether or not the brush is currently active.
      snapshotRef.current = bridge.imf.bindings.save([labelMap]);
      setCanReset(true);

      labelValues.forEach((value) => {
        if (!bridge.imf.bindings.getLabelConfig(labelMap, value)) {
          bridge.imf.bindings.setDefaultLabelConfig(labelMap, value);
        }
      });
      const initialLabel = labelValues[0] ?? 1;
      applyLabelSelection(initialLabel, labelMap);

      const range = brush.radiusRangeMM() ?? [1, 50];
      const nextRadius = Math.max(range[0], Math.min(range[1], initialRadius));
      setRadiusRange([range[0], range[1]]);
      setRadius(nextRadius);
      setAdaptiveness(initialAdaptiveness);
      setSelectedLabel(initialLabel);
      setSaved(Boolean(config.committed));
      setActive(false);
      setCommitting(false);
      setError('');
      brush.setRadiusMM(nextRadius);
      brush.setAdaptiveness(initialAdaptiveness);
      brush.disable();
    } catch (reason) {
      labelMapRef.current = null;
      snapshotRef.current = null;
      setCanReset(false);
      setError(reason instanceof Error ? reason.message : String(reason));
    }

    return () => {
      brush.disable();
      labelMapRef.current = null;
      snapshotRef.current = null;
      setCanReset(false);
    };
    // Re-run only when the server enters this step anew (entryToken bumps on
    // every on_enter). label_map_index and other config fields also change
    // right after our own commits; reacting to those would reset the
    // radius/adaptiveness/label controls the user just configured.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bridge.imf, step.id, entryToken]);

  const toggleBrush = useCallback(() => {
    if (errorRef.current || committingRef.current || resettingRef.current) return;
    if (!activeRef.current) {
      bridge.sendWorkflowData({ editing: true });
      bridge.imf.brush.enable();
      setSaved(false);
      setActive(true);
      return;
    }
    const labelMap = labelMapRef.current;
    if (!labelMap) return;
    setCommitting(true);
    bridge.commitBrush(labelMap, targetIndexRef.current).then((result) => {
      setCommitting(false);
      if (result.success) {
        if (typeof result.index === 'number') targetIndexRef.current = result.index;
        bridge.imf.brush.disable();
        setActive(false);
        setSaved(true);
        setError('');
      } else {
        setError(result.message ?? 'Cannot save the label map.');
      }
    });
  }, [bridge.commitBrush, bridge.imf, bridge.sendWorkflowData]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.code !== 'Space' && event.key !== ' ') return;
      const target = event.target as HTMLElement | null;
      const tag = target?.tagName;
      const isTextEntry = tag === 'TEXTAREA'
        || Boolean(target?.isContentEditable)
        || (tag === 'INPUT' && !['range', 'checkbox', 'radio', 'button', 'submit'].includes(
          (target as HTMLInputElement).type,
        ));
      if (isTextEntry) return;
      event.preventDefault();
      toggleBrush();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [toggleBrush]);

  const handleReset = useCallback(() => {
    const stale = labelMapRef.current;
    const image = imageRef.current;
    const snapshot = snapshotRef.current;
    if (!stale || !image || !snapshot || committingRef.current || resettingRef.current) return;
    const wasActive = activeRef.current;
    setResetting(true);
    // Disable painting immediately so nothing keeps touching `stale` while
    // it is being replaced.
    bridge.imf.brush.disable();
    bridge.loadSnapshot(snapshot, config.label_map_name ?? 'Label Map')
      .then((restored) => {
        const restoredLabelMap = restored as SharedImageSet;
        labelValues.forEach((value) => {
          if (!bridge.imf.bindings.getLabelConfig(restoredLabelMap, value)) {
            bridge.imf.bindings.setDefaultLabelConfig(restoredLabelMap, value);
          }
        });
        // Rebind the brush onto the restored data before removing `stale`
        // from the data model, otherwise the brush is left with a dangling
        // reference to freed WASM memory.
        bridge.imf.brush.setData(image, restoredLabelMap);
        bridge.imf.brush.setRadiusMM(radius);
        bridge.imf.brush.setAdaptiveness(adaptiveness);
        applyLabelSelection(selectedLabel, restoredLabelMap);
        bridge.swapLocalData(stale, restoredLabelMap);
        labelMapRef.current = restoredLabelMap;
        snapshotRef.current = bridge.imf.bindings.save([restoredLabelMap]);
        if (wasActive) bridge.imf.brush.enable();
        setResetting(false);
        setError('');
      })
      .catch((reason) => {
        setResetting(false);
        if (wasActive) bridge.imf.brush.enable();
        setError(reason instanceof Error ? reason.message : String(reason));
      });
  }, [
    adaptiveness,
    applyLabelSelection,
    bridge.imf,
    bridge.loadSnapshot,
    bridge.swapLocalData,
    config.label_map_name,
    labelValues,
    radius,
    selectedLabel,
  ]);

  const hasLabelPicker = labelValues.length > 1;

  return (
    <div className="workflow-step-brush">
      <p className="workflow-step-brush__message">
        {config.message ?? 'Start the brush, paint in the viewer, then stop it to save your edits.'}
      </p>
      {hasLabelPicker && (
        <Field.Root className="operation-input workflow-step-brush__label-select">
          <Field.Label>Label</Field.Label>
          <OptionSelect
            value={String(selectedLabel)}
            onChange={(next) => {
              const value = Number(next);
              setSelectedLabel(value);
              const labelMap = labelMapRef.current;
              if (labelMap) applyLabelSelection(value, labelMap);
            }}
            placeholder="Select a label…"
            options={labelValues.map((value) => {
              const labelMap = labelMapRef.current;
              const labelConfig = labelMap
                ? bridge.imf.bindings.getLabelConfig(labelMap, value)
                : undefined;
              const label = labelConfig?.name ? String(labelConfig.name) : '';
              return { value: String(value), label: label || `Label ${value}` };
            })}
          />
        </Field.Root>
      )}
      {config.allow_radius_change !== false && (
        <Slider
          label="Brush radius"
          value={radius}
          min={radiusRange[0]}
          max={radiusRange[1]}
          step={0.1}
          decimals={1}
          unit="mm"
          onChange={(value) => {
            setRadius(value);
            bridge.imf.brush.setRadiusMM(value);
          }}
        />
      )}
      {config.allow_adaptiveness_change !== false && (
        <Slider
          label="Adaptiveness"
          value={adaptiveness}
          min={0}
          max={1}
          step={0.01}
          onChange={(value) => {
            setAdaptiveness(value);
            bridge.imf.brush.setAdaptiveness(value);
          }}
        />
      )}
      {error && <p className="workflow-step-brush__error" role="alert">{error}</p>}
      <div className="workflow-step-brush__actions">
        <Button
          size="sm"
          variant={active ? 'negative' : 'primary'}
          className={`workflow-step-brush__toggle ${active ? 'workflow-step-brush__toggle--active' : ''}`}
          startIcon={<i className={`bi ${active ? 'bi-stop-fill' : 'bi-play-fill'}`} />}
          aria-pressed={active}
          disabled={Boolean(error) || committing || resetting}
          onClick={toggleBrush}
          title="Toggle with the Space bar"
        >
          {committing ? 'Saving…' : active ? 'Stop Brush' : 'Start Brush'}
        </Button>
        <Button
          size="sm"
          type="button"
          variant="secondary"
          className="workflow-step-brush__reset"
          startIcon={<i className="bi bi-arrow-counterclockwise" />}
          disabled={!canReset || committing || resetting}
          onClick={handleReset}
          title="Discard edits made since entering this step"
        >
          {resetting ? 'Resetting…' : 'Reset'}
        </Button>
      </div>
      {saved && (
        <p className="workflow-step-brush__confirmation" role="status">
          <i className="bi bi-check-circle" /> Label map saved.
        </p>
      )}
    </div>
  );
}
