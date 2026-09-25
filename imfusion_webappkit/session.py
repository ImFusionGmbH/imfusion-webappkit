"""Per-connection state for the ImFusion web application."""

# Session coordinates private synchronization hooks by design.
# pylint: disable=protected-access

import asyncio

from typing import Optional, TYPE_CHECKING

from fastapi import WebSocket

from .annotation_model import WebAnnotationModel
from .application_controller import WebApplicationController
from .data_model import WebAppDataModel
from .jobs import SessionJobManager

if TYPE_CHECKING:
    from .app import ImFusionWebApp
    from .workflow import Workflow


class Session:
    """State isolated to a single browser WebSocket connection."""

    def __init__(self, host: "ImFusionWebApp", session_id: str):
        self.host = host
        self.session_id = session_id
        self.websocket: Optional[WebSocket] = None
        self.data_model = WebAppDataModel(host, session=self)
        self.jobs = SessionJobManager()
        self.controller = WebApplicationController(host, self)
        self.annotation_model = WebAnnotationModel(host, self)
        self.workflow: Optional["Workflow"] = None
        self._initialized = False
        self.operation_tasks: set[asyncio.Task] = set()
        self.data_model.add_data_invalidation_listener(self._data_invalidated)

    def initialize(self) -> None:
        """Copy seed data and create workflow state on the SDK owner thread."""
        if self._initialized:
            return
        seed_data = self.host.initial_data._data
        copied_data = (
            self.host.protocol.deserialize_data_list(
                self.host.protocol.serialize_data_list(seed_data)
            )
            if seed_data
            else []
        )
        for data, name, source_path in zip(
            copied_data,
            self.host.initial_data._names,
            self.host.initial_data._source_paths,
        ):
            self.data_model._append_seed(data, name, source_path)
        if self.host._workflow_factory and self.workflow is None:
            self.workflow = self.host._workflow_factory(self.controller)
            self.data_model.add_change_listener(self.workflow._on_data_model_changed)
        self._initialized = True
        # After the workflow, so a callback can reach it, and after
        # `_initialized`, so anything it does to the model is a normal update
        # rather than part of the seeding.
        for callback in self.host._session_callbacks:
            callback(self.controller)

    def set_websocket(self, websocket: WebSocket) -> None:
        """Set the WebSocket connection for this session."""
        self.websocket = websocket
        self.data_model._set_websocket(websocket)

    def clear_websocket(self) -> None:
        """Clear the WebSocket connection."""
        self.websocket = None
        self.data_model._clear_websocket()

    def send_message(self, message_type: str, data: dict) -> None:
        """Send a session-scoped message from any thread."""
        self.data_model._sync_send_message(message_type, data)

    def data_removed(self, index: int) -> None:
        """Keep selection indices aligned after a model removal."""
        remapped = []
        for selected_index in self.controller._selected_indices:
            if selected_index == index:
                continue
            remapped.append(
                selected_index - 1 if selected_index > index else selected_index
            )
        self.controller._set_selected_indices(remapped, notify=True)

    def data_cleared(self) -> None:
        """Clear session selection with the model."""
        self.controller._set_selected_indices([], notify=True)

    def _data_invalidated(self, data: Optional[object]) -> None:
        """Retire annotations before the browser drops their dataset."""
        if data is None:
            self.annotation_model.clear()
        else:
            self.annotation_model._remove_for_data(data)

    def dispose(self) -> None:
        """Release session-owned SDK data on the SDK owner thread."""
        self.workflow = None
        self.annotation_model._dispose()
        self.data_model._dispose()
