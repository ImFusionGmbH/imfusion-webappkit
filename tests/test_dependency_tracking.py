"""Workflow dependency invalidation tests."""

from types import SimpleNamespace

import pytest

from imfusion_webappkit import (
    BrushStep,
    FloatParameter,
    InputSelectionStep,
    InputSpec,
    MessageStep,
    ParameterStep,
    ProcessingStep,
    ValidationStep,
    Workflow,
)


class MockDataModel:
    def __init__(self):
        self.values = []
        self._change_listeners = []

    def __len__(self):
        return len(self.values)

    def __getitem__(self, index):
        return self.values[index]

    def clear(self):
        self.values.clear()
        self._notify_change()

    def contains(self, value):
        return value in self.values

    def index(self, value):
        return self.values.index(value)

    def get_name(self, index):
        return f"Data {index + 1}"

    def add_change_listener(self, callback):
        self._change_listeners.append(callback)

    def _notify_change(self):
        for callback in tuple(self._change_listeners):
            callback()

    def _append_from_client(self, value, _name=""):
        self.values.append(value)
        self._notify_change()

    def _replace_from_client(self, index, value):
        self.values[index] = value
        self._notify_change()

    def remove(self, value):
        self.values.remove(value)
        self._notify_change()


def controller():
    session = SimpleNamespace(send_message=lambda *_args: None)
    app = SimpleNamespace(
        data_model=MockDataModel(),
        selected_data=[],
        publish_results=lambda *_args, **_kwargs: [],
        _session=session,
    )
    app.select_data = lambda values: app.selected_data.__setitem__(slice(None), values)
    return app


def input_selection_workflow(app, *specs):
    """Start a workflow whose first step selects inputs, wired like a session."""
    step = InputSelectionStep(inputs=list(specs), step_id="input")
    workflow = Workflow(app, [step, MessageStep("Done", "Complete")])
    app.data_model.add_change_listener(workflow._on_data_model_changed)
    workflow.start()
    return workflow, step


def test_input_selection_keeps_its_role_when_other_data_is_removed():
    app = controller()
    other = object()
    image = object()
    _, step = input_selection_workflow(app, InputSpec("image", "Image"))

    app.data_model._append_from_client(other)
    app.data_model._append_from_client(image)

    assert step.inputs == {"image": image}
    assert step.get_ui_config()["values"] == {"image": 1}

    app.data_model.remove(other)

    assert step.inputs == {"image": image}
    assert step.get_ui_config()["values"] == {"image": 0}
    assert step.can_proceed() == (True, "")


def test_input_selection_follows_the_newest_dataset():
    app = controller()
    first = object()
    second = object()
    _, step = input_selection_workflow(app, InputSpec("image", "Image"))

    app.data_model._append_from_client(first)

    assert step.inputs == {"image": first}
    assert app.selected_data == [first]

    app.data_model._append_from_client(second)

    assert step.inputs == {"image": second}
    assert app.selected_data == [second]


def test_input_selection_fills_required_roles_in_declaration_order():
    app = controller()
    fixed = object()
    moving = object()
    _, step = input_selection_workflow(
        app,
        InputSpec("fixed", "Fixed image"),
        InputSpec("moving", "Moving image"),
    )

    app.data_model._append_from_client(fixed)
    app.data_model._append_from_client(moving)

    assert step.inputs == {"fixed": fixed, "moving": moving}
    assert app.selected_data == [fixed, moving]


def test_input_selection_ignores_data_added_once_the_step_is_left():
    app = controller()
    image = object()
    generated = object()
    workflow, step = input_selection_workflow(app, InputSpec("image", "Image"))
    app.data_model._append_from_client(image)

    assert workflow.next_step() == (True, "")

    app.data_model._append_from_client(generated)

    assert step.inputs == {"image": image}
    assert app.selected_data == [image]


def test_input_selection_clears_a_role_whose_dataset_is_removed():
    app = controller()
    image = object()
    _, step = input_selection_workflow(app, InputSpec("image", "Image"))
    app.data_model._append_from_client(image)

    app.data_model.remove(image)

    assert step.inputs == {}
    assert step.can_proceed() == (False, "Please select Image")


def test_input_selection_reports_a_role_that_outlived_its_dataset():
    app = controller()
    image = object()
    step = InputSelectionStep(inputs=[InputSpec("image", "Image")], step_id="input")
    Workflow(app, [step])
    app.data_model.values.append(image)
    step.receive_data({"inputs": {"image": 0}})

    app.data_model.values.remove(image)

    assert step.can_proceed() == (False, "Selected Image is no longer available")


def test_parameter_change_invalidates_transitive_dependents():
    parameters = ParameterStep(
        parameters=[{"name": "value", "type": "float", "default": 10.0}],
        step_id="configure",
    )
    processing = ProcessingStep(
        callback=lambda: None,
        step_id="process",
        depends_on=["configure"],
    )
    validation = ValidationStep(step_id="review", depends_on=["process"])
    workflow = Workflow(controller(), [parameters, processing, validation])

    processing._completed = True
    validation._completed = True
    processing._dependencies_hash = processing._compute_dependencies_hash()
    validation._dependencies_hash = validation._compute_dependencies_hash()

    workflow.receive_step_data({"parameters": {"value": 50.0}})

    assert processing._completed is False
    assert validation._completed is False


def test_unrelated_step_is_not_invalidated():
    parameters = ParameterStep(
        parameters=[{"name": "value", "type": "float", "default": 10.0}],
        step_id="configure",
    )
    independent = ProcessingStep(callback=lambda: None, step_id="independent")
    workflow = Workflow(controller(), [parameters, independent])
    independent._completed = True

    workflow.receive_step_data({"parameters": {"value": 50.0}})

    assert independent._completed is True


def test_processing_step_uses_action_style_callback_contract():
    image = object()
    app = controller()
    app.data_model.values.append(image)
    observed = {}

    def process(value, *, amount, app):
        observed.update(value=value, amount=amount, app=app)
        return value

    parameters = ParameterStep(
        parameters=[{"name": "amount", "type": "float", "default": 2.0}],
        step_id="parameters",
    )
    processing = ProcessingStep(
        callback=process,
        parameters_from="parameters",
        step_id="processing",
    )
    Workflow(app, [parameters, processing])

    processing.on_enter()

    assert observed == {"value": image, "amount": 2.0, "app": app}
    assert processing.can_proceed() == (True, "")


def test_manual_processing_step_waits_for_explicit_run():
    observed = []
    app = controller()
    processing = ProcessingStep(
        callback=lambda: observed.append("ran"),
        auto_run=False,
        run_label="Run Segmentation",
        step_id="processing",
    )
    workflow = Workflow(app, [processing])

    workflow.start()

    assert observed == []
    assert processing.can_proceed() == (False, "Processing not complete")
    assert processing.get_ui_config()["run_label"] == "Run Segmentation"

    assert workflow.run_current_step() == (True, "")
    assert observed == ["ran"]
    assert processing.can_proceed() == (True, "")


def test_processing_step_does_not_reuse_its_published_output_as_input():
    source = object()
    observed = []
    generated = []
    app = controller()
    app.data_model.values.append(source)
    app.selected_data.append(source)

    def process(value):
        observed.append(value)
        output = object()
        generated.append(output)
        return output

    def publish(result, _title, _inputs, replace=None):
        previous = list(replace or [])
        if previous and previous[0] in app.data_model.values:
            index = app.data_model.values.index(previous[0])
            app.data_model.values[index] = result
        else:
            app.data_model.values.append(result)
        app.selected_data[:] = [source, result]
        return [result]

    app.publish_results = publish
    processing = ProcessingStep(callback=process, step_id="processing")
    Workflow(app, [processing])

    processing.on_enter()
    processing.reset_state()
    processing.on_enter()

    assert observed == [source, source]
    assert app.data_model.values == [source, generated[-1]]

    app.selected_data[:] = [generated[-1]]
    processing.reset_state()
    processing.on_enter()

    assert observed == [source, source, source]
    assert app.data_model.values == [source, generated[-1]]


def test_processing_failure_propagates_to_job_boundary():
    app = controller()
    processing = ProcessingStep(
        callback=lambda: (_ for _ in ()).throw(ValueError("broken")),
        step_id="processing",
    )
    Workflow(app, [processing])

    with pytest.raises(RuntimeError, match="Processing failed: broken"):
        processing.on_enter()

    assert processing.get_ui_config()["error"] == "broken"


def test_parameter_step_accepts_typed_parameter_classes():
    step = ParameterStep(
        parameters=[
            FloatParameter("threshold", default=100.0, minimum=0.0, maximum=200.0)
        ],
        step_id="configure",
    )

    assert step.values == {"threshold": 100.0}
    descriptor = step.get_ui_config()["parameters"][0]
    assert descriptor["name"] == "threshold"
    assert descriptor["type"] == "float"
    assert descriptor["min"] == 0.0
    assert descriptor["max"] == 200.0
    assert descriptor["value"] == 100.0


def test_parameter_step_validates_updates_from_the_browser():
    step = ParameterStep(
        parameters=[
            FloatParameter("threshold", default=100.0, minimum=0.0, maximum=200.0)
        ],
        step_id="configure",
    )

    step.receive_data({"parameters": {"threshold": 50.0}})
    assert step.values["threshold"] == 50.0

    with pytest.raises(ValueError, match="at most 200.0"):
        step.receive_data({"parameters": {"threshold": 500.0}})

    with pytest.raises(ValueError, match="Unknown action parameters"):
        step.receive_data({"parameters": {"unknown": 1.0}})


def test_parameter_step_still_accepts_dict_descriptors():
    step = ParameterStep(
        parameters=[{"name": "threshold", "type": "float", "default": 10.0}],
        step_id="configure",
    )

    assert step.values == {"threshold": 10.0}


def test_processing_step_unpacks_named_inputs_by_role():
    app = controller()
    fixed = object()
    moving = object()
    observed = {}

    def register(fixed, moving, app):
        observed.update(fixed=fixed, moving=moving, app=app)
        return moving

    processing = ProcessingStep(callback=register, step_id="processing")
    Workflow(app, [processing])
    processing._infer_processing_inputs = lambda: {"fixed": fixed, "moving": moving}

    processing.on_enter()

    assert observed == {"fixed": fixed, "moving": moving, "app": app}


def test_processing_step_keeps_passing_a_dict_to_a_catch_all_parameter():
    app = controller()
    fixed = object()
    moving = object()
    observed = {}

    def register(inputs, app):
        observed.update(inputs=inputs, app=app)
        return inputs["moving"]

    processing = ProcessingStep(callback=register, step_id="processing")
    Workflow(app, [processing])
    processing._infer_processing_inputs = lambda: {"fixed": fixed, "moving": moving}

    processing.on_enter()

    assert observed == {"inputs": {"fixed": fixed, "moving": moving}, "app": app}


def test_processing_auto_proceed_advances_workflow():
    app = controller()
    processing = ProcessingStep(callback=lambda: None, auto_proceed=True)
    done = MessageStep("Done", "Complete")
    workflow = Workflow(app, [processing, done])

    workflow.start()

    assert workflow.current_step is done


def test_brush_step_infers_image_from_processing_source():
    app = controller()
    image = object()
    label_map = object()
    app.data_model.values.extend([image, label_map])
    processing = ProcessingStep(step_id="segment")
    processing.result = label_map
    processing._published_outputs = [label_map]
    processing._last_source_inputs = [image]
    brush = BrushStep(
        label_map_from="segment",
        radius_mm=4.5,
        adaptiveness=0.75,
        step_id="correct",
    )
    Workflow(app, [processing, brush])

    brush.on_enter()

    config = brush.get_ui_config()
    assert config["type"] == "brush"
    assert config["image_index"] == 0
    assert config["label_map_index"] == 1
    assert config["radius_mm"] == 4.5
    assert config["adaptiveness"] == 0.75
    assert app.selected_data == [image, label_map]
    assert brush.can_proceed() == (True, "")

    brush.receive_data({"editing": True})

    assert brush.can_proceed() == (False, "Save the label map before continuing")


def test_brush_step_commits_new_label_map_and_can_proceed():
    app = controller()
    image = object()
    edited = object()
    app.data_model.values.append(image)
    inputs = InputSelectionStep(
        inputs=[InputSpec("image", "Image")],
        step_id="inputs",
    )
    inputs.assignments = {"image": image}
    brush = BrushStep(image_from="inputs", step_id="correct")
    Workflow(app, [inputs, brush])
    brush.on_enter()

    assert brush.can_proceed() == (False, "Save the label map before continuing")

    brush.commit_label_map(edited, None)

    assert app.data_model.values == [image, edited]
    assert brush.get_ui_config()["label_map_index"] == 1
    assert brush.can_proceed() == (True, "")

    brush.receive_data({"editing": True})

    assert brush.can_proceed() == (False, "Save the label map before continuing")

    brush.reset_state()

    assert app.data_model.values == [image]


def test_brush_step_replaces_existing_label_map_at_stable_index():
    app = controller()
    image = object()
    original = object()
    edited = object()
    app.data_model.values.extend([image, original])
    processing = ProcessingStep(step_id="segment")
    processing._published_outputs = [original]
    processing._last_source_inputs = [image]
    brush = BrushStep(label_map_from="segment", step_id="correct")
    Workflow(app, [processing, brush])
    brush.on_enter()

    brush.commit_label_map(edited, 1)

    assert app.data_model.values == [image, edited]
    assert brush.get_ui_config()["label_map_index"] == 1
    assert processing._published_outputs == [edited]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"radius_mm": 0}, "radius_mm"),
        ({"adaptiveness": 1.1}, "adaptiveness"),
        ({"labels": []}, "labels"),
        ({"labels": [0]}, "labels"),
        ({"labels": [1, 1]}, "labels"),
    ],
)
def test_brush_step_validates_configuration(kwargs, message):
    with pytest.raises(ValueError, match=message):
        BrushStep(**kwargs)


def test_brush_step_exposes_configured_labels_and_entry_token():
    app = controller()
    image = object()
    app.data_model.values.append(image)
    inputs = InputSelectionStep(
        inputs=[InputSpec("image", "Image")],
        step_id="inputs",
    )
    inputs.assignments = {"image": image}
    brush = BrushStep(image_from="inputs", labels=[2, 5], step_id="correct")
    Workflow(app, [inputs, brush])

    brush.on_enter()
    first_token = brush.get_ui_config()["entry_token"]

    assert brush.get_ui_config()["labels"] == [2, 5]
    assert first_token >= 1

    brush.reset_state()
    brush.on_enter()

    assert brush.get_ui_config()["entry_token"] > first_token


def test_brush_step_commit_invalidates_dependent_steps():
    app = controller()
    image = object()
    edited = object()
    app.data_model.values.append(image)
    inputs = InputSelectionStep(
        inputs=[InputSpec("image", "Image")],
        step_id="inputs",
    )
    inputs.assignments = {"image": image}
    brush = BrushStep(image_from="inputs", step_id="correct")
    validation = ValidationStep(step_id="review", depends_on=["correct"])
    Workflow(app, [inputs, brush, validation])
    brush.on_enter()

    brush.commit_label_map(edited, None)
    validation._completed = True
    validation._dependencies_hash = validation._compute_dependencies_hash()

    brush.receive_data({"editing": True})
    brush.commit_label_map(edited, brush.get_ui_config()["label_map_index"])

    assert validation._completed is False


def test_brush_step_label_map_role_selects_from_multi_input_step():
    app = controller()
    image = object()
    label_map = object()
    app.data_model.values.extend([image, label_map])
    inputs = InputSelectionStep(
        inputs=[
            InputSpec("image", "Image"),
            InputSpec("mask", "Mask"),
        ],
        step_id="inputs",
    )
    inputs.assignments = {"image": image, "mask": label_map}
    brush = BrushStep(
        image_from="inputs",
        image_role="image",
        label_map_from="inputs",
        label_map_role="mask",
        step_id="correct",
    )
    Workflow(app, [inputs, brush])

    brush.on_enter()

    config = brush.get_ui_config()
    assert config["image_index"] == 0
    assert config["label_map_index"] == 1
