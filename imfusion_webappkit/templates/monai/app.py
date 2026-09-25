"""Run the {{PROJECT_TITLE}} MONAI inference workflow."""

from imfusion_webappkit import (
    ExportStep,
    ImFusionWebApp,
    InputSelectionStep,
    InputSpec,
    LayoutConfig,
    MessageStep,
    ProcessingStep,
    SidebarConfig,
    SidePosition,
    ThemeConfig,
    ThemePreset,
    TitlePosition,
    ValidationStep,
)

from algorithm import run_segmentation


webapp = ImFusionWebApp(
    title="{{PROJECT_TITLE}}",
    theme=ThemeConfig(preset=ThemePreset.{{THEME_PRESET}}),
    sidebar=SidebarConfig(
        show_datamodel=True,
        show_views=True,
        show_display_options=True,
        collapsed=True,
    ),
    layout=LayoutConfig(
        workflow_panel_position=SidePosition.LEFT,
        workflow_panel_width=320,
        sidebar_position=SidePosition.RIGHT,
        sidebar_width=300,
        header_title_position=TitlePosition.CENTER,
    ),
    show_load_button=False,
    show_export_button=False,
)
webapp.set_workflow(
    [
        MessageStep(
            "Welcome",
            (
                "Load a 3D CT volume, run the configured MONAI model, review "
                "the label map, and export it. The model downloads "
                "automatically on first use. This example is not for "
                "diagnostic use."
            ),
            step_id="welcome",
        ),
        InputSelectionStep(
            "Select Model Input",
            inputs=[InputSpec("ct", "Source CT")],
            message=(
                "Load a single-channel 3D CT image with intensities in "
                "Hounsfield units, then confirm the source CT."
            ),
            step_id="select_input",
        ),
        ProcessingStep(
            "Run Model",
            callback=run_segmentation,
            inputs_from="select_input",
            auto_run=False,
            run_label="Run Segmentation",
            step_id="process",
        ),
        ValidationStep(
            "Review Result",
            "Does the generated label map align with the source CT?",
            step_id="review",
            depends_on=["process"],
        ),
        ExportStep(
            "Export Segmentation",
            "Export the label map and finish the workflow.",
            step_id="export",
            depends_on=["review"],
        ),
    ]
)


if __name__ == "__main__":
    webapp.run(host="127.0.0.1", port=8000)
