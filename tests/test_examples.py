"""Ensure shipped examples track the installed ImFusion SDK API."""

import importlib

import imfusion
import numpy as np
import pytest

from imfusion_webappkit.algorithm_registry import AlgorithmRegistry

EXAMPLE_MODULES = [
    "add_noise_algorithm",
    "annotation_demo",
    "annotation_workflow_demo",
    "registration_demo",
    "registration_workflow_demo",
    "static_demos",
    "webapp_demo",
    "workflow_demo",
]


@pytest.mark.parametrize("module_name", EXAMPLE_MODULES)
def test_example_imports(module_name):
    importlib.import_module(f"imfusion_webappkit.examples.{module_name}")


@pytest.mark.parametrize("spec_name", ["actions", "workflow"])
def test_static_demo_examples_describe_a_recordable_application(spec_name):
    """Guard the claim the examples make, without paying to record them.

    Recording either one takes half a minute and several megabytes. What can rot
    cheaply is the configuration: an application that offers to load a dataset,
    export a file, or list algorithms cannot answer for any of it once Python is
    gone, and the recorder only says so as a warning.
    """
    from imfusion_webappkit.static_demo.recorder import inspect_app

    module = importlib.import_module("imfusion_webappkit.examples.static_demos")
    spec = getattr(module, spec_name)
    metadata = inspect_app(spec)

    assert not metadata.config["show_load_button"]
    assert not metadata.config["show_export_button"]
    assert not metadata.config["algorithms_enabled"]
    assert not metadata.sample_datasets
    assert len(spec.app().initial_data), "a recorded demo has to arrive with its data"


def test_add_noise_algorithm_uses_registered_algorithm_api():
    module = importlib.import_module("imfusion_webappkit.examples.add_noise_algorithm")
    images = imfusion.SharedImageSet(np.ones((1, 8, 8, 1), dtype=np.float32))
    algorithm = module.AddNoiseAlgorithm(images)
    algorithm.num_voxels = 4

    result = algorithm()

    assert "PYTHON.AddNoiseAlgorithm" in imfusion.algorithm.list_available()
    assert isinstance(result, imfusion.SharedImageSet)
    assert len(result) == 1
    assert np.count_nonzero(np.asarray(result[0]) == 0) >= 1


def test_registered_example_executes_through_webapp_registry():
    importlib.import_module("imfusion_webappkit.examples.add_noise_algorithm")
    images = imfusion.SharedImageSet(np.ones((1, 8, 8, 1), dtype=np.float32))
    registry = AlgorithmRegistry()
    registry.enable()

    result = registry.execute_algorithm(
        "PYTHON.AddNoiseAlgorithm",
        [images],
        {"Number of noise voxels": 4},
    )

    assert len(result) == 1
    assert isinstance(result[0], imfusion.SharedImageSet)
    assert np.count_nonzero(np.asarray(result[0][0]) == 0) >= 1


def _summary_step_with_label_map(label_map):
    """Bind the demo summary step to a workflow that already produced a result."""
    from types import SimpleNamespace

    from imfusion_webappkit import ProcessingStep, Workflow

    module = importlib.import_module("imfusion_webappkit.examples.workflow_demo")
    processing = ProcessingStep(step_id="process")
    processing.result = label_map
    step = module.SegmentationSummaryStep(label_map_from="process", step_id="summary")
    updates = []
    app = SimpleNamespace(
        cancellation_requested=False,
        update_progress=lambda *_args, **_kwargs: None,
        data_model=SimpleNamespace(
            index=lambda value: 0 if value is label_map else -1,
            update=updates.append,
        ),
        _session=SimpleNamespace(send_message=lambda *_args: None),
    )
    workflow = Workflow(app, [processing, step])
    app.workflow = workflow
    return step, updates


def _binary_label_map(labelled_voxels: int):
    values = np.zeros((1, 4, 4, 1), dtype=np.uint8)
    values.reshape(-1)[:labelled_voxels] = 1
    image = imfusion.SharedImage(values)
    image.spacing = [10.0, 10.0, 10.0]
    return imfusion.SharedImageSet(image)


def test_workflow_demo_summary_step_measures_the_label_map():
    step, _updates = _summary_step_with_label_map(_binary_label_map(4))

    step.on_enter()
    body = step.get_ui_config()["body"]

    metrics = next(element for element in body if element["kind"] == "metrics")
    table = next(element for element in body if element["kind"] == "table")
    assert metrics["items"] == [
        {"label": "Labelled voxels", "value": "4"},
        {"label": "Volume", "value": 4.0, "unit": "mL"},
    ]
    assert table["rows"] == [["Image 1", 4, 4.0]]
    assert not [element for element in body if element["kind"] == "alert"]


def test_workflow_demo_summary_step_charts_the_slice_profile():
    values = np.zeros((3, 4, 4, 1), dtype=np.uint8)
    values[1] = 1
    image = imfusion.SharedImage(values)
    image.spacing = [10.0, 10.0, 2.0]
    step, _updates = _summary_step_with_label_map(imfusion.SharedImageSet(image))

    step.on_enter()
    body = step.get_ui_config()["body"]

    chart = next(element for element in body if element["kind"] == "chart")
    assert chart["variant"] == "line"
    assert chart["series"] == [
        {"label": "Labelled voxels", "values": [0.0, 16.0, 0.0], "x": [0.0, 2.0, 4.0]}
    ]


def test_workflow_demo_summary_step_warns_and_disables_action_when_empty():
    step, _updates = _summary_step_with_label_map(_binary_label_map(0))

    step.on_enter()
    body = step.get_ui_config()["body"]

    assert [element["level"] for element in body if element["kind"] == "alert"] == [
        "warning"
    ]
    assert next(element for element in body if element["kind"] == "button")["disabled"]


def test_workflow_demo_summary_step_applies_the_selected_label_value():
    label_map = _binary_label_map(4)
    step, updates = _summary_step_with_label_map(label_map)
    step.on_enter()

    step.receive_data({"values": {"label_value": 7}})
    step.run_action("apply_label")

    assert sorted(np.unique(np.asarray(label_map[0]))) == [0, 7]
    assert updates == [0]


def test_annotation_demo_labels_boxes_but_leaves_measured_shapes_alone():
    """The session callback is the only thing driving this demo, so it is the test.

    A distance and an angle are labelled by the viewer itself and that text
    wins, so the demo labels neither; a rectangle gets none and is labelled
    here.
    """
    from imfusion_webappkit import AnnotationType

    from .test_annotations import FakeSession, finish

    module = importlib.import_module("imfusion_webappkit.examples.annotation_demo")
    session = FakeSession([object()])
    module.label_with_measurement(session.controller)

    drawn = {}
    for name, shape, points in [
        ("line", "LineSegment", [[0, 0, 0], [3, 4, 0]]),
        ("angle", "Angle", [[1, 0, 0], [0, 0, 0], [0, 1, 0]]),
        ("box", "Rectangle", [[0, 0, 0], [2, 5, 0]]),
    ]:
        session.annotation_model._handle_created(
            {"id": name, "type": shape, "data_index": 0, "points": []}
        )
        drawn[name] = session.annotation_model._find(name)
        finish(session, drawn[name], points)

    assert drawn["box"].label == "5.0 × 2.0 mm"
    assert drawn["line"].label == ""
    assert drawn["angle"].label == ""
    # The measurements themselves are still what the export reports.
    assert module.measurement(drawn["line"]) == "5.0 mm"
    assert module.measurement(drawn["angle"]) == "90.0°"
    # A shape with no measurement of its own reports none, rather than a zero.
    point = session.annotation_model.create_annotation(
        AnnotationType.POINT, session.data_model[0]
    )
    point.points = [[1, 2, 3]]
    assert module.measurement(point) == ""


def test_annotation_demo_exports_the_measurements_it_collected():
    import csv
    import io

    from .test_annotations import FakeSession, finish

    module = importlib.import_module("imfusion_webappkit.examples.annotation_demo")
    session = FakeSession([object()])
    module.label_with_measurement(session.controller)
    session.annotation_model._handle_created(
        {"id": "line", "type": "LineSegment", "data_index": 0, "points": []}
    )
    placed = session.annotation_model._find("line")
    finish(session, placed, [[0, 0, 0], [3, 4, 0]])
    # Still being drawn, so it has no measurement to report yet.
    session.annotation_model._handle_created(
        {"id": "pending", "type": "Angle", "data_index": 0, "points": []}
    )

    module.export_measurements(session.controller)

    filename, content, media_type = session.controller.downloads[0]
    assert (filename, media_type) == ("measurements.csv", "text/csv")
    rows = list(csv.reader(io.StringIO(content.decode())))
    assert rows[0] == ["dataset", "source", "type", "measurement", "points"]
    assert rows[1] == [
        "Data 1",
        "/scans/data1.imf",
        "LineSegment",
        "5.0 mm",
        "0.00,0.00,0.00; 3.00,4.00,0.00",
    ]
    assert len(rows) == 2


def test_annotation_workflow_demo_exports_boxes_in_image_coordinates():
    """Guard the arithmetic between world points and the downloaded JSON.

    World points are what the browser reports and the file has to carry the
    image frame instead, so an image whose matrix is not the identity is the
    only case that tells the two apart.
    """
    import json

    from imfusion_webappkit import (
        AnnotationStep,
        AnnotationType,
        InputSelectionStep,
        InputSpec,
        Workflow,
    )

    from .test_annotations import FakeSession, image

    module = importlib.import_module(
        "imfusion_webappkit.examples.annotation_workflow_demo"
    )
    scan = image(offset=(10.0, 0.0, 0.0))
    session = FakeSession([scan])

    inputs = InputSelectionStep(
        "Select image", inputs=[InputSpec("image", "Image")], step_id="input"
    )
    anatomical = AnnotationStep(
        annotation_type=AnnotationType.RECTANGLE,
        image_from="input",
        image_role="image",
        step_id="anatomical",
    )
    clinical = module.ClinicalBoxStep(image_from="input", step_id="clinical")
    export = module.ExportAnnotationsStep(
        image_from="input",
        anatomical_from="anatomical",
        clinical_from="clinical",
        step_id="export",
    )
    workflow = Workflow(
        session.controller, steps=[inputs, anatomical, clinical, export]
    )
    workflow.app._session = session
    session.controller.workflow = workflow
    inputs.assignments = {"image": scan}

    # Assigning points is the other way an annotation reaches the browser, so
    # the geometry can be set here; placement itself is covered elsewhere.
    anatomical.on_enter()
    anatomical.annotations["image"][0].points = [[10, 0, 0], [20, 40, 0]]
    clinical.on_enter()
    clinical.line.points = [[10, 0, 0], [10, 120, 0]]
    clinical.box.points = [[12, 100, 0], [18, 140, 0]]
    clinical.receive_data({"values": {"motor_point_distance": 120.0}})

    export.on_action("download")

    filename, content, media_type = session.controller.downloads[0]
    payload = json.loads(content)
    assert (filename, media_type) == ("annotations.json", "application/json")
    assert payload["image"] == "/scans/data1.imf"
    assert payload["motor_point_distance_mm"] == 120.0
    # The image sits 10 mm along x in world space, so its own frame starts at zero.
    assert payload["anatomical"][0]["center"] == [5.0, 20.0, 0.0]
    assert payload["anatomical"][0]["size"] == [10.0, 40.0, 0.0]
    assert payload["clinical"][0]["type"] == "LineSegment"


def test_imfusion_feature_dependencies_are_installed():
    assert hasattr(imfusion, "dicom")
    assert hasattr(imfusion, "registration")
    assert hasattr(imfusion.registration, "ImageRegistrationAlgorithm")
    assert hasattr(imfusion.registration, "apply_deformation")
