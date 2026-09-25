"""Replay one sequence of client messages against a real application.

Nothing here re-implements the protocol. A stand-in for Starlette's WebSocket
scripts the messages a browser would have sent and captures what comes back, so
:meth:`~imfusion_webappkit.websocket_handler.WebSocketHandler.handle_websocket`
runs exactly as it does in production, including the connect sequence, the job
lifecycle and the workflow state pushes.

Each transition is recorded by replaying its whole path from a fresh
application. That is slower than snapshotting and restoring the application
between branches, but ImFusion data lives in native objects that cannot be
copied cheaply or reliably, and a wrong snapshot would be recorded as a genuine
result.
"""

# The recorder deliberately drives private session and data-model hooks.
# pylint: disable=protected-access

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import hashlib
import json
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, TYPE_CHECKING

import numpy as np

from ..image_protocol import ImageProtocol
from .canonical import canonical_json

if TYPE_CHECKING:
    from ..app import ImFusionWebApp
    from ..session import Session


@dataclass(frozen=True)
class Frame:
    """One server message the browser would have received."""

    type: str
    data: Dict[str, Any]
    payload: Optional[bytes] = None


@dataclass(frozen=True)
class SessionState:
    """The part of the server's state the browser can observe.

    Two paths that arrive here are indistinguishable to the client, so they can
    share a node in the recorded graph.
    """

    names: List[str]
    contents: List[str]
    selection: List[int]
    workflow: Optional[Dict[str, Any]]

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(
            canonical_json(
                {
                    "names": self.names,
                    "contents": self.contents,
                    "selection": self.selection,
                    "workflow": self.workflow,
                }
            ).encode("utf-8")
        ).hexdigest()


@dataclass
class PathOutcome:
    """What one replayed path produced."""

    # One bucket per dispatched message, plus `steps[0]` for the connect
    # sequence, so a caller can take just the frames its own message caused.
    steps: List[List[Frame]] = field(default_factory=list)
    state: Optional[SessionState] = None

    @property
    def last_frames(self) -> List[Frame]:
        return self.steps[-1] if self.steps else []


def data_content_hash(data: Any) -> str:
    """Hash what a dataset means rather than how it was written to disk.

    An ``.imf`` file is not reproduced byte for byte across a save/load round
    trip, so hashing the container would make every state look new and defeat
    both node collapsing and payload reuse. Voxels and geometry do survive the
    round trip.
    """
    digest = hashlib.sha256()
    digest.update(type(data).__name__.encode("utf-8"))
    digest.update(str(getattr(data, "modality", "")).encode("utf-8"))
    try:
        images = list(data)
    except TypeError:
        # Not an image set: fall back to the serialized form, which is stable
        # for an object that is not round-tripped.
        return hashlib.sha256(
            ImageProtocol.serialize_data_list_bytes([data])
        ).hexdigest()
    for image in images:
        values = np.ascontiguousarray(np.array(image, copy=False))
        digest.update(str(values.dtype).encode("utf-8"))
        digest.update(str(values.shape).encode("utf-8"))
        digest.update(values.tobytes())
        digest.update(np.asarray(image.spacing, dtype=float).tobytes())
        digest.update(np.asarray(image.pixel_to_world_matrix, dtype=float).tobytes())
        digest.update(str(image.modality).encode("utf-8"))
        digest.update(np.asarray([image.shift, image.scale], dtype=float).tobytes())
    return digest.hexdigest()


def payload_content_hash(payload: bytes) -> str:
    """Hash what a serialized payload means, so equal datasets are stored once.

    Hashing the bytes instead would store one copy per recorded path: the same
    dataset written by two separate runs is not the same ``.imf`` file. Must run
    on the SDK owner thread, because it loads the payload to look inside it.
    """
    digest = hashlib.sha256()
    for data in ImageProtocol.deserialize_data_list_bytes(payload):
        digest.update(data_content_hash(data).encode("utf-8"))
    return digest.hexdigest()


def _capture_state(session: "Session") -> SessionState:
    """Read the observable state. Must run on the SDK owner thread."""
    return SessionState(
        names=list(session.data_model._names),
        contents=[data_content_hash(data) for data in session.data_model],
        selection=list(session.controller._selected_indices),
        workflow=(
            session.workflow.get_state() if session.workflow is not None else None
        ),
    )


class ClientView:
    """The visible-data bookkeeping the browser does, mirrored while recording.

    The browser echoes what it shows back as `selection_changed`, and a workflow
    step that infers its input from the selection reads the result, so a
    recording made without that echo would not match a live session. This is the
    one place that restates client behaviour rather than running it; the original
    is the message handler in `PythonBridge.tsx`, and `StaticTransport` checks
    the two still agree while replaying.
    """

    def __init__(self) -> None:
        self.count = 0
        self.visible: List[int] = []

    def apply(self, frame: Frame) -> None:
        if frame.type == "data_add":
            index = int(frame.data.get("index", self.count))
            self.count = max(self.count, index + 1)
            # `showAll` adds to the view group rather than replacing it.
            if index not in self.visible:
                self.visible.append(index)
        elif frame.type == "data_remove":
            removed = int(frame.data["index"])
            self.count = max(0, self.count - 1)
            self.visible = [
                index - 1 if index > removed else index
                for index in self.visible
                if index != removed
            ]
        elif frame.type in {"data_clear", "reset_views"}:
            self.count = 0
            self.visible = []
        elif frame.type == "selection_update":
            self.visible = [
                index
                for index in frame.data.get("indices") or []
                if 0 <= index < self.count
            ]
        elif frame.type == "data_reset":
            raise NotImplementedError(
                "`data_reset` cannot be recorded: the number of datasets it "
                "carries is only known after loading its payload"
            )
        # `data_update` replaces one dataset in place and keeps the view.


class RecordingWebSocket:
    """Stand-in for Starlette's WebSocket that scripts input and keeps output.

    Only the five methods the application uses are implemented: ``accept``,
    ``receive``, ``send_text``, ``send_bytes`` and ``close``.
    """

    def __init__(
        self,
        messages: Sequence[Dict[str, Any]],
        outcome: PathOutcome,
        resolve_session: Callable[[], Optional["Session"]],
        capture: Callable[[Callable[[], Any]], Any],
        idle_seconds: float,
        settle_timeout: float,
    ):
        self._messages = list(messages)
        self._outcome = outcome
        self._resolve_session = resolve_session
        self._capture = capture
        self._idle_seconds = idle_seconds
        self._settle_timeout = settle_timeout
        self._frame_count = 0
        self._view = ClientView()
        self._echoed: Optional[List[int]] = None
        self.closed = False
        self._outcome.steps.append([])

    async def accept(self) -> None:
        return None

    async def close(self, code: int = 1000) -> None:
        del code
        self.closed = True

    async def send_text(self, message: str) -> None:
        parsed = json.loads(message)
        self._record(Frame(parsed["type"], parsed.get("data") or {}))

    async def send_bytes(self, message: bytes) -> None:
        message_type, data, payload = ImageProtocol.parse_binary_message(message)
        self._record(Frame(message_type, data, payload))

    def _record(self, frame: Frame) -> None:
        self._outcome.steps[-1].append(frame)
        self._frame_count += 1
        self._view.apply(frame)

    async def receive(self) -> Dict[str, Any]:
        await self._settle()

        if self._echoed != self._view.visible:
            # Report what the browser would now be showing before it acts again.
            # This carries no reply, so it stays in the current frame bucket.
            self._echoed = list(self._view.visible)
            return {
                "type": "websocket.receive",
                "text": json.dumps(
                    {"type": "selection_changed", "data": {"indices": self._echoed}}
                ),
            }

        if not self._messages:
            # The last chance to read the session: the handler disposes it while
            # unwinding from the disconnect this returns.
            session = self._resolve_session()
            if session is not None:
                self._outcome.state = await self._capture(
                    lambda: _capture_state(session)
                )
            return {"type": "websocket.disconnect", "code": 1000}
        self._outcome.steps.append([])
        return {"type": "websocket.receive", "text": json.dumps(self._messages.pop(0))}

    async def _settle(self) -> None:
        """Wait until the server has finished answering the previous message.

        Operation messages are handled in background tasks, and the messages
        they produce are scheduled onto this loop from the SDK thread, so a
        finished task does not by itself mean every frame has arrived.
        """
        deadline = asyncio.get_running_loop().time() + self._settle_timeout
        while True:
            session = self._resolve_session()
            pending = (
                [task for task in tuple(session.operation_tasks) if not task.done()]
                if session is not None
                else []
            )
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
                continue
            before = self._frame_count
            await asyncio.sleep(self._idle_seconds)
            if before == self._frame_count:
                return
            if asyncio.get_running_loop().time() > deadline:
                raise TimeoutError(
                    "The application kept sending messages while recording; "
                    "a callback may never finish"
                )


def run_path(
    build_app: Callable[[], "ImFusionWebApp"],
    messages: Sequence[Dict[str, Any]],
    *,
    idle_seconds: float = 0.05,
    settle_timeout: float = 600.0,
) -> PathOutcome:
    """Replay `messages` against a new application and return what it sent.

    Must be called from the thread that owns ImFusion, because that is the
    thread `build_app` makes the SDK runtime's owner. The event loop runs on a
    worker thread while this thread pumps SDK work, mirroring
    :meth:`~imfusion_webappkit.app.ImFusionWebApp.run`.
    """
    app = build_app()
    outcome = PathOutcome()
    failure: List[BaseException] = []

    def resolve_session() -> Optional["Session"]:
        return next(iter(app._sessions.values()), None)

    sockets: List[RecordingWebSocket] = []

    async def drive() -> None:
        async def capture(callback: Callable[[], Any]) -> Any:
            return await app.operation_runner.run_sdk_call(callback)

        socket = RecordingWebSocket(
            messages,
            outcome,
            resolve_session,
            capture,
            idle_seconds,
            settle_timeout,
        )
        sockets.append(socket)
        await app.websocket_handler.handle_websocket(socket)

    def worker() -> None:
        try:
            asyncio.run(drive())
        except BaseException as exc:  # surfaced on the calling thread below
            failure.append(exc)

    thread = threading.Thread(target=worker, name="static-demo-recorder", daemon=True)
    thread.start()
    deadline = time.monotonic() + settle_timeout
    while thread.is_alive():
        if time.monotonic() > deadline:
            app.sdk_runtime.stop()
            raise TimeoutError(
                f"Recording did not finish within {settle_timeout:.0f}s for "
                f"{len(messages)} message(s)"
            )
        app.sdk_runtime.run_once(timeout=0.05)
    while app.sdk_runtime.run_once(timeout=0):
        pass
    thread.join()
    app.sdk_runtime.stop()

    if failure:
        raise failure[0]
    if outcome.state is None:
        # The handler turns any application error into a closed connection, so
        # the reason was logged rather than raised.
        raise RuntimeError(
            "The application closed the connection before its state could be "
            "read, which means it raised while handling "
            + (
                f"message {len(outcome.steps) - 1} of {len(messages)} "
                f"({messages[len(outcome.steps) - 2]['type']!r})"
                if len(outcome.steps) > 1
                else "the connect sequence"
            )
            + ". The error itself was logged above."
        )
    return outcome
