"""Run the {{PROJECT_TITLE}} guided workflow."""

from imfusion_webappkit import (
    BrushStep,
    ExportStep,
    FloatParameter,
    ImFusionWebApp,
    InputSelectionStep,
    InputSpec,
    LayoutConfig,
    MessageStep,
    ParameterStep,
    ProcessingStep,
    SidebarConfig,
    SidePosition,
    ThemeConfig,
    ThemePreset,
    TitlePosition,
    ValidationStep,
)

from algorithm import process_image


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
            "Load an image, segment it, correct the label map, review it, and export.",
            step_id="welcome",
        ),
        InputSelectionStep(
            "Select Image",
            inputs=[InputSpec("image", "Image")],
            message="Load a DICOM, NIfTI, or IMF image to segment.",
            step_id="input",
        ),
        ParameterStep(
            "Configure Segmentation",
            parameters=[
                FloatParameter(
                    "threshold",
                    label="Intensity Threshold",
                    default=100.0,
                    minimum=-1000.0,
                    maximum=4096.0,
                    step=1.0,
                ),
            ],
            step_id="configure",
        ),
        ProcessingStep(
            "Segment Image",
            callback=process_image,
            inputs_from="input",
            parameters_from="configure",
            step_id="process",
        ),
        BrushStep(
            "Correct Segmentation",
            "Start the smart brush, correct the label map, then stop it to save.",
            label_map_from="process",
            radius_mm=5.0,
            adaptiveness=0.5,
            step_id="correct",
        ),
        ValidationStep(
            "Review Result",
            "Is the corrected segmentation acceptable?",
            step_id="review",
            depends_on=["correct"],
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
