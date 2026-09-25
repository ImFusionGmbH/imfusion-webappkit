"""Session-scoped application controller exposed to developer callbacks."""

# The generated ImFusion package does not expose complete static member metadata.
# pylint: disable=no-member

from __future__ import annotations

import base64
from collections.abc import Iterable
from typing import Any, List, Optional, TYPE_CHECKING

import imfusion

if TYPE_CHECKING:
    from .app import ImFusionWebApp
    from .session import Session


class WebApplicationController:
    """Browser-session equivalent of the portable ``imfusion.app`` subset."""

    def __init__(self, host: "ImFusionWebApp", session: "Session"):
        self._host = host
        self._session = session
        self._selected_indices: List[int] = []

    @property
    def session_id(self) -> str:
        return self._session.session_id

    @property
    def data_model(self):
        return self._session.data_model

    @property
    def annotation_model(self):
        return self._session.annotation_model

    @property
    def workflow(self):
        return self._session.workflow

    @property
    def selected_data(self) -> List[Any]:
        return [
            self.data_model[index]
            for index in self._selected_indices
            if 0 <= index < len(self.data_model)
        ]

    @property
    def cancellation_requested(self) -> bool:
        job = self._session.jobs.active
        return bool(job and job.cancellation_requested)

    def update_progress(self, progress: float, message: Optional[str] = None) -> None:
        """Publish progress for this session's active job."""
        job = self._session.jobs.active
        if job is None:
            return
        job.progress = max(0.0, min(1.0, float(progress)))
        job.message = message
        self._session.send_message(
            "job_progress",
            {
                **job.to_dict(),
                "progress": job.progress,
                "message": message,
            },
        )

    def open(self, path: str) -> List[Any]:
        """Load data on the SDK thread and add it to this session."""
        self._host.sdk_runtime.assert_owner_thread()
        loaded = list(imfusion.load(path))
        if not self.cancellation_requested:
            for item in loaded:
                self.data_model.add(item, getattr(item, "name", ""), source_path=path)
        return loaded

    def execute_algorithm(
        self,
        algorithm_id: str,
        data: Optional[List[Any]] = None,
        properties=None,
    ) -> List[Any]:
        """Execute an ImFusion algorithm and publish its outputs."""
        self._host.sdk_runtime.assert_owner_thread()
        inputs = list(data) if data is not None else self.selected_data
        outputs = self._host.algorithm_registry.execute_algorithm(
            algorithm_id,
            inputs,
            properties,
            require_enabled=False,
        )
        self.publish_results(outputs, algorithm_id, inputs)
        return outputs

    def publish_results(
        self,
        result: Any,
        operation_name: str,
        inputs: Optional[List[Any]] = None,
        replace: Optional[List[Any]] = None,
    ) -> List[Any]:
        """Insert, replace, or refresh processing outputs."""
        if result is None:
            outputs = list(inputs or [])
        elif isinstance(result, (list, tuple)):
            outputs = list(result)
        else:
            outputs = [result]

        if self.cancellation_requested:
            return [output for output in outputs if output is not None]

        replacements = list(replace or [])
        published: List[Any] = []
        for output_index, output in enumerate(outputs):
            if output is None:
                if output_index < len(replacements) and self.data_model.contains(
                    replacements[output_index]
                ):
                    self.data_model.remove(replacements[output_index])
                continue
            if self.data_model.contains(output):
                if inputs and any(output is item for item in inputs):
                    self.data_model.update(self.data_model.index(output))
            elif output_index < len(replacements) and self.data_model.contains(
                replacements[output_index]
            ):
                index = self.data_model.index(replacements[output_index])
                self.data_model.replace(index, output)
            else:
                source_name = ""
                if inputs:
                    first = inputs[0]
                    if self.data_model.contains(first):
                        source_name = self.data_model.get_name(first)
                name = self._host.websocket_handler.result_name(
                    source_name, operation_name
                )
                if output_index:
                    name = f"{name} {output_index + 1}"
                self.data_model.add(output, name)
            published.append(output)
        for stale in replacements[len(outputs) :]:
            if self.data_model.contains(stale):
                self.data_model.remove(stale)
        return published

    def download(
        self,
        filename: str,
        content: bytes,
        media_type: str = "application/octet-stream",
    ) -> None:
        """Push a file to the browser's downloads.

        For artifacts the app builds itself — annotation geometry as JSON, a
        measurement table as CSV — where ``ExportStep`` does not apply because
        it only writes datasets in ImFusion's own formats.
        """
        if not filename:
            raise ValueError("A download needs a filename")
        self._session.send_message(
            "download_artifact",
            {
                "filename": filename,
                "media_type": media_type,
                "buffer": base64.b64encode(bytes(content)).decode("ascii"),
            },
        )

    def close_all(self) -> None:
        """Clear all session data and browser views."""
        self.data_model.clear()
        self._session.send_message("reset_views", {})

    def select_data(self, data: Any) -> None:
        """Set the browser-visible selection for this session."""
        if isinstance(data, Iterable) and not isinstance(data, (str, bytes)):
            values = list(data)
        else:
            values = [data]
        indices = [
            self.data_model.index(item)
            for item in values
            if self.data_model.contains(item)
        ]
        self._set_selected_indices(indices, notify=True)

    def _set_selected_indices(self, indices: List[int], notify: bool = False) -> None:
        self._selected_indices = [
            index for index in indices if 0 <= index < len(self.data_model)
        ]
        if notify:
            self._session.send_message(
                "selection_update", {"indices": self._selected_indices}
            )
