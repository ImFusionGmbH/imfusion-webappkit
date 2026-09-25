"""Execution-thread and session-isolation tests."""

import threading
from types import SimpleNamespace

import imfusion
import numpy as np
import pytest

from imfusion_webappkit.jobs import JobStatus, SessionBusyError, SessionJobManager
from imfusion_webappkit.sdk_runtime import (
    MainThreadSDKRuntime,
    SDKThreadError,
    SDKWorkCancelled,
    SDKWorkItem,
)
from imfusion_webappkit.session import Session


def test_sdk_runtime_executes_submitted_work_on_owner_thread():
    runtime = MainThreadSDKRuntime()
    owner = threading.get_ident()
    submitted = {}

    def submit():
        submitted["item"] = runtime.submit(threading.get_ident)

    thread = threading.Thread(target=submit)
    thread.start()
    thread.join()
    runtime.run_once(timeout=0)

    assert submitted["item"].future.result() == owner


def test_sdk_runtime_rejects_pumping_from_other_thread():
    runtime = MainThreadSDKRuntime()
    errors = []

    def pump():
        try:
            runtime.run_once(timeout=0)
        except SDKThreadError as exc:
            errors.append(exc)

    thread = threading.Thread(target=pump)
    thread.start()
    thread.join()
    assert errors


def test_sdk_runtime_rejects_submission_after_stop():
    runtime = MainThreadSDKRuntime()
    runtime.stop()

    with pytest.raises(RuntimeError, match="stopping"):
        runtime.submit(lambda: None)


def test_sdk_work_item_cancel_wins_over_later_start():
    item = SDKWorkItem(lambda: "ran")
    item.request_cancel()

    assert item.try_start() is False
    assert item.cancelled.is_set()


def test_sdk_work_item_start_wins_over_later_cancel():
    item = SDKWorkItem(lambda: "ran")

    assert item.try_start() is True
    item.request_cancel()

    assert item.cancelled.is_set()
    assert item.future.running()
    assert item.try_start() is False


def test_sdk_runtime_skips_cancelled_queued_work():
    runtime = MainThreadSDKRuntime()
    ran = []
    submitted = {}

    def submit():
        submitted["item"] = runtime.submit(lambda: ran.append("executed") or "ok")
        submitted["item"].request_cancel()

    thread = threading.Thread(target=submit)
    thread.start()
    thread.join()
    runtime.run_once(timeout=0)

    assert ran == []
    with pytest.raises(SDKWorkCancelled):
        submitted["item"].future.result()


def test_session_job_manager_limits_and_logically_cancels():
    jobs = SessionJobManager()
    job = jobs.create("algorithm", "Registration")

    try:
        jobs.create("action", "Other")
    except SessionBusyError:
        pass
    else:
        raise AssertionError("A second in-flight job was accepted")

    jobs.mark_running(job)
    jobs.request_cancel(job.id)
    assert job.status == JobStatus.CANCEL_REQUESTED
    jobs.complete(job, JobStatus.CANCELLED)
    assert jobs.active is None


def test_progress_is_routed_to_owning_session_only():
    host = SimpleNamespace(_workflow_factory=None)
    first = Session(host, "first")
    second = Session(host, "second")
    first_messages = []
    second_messages = []
    first.send_message = lambda kind, data: first_messages.append((kind, data))
    second.send_message = lambda kind, data: second_messages.append((kind, data))

    first.jobs.create("action", "First")
    second.jobs.create("action", "Second")
    first.controller.update_progress(0.5, "Halfway")

    assert first_messages[0][0] == "job_progress"
    assert first_messages[0][1]["message"] == "Halfway"
    assert second_messages == []


def test_controller_selection_is_session_scoped():
    host = SimpleNamespace(_workflow_factory=None)
    first = Session(host, "first")
    second = Session(host, "second")
    first.send_message = lambda *_args: None
    second.send_message = lambda *_args: None
    first_data = object()
    second_data = object()
    first.data_model.add(first_data, "First")
    second.data_model.add(second_data, "Second")

    first.controller.select_data(first_data)

    assert first.controller.selected_data == [first_data]
    assert second.controller.selected_data == []


def test_web_data_model_documents_flat_reference_semantics():
    host = SimpleNamespace(_workflow_factory=None)
    session = Session(host, "session")
    item = object()

    returned = session.data_model.add(item, "Item")

    assert returned is item
    assert session.data_model.get("Item") is item
    assert session.data_model.get("Missing") is None
    session.data_model.remove(0)
    assert len(session.data_model) == 0


def test_in_place_update_sends_only_the_changed_dataset():
    protocol = SimpleNamespace(
        serialize_data_list_bytes=lambda values: str(len(values)).encode()
    )
    host = SimpleNamespace(_workflow_factory=None, protocol=protocol)
    session = Session(host, "session")
    first = object()
    second = object()
    session.data_model.add(first, "First")
    session.data_model.add(second, "Second")
    messages = []
    session.data_model._websocket = object()
    session.data_model._sync_send_binary_message = (
        lambda kind, metadata, payload: messages.append((kind, metadata, payload))
    )

    session.data_model.update(0)

    assert messages == [
        (
            "data_update",
            {"format": "imf", "name": "First", "index": 0},
            b"1",
        )
    ]


def test_result_publication_distinguishes_in_place_and_already_added_outputs():
    naming = SimpleNamespace(
        result_name=lambda source, operation: f"{source}-{operation}"
    )
    host = SimpleNamespace(_workflow_factory=None, websocket_handler=naming)
    session = Session(host, "session")
    source = object()
    generated = object()
    session.data_model.add(source, "Source")
    updates = []
    session.data_model.update = lambda index: updates.append(index)

    session.controller.publish_results(source, "Process", [source])
    session.controller.publish_results(generated, "Generate", [source])
    session.controller.publish_results(generated, "Generate", [source])

    assert updates == [0]
    assert session.data_model.contains(generated)
    assert len(session.data_model) == 2


def test_result_publication_replaces_previous_generated_output():
    naming = SimpleNamespace(
        result_name=lambda source, operation: f"{source}-{operation}"
    )
    host = SimpleNamespace(_workflow_factory=None, websocket_handler=naming)
    session = Session(host, "session")
    source = object()
    previous = object()
    replacement = object()
    session.data_model.add(source, "Source")

    session.controller.publish_results(previous, "Segment", [source])
    output_name = session.data_model.get_name(1)
    session.controller.publish_results(
        replacement,
        "Segment",
        [source],
        replace=[previous],
    )

    assert len(session.data_model) == 2
    assert session.data_model[1] is replacement
    assert session.data_model.get_name(1) == output_name
    assert not session.data_model.contains(previous)


def test_seed_data_is_copied_per_session():
    seed = {"value": 1}
    initial_data = SimpleNamespace(_data=[seed], _names=["Seed"], _source_paths=[None])
    protocol = SimpleNamespace(
        serialize_data_list=lambda values: list(values),
        deserialize_data_list=lambda values: [dict(value) for value in values],
    )
    host = SimpleNamespace(
        _workflow_factory=None,
        _session_callbacks=[],
        initial_data=initial_data,
        protocol=protocol,
    )
    first = Session(host, "first")
    second = Session(host, "second")

    first.initialize()
    second.initialize()
    first.data_model[0]["value"] = 2

    assert second.data_model[0]["value"] == 1
    assert first.data_model[0] is not second.data_model[0]


def test_remove_remaps_session_selection():
    host = SimpleNamespace(_workflow_factory=None)
    session = Session(host, "session")
    first = object()
    second = object()
    session.data_model.add(first, "First")
    session.data_model.add(second, "Second")
    messages = []
    session.send_message = lambda kind, payload: messages.append((kind, payload))
    session.controller._set_selected_indices([0, 1])

    session.data_model.remove(0)

    assert session.controller.selected_data == [second]
    assert messages[-1] == ("selection_update", {"indices": [0]})


def test_set_name_synchronizes_with_browser():
    host = SimpleNamespace(_workflow_factory=None)
    session = Session(host, "session")
    item = object()
    session.data_model.add(item, "Before")
    messages = []
    session.data_model._websocket = object()
    session.data_model._sync_send_message = lambda kind, payload: messages.append(
        (kind, payload)
    )

    session.data_model.set_name(item, "After")

    assert session.data_model.get_name(item) == "After"
    assert messages == [("data_metadata", {"index": 0, "name": "After"})]


def _recording_session():
    """Session whose data model records the frames it would have sent."""
    host = SimpleNamespace(
        _workflow_factory=None,
        protocol=SimpleNamespace(serialize_data_list_bytes=lambda values: b"payload"),
    )
    session = Session(host, "session")
    sent = []
    session.data_model._websocket = object()
    session.data_model._sync_send_message = lambda kind, payload: sent.append(
        (kind, payload)
    )
    session.data_model._sync_send_binary_message = (
        lambda kind, payload, content: sent.append((kind, payload))
    )
    return session, sent


def _added_image(session, sent):
    images = imfusion.SharedImageSet(np.ones((1, 4, 4, 1), dtype=np.float32))
    session.data_model.add(images, "Scan")
    sent.clear()
    return images


def test_update_metadata_sends_modality_without_the_pixels():
    session, sent = _recording_session()
    images = _added_image(session, sent)

    images.modality = imfusion.Data.Modality.LABEL

    assert session.data_model.update_metadata(0) is True
    assert sent == [("data_metadata", {"index": 0, "modality": "LABEL"})]


def test_update_metadata_sends_nothing_when_nothing_changed():
    session, sent = _recording_session()
    _added_image(session, sent)

    assert session.data_model.update_metadata(0) is True
    assert sent == []


def test_update_metadata_falls_back_to_a_full_transfer_on_spacing():
    session, sent = _recording_session()
    images = _added_image(session, sent)

    images[0].spacing = [1.0, 1.0, 2.0]

    assert session.data_model.update_metadata(0) is False
    assert sent == [("data_update", {"format": "imf", "name": "Scan", "index": 0})]


def test_update_metadata_falls_back_to_a_full_transfer_on_matrix():
    session, sent = _recording_session()
    images = _added_image(session, sent)

    moved = np.eye(4)
    moved[0, 3] = 5.0
    images.set_matrix(moved)

    assert session.data_model.update_metadata(0) is False
    assert sent == [("data_update", {"format": "imf", "name": "Scan", "index": 0})]


def test_every_mutation_keeps_the_parallel_lists_aligned():
    """The snapshot list is indexed by position, so it must track every edit."""
    session, sent = _recording_session()
    model = session.data_model
    aligned = lambda: len(model._data) == len(model._names) == len(model._metadata)

    model.add(object(), "First")
    model.add(object(), "Second")
    model._append_seed(object(), "Third")
    model._append_from_client(object(), "Fourth")
    assert aligned()

    model.replace(0, object())
    model._replace_from_client(1, object())
    assert aligned()

    model.remove(0)
    model.remove(model[0])
    model._remove_from_client(0)
    assert aligned()

    model.clear()
    assert aligned()


def test_update_metadata_falls_back_for_data_without_a_snapshot():
    session, sent = _recording_session()
    session.data_model.add(object(), "Opaque")
    sent.clear()

    assert session.data_model.update_metadata(0) is False
    assert sent == [("data_update", {"format": "imf", "name": "Opaque", "index": 0})]
