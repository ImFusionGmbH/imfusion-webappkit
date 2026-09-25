"""Guided image-segmentation workflow using the session controller API."""

import imfusion
import numpy as np

from imfusion_webappkit import (
    Alert,
    BrandingConfig,
    BrushStep,
    Button,
    Chart,
    CustomStep,
    ExportStep,
    Fields,
    FloatParameter,
    ImFusionWebApp,
    InputSelectionStep,
    InputSpec,
    IntParameter,
    LayoutConfig,
    MessageStep,
    Metric,
    Metrics,
    ParameterStep,
    ProcessingStep,
    SampleDataset,
    Series,
    SidebarConfig,
    SidePosition,
    Table,
    Text,
    ValidationStep,
    WebApplicationController,
)
from imfusion_webappkit.examples._assets import (
    DEFAULT_LOGO,
    SAMPLE_IMAGE,
    SAMPLE_IMAGE_THUMBNAIL,
)


def apply_intensity_threshold(
    imageset: imfusion.SharedImageSet,
    *,
    threshold: float,
    app: WebApplicationController,
) -> imfusion.SharedImageSet:
    """Create a label map containing voxels at or above the threshold."""
    label_map = imfusion.SharedImageSet()

    for index, image in enumerate(imageset):
        source = image.numpy()
        segmentation = (source >= threshold).astype(np.uint8)
        output_image = imfusion.SharedImage(segmentation)
        output_image.image_to_world_matrix = image.image_to_world_matrix
        output_image.spacing = image.spacing
        label_map.add(output_image)
        app.update_progress(
            (index + 1) / len(imageset),
            f"Thresholding image {index + 1} of {len(imageset)}",
        )

    label_map.name = "Threshold segmentation"
    label_map.modality = imfusion.Data.Modality.LABEL
    return label_map


class SegmentationSummaryStep(CustomStep):
    """Report label statistics and set the label value used for export.

    This step is mostly meant as a demonstration of how to implement a custom workflow step.
    """

    def __init__(self, label_map_from, step_id="summary"):
        super().__init__(
            "Segmentation Summary",
            step_id=step_id,
            depends_on=[label_map_from],
        )
        self.label_map_from = label_map_from
        self._statistics = []
        self._profile = []

    def _label_map(self):
        return self.app.workflow.get_step(self.label_map_from).result

    def _measure(self):
        self._statistics = []
        self._profile = []
        for index, image in enumerate(self._label_map()):
            values = np.asarray(image)
            labelled = int(np.count_nonzero(values))
            volume_ml = labelled * float(np.prod(image.spacing)) / 1000.0
            self._statistics.append(
                (f"Image {index + 1}", labelled, round(volume_ml, 2))
            )
            if index or values.shape[0] < 2:
                continue
            # Arrays are ordered (Z, Y, X, C) and spacing is (X, Y, Z). A chart
            # summarizes a profile, so subsample instead of sending every slice.
            counts = np.count_nonzero(values.reshape(values.shape[0], -1), axis=1)
            stride = max(1, len(counts) // 256)
            self._profile = [
                (round(z * float(image.spacing[2]), 2), int(counts[z]))
                for z in range(0, len(counts), stride)
            ]

    def on_enter(self):
        # Measuring here keeps body() cheap: the browser rebuilds the step on
        # every workflow state update.
        self._measure()

    def body(self):
        voxels = sum(count for _name, count, _volume in self._statistics)
        volume_ml = sum(volume for _name, _count, volume in self._statistics)
        elements = [
            Text("Statistics for the corrected label map."),
            Metrics(
                [
                    Metric("Labelled voxels", f"{voxels:,}"),
                    Metric("Volume", round(volume_ml, 2), unit="mL"),
                ]
            ),
        ]
        if self._statistics:
            elements.append(
                Table(self._statistics, columns=["Image", "Voxels", "Volume (mL)"])
            )
        if self._profile:
            elements.append(
                Chart(
                    "line",
                    Series(
                        "Labelled voxels",
                        [count for _position, count in self._profile],
                        x=[position for position, _count in self._profile],
                    ),
                    x_label="Slice position (mm)",
                    y_label="Voxels",
                    caption="Profile along the first image's slice axis.",
                )
            )
        if not voxels:
            elements.append(
                Alert(
                    "The label map is empty. Go back and lower the threshold.",
                    "warning",
                )
            )
        elements += [
            Fields(
                [
                    IntParameter(
                        "label_value",
                        label="Exported label value",
                        default=1,
                        minimum=1,
                        maximum=255,
                    )
                ]
            ),
            Button(
                "apply_label",
                "Apply label value",
                style="primary",
                job=True,
                disabled=not voxels,
            ),
        ]
        return elements

    def on_action(self, action):
        if action != "apply_label":
            return
        label_value = self.values["label_value"]
        label_map = self._label_map()
        for index, image in enumerate(label_map):
            if self.app.cancellation_requested:
                return
            values = np.array(image, copy=True)
            values[values > 0] = label_value
            image.assign_array(values)
            self.app.update_progress(
                (index + 1) / len(label_map),
                f"Labelling image {index + 1} of {len(label_map)}",
            )
        self.data_model.update(self.data_model.index(label_map))
        self._measure()

    def reset_state(self):
        super().reset_state()
        self._statistics = []


def main(host: str = "127.0.0.1", port: int = 8000) -> None:
    sample_datasets = (
        [
            SampleDataset(
                "Sample Image",
                SAMPLE_IMAGE,
                SAMPLE_IMAGE_THUMBNAIL if SAMPLE_IMAGE_THUMBNAIL.is_file() else None,
            )
        ]
        if SAMPLE_IMAGE.is_file()
        else []
    )

    webapp = ImFusionWebApp(
        title="Intensity Threshold Segmentation",
        branding=BrandingConfig(logo=DEFAULT_LOGO),
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
        ),
        sample_datasets=sample_datasets,
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
                callback=apply_intensity_threshold,
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
            SegmentationSummaryStep(label_map_from="process", step_id="summary"),
            ValidationStep(
                "Review Result",
                "Is the corrected segmentation acceptable?",
                step_id="review",
                depends_on=["correct"],
            ),
            ExportStep(
                "Export Segmentation",
                "Export the label map.",
                step_id="export",
                depends_on=["review"],
                require_export_before_finish=False,
            ),
        ]
    )
    webapp.run(host=host, port=port)


if __name__ == "__main__":
    main()
