import { useRef, useState, type ChangeEvent, type DragEvent } from 'react';
import { Button } from '@imfusion/web-ui';
import { usePythonBridge } from './PythonBridge';
import { droppedFiles } from './fileDrop';

export function SampleDatasets({ compact = false, onImport }: { compact?: boolean; onImport?: () => void }) {
  const bridge = usePythonBridge();
  if (!bridge.config.sample_datasets.length) return null;

  return (
    <section className={`landing-page__examples-panel ${compact ? 'landing-page__examples-panel--compact' : ''}`}>
      <h2 className="landing-page__examples-title">Sample datasets</h2>
      <div className="landing-page__examples-grid">
        {bridge.config.sample_datasets.map((dataset) => (
          <button
            className={`landing-page__example-card ${dataset.thumbnail_url ? '' : 'landing-page__example-card--text-only'}`}
            key={dataset.data_url}
            type="button"
            disabled={bridge.busy.active}
            onClick={() => {
              onImport?.();
              void bridge.loadSampleDataset(dataset);
            }}
          >
            {dataset.thumbnail_url && (
              <img
                className="landing-page__example-thumbnail"
                src={dataset.thumbnail_url}
                alt=""
              />
            )}
            <span className="landing-page__example-name">{dataset.name}</span>
          </button>
        ))}
      </div>
    </section>
  );
}

export function DropZone({
  compact = false,
  dialog = false,
  message,
  onImport,
}: {
  compact?: boolean;
  dialog?: boolean;
  message?: string;
  onImport?: () => void;
}) {
  const bridge = usePythonBridge();
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const folderInput = useRef<HTMLInputElement>(null);
  const onDrop = async (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    const files = await droppedFiles(event.dataTransfer);
    if (files.length) {
      onImport?.();
      await bridge.loadFiles(files);
    }
  };
  const rootClass = compact
    ? 'workflow-step-file-upload'
    : dialog
      ? 'import-dialog'
      : 'landing-page';

  return (
    <div
      className={`${rootClass} ${dragging ? 'drag-over' : ''}`}
      onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
    >
      <div className={compact ? '' : 'landing-page__content'}>
        <div className={compact ? '' : 'landing-page__load-panel'}>
          {!compact && bridge.config.branding.landing_page_title && (
            <h2 className="landing-page__title">{bridge.config.branding.landing_page_title}</h2>
          )}
          <div className="file-picker-buttons">
            <Button
              size={compact ? 'sm' : 'md'}
              variant={compact ? 'secondary' : 'primary'}
              startIcon={<i className="bi bi-file-earmark-arrow-up" />}
              disabled={bridge.busy.active}
              onClick={() => {
                if (input.current) input.current.value = '';
                input.current?.click();
              }}
            >
              Choose Files
            </Button>
            <Button
              size={compact ? 'sm' : 'md'}
              variant="secondary"
              startIcon={<i className="bi bi-folder2-open" />}
              disabled={bridge.busy.active}
              onClick={() => {
                if (folderInput.current) folderInput.current.value = '';
                folderInput.current?.click();
              }}
            >
              Choose Folder
            </Button>
          </div>
          <span className="landing-page__message">
            {message
              ?? (compact ? null : bridge.config.branding.landing_page_message)
              ?? 'or drag and drop here'}
          </span>
          <input
            ref={input}
            hidden
            type="file"
            multiple
            onChange={(event: ChangeEvent<HTMLInputElement>) => {
              const files = Array.from(event.target.files ?? []);
              if (files.length) {
                onImport?.();
                void bridge.loadFiles(files);
              }
            }}
          />
          <input
            ref={(element) => {
              folderInput.current = element;
              element?.setAttribute('webkitdirectory', '');
            }}
            hidden
            type="file"
            multiple
            onChange={(event: ChangeEvent<HTMLInputElement>) => {
              const files = Array.from(event.target.files ?? []);
              if (files.length) {
                onImport?.();
                void bridge.loadFiles(files);
              }
            }}
          />
        </div>
        {!compact && <SampleDatasets onImport={onImport} />}
      </div>
    </div>
  );
}
