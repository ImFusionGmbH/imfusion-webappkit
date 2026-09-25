"""WebSocket lifecycle and operation routing."""

# This coordinator owns private session/model hooks and reports callback errors.
# pylint: disable=protected-access,broad-exception-caught

from __future__ import annotations

import asyncio
import base64
import logging
import re
from typing import Callable, TYPE_CHECKING

from fastapi import WebSocket, WebSocketDisconnect

from .data_export import export_data
from .operation_runner import PreparedOperation
from .session import Session
from .workflow_handler import WorkflowMessageHandler

if TYPE_CHECKING:
    from .app import ImFusionWebApp

logger = logging.getLogger(__name__)


class WebSocketHandler:
    """Handle WebSocket traffic for one application host."""

    operation_message_types = {
        "execute_action",
        "discover_algorithms",
        "execute_algorithm",
        "check_controller_compatibility",
        "execute_controller",
        "export_data",
        "workflow_next",
        "workflow_back",
        "workflow_run",
    }

    def __init__(self, host: "ImFusionWebApp"):
        self._host = host
        self.workflow_messages = WorkflowMessageHandler(host)

    @staticmethod
    def result_name(source_name: str, operation_name: str) -> str:
        short_name = operation_name.rsplit(".", 1)[-1].replace("_", " ")
        readable = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", short_name)
        return f"{source_name or 'Data'} — {readable}"

    @staticmethod
    def _resolve_role_inputs(data: dict, session: Session, specs=None):
        refs = data.get("inputs")
        if refs is None:
            indices = data.get("indices", [])
            refs = [
                {
                    "role": (
                        specs[index].key if specs and index < len(specs) else str(index)
                    ),
                    "index": value,
                }
                for index, value in enumerate(indices)
            ]
        if not isinstance(refs, list):
            raise ValueError("Inputs must be a list")

        by_role = {}
        ordered_refs = []
        for ref in refs:
            if not isinstance(ref, dict) or not isinstance(ref.get("index"), int):
                raise ValueError("Each input must contain a role and integer index")
            role = str(ref.get("role", len(ordered_refs)))
            if role in by_role:
                raise ValueError(f"Duplicate input role: {role}")
            by_role[role] = ref["index"]
            ordered_refs.append((role, ref["index"]))

        if specs:
            ordered_refs = []
            for spec in specs:
                if spec.key not in by_role:
                    if spec.required:
                        raise ValueError(f"Missing required input: {spec.label}")
                    continue
                ordered_refs.append((spec.key, by_role[spec.key]))

        indices = [index for _, index in ordered_refs]
        if not indices:
            raise ValueError("At least one data input is required")
        if len(indices) != len(set(indices)):
            raise ValueError("Each input must use a different dataset")
        if any(index < 0 or index >= len(session.data_model) for index in indices):
            raise ValueError(
                f"Invalid input indices: {indices}. Data model size: "
                f"{len(session.data_model)}"
            )
        ordered = [session.data_model[index] for index in indices]
        role_map = {role: value for (role, _), value in zip(ordered_refs, ordered)}
        return ordered, role_map, indices

    async def handle_websocket(self, websocket: WebSocket) -> None:
        await websocket.accept()
        session = self._host._create_session()
        session.set_websocket(websocket)
        logger.info("WebSocket session established: %s", session.session_id)
        handler_cancelled = False

        try:
            await self._host.operation_runner.run_sdk_call(session.initialize)
            await session.data_model._send_message(
                "actions",
                {"actions": self._host.action_registry.list_action_descriptors()},
            )
            payloads = await self._host.operation_runner.run_sdk_call(
                session.data_model._initial_state_payloads
            )
            for metadata, payload in payloads:
                await session.data_model._send_binary_message(
                    "data_add", metadata, payload
                )
            await session.data_model._send_message(
                "initial_sync_complete", {"count": len(session.data_model)}
            )
            if session.workflow:
                await self._host.operation_runner.run_sdk_call(session.workflow.start)

            while True:
                received = await websocket.receive()
                if received["type"] == "websocket.disconnect":
                    raise WebSocketDisconnect(received.get("code", 1000))
                binary_message = received.get("bytes")
                if binary_message is not None:
                    await self.process_binary_message(binary_message, session)
                    continue

                message = received.get("text")
                if message is None:
                    raise ValueError("WebSocket message has no text or binary payload")
                message_type, _ = self._host.protocol.parse_message(message)
                if message_type in self.operation_message_types:
                    task = asyncio.create_task(
                        self.process_message(websocket, message, session)
                    )
                    session.operation_tasks.add(task)
                    task.add_done_callback(session.operation_tasks.discard)
                else:
                    await self.process_message(websocket, message, session)
        except WebSocketDisconnect:
            logger.info("WebSocket session disconnected: %s", session.session_id)
        except asyncio.CancelledError:
            handler_cancelled = True
        except Exception as exc:
            logger.error("WebSocket error: %s", exc, exc_info=True)
            try:
                await websocket.close()
            except RuntimeError:
                pass
        finally:
            active = session.jobs.active
            if active is not None:
                session.jobs.request_cancel(active.id)
            if session.operation_tasks:
                operations = asyncio.gather(
                    *session.operation_tasks, return_exceptions=True
                )
                try:
                    await asyncio.shield(operations)
                except asyncio.CancelledError:
                    handler_cancelled = True
                    await operations
            session.clear_websocket()
            try:
                await self._host.operation_runner.run_sdk_call(session.dispose)
            except (RuntimeError, asyncio.CancelledError):
                logger.warning(
                    "Could not dispose session %s on the SDK thread",
                    session.session_id,
                )
            self._host._remove_session(session)
        if handler_cancelled:
            raise asyncio.CancelledError

    async def process_binary_message(
        self, binary_message: bytes, session: Session
    ) -> None:
        # Reported back with any failure: the client holds the interface that
        # sent this request busy until it hears one way or the other.
        request_id = None
        try:
            message_type, data, payload = self._host.protocol.parse_binary_message(
                binary_message
            )
            request_id = data.get("request_id")
            if message_type == "data_loaded":
                await self._data_loaded_bytes(session, data, payload)
            elif message_type == "workflow_brush_commit":
                await self.workflow_messages.commit_brush(data, payload, session)
            else:
                raise ValueError(f"Unknown binary message type: {message_type}")
        except Exception as exc:
            logger.error("Error processing binary message: %s", exc, exc_info=True)
            if session.websocket is not None:
                await session.data_model._send_message(
                    "job_failed",
                    {
                        "job_id": None,
                        "request_id": request_id,
                        "status": "failed",
                        "error": {
                            "code": "invalid_request",
                            "message": str(exc),
                            "recoverable": True,
                        },
                    },
                )

    async def process_message(
        self, websocket: WebSocket, message: str, session: Session
    ) -> None:
        del websocket  # the session owns the active transport
        try:
            msg_type, data = self._host.protocol.parse_message(message)
            data = data or {}

            if msg_type == "execute_action":
                await self._execute_action(session, data)
            elif msg_type == "discover_algorithms":
                await self._discover_algorithms(session, data)
            elif msg_type == "execute_algorithm":
                await self._execute_algorithm(session, data)
            elif msg_type == "check_controller_compatibility":
                await self._check_controller(session, data)
            elif msg_type == "execute_controller":
                await self._execute_controller(session, data)
            elif msg_type == "data_loaded":
                await self._data_loaded(session, data)
            elif msg_type == "data_removed":
                await self._data_removed(session, data)
            elif msg_type == "export_data":
                await self._export_data(session, data)
            elif msg_type == "selection_changed":
                indices = data.get("indices", [])
                session.controller._set_selected_indices(indices)
            elif msg_type == "annotation_event":
                await self._annotation_event(session, data)
            elif msg_type == "annotation_created":
                await self._annotation_created(session, data)
            elif msg_type in self.workflow_messages.message_types:
                await self.workflow_messages.handle(msg_type, data, session)
            elif msg_type == "cancel_job":
                await self._host.operation_runner.cancel(
                    session, data.get("job_id", "")
                )
            else:
                raise ValueError(f"Unknown message type: {msg_type}")
        except Exception as exc:
            logger.error("Error processing message: %s", exc, exc_info=True)
            if session.websocket is not None:
                await session.data_model._send_message(
                    "job_failed",
                    {
                        "job_id": None,
                        "status": "failed",
                        "error": {
                            "code": "invalid_request",
                            "message": str(exc),
                            "recoverable": True,
                        },
                    },
                )

    async def _execute_and_publish(
        self,
        session: Session,
        job_kind: str,
        job_name: str,
        ordered: list,
        compute_outputs,
    ) -> None:
        """Run `compute_outputs` on the SDK thread, then publish and report its results."""

        def execute():
            outputs = compute_outputs()

            def commit():
                published = session.controller.publish_results(
                    outputs, job_name, ordered
                )
                return {"operation": job_name, "outputs": len(published)}

            return PreparedOperation(commit)

        await self._host.operation_runner.run_job(session, job_kind, job_name, execute)

    async def _execute_action(self, session: Session, data: dict) -> None:
        name = data["action"]
        metadata = self._host.action_registry.get_action_metadata(name)
        if metadata["is_app_only"]:

            def execute():
                self._host.action_registry.execute_action(
                    name, {}, data.get("parameters", {}), app=session.controller
                )
                return {"operation": name, "outputs": 0}

            await self._host.operation_runner.run_job(session, "action", name, execute)
            return

        ordered, role_inputs, _ = self._resolve_role_inputs(
            data, session, metadata["inputs"]
        )

        def compute_outputs():
            result = self._host.action_registry.execute_action(
                name,
                role_inputs,
                data.get("parameters", {}),
                app=session.controller,
            )
            return (
                result if result is not None else role_inputs[metadata["result_input"]]
            )

        await self._execute_and_publish(
            session, "action", name, ordered, compute_outputs
        )

    async def _discover_algorithms(self, session: Session, data: dict) -> None:
        ordered, _, _ = self._resolve_role_inputs(data, session)

        def discover():
            return {
                "algorithms": self._host.algorithm_registry.discover_compatible_algorithms(
                    ordered
                )
            }

        await self._host.operation_runner.run_job(
            session, "algorithm_discovery", "Discover algorithms", discover
        )

    async def _execute_algorithm(self, session: Session, data: dict) -> None:
        algorithm_id = data["algorithm_id"]
        ordered, _, _ = self._resolve_role_inputs(data, session)

        def compute_outputs():
            return self._host.algorithm_registry.execute_algorithm(
                algorithm_id, ordered, data.get("parameters", {})
            )

        await self._execute_and_publish(
            session, "algorithm", algorithm_id, ordered, compute_outputs
        )

    async def _check_controller(self, session: Session, data: dict) -> None:
        requested = data.get("controller_name")
        controllers = (
            [self._host.algorithm_registry.get_controller(requested)]
            if requested
            else [
                self._host.algorithm_registry.get_controller(item["name"])
                for item in self._host.algorithm_registry.get_controllers()
            ]
        )
        input_map = {
            item["name"]: self._resolve_role_inputs(data, session, item["inputs"])[0]
            for item in controllers
        }

        def check():
            return {
                "controllers": [
                    self._host.algorithm_registry.get_controller_with_compatibility(
                        item["name"], input_map[item["name"]]
                    )
                    for item in controllers
                ]
            }

        await self._host.operation_runner.run_job(
            session, "controller_check", "Check compatibility", check
        )

    async def _execute_controller(self, session: Session, data: dict) -> None:
        name = data["controller_name"]
        controller = self._host.algorithm_registry.get_controller(name)
        ordered, _, _ = self._resolve_role_inputs(data, session, controller["inputs"])
        result_index = next(
            index
            for index, spec in enumerate(controller["inputs"])
            if spec.key == controller["result_input"]
        )

        def compute_outputs():
            return self._host.algorithm_registry.execute_algorithm(
                controller["id"],
                ordered,
                data.get("parameters", {}),
                result_index,
            )

        await self._execute_and_publish(
            session, "controller", name, ordered, compute_outputs
        )

    async def _data_loaded(self, session: Session, data: dict) -> None:
        def load():
            loaded = self._host.protocol.deserialize_data_list(data["image"])
            self._append_loaded_data(session, loaded, data)
            return len(loaded)

        await self._accept_client_data(session, data, load)

    async def _data_loaded_bytes(
        self, session: Session, data: dict, payload: bytes
    ) -> None:
        if data.get("format") != "imf":
            raise ValueError(f"Unsupported binary data format: {data.get('format')}")

        def load():
            loaded = self._host.protocol.deserialize_data_list_bytes(payload)
            self._append_loaded_data(session, loaded, data)
            return len(loaded)

        await self._accept_client_data(session, data, load)

    async def _accept_client_data(self, session: Session, data: dict, load) -> None:
        """Take data the browser loaded, then tell it the server has the data.

        Deserializing a volume on the SDK thread takes as long as loading it did,
        and until it finishes the browser is showing a dataset this process knows
        nothing about. An index sent for it in that window resolves to the wrong
        dataset or to none at all, so the client keeps everything that references
        an index disabled until this acknowledgement arrives.
        """
        count = await self._host.operation_runner.run_sdk_call(load)
        await session.data_model._send_message(
            "data_sync_complete",
            {
                "request_id": data.get("request_id"),
                "count": count,
                "total": len(session.data_model),
            },
        )

    @staticmethod
    def _append_loaded_data(session: Session, loaded: list, data: dict) -> None:
        names = data.get("names", [])
        fallback = data.get("name", "Unnamed")
        for index, item in enumerate(loaded):
            name = (
                names[index]
                if index < len(names)
                else fallback if index == 0 else f"{fallback} {index + 1}"
            )
            session.data_model._append_from_client(item, name)

    async def _data_removed(self, session: Session, data: dict) -> None:
        index = data.get("index")

        def remove():
            if not isinstance(index, int) or not 0 <= index < len(session.data_model):
                raise ValueError(f"Invalid data index: {index}")
            session.data_model._remove_from_client(index)

        await self._host.operation_runner.run_sdk_call(remove)

    @staticmethod
    def _apply_annotation(session: Session, apply: Callable[[], None]) -> None:
        """Apply an annotation message, then republish the workflow panel.

        Any step can show annotation state — ``AnnotationField`` in a custom
        step as much as ``AnnotationStep`` — and none of them has another way
        to hear that the user finished drawing. Republished even when applying
        raised, because the browser is already showing the new geometry.
        """
        try:
            apply()
        finally:
            if session.workflow is not None:
                session.workflow._sync_state()

    async def _annotation_event(self, session: Session, data: dict) -> None:
        """Apply an annotation lifecycle event from the browser.

        Awaited inline rather than dispatched as an operation so a burst of
        point updates stays in order, the same way ``workflow_step_data`` does.
        """
        await self._host.operation_runner.run_sdk_call(
            lambda: self._apply_annotation(
                session, lambda: session.annotation_model._handle_event(data)
            )
        )

    async def _annotation_created(self, session: Session, data: dict) -> None:
        await self._host.operation_runner.run_sdk_call(
            lambda: self._apply_annotation(
                session, lambda: session.annotation_model._handle_created(data)
            )
        )

    async def _export_data(self, session: Session, data: dict) -> None:
        try:
            indices = data.get("indices", [])
            if not isinstance(indices, list) or not indices:
                raise ValueError("At least one dataset must be selected for export")
            if any(
                not isinstance(index, int)
                or index < 0
                or index >= len(session.data_model)
                for index in indices
            ):
                raise ValueError(f"Invalid export indices: {indices}")

            def create_export():
                values = [session.data_model[index] for index in indices]
                names = [session.data_model.get_name(index) for index in indices]
                return export_data(values, names, str(data.get("format", "imf")))

            artifact = await self._host.operation_runner.run_sdk_call(create_export)
            await session.data_model._send_message(
                "export_result",
                {
                    "request_id": data.get("request_id"),
                    "filename": artifact.filename,
                    "media_type": artifact.media_type,
                    "buffer": base64.b64encode(artifact.content).decode("ascii"),
                },
            )
        except Exception as exc:
            await session.data_model._send_message(
                "export_failed",
                {
                    "request_id": data.get("request_id"),
                    "message": str(exc),
                },
            )
