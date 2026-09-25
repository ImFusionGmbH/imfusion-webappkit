"""Guided ROI annotation, measured against a user-supplied distance.

Shows the two ways to collect geometry: :class:`AnnotationStep` when a step's
only job is placement, and :class:`AnnotationField` when placement has to sit
next to other input in a :class:`CustomStep`. The result is written out with
``app.download``, which sends a file the server produced without going through
the ImFusion writers that :class:`ExportStep` uses.
"""

import json

from imfusion_webappkit import (
    AnnotationField,
    AnnotationStep,
    AnnotationType,
    BrandingConfig,
    Button,
    CustomStep,
    Fields,
    FloatParameter,
    ImFusionWebApp,
    InputSelectionStep,
    InputSpec,
    MessageStep,
    SampleDataset,
    SidebarConfig,
    Text,
)
from imfusion_webappkit.examples._assets import (
    DEFAULT_LOGO,
    SAMPLE_IMAGE,
    SAMPLE_IMAGE_THUMBNAIL,
)


class ClinicalBoxStep(CustomStep):
    """Measure down from a landmark by a participant-specific distance.

    The distance is a number the operator reads off a chart rather than
    something in the image, so it cannot come from the annotation. The step
    collects it in a field, draws the line at that length from the landmark the
    user clicks, and then asks for the region around the line's far end.
    """

    def __init__(self, image_from, step_id="clinical"):
        super().__init__(
            "Clinical Region",
            step_id=step_id,
            depends_on=[image_from],
        )
        self.image_from = image_from
        self.line = None
        self.box = None

    def _image(self):
        return self.app.workflow.get_step(self.image_from).inputs["image"]

    def on_enter(self):
        # Annotations are created up front so the panel can show empty slots,
        # and armed one at a time from on_action.
        model = self.app.annotation_model
        image = self._image()
        if self.line is None:
            self.line = model.create_annotation(AnnotationType.LINE, image)
            self.line.color = (0.2, 0.8, 1.0)
            self.line.label = "Motor point"
        if self.box is None:
            self.box = model.create_annotation(AnnotationType.RECTANGLE, image)
            self.box.color = (1.0, 0.45, 0.8)
            self.box.label = "Clinical region"

    def body(self):
        if self.line is None:
            # A dependent step's invalidation reads this one's fields, which can
            # happen before the step has ever been entered.
            return [Text("Select an image first.")]
        elements = [
            Text(
                "Enter the motor-point distance, measure it from the tibial "
                "plateau, then box the muscle belly around the line's end."
            ),
            Fields(
                [
                    FloatParameter(
                        "motor_point_distance",
                        label="Motor-point distance",
                        default=120.0,
                        minimum=1.0,
                        maximum=500.0,
                        step=1.0,
                        unit="mm",
                    )
                ],
                submit_action="set_distance",
            ),
            AnnotationField(
                [self.line, self.box],
                label="Placement",
                place_action="place",
                clear_action="clear",
                prompts=["Measure from the tibial plateau", "Box the muscle belly"],
                show_measurements=True,
            ),
        ]
        if self.line.complete and not self.box.complete:
            elements.append(
                Text(
                    f"Line length: {self.line.length:.1f} mm. Place the box next.",
                )
            )
        return elements

    def on_action(self, action):
        if action == "place":
            target = self.line if not self.line.complete else self.box
            if not target.complete:
                target.start_editing()
        elif action == "clear":
            for annotation in (self.line, self.box):
                self.app.annotation_model.remove(annotation)
            self.line = None
            self.box = None
            self.on_enter()

    def can_proceed(self):
        if self.box is None or not self.box.complete:
            return False, "Place both the line and the region before continuing"
        return True, ""

    def reset_workflow_state(self):
        super().reset_workflow_state()
        self.line = None
        self.box = None


class ExportAnnotationsStep(CustomStep):
    """Write the collected geometry, in image coordinates, to a JSON download."""

    def __init__(self, image_from, anatomical_from, clinical_from, step_id="export"):
        super().__init__(
            "Export Annotations",
            step_id=step_id,
            depends_on=[anatomical_from, clinical_from],
        )
        self.image_from = image_from
        self.anatomical_from = anatomical_from
        self.clinical_from = clinical_from

    def body(self):
        return [
            Text("Download the boxes and the source image path as JSON."),
            Button("download", "Download annotations", style="primary"),
        ]

    def on_action(self, action):
        if action != "download":
            return
        image = self.app.workflow.get_step(self.image_from).inputs["image"]
        anatomical = self.app.workflow.get_step(self.anatomical_from)
        clinical = self.app.workflow.get_step(self.clinical_from)

        def describe(annotation):
            # Image coordinates, not world: the world points stop meaning
            # anything the moment the image's matrix changes.
            points = annotation.points_in(image)
            lower = [min(axis) for axis in zip(*points)]
            upper = [max(axis) for axis in zip(*points)]
            return {
                "label": annotation.label,
                "type": annotation.type.value,
                "center": [(low + high) / 2 for low, high in zip(lower, upper)],
                "size": [high - low for low, high in zip(lower, upper)],
                "points": [list(point) for point in points],
            }

        payload = {
            "image": self.data_model.get_source_path(image),
            "image_name": self.data_model.get_name(image),
            "anatomical": [
                describe(annotation) for annotation in anatomical.annotations["image"]
            ],
            "clinical": [describe(clinical.line), describe(clinical.box)],
            "motor_point_distance_mm": clinical.values.get("motor_point_distance"),
        }
        self.app.download(
            "annotations.json",
            json.dumps(payload, indent=2).encode(),
            media_type="application/json",
        )


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
        title="Region Annotation",
        branding=BrandingConfig(logo=DEFAULT_LOGO),
        sidebar=SidebarConfig(show_datamodel=True, show_views=True, collapsed=True),
        sample_datasets=sample_datasets,
        show_export_button=False,
    )
    webapp.set_workflow(
        [
            MessageStep(
                "Welcome",
                "Load an image, annotate two regions, then export the geometry.",
                step_id="welcome",
            ),
            InputSelectionStep(
                "Select Image",
                inputs=[InputSpec("image", "Image")],
                message="Load the image to annotate.",
                step_id="input",
            ),
            AnnotationStep(
                title="Anatomical Region",
                message=(
                    "Locate the region of strongest nerve branching, then box "
                    "it in an axial slice."
                ),
                annotation_type=AnnotationType.RECTANGLE,
                image_from="input",
                image_role="image",
                show_measurements=True,
                step_id="anatomical",
            ),
            ClinicalBoxStep(image_from="input", step_id="clinical"),
            ExportAnnotationsStep(
                image_from="input",
                anatomical_from="anatomical",
                clinical_from="clinical",
                step_id="export",
            ),
        ]
    )
    webapp.run(host=host, port=port)


if __name__ == "__main__":
    main()
