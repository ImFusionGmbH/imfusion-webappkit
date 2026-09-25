"""Annotation model, workflow step, action parameter and lifetime coverage."""

import asyncio
import json
import threading
import time

import numpy as np
import pytest

from imfusion_webappkit import (
    AnnotationField,
    AnnotationParameter,
    AnnotationStep,
    AnnotationType,
    CustomStep,
    ImFusionWebApp,
    InputSelectionStep,
    InputSpec,
    MessageStep,
    Workflow,
)
from imfusion_webappkit.annotation_model import WebAnnotationModel
from imfusion_webappkit.parameter_spec import resolve_annotation_parameters


class FakeSession:
    """Just enough session for the annotation model and a workflow step."""

    def __init__(self, datasets=()):
        self.messages = []
        self.data_model = FakeDataModel(list(datasets))
        self.controller = FakeController(self)
        self.annotation_model = WebAnnotationModel(object(), self)
        self.data_model.session = self

    def send_message(self, message_type, data):
        self.messages.append((message_type, data))

    def sent(self, message_type):
        return [data for kind, data in self.messages if kind == message_type]


class FakeDataModel(list):
    """A data model whose removals drive the same invalidation hook as the real one."""

    session = None

    def contains(self, data):
        return any(item is data for item in self)

    def index(self, data):
        for position, item in enumerate(self):
            if item is data:
                return position
        raise ValueError("Data not found in model")

    def get_name(self, data_or_index):
        index = (
            data_or_index
            if isinstance(data_or_index, int)
            else self.index(data_or_index)
        )
        return f"Data {index + 1}"

    def get_source_path(self, data_or_index):
        index = (
            data_or_index
            if isinstance(data_or_index, int)
            else self.index(data_or_index)
        )
        return f"/scans/data{index + 1}.imf"

    def remove(self, data):
        self.session.annotation_model._remove_for_data(data)
        super().remove(data)


class FakeController:
    def __init__(self, session):
        self._session = session
        self.selected = []
        self.downloads = []

    @property
    def data_model(self):
        return self._session.data_model

    @property
    def annotation_model(self):
        return self._session.annotation_model

    @property
    def selected_data(self):
        return list(self.selected)

    def select_data(self, data):
        self.selected = list(data) if isinstance(data, (list, tuple)) else [data]

    def download(self, filename, content, media_type="application/octet-stream"):
        self.downloads.append((filename, content, media_type))


def image(offset=(0.0, 0.0, 0.0)):
    """A real SharedImageSet, so matrix-based conversions are exercised."""
    import imfusion

    data = imfusion.SharedImageSet(
        imfusion.SharedImage(np.zeros((4, 4, 4, 1), dtype=np.uint8))
    )
    matrix = np.eye(4)
    matrix[:3, 3] = offset
    data.set_matrix(matrix)
    return data


def finish(session, annotation, points):
    """Deliver the event the browser would send once the user is done."""
    session.annotation_model._handle_event(
        {
            "id": annotation.id,
            "event": "editing_finished",
            "points": points,
            "max_points": len(points),
        }
    )


# ===== model =====


def test_create_annotation_defers_the_browser_call_until_editing_starts():
    session = FakeSession([object()])
    annotation = session.annotation_model.create_annotation(
        AnnotationType.RECTANGLE, session.data_model[0]
    )

    assert session.messages == []

    annotation.start_editing()

    (payload,) = session.sent("annotation_add")
    assert payload["id"] == annotation.id
    assert payload["type"] == "Rectangle"
    assert payload["data_index"] == 0
    assert payload["editing"] is True


def test_appearance_set_before_editing_travels_with_the_creation_message():
    session = FakeSession([object()])
    annotation = session.annotation_model.create_annotation(
        AnnotationType.LINE, session.data_model[0]
    )
    annotation.color = (1.0, 0.0, 0.0)
    annotation.label = "Femur"

    assert session.messages == []

    annotation.start_editing()

    (payload,) = session.sent("annotation_add")
    assert payload["color"] == [1.0, 0.0, 0.0, 1.0]
    assert payload["label"] == "Femur"


def test_assigning_points_publishes_a_display_only_annotation():
    session = FakeSession([object()])
    annotation = session.annotation_model.create_annotation(
        AnnotationType.LINE, session.data_model[0]
    )
    annotation.points = [(0, 0, 0), (1, 2, 3)]

    (payload,) = session.sent("annotation_add")
    assert payload["editing"] is False
    assert payload["points"] == [[0.0, 0.0, 0.0], [1.0, 2.0, 3.0]]


def test_setting_points_after_creation_sends_an_update():
    session = FakeSession([object()])
    annotation = session.annotation_model.create_annotation(
        AnnotationType.LINE, session.data_model[0]
    )
    annotation.start_editing()
    annotation.points = [(0, 0, 0), (5, 0, 0)]

    (payload,) = session.sent("annotation_update")
    assert payload == {
        "id": annotation.id,
        "points": [[0.0, 0.0, 0.0], [5.0, 0.0, 0.0]],
    }


def test_create_annotation_falls_back_to_the_selection():
    session = FakeSession([object(), object()])
    session.controller.selected = [session.data_model[1]]

    annotation = session.annotation_model.create_annotation(AnnotationType.POINT)

    assert annotation.data is session.data_model[1]


def test_create_annotation_without_a_dataset_or_a_single_selection_is_rejected():
    session = FakeSession([object(), object()])
    session.controller.selected = list(session.data_model)

    with pytest.raises(ValueError, match="exactly one is selected"):
        session.annotation_model.create_annotation(AnnotationType.POINT)


def test_editing_finished_updates_points_and_calls_back():
    session = FakeSession([object()])
    annotation = session.annotation_model.create_annotation(
        AnnotationType.LINE, session.data_model[0]
    )
    calls = []
    annotation.on_editing_finished(lambda: calls.append("no-args"))
    annotation.on_editing_finished(lambda annotation: calls.append(annotation.id))
    annotation.start_editing()

    finish(session, annotation, [[0, 0, 0], [3, 4, 0]])

    assert calls == ["no-args", annotation.id]
    assert annotation.points == [(0.0, 0.0, 0.0), (3.0, 4.0, 0.0)]
    assert annotation.complete is True
    assert annotation.max_points == 2
    assert annotation.length == pytest.approx(5.0)


def test_points_changed_streaming_is_requested_only_when_someone_listens():
    session = FakeSession([object()])
    model = session.annotation_model
    quiet = model.create_annotation(AnnotationType.LINE, session.data_model[0])
    quiet.start_editing()
    assert session.sent("annotation_add")[0]["notify_points_changed"] is False

    changes = []
    quiet.on_points_changed(lambda: changes.append(1))

    # Registering after start_editing has to switch streaming on, so the SDK's
    # "register first" advice stays advice rather than a trap.
    assert session.sent("annotation_update")[-1]["notify_points_changed"] is True

    model._handle_event(
        {"id": quiet.id, "event": "points_changed", "points": [[0, 0, 0]]}
    )
    assert changes == [1]


def test_aborting_clears_the_annotation_rather_than_leaving_it_armed():
    session = FakeSession([object()])
    annotation = session.annotation_model.create_annotation(
        AnnotationType.RECTANGLE, session.data_model[0]
    )
    annotation.start_editing()

    session.annotation_model._handle_event(
        {"id": annotation.id, "event": "editing_aborted", "points": []}
    )

    assert annotation.editing is False
    assert annotation.complete is False
    assert annotation.points == []


def test_an_already_placed_annotation_cannot_be_re_armed():
    session = FakeSession([object()])
    annotation = session.annotation_model.create_annotation(
        AnnotationType.POINT, session.data_model[0]
    )
    annotation.start_editing()
    finish(session, annotation, [[1, 1, 1]])

    with pytest.raises(RuntimeError, match="remove it and create a new one"):
        annotation.start_editing()


def test_an_unsupported_type_is_reported_as_an_error_not_a_crash():
    session = FakeSession([object()])
    annotation = session.annotation_model.create_annotation(
        AnnotationType.BOX, session.data_model[0]
    )
    annotation.start_editing()

    session.annotation_model._handle_event(
        {"id": annotation.id, "event": "unsupported", "message": "no Box in this build"}
    )

    assert annotation.editing is False
    assert annotation.error == "no Box in this build"


def test_events_for_unknown_ids_are_ignored():
    session = FakeSession([object()])

    session.annotation_model._handle_event(
        {"id": "gone", "event": "editing_finished", "points": [[0, 0, 0]]}
    )

    assert session.annotation_model.annotations() == []


def test_a_failing_callback_does_not_break_the_event_dispatch():
    session = FakeSession([object()])
    annotation = session.annotation_model.create_annotation(
        AnnotationType.POINT, session.data_model[0]
    )
    later = []
    annotation.on_editing_finished(lambda: 1 / 0)
    annotation.on_editing_finished(lambda: later.append("ran"))
    annotation.start_editing()

    finish(session, annotation, [[0, 0, 0]])

    assert later == ["ran"]


def test_points_in_converts_into_a_datasets_own_frame():
    moving = image(offset=(10.0, 0.0, 0.0))
    session = FakeSession([moving])
    annotation = session.annotation_model.create_annotation(
        AnnotationType.POINT, moving
    )
    annotation.start_editing()
    finish(session, annotation, [[12.0, 3.0, 0.0]])

    assert annotation.points == [(12.0, 3.0, 0.0)]
    assert annotation.points_in() == [pytest.approx((2.0, 3.0, 0.0))]


def test_angle_is_measured_at_the_middle_control_point():
    session = FakeSession([object()])
    annotation = session.annotation_model.create_annotation(
        AnnotationType.ANGLE, session.data_model[0]
    )
    annotation.start_editing()
    finish(session, annotation, [[1, 0, 0], [0, 0, 0], [0, 1, 0]])

    assert annotation.angle == pytest.approx(90.0)
    assert annotation.length is None


def test_data_annotations_and_clear():
    first, second = object(), object()
    session = FakeSession([first, second])
    model = session.annotation_model
    one = model.create_annotation(AnnotationType.POINT, first)
    two = model.create_annotation(AnnotationType.POINT, second)

    assert model.data_annotations(first) == [one]
    assert model.annotations() == [one, two]

    model.clear()
    assert model.annotations() == []


def test_a_client_drawn_annotation_reaches_python():
    session = FakeSession([object()])
    seen = []
    session.annotation_model.on_annotation_added(
        lambda annotation: seen.append(annotation)
    )

    session.annotation_model._handle_created(
        {
            "id": "client-1",
            "type": "LineSegment",
            "data_index": 0,
            "points": [[0, 0, 0], [1, 0, 0]],
        }
    )

    (annotation,) = session.annotation_model.annotations()
    assert seen == [annotation]
    assert annotation.type is AnnotationType.LINE
    assert annotation.complete is True
    assert annotation.points == [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)]


def test_a_sidebar_annotation_is_still_being_drawn_when_it_arrives():
    """The browser reports it as soon as the user picks a tool, so it is not done.

    Calling it complete would let ``complete`` be true with no geometry, and
    would make ``start_editing`` refuse an annotation nobody has drawn yet.
    """
    session = FakeSession([object()])

    session.annotation_model._handle_created(
        {"id": "client-1", "type": "Rectangle", "data_index": 0, "points": []}
    )

    (annotation,) = session.annotation_model.annotations()
    assert annotation.complete is False
    assert annotation.editing is True

    finish(session, annotation, [[0, 0, 0], [2, 3, 0]])

    assert annotation.complete is True
    assert annotation.editing is False


def test_a_duplicate_client_annotation_is_ignored():
    session = FakeSession([object()])
    payload = {"id": "client-1", "type": "Angle", "data_index": 0, "points": []}

    session.annotation_model._handle_created(payload)
    session.annotation_model._handle_created(payload)

    assert len(session.annotation_model.annotations()) == 1


def test_removing_a_dataset_retires_its_annotations_first():
    keep, doomed = object(), object()
    session = FakeSession([keep, doomed])
    model = session.annotation_model
    survivor = model.create_annotation(AnnotationType.POINT, keep)
    survivor.start_editing()
    dying = model.create_annotation(AnnotationType.POINT, doomed)
    dying.start_editing()

    session.data_model.remove(doomed)

    assert model.annotations() == [survivor]
    # The removal has to be on the wire before the dataset's, or the Web SDK is
    # left keying annotations by a freed pointer.
    order = [kind for kind, _ in session.messages]
    assert order[-1] == "annotation_remove"
    assert session.sent("annotation_remove")[-1] == {"id": dying.id}


# ===== workflow step =====


def workflow_with(step, datasets):
    session = FakeSession(datasets)
    session.controller.selected = list(datasets)
    workflow = Workflow(session.controller, steps=[step, MessageStep("Done", "done")])
    workflow.app._session = session
    return session, workflow


def test_annotation_step_arms_only_when_asked_and_gates_next():
    data = object()
    step = AnnotationStep(annotation_type=AnnotationType.RECTANGLE, step_id="roi")
    session, workflow = workflow_with(step, [data])
    workflow.start()

    # Entry must not arm: the first click would otherwise become an annotation
    # while the user is still navigating.
    assert session.sent("annotation_add") == []
    assert step.can_proceed()[0] is False

    workflow.receive_step_data({"action": "place"})
    (payload,) = session.sent("annotation_add")
    assert payload["editing"] is True

    annotation = step.annotations["default"][0]
    finish(session, annotation, [[0, 0, 0], [1, 1, 0]])

    assert step.complete is True
    assert step.can_proceed() == (True, "")
    assert step.points == [[(0.0, 0.0, 0.0), (1.0, 1.0, 0.0)]]


def test_a_labelled_sequence_arms_the_next_prompt_by_itself():
    data = object()
    step = AnnotationStep(
        annotation_type=AnnotationType.POINT,
        labels=["Tibial plateau", "Motor point"],
        step_id="landmarks",
    )
    session, workflow = workflow_with(step, [data])
    workflow.start()
    workflow.receive_step_data({"action": "place"})

    first, second = step.annotations["default"]
    assert first.label == "Tibial plateau"
    finish(session, first, [[0, 0, 0]])

    # One button press, N clicks.
    assert second.editing is True
    assert len(session.sent("annotation_add")) == 2

    finish(session, second, [[1, 0, 0]])
    assert step.complete is True


def test_roles_collect_one_annotation_per_dataset_in_distinct_colours():
    fixed, moving = object(), object()
    inputs = InputSelectionStep(
        inputs=[InputSpec("fixed", "Fixed"), InputSpec("moving", "Moving")],
        step_id="pair",
    )
    step = AnnotationStep(
        annotation_type=AnnotationType.POINT,
        image_from="pair",
        image_roles=["fixed", "moving"],
        labels=["A", "B", "C"],
        step_id="init",
    )
    session = FakeSession([fixed, moving])
    workflow = Workflow(session.controller, steps=[inputs, step])
    inputs.assignments = {"fixed": fixed, "moving": moving}
    workflow._current_index = 1
    step.on_enter()

    assert [a.data for a in step.annotations["fixed"]] == [fixed] * 3
    assert [a.data for a in step.annotations["moving"]] == [moving] * 3
    assert step.annotations["fixed"][0].color != step.annotations["moving"][0].color
    config = step.get_ui_config()
    assert [role["role"] for role in config["roles"]] == ["fixed", "moving"]
    assert config["total"] == 6


def test_redo_replaces_the_annotation_because_creation_mode_cannot_be_re_armed():
    data = object()
    step = AnnotationStep(annotation_type=AnnotationType.POINT, step_id="roi")
    session, workflow = workflow_with(step, [data])
    workflow.start()
    workflow.receive_step_data({"action": "place"})
    original = step.annotations["default"][0]
    finish(session, original, [[0, 0, 0]])

    workflow.receive_step_data({"action": "redo"})

    replacement = step.annotations["default"][0]
    assert replacement is not original
    assert replacement.editing is True
    assert session.sent("annotation_remove")[-1] == {"id": original.id}


def test_clear_removes_the_annotations_and_starts_over():
    data = object()
    step = AnnotationStep(annotation_type=AnnotationType.POINT, step_id="roi")
    session, workflow = workflow_with(step, [data])
    workflow.start()
    workflow.receive_step_data({"action": "place"})
    finish(session, step.annotations["default"][0], [[0, 0, 0]])

    workflow.receive_step_data({"action": "clear"})

    assert step.complete is False
    assert step.points == [[]]


def test_an_optional_step_can_be_skipped():
    step = AnnotationStep(
        annotation_type=AnnotationType.POINT, required=False, step_id="optional"
    )
    _session, workflow = workflow_with(step, [object()])
    workflow.start()

    assert step.can_proceed() == (True, "")
    assert step.complete is False


def test_keeping_annotations_reuses_them_when_the_step_is_re_entered():
    data = object()
    step = AnnotationStep(annotation_type=AnnotationType.POINT, step_id="roi")
    session, workflow = workflow_with(step, [data])
    workflow.start()
    workflow.receive_step_data({"action": "place"})
    annotation = step.annotations["default"][0]
    finish(session, annotation, [[2, 2, 2]])

    workflow.next_step()
    workflow.previous_step()

    assert step.annotations["default"] == [annotation]
    assert step.points == [[(2.0, 2.0, 2.0)]]
    assert len(session.annotation_model.annotations()) == 1


def test_discarding_annotations_on_exit_removes_them():
    data = object()
    step = AnnotationStep(
        annotation_type=AnnotationType.POINT,
        keep_annotations=False,
        step_id="roi",
    )
    session, workflow = workflow_with(step, [data])
    workflow.start()
    workflow.receive_step_data({"action": "place"})
    finish(session, step.annotations["default"][0], [[0, 0, 0]])

    workflow.next_step()

    assert session.annotation_model.annotations() == []


def test_the_step_forgets_annotations_whose_dataset_was_removed():
    data = object()
    step = AnnotationStep(annotation_type=AnnotationType.POINT, step_id="roi")
    session, workflow = workflow_with(step, [data])
    workflow.start()
    workflow.receive_step_data({"action": "place"})
    finish(session, step.annotations["default"][0], [[0, 0, 0]])

    session.data_model.remove(data)
    step.on_data_model_changed()

    assert step.annotations["default"] == []
    assert step.complete is False


def test_the_step_reports_geometry_changes_as_a_dependency_change():
    data = object()
    step = AnnotationStep(annotation_type=AnnotationType.POINT, step_id="roi")
    session, workflow = workflow_with(step, [data])
    workflow.start()
    before = step.dependency_value()
    workflow.receive_step_data({"action": "place"})
    finish(session, step.annotations["default"][0], [[0, 0, 0]])

    assert step.dependency_value() != before


def test_on_finished_runs_once_the_last_annotation_lands():
    data = object()
    seen = []
    step = AnnotationStep(
        annotation_type=AnnotationType.POINT,
        count=2,
        on_finished=lambda step: seen.append(len(step.points)),
        step_id="roi",
    )
    session, workflow = workflow_with(step, [data])
    workflow.start()
    workflow.receive_step_data({"action": "place"})
    first, second = step.annotations["default"]
    finish(session, first, [[0, 0, 0]])
    assert seen == []

    finish(session, second, [[1, 0, 0]])
    assert seen == [2]


def test_labels_and_count_must_agree():
    with pytest.raises(ValueError, match="count must match"):
        AnnotationStep(labels=["a", "b"], count=3)


def test_role_and_roles_are_mutually_exclusive():
    with pytest.raises(ValueError, match="either image_role or image_roles"):
        AnnotationStep(image_role="fixed", image_roles=["fixed"])


def test_default_views_exclude_the_volume_view_for_flat_shapes():
    flat = AnnotationStep(annotation_type=AnnotationType.RECTANGLE).get_ui_config()
    spatial = AnnotationStep(annotation_type=AnnotationType.BOX).get_ui_config()

    assert "3d" not in flat["views"]
    assert "3d" in spatial["views"]


# ===== action parameter =====


def test_annotation_parameter_resolves_its_id_to_the_annotation():
    session = FakeSession([object()])
    annotation = session.annotation_model.create_annotation(
        AnnotationType.RECTANGLE, session.data_model[0]
    )
    spec = AnnotationParameter("roi", annotation_type=AnnotationType.RECTANGLE)

    resolved = resolve_annotation_parameters(
        [spec], {"roi": annotation.id}, session.annotation_model
    )

    assert resolved["roi"] is annotation


def test_annotation_parameter_reports_a_missing_annotation_clearly():
    session = FakeSession([object()])
    spec = AnnotationParameter(
        "roi", annotation_type=AnnotationType.BOX, label="Region of interest"
    )

    with pytest.raises(ValueError, match="Place the Region of interest annotation"):
        resolve_annotation_parameters([spec], {"roi": ""}, session.annotation_model)


def test_annotation_parameter_serializes_its_type_for_the_browser():
    spec = AnnotationParameter("roi", annotation_type=AnnotationType.BOX)

    descriptor = spec.to_dict()

    assert descriptor["type"] == "annotation"
    assert descriptor["annotation_type"] == "Box"
    assert descriptor["value"] == ""


def test_only_annotation_parameters_may_declare_an_annotation_type():
    from imfusion_webappkit.parameter_spec import ParameterSpec

    with pytest.raises(ValueError, match="Only annotation parameters"):
        ParameterSpec("x", "int", 0, annotation_type="Box")


# ===== custom step element =====


def test_annotation_field_serializes_live_state_for_a_custom_step():
    session = FakeSession([object()])
    annotation = session.annotation_model.create_annotation(
        AnnotationType.LINE, session.data_model[0]
    )
    annotation.start_editing()
    finish(session, annotation, [[0, 0, 0], [0, 3, 4]])

    descriptor = AnnotationField(
        [annotation],
        label="Motor point distance",
        place_action="place_line",
        show_measurements=True,
    ).to_dict()

    assert descriptor["kind"] == "annotation"
    assert descriptor["place_action"] == "place_line"
    assert descriptor["annotations"][0]["complete"] is True
    assert descriptor["annotations"][0]["length"] == pytest.approx(5.0)


def test_annotation_field_rejects_a_prompt_count_that_does_not_match():
    session = FakeSession([object()])
    annotation = session.annotation_model.create_annotation(
        AnnotationType.POINT, session.data_model[0]
    )

    with pytest.raises(ValueError, match="one entry per annotation"):
        AnnotationField([annotation], prompts=["a", "b"])


def test_a_custom_step_can_mix_fields_with_annotation_placement():
    session = FakeSession([object()])
    placed = []

    class MeasureStep(CustomStep):
        def __init__(self):
            super().__init__("Measure", step_id="measure")
            self.line = None

        def body(self):
            return [
                AnnotationField(
                    [self.line] if self.line else [],
                    place_action="place_line",
                )
            ]

        def on_action(self, action):
            placed.append(action)
            self.line = self.app.annotation_model.create_annotation(
                AnnotationType.LINE, self.app.data_model[0]
            )
            self.line.start_editing()

    step = MeasureStep()
    workflow = Workflow(session.controller, steps=[step])
    workflow.start()
    workflow.run_current_step("place_line")

    assert placed == ["place_line"]
    (element,) = step.get_ui_config()["body"]
    assert element["kind"] == "annotation"
    assert element["annotations"][0]["id"] == step.line.id


def test_a_session_callback_can_register_an_annotation_listener():
    """The hook a non-workflow application uses to hear about drawn annotations."""
    webapp = ImFusionWebApp()
    seen = []
    webapp.on_session_created(
        lambda app: app.annotation_model.on_annotation_added(seen.append)
    )
    session = webapp._create_session()
    session.initialize()
    session.data_model._append_seed(object(), "Image")

    session.annotation_model._handle_created(
        {"id": "abc", "type": "Rectangle", "data_index": 0, "points": []}
    )

    assert [annotation.id for annotation in seen] == ["abc"]


# ===== protocol and controller =====


def _run_sync(webapp, coroutine, timeout=5.0):
    """Run `coroutine` while pumping the SDK owner thread, as the server does."""
    box = {}

    def runner():
        try:
            box["value"] = asyncio.run(coroutine)
        except BaseException as exc:  # noqa: BLE001 - surfaced to the caller
            box["error"] = exc

    thread = threading.Thread(target=runner)
    thread.start()
    deadline = time.monotonic() + timeout
    while thread.is_alive():
        if time.monotonic() > deadline:
            raise TimeoutError("Coroutine did not complete within the timeout")
        webapp.sdk_runtime.run_once(timeout=0.05)
    thread.join()
    if "error" in box:
        raise box["error"]
    return box.get("value")


def test_annotation_events_run_developer_callbacks_on_the_sdk_thread():
    webapp = ImFusionWebApp()
    session = webapp._create_session()
    session.websocket = object()
    session.data_model._append_seed(object(), "Image")
    annotation = session.annotation_model.create_annotation(
        AnnotationType.POINT, session.data_model[0]
    )
    threads = []
    annotation.on_editing_finished(
        lambda: threads.append(threading.current_thread().ident)
    )

    message = json.dumps(
        {
            "type": "annotation_event",
            "data": {
                "id": annotation.id,
                "event": "editing_finished",
                "points": [[1, 2, 3]],
                "max_points": 1,
            },
        }
    )

    _run_sync(
        webapp,
        webapp.websocket_handler.process_message(None, message, session),
    )

    assert threads == [threading.main_thread().ident]
    assert annotation.points == [(1.0, 2.0, 3.0)]


def test_download_sends_an_unsolicited_artifact():
    webapp = ImFusionWebApp()
    session = webapp._create_session()
    messages = []
    session.data_model._sync_send_message = lambda kind, data: messages.append(
        (kind, data)
    )

    session.controller.download("boxes.json", b'{"a": 1}', "application/json")

    kind, payload = messages[-1]
    assert kind == "download_artifact"
    assert payload["filename"] == "boxes.json"
    assert payload["media_type"] == "application/json"
    assert payload["buffer"] == "eyJhIjogMX0="


def test_download_needs_a_filename():
    webapp = ImFusionWebApp()
    session = webapp._create_session()

    with pytest.raises(ValueError, match="needs a filename"):
        session.controller.download("", b"payload")


def test_source_paths_follow_removals(tmp_path):
    first = tmp_path / "first.imf"
    second = tmp_path / "second.imf"
    webapp = ImFusionWebApp()
    model = webapp.initial_data
    model.add(object(), "One", source_path=str(first))
    model.add(object(), "Two", source_path=str(second))

    model.remove(0)

    assert model.get_source_path(0) == str(second)
    assert model.get_source_path(model[0]) == str(second)


def test_browser_supplied_data_has_no_source_path():
    webapp = ImFusionWebApp()
    model = webapp.initial_data
    model._append_from_client(object(), "Uploaded")

    assert model.get_source_path(0) is None
