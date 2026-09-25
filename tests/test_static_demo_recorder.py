"""Coverage for exploring an application into a recorded transition graph."""

import imfusion
import numpy as np
import pytest

from imfusion_webappkit import (
    FloatParameter,
    ImFusionWebApp,
    BrushStep,
    MessageStep,
    ParameterStep,
    ProcessingStep,
    ValidationStep,
)
from imfusion_webappkit.static_demo import (
    ActionScenario,
    DemoLimits,
    StaticDemoSpec,
    WorkflowScenario,
)
from imfusion_webappkit.static_demo.canonical import edge_key
from imfusion_webappkit.static_demo.recorder import (
    DemoLimitExceeded,
    UnsupportedDemoInteraction,
    inspect_app,
    record,
)


def _image():
    values = np.arange(64, dtype=np.float32).reshape(1, 8, 8, 1)
    return imfusion.SharedImageSet(values)


def _threshold(imageset, *, threshold: float):
    mask = imageset.clone()
    values = np.array(mask[0])
    mask[0].assign_array((values >= threshold).astype(values.dtype))
    mask.modality = imfusion.Data.Modality.LABEL
    return mask


def _action_app() -> ImFusionWebApp:
    webapp = ImFusionWebApp(title="Recorder Test", show_load_button=False)
    webapp.register(
        "Threshold",
        _threshold,
        parameters=[FloatParameter("threshold", default=10.0, minimum=0.0)],
    )
    webapp.initial_data.add(_image(), "Sample")
    return webapp


def _record(spec: StaticDemoSpec):
    return record(spec, inspect_app(spec), progress=lambda _message: None)


def test_records_one_edge_per_recorded_parameter_value():
    spec = StaticDemoSpec(app=_action_app, parameters={"threshold": [10.0, 40.0]})
    graph = _record(spec)

    initial = graph.nodes[graph.initial_node]
    assert len(initial.edges) == 2
    assert [frame.type for frame in graph.connect_frames] == [
        "actions",
        "data_add",
        "initial_sync_complete",
    ]
    for edge in initial.edges.values():
        assert [frame.type for frame in edge.frames] == [
            "job_started",
            "data_add",
            "job_result",
        ]


def test_edge_keys_match_the_message_the_browser_sends():
    """The browser computes these keys itself, so they have to agree exactly."""
    spec = StaticDemoSpec(app=_action_app, parameters={"threshold": [10.0]})
    graph = _record(spec)

    expected = edge_key(
        "execute_action",
        {
            "action": "Threshold",
            "inputs": [{"role": "image", "index": 0}],
            "parameters": {"threshold": 10.0},
        },
    )
    assert expected in graph.nodes[graph.initial_node].edges


def test_allowed_values_are_published_for_snapping():
    spec = StaticDemoSpec(app=_action_app, parameters={"threshold": [10.0, 40.0]})
    graph = _record(spec)

    parameters = graph.actions[0]["parameters"]
    assert parameters["threshold"]["allowed_values"] == [10.0, 40.0]


def test_a_control_opens_on_a_value_that_was_recorded():
    """The application's default is 10.0, and neither recorded value is it."""
    spec = StaticDemoSpec(app=_action_app, parameters={"threshold": [25.0, 40.0]})
    graph = _record(spec)

    threshold = graph.actions[0]["parameters"]["threshold"]
    assert threshold["value"] == 25.0
    assert threshold["default"] == 25.0
    assert (
        edge_key(
            "execute_action",
            {
                "action": "Threshold",
                "inputs": [{"role": "image", "index": 0}],
                "parameters": {"threshold": 25.0},
            },
        )
        in graph.nodes[graph.initial_node].edges
    )


def test_handler_backed_actions_are_not_recorded():
    spec = StaticDemoSpec(
        app=_action_app,
        actions={"Threshold": ActionScenario(handler="threshold")},
    )
    graph = _record(spec)

    assert graph.handlers == {"Threshold": "threshold"}
    assert graph.nodes[graph.initial_node].edges == {}
    assert graph.actions[0]["handler"] == "threshold"
    assert "allowed_values" not in graph.actions[0]["parameters"]["threshold"]


def test_repeated_application_records_results_of_results():
    spec = StaticDemoSpec(
        app=_action_app,
        parameters={"threshold": [10.0]},
        actions={"Threshold": ActionScenario(repeat=2)},
    )
    graph = _record(spec)

    # One dataset to begin with, so the first run has a single input. The second
    # run can target either the source or the new label map.
    assert len(graph.nodes) == 4
    assert sum(len(node.edges) for node in graph.nodes.values()) == 3


def test_identical_payloads_are_stored_once():
    spec = StaticDemoSpec(
        app=_action_app,
        parameters={"threshold": [10.0]},
        actions={"Threshold": ActionScenario(repeat=2)},
    )
    graph = _record(spec)

    references = [
        frame.payload
        for node in graph.nodes.values()
        for edge in node.edges.values()
        for frame in edge.frames
        if frame.payload
    ]
    assert len(references) > len(set(references)), "expected a reused payload"
    assert set(references) <= set(graph.payloads)


def test_node_limit_is_enforced():
    spec = StaticDemoSpec(
        app=_action_app,
        parameters={"threshold": [1.0, 2.0, 3.0, 4.0]},
        limits=DemoLimits(max_nodes=2),
    )
    with pytest.raises(DemoLimitExceeded, match="reached 2 states"):
        _record(spec)


def test_payload_limit_is_enforced():
    spec = StaticDemoSpec(
        app=_action_app,
        parameters={"threshold": [1.0, 2.0]},
        limits=DemoLimits(max_bytes=1024),
    )
    with pytest.raises(DemoLimitExceeded, match="over the"):
        _record(spec)


def _workflow_app() -> ImFusionWebApp:
    webapp = ImFusionWebApp(title="Workflow Recorder Test", show_load_button=False)
    webapp.set_workflow(
        [
            MessageStep("Welcome", "Start here"),
            ParameterStep(
                "Configure",
                parameters=[FloatParameter("threshold", default=10.0, minimum=0.0)],
                step_id="configure",
            ),
            ProcessingStep("Segment", _threshold, parameters_from="configure"),
        ]
    )
    webapp.initial_data.add(_image(), "Sample")
    return webapp


def _last_workflow_state(edge):
    return next(
        frame.data for frame in reversed(edge.frames) if frame.type == "workflow_state"
    )


def test_workflow_navigation_is_recorded_in_both_directions():
    spec = StaticDemoSpec(app=_workflow_app, parameters={"threshold": [10.0]})
    graph = _record(spec)

    initial = graph.nodes[graph.initial_node]
    assert edge_key("workflow_next") in initial.edges
    assert edge_key("workflow_back") not in initial.edges

    second = graph.nodes[initial.edges[edge_key("workflow_next")].target]
    assert edge_key("workflow_back") in second.edges


def test_revisiting_a_state_reuses_its_node():
    """Equivalent states must share a node, or exploring a loop never ends."""
    spec = StaticDemoSpec(app=_workflow_app, parameters={"threshold": [10.0]})
    graph = _record(spec)

    second = graph.nodes[graph.initial_node].edges[edge_key("workflow_next")].target
    # Stepping back and forward again returns to the same state. It is not the
    # initial one, because the workflow now remembers the step was visited.
    back = graph.nodes[second].edges[edge_key("workflow_back")].target
    assert back != graph.initial_node
    assert graph.nodes[back].edges[edge_key("workflow_next")].target == second


def test_finishing_a_workflow_restarts_the_demo():
    """Finish clears the session; a recording cannot load data, so it starts over.

    Publishing the empty Welcome screen greys out both buttons. Replaying the
    connect sequence onto the initial node is the demo equivalent of a reload.
    """
    spec = StaticDemoSpec(app=_workflow_app, parameters={"threshold": [10.0]})
    graph = _record(spec)

    assert not [node for node in graph.nodes.values() if node.selection == []]
    finish = [
        edge
        for node in graph.nodes.values()
        for edge in node.edges.values()
        if edge.message["type"] == "workflow_next"
        and edge.target == graph.initial_node
        and node.id != graph.initial_node
    ]
    assert finish, "expected Finish to return to the initial state"
    assert all(
        any(frame.type == "data_add" for frame in edge.frames) for edge in finish
    )
    assert all(_last_workflow_state(edge)["can_proceed"] for edge in finish)
    assert not any(
        frame.type == "job_failed"
        for node in graph.nodes.values()
        for edge in node.edges.values()
        for frame in edge.frames
    )


def test_back_navigation_can_be_excluded():
    spec = StaticDemoSpec(
        app=_workflow_app,
        parameters={"threshold": [10.0]},
        workflow=WorkflowScenario(include_back=False),
    )
    graph = _record(spec)

    assert not any(
        edge_key("workflow_back") in node.edges for node in graph.nodes.values()
    )
    # A button the panel still offers is a button that leads to the notice, so
    # the recorded states have to stop claiming the workflow can go back.
    assert not any(
        frame.data.get("can_go_back")
        for node in graph.nodes.values()
        for edge in node.edges.values()
        for frame in edge.frames
        if frame.type == "workflow_state"
    )


def test_back_navigation_stays_offered_when_it_is_recorded():
    spec = StaticDemoSpec(app=_workflow_app, parameters={"threshold": [10.0]})
    graph = _record(spec)

    assert any(
        frame.data.get("can_go_back")
        for node in graph.nodes.values()
        for edge in node.edges.values()
        for frame in edge.frames
        if frame.type == "workflow_state"
    )


def _validation_app() -> ImFusionWebApp:
    webapp = ImFusionWebApp(show_load_button=False)
    webapp.set_workflow([MessageStep("Welcome", "Hello"), ValidationStep("Review")])
    webapp.initial_data.add(_image(), "Sample")
    return webapp


def test_validation_step_records_both_decisions():
    graph = _record(StaticDemoSpec(app=_validation_app))

    review = graph.nodes[
        graph.nodes[graph.initial_node].edges[edge_key("workflow_next")].target
    ]
    assert edge_key("workflow_step_data", {"data": {"accepted": True}}) in review.edges
    assert edge_key("workflow_step_data", {"data": {"accepted": False}}) in review.edges


def test_accepted_validation_can_finish_and_rejected_validation_can_go_back():
    """Rejecting disables Finish on purpose; Back has to stay as the way out.

    `include_back=False` is an optimisation, not a licence to trap the visitor
    on a ValidationStep after they pick an answer.
    """
    graph = _record(
        StaticDemoSpec(
            app=_validation_app,
            workflow=WorkflowScenario(include_back=False),
        )
    )
    review = graph.nodes[
        graph.nodes[graph.initial_node].edges[edge_key("workflow_next")].target
    ]
    accept = edge_key("workflow_step_data", {"data": {"accepted": True}})
    reject = edge_key("workflow_step_data", {"data": {"accepted": False}})
    accepted = graph.nodes[review.edges[accept].target]
    rejected = graph.nodes[review.edges[reject].target]

    assert edge_key("workflow_next") in accepted.edges
    assert accepted.edges[edge_key("workflow_next")].target == graph.initial_node
    assert edge_key("workflow_back") not in accepted.edges
    assert edge_key("workflow_back") in rejected.edges
    assert edge_key("workflow_next") not in rejected.edges

    arrived_accepted = _last_workflow_state(review.edges[accept])
    arrived_rejected = _last_workflow_state(review.edges[reject])
    assert arrived_accepted["can_proceed"] is True
    assert arrived_accepted["can_go_back"] is False
    assert arrived_rejected["can_proceed"] is False
    assert arrived_rejected["can_go_back"] is True


def test_brush_steps_are_refused_with_an_explanation():
    def app() -> ImFusionWebApp:
        webapp = ImFusionWebApp(show_load_button=False)
        # The brush resolves its image from the selection, which the browser only
        # reports once it has loaded the seed data, so it cannot be step one.
        webapp.set_workflow([MessageStep("Welcome", "Hello"), BrushStep("Paint")])
        webapp.initial_data.add(_image(), "Sample")
        return webapp

    with pytest.raises(UnsupportedDemoInteraction, match="brush step"):
        _record(StaticDemoSpec(app=app))


def test_review_warns_about_interactions_that_cannot_work():
    def app() -> ImFusionWebApp:
        webapp = ImFusionWebApp(show_load_button=True, show_export_button=True)
        webapp.initial_data.add(_image(), "Sample")
        return webapp

    graph = _record(StaticDemoSpec(app=app))

    joined = " ".join(graph.warnings)
    assert "load button" in joined
    assert "Export" in joined
