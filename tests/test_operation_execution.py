"""Coverage for the SDK-thread job runner and its WebSocket entry points.

These tests drive `OperationRunner.run_job` the same way the production
server does: the job runs on a background thread via `asyncio.run`, while the
main (owner) thread services the SDK work queue with `run_once`, mirroring
`ImFusionWebApp.run`.
"""

import asyncio
import threading
import time

import imfusion
import numpy as np
import pytest

from imfusion_webappkit import ImFusionWebApp, InputSpec
from imfusion_webappkit.jobs import JobStatus
from imfusion_webappkit.operation_runner import PreparedOperation
from imfusion_webappkit.workflow_handler import WorkflowMessageHandler

# Ensure the example algorithm is registered with the ImFusion SDK.
import imfusion_webappkit.examples.add_noise_algorithm  # noqa: F401


def _run_sync(webapp: ImFusionWebApp, coroutine, timeout: float = 5.0):
    """Run `coroutine` to completion while pumping the SDK owner thread."""
    result_box: dict = {}

    def runner():
        try:
            result_box["value"] = asyncio.run(coroutine)
        except BaseException as exc:  # noqa: BLE001 - surfaced to the caller
            result_box["error"] = exc

    thread = threading.Thread(target=runner)
    thread.start()
    deadline = time.monotonic() + timeout
    while thread.is_alive():
        if time.monotonic() > deadline:
            raise TimeoutError("Coroutine did not complete within the timeout")
        webapp.sdk_runtime.run_once(timeout=0.05)
    thread.join()
    if "error" in result_box:
        raise result_box["error"]
    return result_box.get("value")


def _prepare_session(webapp: ImFusionWebApp):
    """Create a session with message capture, bypassing the real WebSocket."""
    session = webapp._create_session()
    session.websocket = object()
    messages = []

    async def capture(msg_type, data):
        messages.append((msg_type, data))

    session.data_model._send_message = capture
    return session, messages


def test_run_job_sends_started_and_result_messages():
    webapp = ImFusionWebApp()
    session, messages = _prepare_session(webapp)

    def execute():
        return {"operation": "Test", "outputs": 1}

    _run_sync(
        webapp,
        webapp.operation_runner.run_job(session, "action", "Test", execute),
    )

    kinds = [kind for kind, _ in messages]
    assert kinds == ["job_started", "job_result"]
    assert messages[-1][1]["status"] == JobStatus.SUCCEEDED.value
    assert session.jobs.active is None


def test_run_job_reports_busy_session_without_touching_sdk_thread():
    webapp = ImFusionWebApp()
    session, messages = _prepare_session(webapp)
    session.jobs.create("action", "First")

    _run_sync(
        webapp,
        webapp.operation_runner.run_job(session, "action", "Second", lambda: None),
    )

    assert [kind for kind, _ in messages] == ["job_failed"]
    assert messages[0][1]["error"]["code"] == "session_busy"


def test_run_job_discards_prepared_operation_when_cancelled_before_start():
    webapp = ImFusionWebApp()
    session, messages = _prepare_session(webapp)
    committed = []

    def execute():
        return PreparedOperation(lambda: committed.append(True) or {})

    async def run_and_cancel():
        task = asyncio.ensure_future(
            webapp.operation_runner.run_job(session, "action", "Slow", execute)
        )
        while session.jobs.active is None:
            await asyncio.sleep(0)
        session.jobs.request_cancel(session.jobs.active.id)
        await task

    _run_sync(webapp, run_and_cancel())

    assert not committed
    kinds = [kind for kind, _ in messages]
    assert kinds[-1] == "job_cancelled"


def _new_webapp():
    return ImFusionWebApp()


def test_execute_action_publishes_new_output():
    webapp = _new_webapp()
    source = object()
    generated = object()
    webapp.register("Generate")(lambda image: generated)
    session, messages = _prepare_session(webapp)
    session.data_model.add(source, "Source")

    _run_sync(
        webapp,
        webapp.websocket_handler._execute_action(
            session, {"action": "Generate", "indices": [0]}
        ),
    )

    assert session.data_model.contains(generated)
    assert len(session.data_model) == 2
    result_message = next(data for kind, data in messages if kind == "job_result")
    assert result_message["result"]["outputs"] == 1


def test_execute_action_falls_back_to_result_input_when_callback_returns_none():
    webapp = _new_webapp()
    source = object()
    updates = []
    webapp.register("Tweak in place")(lambda image: None)
    session, messages = _prepare_session(webapp)
    session.data_model.add(source, "Source")
    session.data_model.update = lambda index: updates.append(index)

    _run_sync(
        webapp,
        webapp.websocket_handler._execute_action(
            session, {"action": "Tweak in place", "indices": [0]}
        ),
    )

    assert updates == [0]
    assert len(session.data_model) == 1


def test_execute_action_app_only_does_not_touch_data_model():
    webapp = _new_webapp()
    calls = []
    webapp.register("Clear all")(lambda app: calls.append(app))
    session, messages = _prepare_session(webapp)

    _run_sync(
        webapp,
        webapp.websocket_handler._execute_action(session, {"action": "Clear all"}),
    )

    assert calls == [session.controller]
    result_message = next(data for kind, data in messages if kind == "job_result")
    assert result_message["result"]["outputs"] == 0


def _noise_image():
    return imfusion.SharedImageSet(np.ones((1, 4, 4, 1), dtype=np.float32))


def test_execute_algorithm_publishes_generated_output():
    webapp = ImFusionWebApp(algorithm_selector="sidebar")
    session, messages = _prepare_session(webapp)
    session.data_model.add(_noise_image(), "Source")

    _run_sync(
        webapp,
        webapp.websocket_handler._execute_algorithm(
            session,
            {
                "algorithm_id": "PYTHON.AddNoiseAlgorithm",
                "indices": [0],
                "parameters": {"Number of noise voxels": 4},
            },
        ),
    )

    assert len(session.data_model) == 2
    result_message = next(data for kind, data in messages if kind == "job_result")
    assert result_message["result"]["outputs"] == 1


def test_execute_controller_publishes_generated_output():
    webapp = _new_webapp()
    webapp.register(
        "Add Noise",
        algorithm="PYTHON.AddNoiseAlgorithm",
        inputs=[InputSpec("image", "Image")],
    )
    session, messages = _prepare_session(webapp)
    session.data_model.add(_noise_image(), "Source")

    _run_sync(
        webapp,
        webapp.websocket_handler._execute_controller(
            session, {"controller_name": "PYTHON.AddNoiseAlgorithm", "indices": [0]}
        ),
    )

    assert len(session.data_model) == 2
    result_message = next(data for kind, data in messages if kind == "job_result")
    assert result_message["result"]["outputs"] == 1


def test_workflow_message_handler_requires_configured_workflow():
    webapp = _new_webapp()
    session, _ = _prepare_session(webapp)
    handler = WorkflowMessageHandler(webapp)

    with pytest.raises(ValueError, match="No workflow is configured"):
        _run_sync(webapp, handler.handle("workflow_next", {}, session))


def test_workflow_message_handler_runs_navigation_as_a_job():
    from imfusion_webappkit.workflow import MessageStep, Workflow

    webapp = _new_webapp()
    session, messages = _prepare_session(webapp)
    session.workflow = Workflow(
        session.controller,
        steps=[MessageStep("Welcome", "Hi"), MessageStep("Done", "Bye")],
    )
    session.workflow.start()
    handler = WorkflowMessageHandler(webapp)

    _run_sync(webapp, handler.handle("workflow_next", {}, session))

    assert session.workflow.current_step.id == "Done"
    kinds = [kind for kind, _ in messages]
    assert kinds == ["job_started", "job_result"]


def test_workflow_message_handler_runs_custom_step_action_as_a_job():
    from imfusion_webappkit.ui_elements import Button
    from imfusion_webappkit.workflow import CustomStep, Workflow

    webapp = _new_webapp()
    session, messages = _prepare_session(webapp)
    observed = []

    class ReportStep(CustomStep):
        def on_action(self, action):
            observed.append(action)
            self.app.update_progress(0.5, "Writing report")
            self.completed = True

    step = ReportStep(
        "Report",
        body=[Button("save_report", job=True)],
        step_id="report",
        require_completion=True,
    )
    session.workflow = Workflow(session.controller, steps=[step])
    session.workflow.start()
    handler = WorkflowMessageHandler(webapp)

    _run_sync(
        webapp, handler.handle("workflow_run", {"action": "save_report"}, session)
    )

    assert observed == ["save_report"]
    assert step.can_proceed() == (True, "")
    assert [kind for kind, _ in messages] == ["job_started", "job_result"]


def test_workflow_message_handler_fails_unknown_custom_step_action():
    from imfusion_webappkit.ui_elements import Button
    from imfusion_webappkit.workflow import CustomStep, Workflow

    webapp = _new_webapp()
    session, messages = _prepare_session(webapp)
    step = CustomStep("Report", body=[Button("save_report", job=True)])
    session.workflow = Workflow(session.controller, steps=[step])
    session.workflow.start()
    handler = WorkflowMessageHandler(webapp)

    _run_sync(webapp, handler.handle("workflow_run", {"action": "delete"}, session))

    kind, data = messages[-1]
    assert kind == "job_failed"
    assert "Unknown custom step action" in data["error"]["message"]


def test_workflow_message_handler_forwards_step_data_on_sdk_thread():
    from imfusion_webappkit.workflow import ParameterStep, Workflow
    from imfusion_webappkit.parameter_spec import FloatParameter

    webapp = _new_webapp()
    session, _messages = _prepare_session(webapp)
    step = ParameterStep(parameters=[FloatParameter("amount", default=1.0)])
    session.workflow = Workflow(session.controller, steps=[step])
    session.workflow.start()
    handler = WorkflowMessageHandler(webapp)

    _run_sync(
        webapp,
        handler.handle(
            "workflow_step_data", {"data": {"parameters": {"amount": 5.0}}}, session
        ),
    )

    assert step.values["amount"] == 5.0


def test_workflow_message_handler_commits_brush_data_at_stable_index():
    from imfusion_webappkit.workflow import BrushStep, ProcessingStep, Workflow

    webapp = _new_webapp()
    session, messages = _prepare_session(webapp)
    image = object()
    original = object()
    edited = object()
    session.data_model._append_seed(image, "Image")
    session.data_model._append_seed(original, "Label Map")
    processing = ProcessingStep(step_id="segment")
    processing._published_outputs = [original]
    processing._last_source_inputs = [image]
    brush = BrushStep(label_map_from="segment", step_id="correct")
    session.workflow = Workflow(session.controller, steps=[processing, brush])
    session.workflow._current_index = 1
    brush.on_enter()
    webapp.protocol.deserialize_data_list_bytes = lambda _payload: [edited]
    handler = WorkflowMessageHandler(webapp)

    _run_sync(
        webapp,
        handler.commit_brush(
            {"format": "imf", "target_index": 1, "request_id": "req-1"},
            b"edited label map",
            session,
        ),
    )

    assert session.data_model[1] is edited
    assert brush.can_proceed() == (True, "")
    kind, data = messages[-1]
    assert kind == "workflow_brush_result"
    assert data == {"request_id": "req-1", "index": 1}


def test_workflow_message_handler_reports_brush_commit_failure_without_raising():
    from imfusion_webappkit.workflow import BrushStep, Workflow

    webapp = _new_webapp()
    session, messages = _prepare_session(webapp)
    session.data_model._append_seed(object(), "Image")
    brush = BrushStep(step_id="correct")
    session.workflow = Workflow(session.controller, steps=[brush])
    handler = WorkflowMessageHandler(webapp)

    _run_sync(
        webapp,
        handler.commit_brush(
            {"format": "not-imf", "target_index": None, "request_id": "req-2"},
            b"payload",
            session,
        ),
    )

    kind, data = messages[-1]
    assert kind == "workflow_brush_failed"
    assert data["request_id"] == "req-2"
    assert "Unsupported brush data format" in data["message"]
