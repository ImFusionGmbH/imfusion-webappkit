"""WebSocket adapter for the optional workflow feature."""

# This coordinator owns private step/workflow hooks and reports errors as
# protocol messages instead of letting them crash the connection.
# pylint: disable=protected-access,broad-exception-caught

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from .workflow import BrushStep

if TYPE_CHECKING:
    from .app import ImFusionWebApp
    from .session import Session

logger = logging.getLogger(__name__)


class WorkflowMessageHandler:
    """Handle workflow protocol messages without coupling core operations."""

    message_types = {
        "workflow_next",
        "workflow_back",
        "workflow_run",
        "workflow_step_data",
    }

    def __init__(self, host: "ImFusionWebApp"):
        self._host = host

    async def handle(self, message_type: str, data: dict, session: "Session") -> None:
        if session.workflow is None:
            raise ValueError("No workflow is configured")
        if message_type == "workflow_step_data":
            await self._host.operation_runner.run_sdk_call(
                lambda: session.workflow.receive_step_data(data.get("data", {}))
            )
            return
        if message_type == "workflow_run":
            await self._run_step(session, data.get("action"))
            return
        await self._navigate(session, forward=message_type == "workflow_next")

    async def commit_brush(
        self, data: dict, payload: bytes, session: "Session"
    ) -> None:
        """Commit one browser-edited label map, acknowledging success or failure.

        Failures are reported to the browser as a `workflow_brush_failed`
        message rather than propagated, so a rejected edit never tears down
        the WebSocket connection.
        """
        request_id = data.get("request_id")
        try:
            if session.workflow is None:
                raise ValueError("No workflow is configured")

            def commit() -> int:
                step = session.workflow.current_step
                if not isinstance(step, BrushStep):
                    raise ValueError("Current workflow step is not a brush step")
                if data.get("format") != "imf":
                    raise ValueError(
                        f"Unsupported brush data format: {data.get('format')}"
                    )
                loaded = self._host.protocol.deserialize_data_list_bytes(payload)
                if len(loaded) != 1:
                    raise ValueError("Brush commit must contain exactly one label map")
                target_index = data.get("target_index")
                if target_index is not None and not isinstance(target_index, int):
                    raise ValueError("Brush target_index must be an integer or null")
                index = step.commit_label_map(loaded[0], target_index)
                session.workflow._sync_state()
                return index

            index = await self._host.operation_runner.run_sdk_call(commit)
            await session.data_model._send_message(
                "workflow_brush_result",
                {"request_id": request_id, "index": index},
            )
        except Exception as exc:
            logger.error("Brush commit failed: %s", exc, exc_info=True)
            if session.websocket is not None:
                await session.data_model._send_message(
                    "workflow_brush_failed",
                    {"request_id": request_id, "message": str(exc)},
                )

    async def _run_step(self, session: "Session", action: Any = None) -> None:
        def run():
            if action is not None and not isinstance(action, str):
                raise ValueError("Workflow action must be a string")
            success, message = session.workflow.run_current_step(action)
            if not success:
                raise ValueError(message)
            return {"workflow": session.workflow.get_state()}

        await self._host.operation_runner.run_job(
            session,
            "workflow",
            "Workflow processing",
            run,
        )

    async def _navigate(self, session: "Session", *, forward: bool) -> None:
        def navigate():
            success, message = (
                session.workflow.next_step()
                if forward
                else session.workflow.previous_step()
            )
            if not success:
                raise ValueError(message)
            return {"workflow": session.workflow.get_state()}

        await self._host.operation_runner.run_job(
            session,
            "workflow",
            "Workflow next" if forward else "Workflow back",
            navigate,
        )
