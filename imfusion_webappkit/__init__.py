"""
ImFusion WebAppKit

A Python toolkit for building browser-based ImFusion applications with
server-side processing.
"""

from importlib import import_module
from typing import Dict, Tuple

__version__ = "0.3.0"

_EXPORTS: Dict[str, Tuple[str, str]] = {
    "ImFusionWebApp": (".app", "ImFusionWebApp"),
    "WebApplicationController": (
        ".application_controller",
        "WebApplicationController",
    ),
    "BrandingConfig": (".config", "BrandingConfig"),
    "InfoConfig": (".config", "InfoConfig"),
    "ThemeConfig": (".config", "ThemeConfig"),
    "ThemePreset": (".config", "ThemePreset"),
    "LayoutConfig": (".config", "LayoutConfig"),
    "TitlePosition": (".config", "TitlePosition"),
    "SidePosition": (".config", "SidePosition"),
    "ViewLayout": (".config", "ViewLayout"),
    "ViewType": (".config", "ViewType"),
    "SampleDataset": (".config", "SampleDataset"),
    "SidebarConfig": (".config", "SidebarConfig"),
    "ExportFormat": (".data_export", "ExportFormat"),
    "WebAppDataModel": (".data_model", "WebAppDataModel"),
    "Annotation": (".annotation_model", "Annotation"),
    "AnnotationType": (".annotation_model", "AnnotationType"),
    "WebAnnotationModel": (".annotation_model", "WebAnnotationModel"),
    "InputSpec": (".input_spec", "InputSpec"),
    "ParameterSpec": (".parameter_spec", "ParameterSpec"),
    "BoolParameter": (".parameter_spec", "BoolParameter"),
    "IntParameter": (".parameter_spec", "IntParameter"),
    "FloatParameter": (".parameter_spec", "FloatParameter"),
    "StringParameter": (".parameter_spec", "StringParameter"),
    "ChoiceParameter": (".parameter_spec", "ChoiceParameter"),
    "AnnotationParameter": (".parameter_spec", "AnnotationParameter"),
    "Workflow": (".workflow", "Workflow"),
    "WorkflowStep": (".workflow", "WorkflowStep"),
    "StepUIType": (".workflow", "StepUIType"),
    "ParameterStep": (".workflow", "ParameterStep"),
    "ProcessingStep": (".workflow", "ProcessingStep"),
    "BrushStep": (".workflow", "BrushStep"),
    "AnnotationStep": (".workflow", "AnnotationStep"),
    "ValidationStep": (".workflow", "ValidationStep"),
    "ExportStep": (".workflow", "ExportStep"),
    "MessageStep": (".workflow", "MessageStep"),
    "InputSelectionStep": (".workflow", "InputSelectionStep"),
    "CustomStep": (".workflow", "CustomStep"),
    "UIElement": (".ui_elements", "UIElement"),
    "Text": (".ui_elements", "Text"),
    "Alert": (".ui_elements", "Alert"),
    "Metric": (".ui_elements", "Metric"),
    "Metrics": (".ui_elements", "Metrics"),
    "Table": (".ui_elements", "Table"),
    "Series": (".ui_elements", "Series"),
    "Chart": (".ui_elements", "Chart"),
    "Image": (".ui_elements", "Image"),
    "Fields": (".ui_elements", "Fields"),
    "Button": (".ui_elements", "Button"),
    "AnnotationField": (".ui_elements", "AnnotationField"),
}


def __getattr__(name: str):
    """Load public SDK-backed objects only when requested."""
    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(_EXPORTS))


__all__ = [
    "ImFusionWebApp",
    "WebApplicationController",
    "BrandingConfig",
    "InfoConfig",
    "ThemeConfig",
    "ThemePreset",
    "LayoutConfig",
    "TitlePosition",
    "SidePosition",
    "ViewLayout",
    "ViewType",
    "SampleDataset",
    "SidebarConfig",
    "ExportFormat",
    "WebAppDataModel",
    "Annotation",
    "AnnotationType",
    "WebAnnotationModel",
    "InputSpec",
    "ParameterSpec",
    "BoolParameter",
    "IntParameter",
    "FloatParameter",
    "StringParameter",
    "ChoiceParameter",
    "AnnotationParameter",
    "Workflow",
    "WorkflowStep",
    "StepUIType",
    "ParameterStep",
    "ProcessingStep",
    "BrushStep",
    "AnnotationStep",
    "ValidationStep",
    "ExportStep",
    "MessageStep",
    "InputSelectionStep",
    "CustomStep",
    "UIElement",
    "Text",
    "Alert",
    "Metric",
    "Metrics",
    "Table",
    "Series",
    "Chart",
    "Image",
    "Fields",
    "Button",
    "AnnotationField",
]
