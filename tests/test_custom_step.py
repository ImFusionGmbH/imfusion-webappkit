"""Custom workflow step and declarative UI element tests."""

import base64
from types import SimpleNamespace

import pytest

from imfusion_webappkit import (
    Alert,
    Button,
    Chart,
    CustomStep,
    Fields,
    FloatParameter,
    Image,
    Metric,
    Metrics,
    Series,
    Table,
    Text,
    ValidationStep,
    Workflow,
)


def controller():
    session = SimpleNamespace(send_message=lambda *_args: None)
    return SimpleNamespace(data_model=[], selected_data=[], _session=session)


class QualityCheckStep(CustomStep):
    """Custom step that records the actions it received."""

    def __init__(self, step_id="check"):
        super().__init__(
            "Quality check",
            body=[Button("approve", style="primary"), Button("reject", style="danger")],
            step_id=step_id,
            require_completion=True,
            completion_message="Approve the result first",
        )
        self.actions = []

    def on_action(self, action):
        self.actions.append(action)
        self.completed = action == "approve"


class CountingStep(CustomStep):
    """Custom step with a dynamic body that records how often it is built."""

    def __init__(self, step_id="counting"):
        super().__init__("Counting", step_id=step_id)
        self.calls = 0
        self.actions = []
        self.show_button = True

    def body(self):
        self.calls += 1
        elements = [Fields([FloatParameter("threshold", default=1.0)])]
        if self.show_button:
            elements.append(Button("confirm"))
        return elements

    def on_action(self, action):
        self.actions.append(action)


def test_static_body_is_serialized_for_the_browser():
    step = CustomStep(
        "Summary",
        body=[
            Text("**Segmentation complete**"),
            Metrics({"Dice": 0.91}),
            Alert("Review the apex slices", "warning"),
        ],
    )

    config = step.get_ui_config()

    assert config["type"] == "custom"
    assert config["body"] == [
        {"kind": "text", "content": "**Segmentation complete**"},
        {"kind": "metrics", "items": [{"label": "Dice", "value": 0.91}]},
        {"kind": "alert", "content": "Review the apex slices", "level": "warning"},
    ]
    assert step.can_proceed() == (True, "")


def test_metrics_and_tables_describe_units_and_columns():
    metrics = Metrics([Metric("Volume", 12.5, unit="mL")])
    table = Table(
        [{"Label": "Liver", "Volume": 1502.0}, {"Label": "Spleen", "Volume": 210.5}],
        caption="Volumes in mm³",
    )

    assert metrics.to_dict()["items"] == [
        {"label": "Volume", "value": 12.5, "unit": "mL"}
    ]
    assert table.to_dict() == {
        "kind": "table",
        "columns": ["Label", "Volume"],
        "rows": [["Liver", 1502.0], ["Spleen", 210.5]],
        "caption": "Volumes in mm³",
    }


def test_table_accepts_sequence_rows_with_declared_columns():
    table = Table([["Liver", 1502.0], ["Spleen", None]], columns=["Label", "Volume"])

    assert table.to_dict()["rows"] == [["Liver", 1502.0], ["Spleen", None]]


def test_chart_describes_series_positions_and_axes():
    chart = Chart(
        "bar",
        Series("Volume", [1502.0, 210.5], x=["Liver", "Spleen"]),
        x_label="Structure",
        y_label="mm³",
        caption="Segmented volumes",
    )

    assert chart.to_dict() == {
        "kind": "chart",
        "variant": "bar",
        "series": [
            {
                "label": "Volume",
                "values": [1502.0, 210.5],
                "x": ["Liver", "Spleen"],
            }
        ],
        "x_label": "Structure",
        "y_label": "mm³",
        "caption": "Segmented volumes",
    }


def test_chart_accepts_a_mapping_of_series():
    chart = Chart("line", {"Fixed": [1, 2, 3], "Moving": [3, 2, 1]})

    assert [series["label"] for series in chart.to_dict()["series"]] == [
        "Fixed",
        "Moving",
    ]
    assert chart.to_dict()["series"][0]["values"] == [1.0, 2.0, 3.0]
    assert "x" not in chart.to_dict()["series"][0]


def test_image_detects_its_media_type_and_encodes_once():
    png = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    )
    descriptor = Image(png, caption="Overlay preview").to_dict()

    assert descriptor["kind"] == "image"
    assert descriptor["media_type"] == "image/png"
    assert base64.b64decode(descriptor["data"]) == png
    assert descriptor["caption"] == "Overlay preview"
    assert "alt" not in descriptor


def test_image_reads_a_file_path(tmp_path):
    path = tmp_path / "plot.jpg"
    path.write_bytes(b"\xff\xd8\xff\xe0 body")

    assert Image(path).to_dict()["media_type"] == "image/jpeg"


def test_fields_provide_defaults_and_validate_browser_updates():
    step = CustomStep(
        body=[Fields([FloatParameter("threshold", default=1.0, maximum=10.0)])]
    )

    assert step.values == {"threshold": 1.0}

    step.receive_data({"values": {"threshold": 4.0}})

    assert step.values == {"threshold": 4.0}
    assert step.get_ui_config()["body"][0]["parameters"][0]["value"] == 4.0

    with pytest.raises(ValueError, match="at most 10.0"):
        step.receive_data({"values": {"threshold": 99.0}})

    with pytest.raises(ValueError, match="Unknown action parameters"):
        step.receive_data({"values": {"unknown": 1.0}})


def test_duplicate_parameter_names_across_fields_are_rejected():
    step = CustomStep(
        body=[
            Fields([FloatParameter("threshold", default=1.0)]),
            Fields([FloatParameter("threshold", default=2.0)]),
        ]
    )

    with pytest.raises(ValueError, match="Duplicate custom step parameter"):
        step.get_ui_config()


def test_button_press_dispatches_to_on_action():
    step = QualityCheckStep()

    assert step.can_proceed() == (False, "Approve the result first")

    step.receive_data({"action": "approve"})

    assert step.actions == ["approve"]
    assert step.can_proceed() == (True, "")

    with pytest.raises(ValueError, match="Unknown custom step action: 'delete'"):
        step.receive_data({"action": "delete"})


def test_disabled_button_presses_are_rejected():
    step = QualityCheckStep()
    step._static_body = [Button("approve", disabled=True)]

    with pytest.raises(ValueError, match="Disabled custom step action: 'approve'"):
        step.receive_data({"action": "approve"})

    assert step.actions == []


def test_dynamic_body_reflects_current_session_state():
    class SummaryStep(CustomStep):
        def __init__(self):
            super().__init__("Summary")
            self.dataset_count = 0

        def body(self):
            return [Metrics({"Datasets": self.dataset_count})]

    step = SummaryStep()
    step.dataset_count = 3

    assert step.get_ui_config()["body"][0]["items"][0]["value"] == 3


def test_dynamic_body_is_built_once_per_browser_update():
    step = CountingStep()

    step.get_ui_config()

    assert step.calls == 1


def test_actions_are_validated_against_the_rendered_body():
    step = CountingStep()
    step.get_ui_config()
    step.show_button = False

    step.receive_data({"action": "confirm"})

    assert step.actions == ["confirm"]
    assert "button" not in [element["kind"] for element in step.get_ui_config()["body"]]
    with pytest.raises(ValueError, match="Unknown custom step action"):
        step.receive_data({"action": "confirm"})


def test_value_change_invalidates_dependent_steps():
    custom = CustomStep(
        body=[Fields([FloatParameter("threshold", default=1.0)])],
        step_id="configure",
    )
    validation = ValidationStep(step_id="review", depends_on=["configure"])
    workflow = Workflow(controller(), [custom, validation])
    validation._completed = True
    validation._dependencies_hash = validation._compute_dependencies_hash()

    workflow.receive_step_data({"values": {"threshold": 2.0}})

    assert validation._completed is False


def test_job_backed_action_runs_and_invalidates_dependents():
    check = QualityCheckStep()
    validation = ValidationStep(step_id="review", depends_on=["check"])
    workflow = Workflow(controller(), [check, validation])
    workflow.start()
    validation._completed = True
    validation._dependencies_hash = validation._compute_dependencies_hash()

    assert workflow.run_current_step("approve") == (True, "")
    assert check.actions == ["approve"]
    assert validation._completed is False


def test_custom_step_without_action_reports_no_automatic_run():
    workflow = Workflow(controller(), [QualityCheckStep()])
    workflow.start()

    assert workflow.run_current_step() == (
        False,
        "Current workflow step has no automatic action",
    )


def test_reset_restores_defaults_and_completion():
    step = CustomStep(
        body=[
            Fields([FloatParameter("threshold", default=1.0)]),
            Button("confirm"),
        ]
    )
    step.receive_data({"values": {"threshold": 5.0}})
    step.completed = True

    step.reset_state()

    assert step.values == {"threshold": 1.0}
    assert step.completed is False


@pytest.mark.parametrize(
    ("factory", "error", "message"),
    [
        (lambda: Text("  "), ValueError, "non-empty"),
        (lambda: Alert("Careful", "loud"), ValueError, "level"),
        (lambda: Metrics({}), ValueError, "at least one item"),
        (lambda: Metrics([Metric("Count", None)]), ValueError, "string or a number"),
        (lambda: Table([]), ValueError, "at least one row"),
        (lambda: Table([["a"]]), ValueError, "columns are required"),
        (lambda: Table([["a"]], columns=["x", "y"]), ValueError, "cells"),
        (lambda: Table([{"x": object()}]), ValueError, "scalars"),
        (lambda: Series("", [1.0]), ValueError, "label must not be empty"),
        (lambda: Series("Dice", []), ValueError, "at least one value"),
        (lambda: Series("Dice", [float("nan")]), ValueError, "must be finite"),
        (lambda: Series("Dice", [None]), ValueError, "must be a number"),
        (lambda: Series("Dice", [1.0], x=[1.0, 2.0]), ValueError, "positions for"),
        (
            lambda: Series("Dice", [1.0, 2.0], x=["a", 2.0]),
            ValueError,
            "all numbers or all strings",
        ),
        (lambda: Series("Dice", range(1025)), ValueError, "at most 1024 values"),
        (lambda: Chart("pie", {"Dice": [1.0]}), ValueError, "variant"),
        (lambda: Chart("line", []), ValueError, "at least one series"),
        (lambda: Chart("line", ["not a series"]), TypeError, "Series instances"),
        (
            lambda: Chart("line", [Series("Dice", [1.0]), Series("Dice", [2.0])]),
            ValueError,
            "labels must be unique",
        ),
        (lambda: Image(b"not an image"), ValueError, "PNG, JPEG, or WebP"),
        (lambda: Image(b"\x89PNG\r\n\x1a\n" * 600000), ValueError, "at most 4096 KiB"),
        (lambda: Fields([]), ValueError, "at least one parameter"),
        (lambda: Button("run twice"), ValueError, "Invalid button action"),
        (lambda: Button("run", style="huge"), ValueError, "style"),
        (lambda: CustomStep(body=["not an element"]), TypeError, "UIElement"),
    ],
)
def test_invalid_elements_are_rejected(factory, error, message):
    with pytest.raises(error, match=message):
        factory()
