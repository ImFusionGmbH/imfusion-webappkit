"""Measurements the user draws whenever they like, with no workflow.

The sidebar panel lets them reach for a shape at any point, so the annotations
arrive unprompted. ``on_session_created`` is where a non-workflow application
hooks that up: it labels each finished box with its extent, and two actions
export what has been collected.

``annotation_workflow_demo.py`` is the same feature driven the other way round,
by a workflow that asks for a specific annotation at a specific step.
"""

import csv
import io
import json

import imfusion

from imfusion_webappkit import (
    Annotation,
    AnnotationParameter,
    AnnotationType,
    BrandingConfig,
    ImFusionWebApp,
    InfoConfig,
    InputSpec,
    SampleDataset,
    SidebarConfig,
    WebApplicationController,
)
from imfusion_webappkit.examples._assets import (
    DEFAULT_LOGO,
    SAMPLE_IMAGE,
    SAMPLE_IMAGE_THUMBNAIL,
)


def measurement(annotation: Annotation) -> str:
    """The annotation's own measurement, or an empty string when it has none.

    ``length`` and ``angle`` are filled in by the model for the shapes that
    have them. A rectangle has neither, so its extent is taken from the two
    corners; the third component is zero because it is drawn in a slice.
    """
    if annotation.length is not None:
        return f"{annotation.length:.1f} mm"
    if annotation.angle is not None:
        return f"{annotation.angle:.1f}°"
    if annotation.type is AnnotationType.RECTANGLE and len(annotation.points) == 2:
        extents = sorted(
            (abs(high - low) for low, high in zip(*annotation.points)), reverse=True
        )
        return f"{extents[0]:.1f} × {extents[1]:.1f} mm"
    return ""


def label_with_measurement(app: WebApplicationController) -> None:
    """Label each finished rectangle with its extent.

    Registered per browser connection, because the annotation model is
    per-session like the data model.

    Only rectangles: the viewer draws its own measurement next to a distance or
    an angle, and that text wins over `label`, so setting one there would be
    both invisible and redundant.
    """

    def track(annotation: Annotation) -> None:
        if annotation.type is not AnnotationType.RECTANGLE:
            return
        # Registered on the new annotation rather than acted on directly: the
        # browser reports it as soon as the user picks a tool, before there are
        # any points to measure.
        annotation.on_editing_finished(
            lambda: setattr(annotation, "label", measurement(annotation))
        )

    app.annotation_model.on_annotation_added(track)


def export_measurements(app: WebApplicationController) -> None:
    """Download every annotation in the session as a CSV of measurements."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["dataset", "source", "type", "measurement", "points"])
    for annotation in app.annotation_model.annotations():
        if not annotation.complete:
            continue
        writer.writerow(
            [
                app.data_model.get_name(annotation.data),
                app.data_model.get_source_path(annotation.data) or "",
                annotation.type.value,
                measurement(annotation),
                # Semicolon-separated, so one annotation stays one row whatever
                # its point count.
                "; ".join(
                    ",".join(f"{value:.2f}" for value in point)
                    for point in annotation.points
                ),
            ]
        )
    app.download("measurements.csv", buffer.getvalue().encode(), "text/csv")


def export_region(
    image: imfusion.SharedImageSet,
    roi: Annotation,
    app: WebApplicationController,
) -> None:
    """Download one region as JSON, in the image's own coordinate frame.

    ``roi`` arrives as an ``Annotation`` the user drew in the action's dialog:
    the browser sends its id and the registry exchanges it for the object.
    """
    corners = roi.points_in(image)
    lower = [min(axis) for axis in zip(*corners)]
    upper = [max(axis) for axis in zip(*corners)]
    payload = {
        "dataset": app.data_model.get_name(image),
        "source": app.data_model.get_source_path(image),
        # Image coordinates, not world: the world points stop meaning anything
        # the moment the image's matrix changes.
        "center": [(low + high) / 2 for low, high in zip(lower, upper)],
        "size": [high - low for low, high in zip(lower, upper)],
        "corners": [list(corner) for corner in corners],
    }
    app.download(
        "region.json", json.dumps(payload, indent=2).encode(), "application/json"
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
        title="Measurements",
        branding=BrandingConfig(logo=DEFAULT_LOGO),
        sidebar=SidebarConfig(
            show_datamodel=True,
            show_views=True,
            show_annotations=True,
        ),
        info=InfoConfig(
            title="About this demo",
            content=(
                "Pick a shape under **Annotations** and draw it in a slice "
                "view. Boxes are labelled with their extent; distances and "
                "angles come with their own. Use the actions to download what "
                "you have measured."
            ),
        ),
        sample_datasets=sample_datasets,
        show_export_button=False,
    )

    webapp.on_session_created(label_with_measurement)
    webapp.register("Export Measurements", export_measurements)
    webapp.register(
        "Export Region",
        export_region,
        inputs=[InputSpec("image", "Image")],
        parameters=[
            AnnotationParameter(
                "roi",
                annotation_type=AnnotationType.RECTANGLE,
                label="Region of interest",
                description="Press Place, then drag a box in a slice view.",
            )
        ],
    )
    webapp.run(host=host, port=port)


if __name__ == "__main__":
    main()
