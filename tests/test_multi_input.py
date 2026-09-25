"""Tests for named, ordered operation inputs."""

# pylint: disable=protected-access

from types import SimpleNamespace

import imfusion
import pytest

from imfusion_webappkit import InputSelectionStep, InputSpec, Workflow
from imfusion_webappkit.action_registry import ActionRegistry
from imfusion_webappkit.algorithm_registry import AlgorithmRegistry
from imfusion_webappkit.websocket_handler import WebSocketHandler


def test_multi_input_action_receives_role_mapping():
    registry = ActionRegistry()
    fixed = object()
    moving = object()

    def register(inputs):
        assert inputs == {"fixed": fixed, "moving": moving}
        return inputs["moving"]

    registry.register(
        "Register",
        register,
        inputs=[
            InputSpec("fixed", "Fixed image"),
            InputSpec("moving", "Moving image"),
        ],
        result_input="moving",
    )

    assert (
        registry.execute_action("Register", {"fixed": fixed, "moving": moving})
        is moving
    )
    descriptor = registry.list_action_descriptors()[0]
    assert [item["key"] for item in descriptor["inputs"]] == ["fixed", "moving"]


def test_single_input_action_remains_backward_compatible():
    registry = ActionRegistry()
    image = object()
    registry.register("Identity", lambda image: image)
    assert registry.execute_action("Identity", image) is image


def test_action_rejects_schema_with_only_optional_inputs():
    registry = ActionRegistry()

    with pytest.raises(ValueError, match="at least one required input"):
        registry.register(
            "Optional only",
            lambda inputs: inputs,
            inputs=[InputSpec("optional", "Optional", required=False)],
        )


def test_algorithm_registry_preserves_input_and_output_order(monkeypatch):
    registry = AlgorithmRegistry()
    registry.enable()
    fixed = object()
    moving = object()
    outputs = [object(), object()]
    observed = {}

    def execute(algo_id, inputs, _properties):
        observed["id"] = algo_id
        observed["inputs"] = inputs
        return outputs

    monkeypatch.setattr(
        "imfusion_webappkit.algorithm_registry.imfusion.algorithm.execute", execute
    )

    assert registry.execute_algorithm("Registration", [fixed, moving]) == outputs
    assert observed == {
        "id": "Registration",
        "inputs": [fixed, moving],
    }


def test_algorithm_registry_uses_configured_in_place_result(monkeypatch):
    registry = AlgorithmRegistry()
    registry.enable()
    fixed = object()
    moving = object()
    monkeypatch.setattr(
        "imfusion_webappkit.algorithm_registry.imfusion.algorithm.execute",
        lambda *_args: [],
    )

    assert registry.execute_algorithm(
        "Registration", [fixed, moving], result_input_index=1
    ) == [moving]


class FakeProperties:
    """Minimal stand-in for `imfusion.Properties` used by discovery tests."""

    def __init__(self, values):
        self._values = values

    def params(self):
        return list(self._values)

    def __getitem__(self, name):
        return self._values[name]

    def param_attributes(self, name):
        if name == "Threshold":
            return [("min", "0"), ("max", "1"), ("step", "0.1")]
        return []


def test_discovery_and_controller_check_describe_parameters_identically(monkeypatch):
    registry = AlgorithmRegistry()
    registry.enable()
    props = FakeProperties({"Threshold": 0.5, "Iterations": 3})
    monkeypatch.setattr(
        "imfusion_webappkit.algorithm_registry.imfusion.algorithm.list_available",
        lambda: ["Base.Threshold"],
    )
    monkeypatch.setattr(
        "imfusion_webappkit.algorithm_registry.imfusion.algorithm.get_properties",
        lambda algo_id, inputs: props,
    )
    registry.register_controller("Threshold", inputs=[InputSpec("image", "Image")])

    [discovered] = registry.discover_compatible_algorithms([object()])
    controller_info = registry.get_controller_with_compatibility(
        "Threshold", [object()]
    )

    expected_parameters = {
        "Threshold": {
            "name": "Threshold",
            "label": "Threshold",
            "value": 0.5,
            "default": 0.5,
            "type": "float",
            "min": 0.0,
            "max": 1.0,
            "step": 0.1,
        },
        "Iterations": {
            "name": "Iterations",
            "label": "Iterations",
            "value": 3,
            "default": 3,
            "type": "int",
        },
    }
    assert discovered["parameters"] == expected_parameters
    assert controller_info["parameters"] == expected_parameters


def test_algorithm_enum_parameters_are_exposed_as_choices():
    registry = AlgorithmRegistry()
    choice = imfusion.Properties.EnumStringParam(
        value="accurate", admitted_values={"fast", "accurate"}
    )

    parameters = registry._describe_parameters(FakeProperties({"Mode": choice}))

    assert parameters["Mode"] == {
        "name": "Mode",
        "label": "Mode",
        "value": "accurate",
        "default": "accurate",
        "type": "choice",
        "options": ["accurate", "fast"],
    }


class FakeDataModel:
    def __init__(self, values):
        self.values = values

    def __len__(self):
        return len(self.values)

    def __getitem__(self, index):
        return self.values[index]

    def get_name(self, index):
        return f"Data {index + 1}"

    def contains(self, value):
        return value in self.values

    def index(self, value):
        return self.values.index(value)


def test_websocket_input_resolution_uses_declared_roles():
    fixed = object()
    moving = object()
    session = SimpleNamespace(data_model=FakeDataModel([moving, fixed]))
    specs = [
        InputSpec("fixed", "Fixed image"),
        InputSpec("moving", "Moving image"),
    ]

    ordered, roles, indices = WebSocketHandler._resolve_role_inputs(
        {
            "inputs": [
                {"role": "moving", "index": 0},
                {"role": "fixed", "index": 1},
            ]
        },
        session,
        specs,
    )

    assert ordered == [fixed, moving]
    assert roles == {"fixed": fixed, "moving": moving}
    assert indices == [1, 0]


def test_workflow_input_selection_resolves_data_and_rejects_duplicates():
    fixed = object()
    moving = object()
    controller = SimpleNamespace(
        data_model=FakeDataModel([fixed, moving]),
        selected_data=[],
    )
    controller.select_data = lambda values: controller.selected_data.__setitem__(
        slice(None), values
    )
    step = InputSelectionStep(
        inputs=[
            InputSpec("fixed", "Fixed image"),
            InputSpec("moving", "Moving image"),
        ],
    )
    Workflow(controller, steps=[step])

    step.receive_data({"inputs": {"fixed": 0, "moving": 1}})
    assert step.inputs == {"fixed": fixed, "moving": moving}
    assert step.can_proceed() == (True, "")
    assert step.get_ui_config()["allow_upload"] is True
    assert step.get_ui_config()["allow_sample_datasets"] is True

    step.receive_data({"inputs": {"fixed": 0, "moving": 0}})
    assert step.can_proceed() == (
        False,
        "Each input must use a different dataset",
    )


@pytest.mark.parametrize(
    ("allow_upload", "allow_sample_datasets", "expected"),
    [(False, None, False), (False, True, True), (True, False, False)],
)
def test_workflow_input_selection_sample_datasets_follow_upload(
    allow_upload, allow_sample_datasets, expected
):
    controller = SimpleNamespace(
        data_model=FakeDataModel([]),
        select_data=lambda values: None,
    )
    step = InputSelectionStep(
        inputs=[InputSpec("image", "Image")],
        allow_upload=allow_upload,
        allow_sample_datasets=allow_sample_datasets,
    )
    Workflow(controller, steps=[step])

    assert step.get_ui_config()["allow_sample_datasets"] is expected
