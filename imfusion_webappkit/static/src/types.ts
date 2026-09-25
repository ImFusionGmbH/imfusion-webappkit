import type { AnnotationDescriptor } from './annotations';

export type { AnnotationDescriptor };

export type ConnectionStatus = 'connected' | 'disconnected' | 'processing' | 'error';
export type ExportFormat = 'imf' | 'nii.gz' | 'dicom';
export type JobStatus =
  | 'queued'
  | 'running'
  | 'cancel_requested'
  | 'succeeded'
  | 'failed'
  | 'cancelled';

export interface JobState {
  job_id: string;
  kind: string;
  label: string;
  status: JobStatus;
  progress: number;
  message?: string;
}

/**
 * Work in flight between the browser and the server, whatever its kind.
 *
 * Transferring a dataset, running an algorithm and waiting for an export all
 * leave the two models of the data briefly disagreeing, and an index the client
 * sends during any of them can resolve to the wrong dataset. Collapsing them
 * into one state is what lets the interface answer "is it safe to act on the
 * data right now" in one place rather than at every control.
 */
export interface BusyState {
  active: boolean;
  /** Work that leaves nothing worth looking at, so the page covers itself. */
  blocking: boolean;
  /** A few words for the status indicator, which has one line to spare. */
  label: string;
  /** The longer sentence the blocking overlay has room for. */
  detail: string | null;
  /** 0 to 1, or null when the work cannot report how far along it is. */
  progress: number | null;
}

export interface SidebarConfig {
  show_datamodel: boolean;
  show_views: boolean;
  show_display_options: boolean;
  show_annotations: boolean;
  collapsed: boolean;
}

export interface AlgorithmController {
  id: string;
  name: string;
  title: string;
  inputs: InputSpec[];
  result_input?: string;
  placement: 'sidebar' | 'header';
}

export interface InputSpec {
  key: string;
  label: string;
  required: boolean;
}

export interface InputReference {
  role: string;
  index: number;
}

export interface ActionDescriptor {
  name: string;
  is_app_only: boolean;
  inputs: InputSpec[];
  parameters: Record<string, Parameter>;
}

export interface BrandingConfig {
  logo_url: string | null;
  favicon_url: string | null;
  landing_page_title: string | null;
  landing_page_message: string | null;
}

export interface SampleDataset {
  name: string;
  data_url: string;
  thumbnail_url: string | null;
}

export interface InfoConfig {
  content: string;
  title: string;
  button_label: string;
}

export interface ThemeConfig {
  preset: 'dark' | 'gray' | 'light';
  primary: string | null;
  primary_hover: string | null;
  secondary: string | null;
  background: string | null;
  surface: string | null;
  surface_raised: string | null;
  surface_high: string | null;
  text: string | null;
  text_muted: string | null;
  text_subtle: string | null;
  on_primary: string | null;
  border: string | null;
  success: string | null;
  danger: string | null;
  warning: string | null;
  info: string | null;
  font_family: string | null;
}

export interface LayoutConfig {
  header_title_position: 'left' | 'center' | 'right';
  header_logo_position: 'left' | 'right';
  sidebar_position: 'left' | 'right';
  sidebar_width: number;
  sidebar_resizable: boolean;
  workflow_panel_position: 'left' | 'right';
  workflow_panel_width: number;
  workflow_panel_resizable: boolean;
  show_status_bar: boolean;
  initial_view_layout: 'Auto' | 'Rows' | 'FocusPlusStack' | 'FocusPlusRows' | null;
  initial_visible_views: Array<
    '2d' | 'mpr' | 'axial' | 'coronal' | 'sagittal' | '3d'
  > | null;
}

export interface AppConfig {
  protocol_version: number;
  title: string;
  branding: BrandingConfig;
  info: InfoConfig | null;
  theme: ThemeConfig;
  layout: LayoutConfig;
  actions?: ActionDescriptor[];
  sidebar: SidebarConfig | null;
  algorithms_enabled: boolean;
  algorithms_placement: 'sidebar' | 'header';
  algorithm_controllers: AlgorithmController[];
  show_load_button: boolean;
  show_export_button: boolean;
  export_formats: ExportFormat[];
  workflow_enabled: boolean;
  sample_datasets: SampleDataset[];
}

export interface SerializedImage {
  format: 'imf';
  buffer: string;
}

export interface Parameter {
  name?: string;
  type: 'bool' | 'int' | 'float' | 'choice' | 'string' | 'annotation';
  value: boolean | number | string;
  default?: boolean | number | string;
  label?: string;
  description?: string;
  min?: number;
  max?: number;
  step?: number;
  unit?: string;
  options?: string[];
  placeholder?: string;
  /** Shape an annotation parameter asks the user to draw. */
  annotation_type?: string;
  /**
   * The only values a recorded demo can answer for. Absent when a server is
   * behind the page, in which case the control accepts anything it allows.
   */
  allowed_values?: (boolean | number | string)[];
}

export interface AlgorithmInfo {
  id: string;
  name: string;
  parameters: Record<string, Parameter>;
}

export interface ControllerStatus {
  id?: string;
  name: string;
  compatible: boolean;
  parameters: Record<string, Parameter>;
  error?: string;
}

export interface TextElement {
  kind: 'text';
  content: string;
}

export interface AlertElement {
  kind: 'alert';
  content: string;
  level: 'info' | 'success' | 'warning' | 'danger';
}

export interface MetricsElement {
  kind: 'metrics';
  items: Array<{ label: string; value: string | number; unit?: string }>;
}

export interface TableElement {
  kind: 'table';
  columns: string[];
  rows: Array<Array<string | number | boolean | null>>;
  caption?: string;
}

export interface ChartElement {
  kind: 'chart';
  variant: 'line' | 'bar' | 'scatter';
  series: Array<{ label: string; values: number[]; x?: Array<number | string> }>;
  x_label?: string;
  y_label?: string;
  caption?: string;
}

export interface ImageElement {
  kind: 'image';
  media_type: string;
  data: string;
  caption?: string;
  alt?: string;
}

export interface FieldsElement {
  kind: 'fields';
  parameters: Array<Parameter & { name: string }>;
  /** Action to run, as if its button had been pressed, on Enter in a field. */
  submit_action?: string;
}

export interface ButtonElement {
  kind: 'button';
  action: string;
  label: string;
  style: 'default' | 'primary' | 'danger';
  job: boolean;
  disabled: boolean;
}

export interface AnnotationElement {
  kind: 'annotation';
  label?: string;
  annotations: AnnotationDescriptor[];
  place_action?: string;
  clear_action?: string;
  show_measurements: boolean;
}

/**
 * Elements a custom workflow step can display. A server may send kinds this
 * client does not know yet, so renderers must skip unrecognized entries.
 */
export type WorkflowUIElement =
  | TextElement
  | AlertElement
  | MetricsElement
  | TableElement
  | ChartElement
  | ImageElement
  | FieldsElement
  | ButtonElement
  | AnnotationElement;

/** One annotation a step or a parameter is collecting. */
export interface AnnotationRole {
  role: string;
  /** True when the role name should be shown, i.e. the step declared roles. */
  labelled: boolean;
  data_index: number | null;
  data_name: string;
  color: number[];
  annotations: AnnotationDescriptor[];
}

export interface WorkflowStep {
  id: string;
  title: string;
  completed: boolean;
  ui_config: {
    type: 'data_selection' | 'parameters' | 'processing' | 'brush' | 'annotation' | 'validation' | 'export' | 'message' | 'custom';
    message?: string;
    parameters?: Array<Parameter & { name: string; label?: string; default?: boolean | number | string }>;
    completed?: boolean;
    error?: string;
    auto_run?: boolean;
    run_label?: string;
    accepted?: boolean;
    formats?: string[];
    exported?: boolean;
    require_export_before_finish?: boolean;
    body?: WorkflowUIElement[];
    inputs?: InputSpec[];
    values?: Record<string, number>;
    datasets?: Array<{ index: number; name: string }>;
    allow_upload?: boolean;
    allow_sample_datasets?: boolean;
    image_index?: number | null;
    label_map_index?: number | null;
    label_map_name?: string;
    radius_mm?: number;
    adaptiveness?: number;
    allow_radius_change?: boolean;
    allow_adaptiveness_change?: boolean;
    labels?: number[];
    committed?: boolean;
    entry_token?: number;
    annotation_type?: string;
    required?: boolean;
    show_measurements?: boolean;
    views?: Array<'2d' | 'mpr' | 'axial' | 'coronal' | 'sagittal' | '3d'>;
    armed_id?: string | null;
    pending_id?: string | null;
    placed?: number;
    total?: number;
    roles?: AnnotationRole[];
  };
}

export interface WorkflowState {
  enabled: boolean;
  current_index: number;
  total_steps: number;
  current_step: WorkflowStep;
  can_go_back: boolean;
  can_proceed: boolean;
  is_last_step: boolean;
  steps: WorkflowStep[];
}

export interface ServerMessage<T = Record<string, unknown>> {
  type: string;
  data: T;
}

export const defaultConfig: AppConfig = {
  protocol_version: 7,
  title: 'ImFusion WebApp',
  branding: {
    logo_url: null,
    favicon_url: null,
    landing_page_title: null,
    landing_page_message: null,
  },
  info: null,
  theme: {
    preset: 'dark',
    primary: null,
    primary_hover: null,
    secondary: null,
    background: null,
    surface: null,
    surface_raised: null,
    surface_high: null,
    text: null,
    text_muted: null,
    text_subtle: null,
    on_primary: null,
    border: null,
    success: null,
    danger: null,
    warning: null,
    info: null,
    font_family: null,
  },
  layout: {
    header_title_position: 'left',
    header_logo_position: 'left',
    sidebar_position: 'left',
    sidebar_width: 320,
    sidebar_resizable: true,
    workflow_panel_position: 'left',
    workflow_panel_width: 320,
    workflow_panel_resizable: true,
    show_status_bar: true,
    initial_view_layout: null,
    initial_visible_views: null,
  },
  actions: [],
  sidebar: null,
  algorithms_enabled: false,
  algorithms_placement: 'sidebar',
  algorithm_controllers: [],
  show_load_button: true,
  show_export_button: false,
  export_formats: ['imf', 'nii.gz', 'dicom'],
  workflow_enabled: false,
  sample_datasets: [],
};
