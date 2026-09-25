import { useMemo, useState, type ReactNode } from 'react';
import type { Data, DisplayLayoutMode, SharedImageSet, View } from '@imfusion/sdk';
import {
  useDisplayOptions2d,
  useDisplayOptions3d,
  useLayoutMode,
  useViewVisibility,
} from '@imfusion/sdk-react';
import { Button, Checkbox } from '@imfusion/web-ui';
import { usePythonBridge } from './PythonBridge';
import { PanelResizer } from './PanelResizer';
import { formatPoint, supportsAnnotationType } from './annotations';
import { Slider } from './controls';
import { AlgorithmPanel, ControllerContent } from './operations';
import { areAliases } from './protocol';

export function Section({ title, children }: { title: string; children: ReactNode }) {
  const [expanded, setExpanded] = useState(true);
  return (
    <section className="sidebar__section">
      <button className="sidebar__header" type="button" onClick={() => setExpanded((value) => !value)}>
        <span className="sidebar__title">{title}</span>
        <span className="sidebar__icon"><i className={`bi bi-chevron-${expanded ? 'down' : 'right'}`} /></span>
      </button>
      <div className={`sidebar__content ${expanded ? 'sidebar__content--expanded' : ''}`}>
        {children}
      </div>
    </section>
  );
}

const MODALITY_ABBREVIATIONS: Record<string, string> = {
  ULTRASOUND: 'US',
  DISTANCE: 'DIST',
};

/** Resolve a public-directory icon against the deployment base, so the sidebar
 *  keeps its icons when the app is served from a subdirectory rather than a
 *  domain root. */
const iconUrl = (name: string) => `${import.meta.env.BASE_URL}icons/${name}`;

/** Short modality tag for a dataset, or null when it carries no useful one.
 *
 * `modality()` reaches into a wasm handle, which a dataset removed between the
 * model update and this render would no longer own. A dangling read there would
 * take down the whole tree, and a missing tag is not worth that. */
function modalityTag(item: Data): string | null {
  try {
    const modality = item.modality();
    if (!modality || modality === 'NA') return null;
    return MODALITY_ABBREVIATIONS[modality] ?? modality;
  } catch {
    return null;
  }
}

function DataPanel() {
  const bridge = usePythonBridge();
  const isSelected = (item: Data) =>
    bridge.visibleData.some((candidate) => areAliases(candidate, item));

  if (!bridge.data.length) {
    return (
      <div className="sidebar__empty">
        <i className="bi bi-inbox" aria-hidden="true" />
        <span>No data loaded</span>
      </div>
    );
  }

  return (
    <div id="data-widget-list">
      {bridge.data.map((item, index) => (
        <div
          className={`data-item ${isSelected(item) ? 'data-item--selected' : ''}`}
          key={`${item.name}-${index}`}
          onClick={() => bridge.setVisibleData([item])}
        >
          <Checkbox.Root
            className="data-item__selectionToggle"
            checked={isSelected(item)}
            onClick={(event) => event.stopPropagation()}
            onCheckedChange={(checked) => {
              const next = checked
                ? [...bridge.visibleData, item]
                : bridge.visibleData.filter((candidate) => !areAliases(candidate, item));
              bridge.setVisibleData(next);
            }}
          >
            <Checkbox.Indicator />
          </Checkbox.Root>
          {modalityTag(item) && <span className="data-item__modality">{modalityTag(item)}</span>}
          <div className="data-item__name">{item.name || `Data ${index + 1}`}</div>
          <button
            className="data-item__delete"
            title="Remove dataset"
            // Removing shifts every index above it, which the server is in no
            // position to follow while it is still catching up on this list.
            disabled={bridge.busy.active}
            onClick={(event) => {
              event.stopPropagation();
              bridge.removeData(item);
            }}
          >
            <i className="bi bi-x" />
          </button>
        </div>
      ))}
    </div>
  );
}

function ViewToggle({ view, label, icon }: { view: View; label: string; icon: string }) {
  const { hidden, setHidden } = useViewVisibility(view);
  return (
    <button
      className={`views__view-button ${hidden ? '' : 'views__view-button--active'}`}
      title={label}
      onClick={() => setHidden(!hidden)}
    >
      <img src={icon} className="views__view-icon" alt={label} />
    </button>
  );
}

function MprViewToggle({
  axial,
  coronal,
  sagittal,
}: {
  axial: View;
  coronal: View;
  sagittal: View;
}) {
  const axialVisibility = useViewVisibility(axial);
  const coronalVisibility = useViewVisibility(coronal);
  const sagittalVisibility = useViewVisibility(sagittal);
  const allHidden = axialVisibility.hidden
    && coronalVisibility.hidden
    && sagittalVisibility.hidden;
  const anyVisible = !axialVisibility.hidden
    || !coronalVisibility.hidden
    || !sagittalVisibility.hidden;

  return (
    <button
      className={`views__view-button ${anyVisible ? 'views__view-button--active' : ''}`}
      title="MPR Views"
      onClick={() => {
        axialVisibility.setHidden(!allHidden);
        coronalVisibility.setHidden(!allHidden);
        sagittalVisibility.setHidden(!allHidden);
      }}
    >
      <img src={iconUrl('IconViewMPR.svg')} className="views__view-icon" alt="MPR Views" />
    </button>
  );
}

function ViewsPanel() {
  const { imf } = usePythonBridge();
  const { mode, setMode } = useLayoutMode();
  const display = imf.display;
  const layouts: Array<{ mode: DisplayLayoutMode; title: string; icon: string }> = [
    { mode: 'Auto', title: 'Auto', icon: 'auto' },
    { mode: 'Rows', title: 'Rows', icon: 'rows' },
    { mode: 'FocusPlusStack', title: 'Focus + Stack', icon: 'focusplusstack' },
    { mode: 'FocusPlusRows', title: 'Focus + Rows', icon: 'focusplusrows' },
  ];

  return (
    <div className="sidebar__widget-content">
      <div className="views__view-buttons">
        <ViewToggle view={display.main2dView()} label="2D View" icon={iconUrl('IconView2D.svg')} />
        <MprViewToggle
          axial={display.mainAxialView()}
          coronal={display.mainCoronalView()}
          sagittal={display.mainSagittalView()}
        />
        <ViewToggle view={display.main3dView()} label="3D View" icon={iconUrl('IconView3D.svg')} />
      </div>
      <div className="views__layout-title">Layout</div>
      <div className="views__layout-buttons">
        {layouts.map((item) => (
          <button
            key={item.mode}
            className={`views__layout-button ${mode === item.mode ? 'views__layout-button--active' : ''}`}
            title={item.title}
            onClick={() => setMode(item.mode)}
          >
            <svg className="views__layout-icon"><use href={iconUrl(`layout.svg#${item.icon}`)} /></svg>
          </button>
        ))}
      </div>
    </div>
  );
}

function DisplayOptions({ image }: { image: SharedImageSet }) {
  const { imf } = usePythonBridge();
  const twoD = useDisplayOptions2d(image);
  const threeD = useDisplayOptions3d(image);
  const [tab, setTab] = useState<'2d' | '3d'>('2d');
  const options = tab === '2d' ? twoD : threeD;
  const [minimum, maximum] = image.minmaxIntensityOriginal();
  const range = Math.max(1, maximum - minimum);

  const updateNumber = (property: 'window' | 'level' | 'gamma', value: number) => {
    if (property === 'gamma' && tab === '3d') return;
    (options as typeof twoD)[property] = value;
    imf.render();
  };

  return (
    <div className="sidebar__widget-content">
      <div className="windowing__tabs">
        {(['2d', '3d'] as const).map((name) => (
          <button
            key={name}
            className={`windowing__tab ${tab === name ? 'windowing__tab--active' : ''}`}
            onClick={() => setTab(name)}
          >
            {name.toUpperCase()}
          </button>
        ))}
      </div>
      <Slider label="Window" value={options.window} min={1} max={range * 2} onChange={(value) => updateNumber('window', value)} />
      <Slider label="Level" value={options.level} min={minimum} max={maximum} onChange={(value) => updateNumber('level', value)} />
      {tab === '2d' && (
        <Slider label="Gamma" value={twoD.gamma} min={0.1} max={3} step={0.1} onChange={(value) => updateNumber('gamma', value)} />
      )}
      <label className="windowing__checkbox-label">
        <Checkbox.Root
          className="windowing__checkbox"
          checked={options.invert}
          onCheckedChange={(checked) => {
            options.invert = checked;
            imf.render();
          }}
        >
          <Checkbox.Indicator />
        </Checkbox.Root>
        <span>Invert</span>
      </label>
      <Button
        size="sm"
        variant="secondary"
        className="windowing__auto-button"
        onClick={() => {
          image.autoWindow();
          threeD.window = twoD.window;
          threeD.level = twoD.level;
          imf.render();
        }}
      >
        Auto Window
      </Button>
    </div>
  );
}

/** Shapes the user can reach for, in the order a measurement panel wants them. */
const ANNOTATION_TOOLS: Array<{ type: string; label: string; icon: string }> = [
  { type: 'LineSegment', label: 'Distance', icon: 'bi-rulers' },
  { type: 'Rectangle', label: 'Rectangle', icon: 'bi-bounding-box' },
  { type: 'Angle', label: 'Angle', icon: 'bi-triangle' },
  // Only offered by SDK builds that bind them; the bridge reports the rest as
  // unsupported rather than letting `add()` throw.
  { type: 'Point', label: 'Point', icon: 'bi-geo' },
  { type: 'Box', label: 'Box', icon: 'bi-box' },
];

function AnnotationPanel() {
  const bridge = usePythonBridge();
  const target = bridge.visibleData[0] ?? bridge.data[0];
  const tools = ANNOTATION_TOOLS.filter(
    (tool) => supportsAnnotationType(bridge.imf.bindings, tool.type),
  );

  if (!target) {
    return (
      <div className="sidebar__empty">
        <i className="bi bi-vector-pen" aria-hidden="true" />
        <span>Select a dataset to annotate it</span>
      </div>
    );
  }

  // Grouped by parent dataset, because that is how the SDK stores them and how
  // the viewer shows them.
  const groups = bridge.data
    .map((item, index) => ({
      name: item.name || `Data ${index + 1}`,
      index,
      items: bridge.annotations.filter((annotation) => annotation.dataIndex === index),
    }))
    .filter((group) => group.items.length > 0);

  return (
    <div className="sidebar__widget-content">
      <div className="annotation-tools">
        {tools.map((tool) => (
          <button
            key={tool.type}
            className="annotation-tools__button"
            title={`Place a ${tool.label.toLowerCase()} on ${target.name || 'the selected dataset'}`}
            onClick={() => bridge.createAnnotation(tool.type, target)}
          >
            <i className={`bi ${tool.icon}`} />
            <span>{tool.label}</span>
          </button>
        ))}
      </div>
      {groups.length === 0 ? (
        <p className="sidebar__hint">Pick a tool, then draw in the viewer.</p>
      ) : (
        groups.map((group) => (
          <div className="annotation-group" key={group.index}>
            <h4 className="annotation-group__title">{group.name}</h4>
            {group.items.map((annotation) => (
              <div className="annotation-group__item" key={annotation.id}>
                <span className="annotation-group__type">{annotation.type}</span>
                <span className="annotation-group__points">
                  {annotation.editing
                    ? 'Drawing…'
                    : annotation.points.map((point) => formatPoint(point)).join('  |  ')}
                </span>
                <button
                  className="annotation-group__delete"
                  title="Remove annotation"
                  onClick={() => bridge.removeAnnotation(annotation.id)}
                >
                  <i className="bi bi-x" />
                </button>
              </div>
            ))}
          </div>
        ))
      )}
    </div>
  );
}

function ControllerPanel({ name, title }: { name: string; title: string }) {
  return <Section title={title}><ControllerContent name={name} /></Section>;
}

export function Sidebar() {
  const bridge = usePythonBridge();
  const image = useMemo(
    () => bridge.imf.bindings.getImage(bridge.visibleData),
    [bridge.imf, bridge.visibleData],
  );
  const sidebar = bridge.config.sidebar;
  if (!sidebar) return null;

  return (
    <>
      <button
        id="sidebar-toggle"
        className="sidebar__toggle"
        aria-label="Toggle sidebar"
        onClick={() => {
          document.body.classList.toggle('sidebar-collapsed');
          window.setTimeout(() => bridge.imf.updateSize(), 250);
        }}
      >
        <i className="bi bi-chevron-left" />
      </button>
      {bridge.config.layout.sidebar_resizable && (
        <PanelResizer
          panel="sidebar"
          variable="--sidebar-width"
          label="Resize sidebar"
          defaultWidth={bridge.config.layout.sidebar_width}
          growsLeftwards={bridge.config.layout.sidebar_position === 'right'}
        />
      )}
      <aside className="sidebar">
        {sidebar.show_datamodel && <Section title="Datasets"><DataPanel /></Section>}
        {sidebar.show_views && <Section title="Views"><ViewsPanel /></Section>}
        {sidebar.show_display_options && (
          <Section title="Display Options">
            {image ? <DisplayOptions image={image} /> : (
              <div className="sidebar__empty">
                <i className="bi bi-sliders" aria-hidden="true" />
                <span>Select an image to adjust display options</span>
              </div>
            )}
          </Section>
        )}
        {sidebar.show_annotations && <Section title="Annotations"><AnnotationPanel /></Section>}
        {bridge.config.algorithms_enabled
          && bridge.config.algorithms_placement === 'sidebar'
          && <Section title="Algorithms"><AlgorithmPanel /></Section>}
        {bridge.config.algorithm_controllers
          .filter((controller) => controller.placement === 'sidebar')
          .map((controller) => (
          <ControllerPanel key={controller.name} name={controller.name} title={controller.title || controller.name} />
          ))}
      </aside>
    </>
  );
}
