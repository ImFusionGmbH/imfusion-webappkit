import { useCallback, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { Button } from '@imfusion/web-ui';
import { Modal } from './Modal';
import { usePythonBridge } from './PythonBridge';
import { DropZone } from './DropZone';
import { exportFormatLabel } from './formatting';
import { ActionControl, AlgorithmControl, AlgorithmControllerControl } from './operations';
import { StatusIndicator } from './StatusIndicator';
import { OptionSelect } from './controls';
import type { ExportFormat } from './types';

/** Which edges of a horizontal scroller still have content beyond them.
 *
 * Drives the toolbar's edge fade: without a cue, a button clipped by a narrow
 * window looks like the end of the row rather than the start of the rest. */
function useScrollEdges<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [edges, setEdges] = useState({ start: false, end: false });

  const measure = useCallback(() => {
    const element = ref.current;
    if (!element) return;
    const start = element.scrollLeft > 1;
    const end = element.scrollWidth - element.clientWidth - element.scrollLeft > 1;
    // Returning the previous object lets React skip the re-render.
    setEdges((prev) => (prev.start === start && prev.end === end ? prev : { start, end }));
  }, []);

  useEffect(() => {
    const element = ref.current;
    if (!element) return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    element.addEventListener('scroll', measure, { passive: true });
    return () => {
      observer.disconnect();
      element.removeEventListener('scroll', measure);
    };
  }, [measure]);

  // An app's button set comes from its configuration, which can change the
  // scrollable width without resizing the strip itself.
  useEffect(measure);

  return { ref, edges };
}

export function Header() {
  const bridge = usePythonBridge();
  const toolbar = useScrollEdges<HTMLDivElement>();
  const logoUrl = bridge.config.branding.logo_url;
  const logoPosition = bridge.config.layout.header_logo_position;
  const titlePosition = bridge.config.layout.header_title_position;
  const logoSharesTitlePosition = Boolean(
    logoUrl && logoPosition === titlePosition,
  );
  const [exportFormat, setExportFormat] = useState<ExportFormat>(
    bridge.config.export_formats[0] ?? 'imf',
  );
  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const [exportDialogOpen, setExportDialogOpen] = useState(false);
  const [infoDialogOpen, setInfoDialogOpen] = useState(false);
  const showAlgorithmAction = bridge.config.algorithms_enabled
    && bridge.config.algorithms_placement === 'header';
  const headerAlgorithmControllers = bridge.config.algorithm_controllers
    .filter((controller) => controller.placement === 'header');
  const hasHeaderActions = (bridge.config.actions?.length ?? 0) > 0
    || showAlgorithmAction
    || headerAlgorithmControllers.length > 0;

  useEffect(() => {
    if (!bridge.config.export_formats.includes(exportFormat)) {
      setExportFormat(bridge.config.export_formats[0] ?? 'imf');
    }
  }, [bridge.config.export_formats, exportFormat]);

  return (
    <div id="header">
      {logoUrl && !logoSharesTitlePosition && (
        <img
          className="header-logo"
          src={logoUrl}
          alt=""
        />
      )}
      <div className={`header-title ${logoSharesTitlePosition ? 'header-title--with-logo' : ''}`}>
        {logoUrl && logoSharesTitlePosition && (
          <img className="header-title__logo" src={logoUrl} alt="" />
        )}
        <h1>{bridge.config.title}</h1>
      </div>
      <div className="header-controls">
        {/* One strip for every button, so a window too narrow for all of them
            scrolls instead of dropping the ones that do not fit. The status
            indicator stays outside it and keeps its place. */}
        <div
          className="header-controls__toolbar"
          ref={toolbar.ref}
          data-overflow-start={toolbar.edges.start}
          data-overflow-end={toolbar.edges.end}
        >
          <div className="header-controls__group">
            {(bridge.config.actions ?? []).map((action) => (
              <ActionControl action={action} key={action.name} />
            ))}
            {showAlgorithmAction && <AlgorithmControl />}
            {headerAlgorithmControllers.map((controller) => (
              <AlgorithmControllerControl
                key={controller.name}
                name={controller.name}
                title={controller.title || controller.name}
              />
            ))}
          </div>
          {hasHeaderActions && <div className="header-controls__separator" />}
          <div className="header-controls__group">
            {bridge.config.show_load_button && (
              <>
                <Button
                  size="sm"
                  variant="secondary"
                  startIcon={<i className="bi bi-box-arrow-in-down" />}
                  disabled={bridge.busy.active}
                  onClick={() => {
                    // A recording has nothing to import into, and saying so now
                    // beats walking the visitor through a file picker first.
                    if (!bridge.importUnavailable()) setImportDialogOpen(true);
                  }}
                >
                  Import
                </Button>
                {importDialogOpen && (
                  <Modal
                    title="Import Data"
                    className="modal--import"
                    onClose={() => setImportDialogOpen(false)}
                  >
                    <DropZone
                      dialog
                      onImport={() => setImportDialogOpen(false)}
                    />
                  </Modal>
                )}
              </>
            )}
            {bridge.config.show_export_button && (
              <>
                <Button
                  size="sm"
                  variant="secondary"
                  startIcon={<i className="bi bi-download" />}
                  disabled={!bridge.data.length || bridge.busy.active}
                  onClick={() => setExportDialogOpen(true)}
                >
                  Export
                </Button>
                {exportDialogOpen && (
                  <Modal
                    title="Export Data"
                    onClose={() => setExportDialogOpen(false)}
                    footer={(
                      <>
                        <Button size="sm" variant="secondary" onClick={() => setExportDialogOpen(false)}>
                          Cancel
                        </Button>
                        <Button
                          size="sm"
                          variant="primary"
                          startIcon={<i className="bi bi-download" />}
                          onClick={() => {
                            setExportDialogOpen(false);
                            void bridge.exportAll(exportFormat);
                          }}
                        >
                          Export
                        </Button>
                      </>
                    )}
                  >
                    <p>Select the file format for the exported datasets.</p>
                    <OptionSelect
                      aria-label="Export format"
                      value={exportFormat}
                      onChange={(value) => setExportFormat(value as ExportFormat)}
                      placeholder="Select a format…"
                      options={bridge.config.export_formats.map((format) => ({
                        value: format,
                        label: exportFormatLabel(format),
                      }))}
                    />
                  </Modal>
                )}
              </>
            )}
          </div>
          {bridge.config.info && (
            <>
              <Button
                size="sm"
                variant="secondary"
                startIcon={<i className="bi bi-info-circle" />}
                onClick={() => setInfoDialogOpen(true)}
              >
                {bridge.config.info.button_label}
              </Button>
              {infoDialogOpen && (
                <Modal
                  title={bridge.config.info.title}
                  className="modal--wide"
                  onClose={() => setInfoDialogOpen(false)}
                  footer={(
                    <Button
                      size="sm"
                      variant="primary"
                      onClick={() => setInfoDialogOpen(false)}
                    >
                      Close
                    </Button>
                  )}
                >
                  <div className="info-content">
                    <ReactMarkdown>{bridge.config.info.content}</ReactMarkdown>
                  </div>
                </Modal>
              )}
            </>
          )}
        </div>
        {/* The status bar is this indicator's home; it only falls back to the
            header when an app turns that bar off. */}
        {!bridge.config.layout.show_status_bar && (
          <>
            <div className="header-controls__separator header-controls__status-separator" />
            <StatusIndicator className="header-controls__status" />
          </>
        )}
      </div>
    </div>
  );
}
