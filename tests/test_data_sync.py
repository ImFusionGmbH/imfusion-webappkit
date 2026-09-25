"""Coverage for acknowledging data the browser uploads.

The browser loads a file itself and then hands the result to the server, which
has to deserialize it before any index referring to it means anything. These
tests pin the acknowledgement that closes that window, and the failure report
that closes it when the upload cannot be read.
"""

import asyncio
import threading
import time

import imfusion
import numpy as np

from imfusion_webappkit import ImFusionWebApp


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


def _upload(webapp: ImFusionWebApp, payload: bytes, request_id: str) -> bytes:
    return webapp.protocol.create_binary_message(
        "data_loaded",
        payload,
        {"format": "imf", "request_id": request_id, "name": "Uploaded"},
    )


def _image() -> imfusion.SharedImageSet:
    return imfusion.SharedImageSet(np.ones((1, 4, 4, 1), dtype=np.float32))


def test_upload_is_acknowledged_once_the_data_is_in_the_model():
    webapp = ImFusionWebApp()
    session, messages = _prepare_session(webapp)
    payload = webapp.protocol.serialize_data_list_bytes([_image()])

    _run_sync(
        webapp,
        webapp.websocket_handler.process_binary_message(
            _upload(webapp, payload, "upload-1"), session
        ),
    )

    assert len(session.data_model) == 1
    assert session.data_model.get_name(0) == "Uploaded"
    assert [kind for kind, _ in messages] == ["data_sync_complete"]
    assert messages[0][1] == {"request_id": "upload-1", "count": 1, "total": 1}


def test_acknowledgement_counts_what_arrived_against_the_whole_model():
    webapp = ImFusionWebApp()
    session, messages = _prepare_session(webapp)
    session.data_model._append_from_client(_image(), "Already here")
    payload = webapp.protocol.serialize_data_list_bytes([_image()])

    _run_sync(
        webapp,
        webapp.websocket_handler.process_binary_message(
            _upload(webapp, payload, "upload-2"), session
        ),
    )

    assert messages[-1][1]["count"] == 1
    assert messages[-1][1]["total"] == 2


def test_unreadable_upload_reports_its_request_so_the_client_can_recover():
    webapp = ImFusionWebApp()
    session, messages = _prepare_session(webapp)

    _run_sync(
        webapp,
        webapp.websocket_handler.process_binary_message(
            _upload(webapp, b"not an imf file", "upload-3"), session
        ),
    )

    assert not len(session.data_model)
    kind, data = messages[-1]
    assert kind == "job_failed"
    assert data["request_id"] == "upload-3"
    assert data["error"]["recoverable"] is True


def test_upload_in_an_unsupported_format_is_reported_against_its_request():
    webapp = ImFusionWebApp()
    session, messages = _prepare_session(webapp)
    message = webapp.protocol.create_binary_message(
        "data_loaded",
        b"",
        {"format": "nifti", "request_id": "upload-4"},
    )

    _run_sync(webapp, webapp.websocket_handler.process_binary_message(message, session))

    kind, data = messages[-1]
    assert kind == "job_failed"
    assert data["request_id"] == "upload-4"
