"""Coverage for replaying client messages against a real application.

These tests drive the production WebSocket handler through the recording
stand-in, so a change to the connect sequence or the job lifecycle shows up here
rather than in a published demo.
"""

import imfusion
import numpy as np
import pytest

from imfusion_webappkit import (
    FloatParameter,
    ImFusionWebApp,
    MessageStep,
    ParameterStep,
    ProcessingStep,
)
from imfusion_webappkit.examples._assets import SAMPLE_IMAGE
from imfusion_webappkit.static_demo.recording import data_content_hash, run_path


def _threshold(imageset, *, threshold: float):
    mask = imageset.clone()
    values = np.array(mask[0])
    mask[0].assign_array((values >= threshold).astype(values.dtype))
    mask.modality = imfusion.Data.Modality.LABEL
    return mask


def _build_action_app() -> ImFusionWebApp:
    webapp = ImFusionWebApp(title="Recording Test")
    webapp.register(
        "Threshold",
        _threshold,
        parameters=[FloatParameter("threshold", default=100.0, minimum=0.0)],
    )
    webapp.initial_data.add(imfusion.io.load(str(SAMPLE_IMAGE))[0], "Sample Image")
    return webapp


def _types(frames):
    return [frame.type for frame in frames]


def test_connect_sequence_is_recorded():
    outcome = run_path(_build_action_app, [])

    assert _types(outcome.steps[0]) == [
        "actions",
        "data_add",
        "initial_sync_complete",
    ]
    assert outcome.steps[0][1].payload, "data_add must carry its IMF payload"
    assert outcome.state.names == ["Sample Image"]
    assert outcome.state.workflow is None


def test_action_frames_are_grouped_per_message():
    message = {
        "type": "execute_action",
        "data": {
            "action": "Threshold",
            "inputs": [{"role": "image", "index": 0}],
            "parameters": {"threshold": 100.0},
        },
    }
    outcome = run_path(_build_action_app, [message])

    assert len(outcome.steps) == 2
    assert _types(outcome.steps[1]) == ["job_started", "data_add", "job_result"]
    assert outcome.state.names == ["Sample Image", "Sample Image — Threshold"]


def test_equivalent_paths_share_a_fingerprint():
    """The fingerprint has to ignore how a state was reached."""
    message = {
        "type": "execute_action",
        "data": {
            "action": "Threshold",
            "inputs": [{"role": "image", "index": 0}],
            "parameters": {"threshold": 100.0},
        },
    }
    first = run_path(_build_action_app, [message])
    second = run_path(_build_action_app, [message])

    assert first.state.fingerprint == second.state.fingerprint


def test_different_parameters_produce_different_fingerprints():
    def message(threshold):
        return {
            "type": "execute_action",
            "data": {
                "action": "Threshold",
                "inputs": [{"role": "image", "index": 0}],
                "parameters": {"threshold": threshold},
            },
        }

    low = run_path(_build_action_app, [message(50.0)])
    high = run_path(_build_action_app, [message(400.0)])

    assert low.state.fingerprint != high.state.fingerprint


def _build_workflow_app() -> ImFusionWebApp:
    webapp = ImFusionWebApp(title="Workflow Recording Test")
    webapp.set_workflow(
        [
            MessageStep("Welcome", "Start here"),
            ParameterStep(
                "Configure",
                parameters=[FloatParameter("threshold", default=100.0, minimum=0.0)],
                step_id="configure",
            ),
            ProcessingStep("Segment", _threshold, parameters_from="configure"),
        ]
    )
    webapp.initial_data.add(imfusion.io.load(str(SAMPLE_IMAGE))[0], "Sample Image")
    return webapp


def test_workflow_state_is_recorded_on_connect():
    outcome = run_path(_build_workflow_app, [])

    assert "workflow_state" in _types(outcome.steps[0])
    assert outcome.state.workflow["current_index"] == 0
    assert outcome.state.workflow["total_steps"] == 3


def test_workflow_navigation_advances_the_recorded_state():
    outcome = run_path(_build_workflow_app, [{"type": "workflow_next", "data": {}}])

    assert outcome.state.workflow["current_index"] == 1
    assert "job_started" in _types(outcome.steps[1])
    assert "workflow_state" in _types(outcome.steps[1])


def test_content_hash_survives_a_serialization_round_trip():
    """Node collapsing and payload reuse both depend on this."""
    from imfusion_webappkit.image_protocol import ImageProtocol

    original = imfusion.io.load(str(SAMPLE_IMAGE))[0]
    restored = ImageProtocol.deserialize_data_list_bytes(
        ImageProtocol.serialize_data_list_bytes([original])
    )[0]

    assert data_content_hash(original) == data_content_hash(restored)
