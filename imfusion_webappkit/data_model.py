"""
WebApp DataModel - A data model that mirrors imfusion.DataModel API and syncs with the web client.

This module provides a DataModel class that can be used like imfusion.app.data_model,
but automatically syncs changes to the connected web application.
"""

import asyncio
import logging
from typing import Callable, Optional, List, Any, Union, TYPE_CHECKING, Tuple

import imfusion

if TYPE_CHECKING:
    from .app import ImFusionWebApp
    from .session import Session

logger = logging.getLogger(__name__)


def _metadata_snapshot(data: Any) -> Optional[dict]:
    """Capture the metadata the browser could apply without new pixel data.

    Returns None for data whose geometry cannot be described, which forces
    callers onto the full-transfer path.
    """
    if not isinstance(data, imfusion.SharedImageSet):
        return None
    return {
        "modality": data.modality.name,
        "spacing": [tuple(image.spacing) for image in data],
        "matrix": [data.matrix(position).tolist() for position in range(len(data))],
    }


class WebAppDataModel:
    """
    A DataModel that mirrors the imfusion.DataModel API and syncs with the web client.

    This class provides the same interface as imfusion.DataModel:
    - add(data, name='') - Add data to the model
    - remove(data) - Remove data from the model (by reference or index)
    - clear() - Remove all data
    - get(name) - Get data by name
    - contains(data) - Check if data is in the model
    - index(data) - Get index of data
    - size (property) - Number of items
    - __getitem__(index) - Get data by index
    - __len__() - Get number of items
    - __iter__() - Iterate over items

    When data is modified, the changes are automatically synced to the web client.

    Example:
        >>> webapp = ImFusionWebApp()
        >>> webapp.initial_data.add(my_image, "CT Scan")
        >>> webapp.initial_data.remove(0)
        >>> webapp.initial_data.clear()
    """

    def __init__(self, webapp: "ImFusionWebApp", session: Optional["Session"] = None):
        """
        Initialize the WebAppDataModel.

        Args:
            webapp: The ImFusionWebApp instance this data model belongs to
            session: Optional Session instance (used for per-session isolation)
        """
        self._webapp = webapp
        self._session = session
        self._data: List[Any] = []
        self._names: List[str] = []  # Names associated with each data item
        # Where each item came from on this machine, when that is knowable.
        # None for anything the browser supplied, including sample datasets:
        # a browser exposes no real path, so there is nothing to record.
        self._source_paths: List[Optional[str]] = []
        self._metadata: List[Optional[dict]] = []  # Last synced geometry per item
        self._websocket = None  # Will be set when websocket connects
        self._event_loop = None  # Event loop for thread-safe messaging
        self._send_lock: Optional[asyncio.Lock] = None
        self._change_listeners: List[Callable[[], None]] = []
        self._invalidation_listeners: List[Callable[[Optional[Any]], None]] = []

    def add_change_listener(self, callback: Callable[[], None]) -> None:
        """Subscribe to model mutations without coupling the transport to features."""
        self._change_listeners.append(callback)

    def add_data_invalidation_listener(
        self, callback: Callable[[Optional[Any]], None]
    ) -> None:
        """Subscribe to a dataset's client-side copy being destroyed.

        The callback receives the data about to be invalidated, or None when the
        whole model is going. Distinct from :meth:`add_change_listener` because
        it fires *before* the message reaches the browser: anything the client
        keys by dataset, such as annotations, has to be torn down first or the
        Web SDK is left holding a freed pointer.
        """
        self._invalidation_listeners.append(callback)

    def _notify_change(self) -> None:
        for callback in tuple(self._change_listeners):
            callback()

    def _notify_invalidation(self, data: Optional[Any]) -> None:
        for callback in tuple(self._invalidation_listeners):
            try:
                callback(data)
            except Exception:
                logger.error("Data invalidation listener failed", exc_info=True)

    def _set_websocket(self, websocket):
        """Set the active WebSocket connection for syncing."""
        self._websocket = websocket
        self._send_lock = asyncio.Lock()
        # Store the event loop for thread-safe message sending
        try:
            self._event_loop = asyncio.get_running_loop()
        except RuntimeError:
            self._event_loop = None

    def _initial_state_payloads(self) -> List[Tuple[dict, bytes]]:
        """Serialize initial state on the ImFusion SDK owner thread."""
        payloads = []
        for index, data in enumerate(self._data):
            payloads.append(
                (
                    {
                        "format": "imf",
                        "name": self._names[index] or f"Data {index + 1}",
                        "index": index,
                    },
                    self._webapp.protocol.serialize_data_list_bytes([data]),
                )
            )
        return payloads

    def _clear_websocket(self):
        """Clear the WebSocket connection."""
        self._websocket = None
        self._event_loop = None
        self._send_lock = None

    async def _send_message(self, msg_type: str, data: dict):
        """Send a message to the connected web client."""
        if self._websocket is None:
            logger.debug(f"No WebSocket connection, skipping {msg_type} message")
            return

        try:
            import json

            message = json.dumps({"type": msg_type, "data": data})
            if self._send_lock is None:
                return
            async with self._send_lock:
                await self._websocket.send_text(message)
            logger.debug(f"Sent {msg_type} message to client")
        except Exception as e:
            logger.warning(f"Failed to send {msg_type} message: {e}")

    async def _send_binary_message(self, msg_type: str, data: dict, payload: bytes):
        """Send a framed binary message to the connected web client."""
        if self._websocket is None:
            logger.debug(f"No WebSocket connection, skipping {msg_type} message")
            return

        try:
            message = self._webapp.protocol.create_binary_message(
                msg_type, payload, data
            )
            if self._send_lock is None:
                return
            async with self._send_lock:
                await self._websocket.send_bytes(message)
            logger.debug(f"Sent binary {msg_type} message to client")
        except Exception as e:
            logger.warning(f"Failed to send binary {msg_type} message: {e}")

    def _schedule(self, msg_type: str, coroutine) -> None:
        """Schedule a send coroutine from any context.

        This can be called from any context:
        - From async code on the server event loop
        - From sync code on the ImFusion SDK owner thread
        """
        if self._websocket is None:
            coroutine.close()
            logger.debug(f"No WebSocket connection, skipping {msg_type} message")
            return

        try:
            # Try to get the running loop (works when called from async context)
            asyncio.get_running_loop()
            asyncio.create_task(coroutine)
        except RuntimeError:
            # No running loop in this thread - use the stored event loop.
            # This happens when called from the SDK owner thread.
            if self._event_loop is not None and self._event_loop.is_running():
                # Schedule coroutine from another thread (thread-safe)
                asyncio.run_coroutine_threadsafe(coroutine, self._event_loop)
            else:
                coroutine.close()
                logger.debug(
                    f"No running event loop, message {msg_type} will be skipped"
                )
        except Exception as e:
            coroutine.close()
            logger.warning(f"Failed to schedule {msg_type} message: {e}")

    def _sync_send_message(self, msg_type: str, data: dict) -> None:
        """Synchronously send a message (schedules async send)."""
        self._schedule(msg_type, self._send_message(msg_type, data))

    def _sync_send_binary_message(
        self, msg_type: str, data: dict, payload: bytes
    ) -> None:
        """Schedule a binary message from the event-loop or SDK thread."""
        self._schedule(msg_type, self._send_binary_message(msg_type, data, payload))

    # ===== imfusion.DataModel API =====

    @property
    def size(self) -> int:
        """Return the total amount of data in the model."""
        return len(self._data)

    def __len__(self) -> int:
        """Return the number of items in the model."""
        return len(self._data)

    def __getitem__(self, index: Union[int, slice, List[int]]) -> Any:
        """
        Get data by index.

        Supports:
        - Single index: data_model[0]
        - Slice: data_model[0:3]
        - List of indices: data_model[[0, 2, 4]]
        """
        if isinstance(index, int):
            return self._data[index]
        elif isinstance(index, slice):
            return self._data[index]
        elif isinstance(index, list):
            return [self._data[i] for i in index]
        else:
            raise TypeError(f"Invalid index type: {type(index)}")

    def __iter__(self):
        """Iterate over all data items."""
        return iter(self._data)

    def add(self, data: Any, name: str = "", source_path: Optional[str] = None) -> Any:
        """
        Add data to the model.

        Args:
            data: The data to add (e.g., SharedImageSet)
            name: Optional name for the data
            source_path: Where the data was loaded from, for apps that export
                references to their inputs

        Returns:
            The added data (same reference, unlike imfusion.DataModel which copies)
        """
        if isinstance(data, list):
            if name:
                raise ValueError("A name cannot be supplied when adding a data list")
            return [self.add(item, source_path=source_path) for item in data]

        self._data.append(data)
        self._names.append(name or f"Data {len(self._data)}")
        self._source_paths.append(str(source_path) if source_path else None)
        self._metadata.append(_metadata_snapshot(data))

        index = len(self._data) - 1
        logger.info(f"Added data to model at index {index}: {name or 'unnamed'}")

        # Sync to web client - serialize and send
        self._sync_add_to_client(data, name, index)
        self._notify_change()

        return data

    def _sync_add_to_client(self, data: Any, name: str, index: int):
        """Sync added data to the web client."""
        if self._websocket is None:
            return

        try:
            image_data = self._webapp.protocol.serialize_data_list_bytes([data])
            self._sync_send_binary_message(
                "data_add",
                {
                    "format": "imf",
                    "name": name or f"Data {index + 1}",
                    "index": index,
                },
                image_data,
            )
        except Exception as e:
            logger.warning(f"Failed to sync add to client: {e}")

    def update(self, index: int) -> None:
        """
        Sync updated data at the given index back to the client.

        Call this after modifying data in-place to push the changes
        to the web client's visualization.

        Args:
            index: Index of the data that was modified

        Example:
            >>> imageset = app.data_model[0]
            >>> # ... modify imageset ...
            >>> app.data_model.update(0)  # Sync changes to client
        """
        if index < 0 or index >= len(self._data):
            raise IndexError(f"Index {index} out of range")

        data = self._data[index]
        name = self._names[index]

        logger.info(f"Updating data at index {index}: {name}")

        # Sync to web client. The client rebuilds its SDK object, so anything
        # holding the old one has to let go first.
        self._notify_invalidation(data)
        self._metadata[index] = _metadata_snapshot(data)
        self._sync_update_to_client(data, name, index)
        self._notify_change()

    def update_metadata(self, index: int) -> bool:
        """Sync a metadata-only change at ``index`` without resending pixels.

        The caller asserts that the pixels are untouched; they are never
        inspected, because comparing them would cost as much as sending them.

        Returns True when the change travelled as metadata, and False when it
        had to fall back to a full transfer.

        Example:
            >>> imageset.modality = imfusion.Data.Modality.LABEL
            >>> app.data_model.update_metadata(app.data_model.index(imageset))
        """
        if index < 0 or index >= len(self._data):
            raise IndexError(f"Index {index} out of range")

        data = self._data[index]
        previous = self._metadata[index]
        current = _metadata_snapshot(data)
        self._metadata[index] = current

        # TODO: carry spacing and matrix as metadata too, once the web SDK can
        # apply them. `descriptor()` and `descriptorWorld()` are bound as
        # by-value returns, so `ImageDescriptor.setSpacing` on the client
        # mutates a detached copy, and nothing installs a descriptor back onto
        # a live image.
        if previous is None or current is None:
            reason = "no metadata snapshot for this kind of data"
        elif previous["spacing"] != current["spacing"]:
            reason = "spacing changed"
        elif previous["matrix"] != current["matrix"]:
            reason = "matrix changed"
        else:
            reason = ""

        if reason:
            logger.info(
                "Full transfer for index %s (%s): %s",
                index,
                self._names[index],
                reason,
            )
            self._notify_invalidation(data)
            self._sync_update_to_client(data, self._names[index], index)
            self._notify_change()
            return False

        if previous["modality"] != current["modality"]:
            self._sync_send_message(
                "data_metadata",
                {"index": index, "modality": current["modality"]},
            )
        self._notify_change()
        return True

    def replace(self, index: int, data: Any, name: Optional[str] = None) -> Any:
        """Replace data at an existing index and refresh the client in place."""
        if index < 0 or index >= len(self._data):
            raise IndexError(f"Index {index} out of range")

        self._notify_invalidation(self._data[index])
        self._data[index] = data
        if name is not None:
            self._names[index] = name
        # A replacement is a different dataset, so it no longer came from
        # whatever file the previous one did.
        self._source_paths[index] = None
        self._metadata[index] = _metadata_snapshot(data)
        logger.info(f"Replaced data at index {index}: {self._names[index]}")
        self._sync_update_to_client(data, self._names[index], index)
        self._notify_change()
        return data

    def _sync_update_to_client(self, data: Any, name: str, index: int):
        """Refresh the client model while preserving its existing views."""
        if self._websocket is None:
            return

        try:
            image_data = self._webapp.protocol.serialize_data_list_bytes([data])
            self._sync_send_binary_message(
                "data_update",
                {
                    "format": "imf",
                    "name": name,
                    "index": index,
                },
                image_data,
            )
        except Exception as e:
            logger.warning(f"Failed to sync update to client: {e}")

    def remove(self, data_or_index: Union[Any, int]) -> None:
        """
        Remove data from the model.

        Args:
            data_or_index: Either the data object to remove, or its index
        """
        if isinstance(data_or_index, int):
            index = data_or_index
            if index < 0 or index >= len(self._data):
                raise IndexError(f"Index {index} out of range")
        else:
            # Find by reference
            try:
                index = self._data.index(data_or_index)
            except ValueError:
                raise ValueError("Data not found in model")

        name = self._names[index]
        self._notify_invalidation(self._data[index])
        self._data.pop(index)
        self._names.pop(index)
        self._source_paths.pop(index)
        self._metadata.pop(index)

        logger.info(f"Removed data from model at index {index}: {name}")

        # Sync to web client
        self._sync_send_message("data_remove", {"index": index, "name": name})
        if self._session is not None:
            self._session.data_removed(index)
        self._notify_change()

    def clear(self) -> None:
        """Remove all data from the model."""
        count = len(self._data)
        self._notify_invalidation(None)
        self._data.clear()
        self._names.clear()
        self._source_paths.clear()
        self._metadata.clear()

        logger.info(f"Cleared data model ({count} items removed)")

        # Sync to web client
        self._sync_send_message("data_clear", {})
        if self._session is not None:
            self._session.data_cleared()
        self._notify_change()

    def get(self, name: str) -> Optional[Any]:
        """
        Get data by name.

        Args:
            name: The name of the data to find

        Returns:
            The data if found, None otherwise
        """
        try:
            index = self._names.index(name)
            return self._data[index]
        except ValueError:
            return None

    def contains(self, data: Any) -> bool:
        """Check if data is in the model."""
        return data in self._data

    def index(self, data: Any) -> int:
        """
        Return index of data.

        Args:
            data: The data to find

        Returns:
            The index of the data

        Raises:
            ValueError: If data is not in the model
        """
        return self._data.index(data)

    def get_name(self, data_or_index: Union[Any, int]) -> str:
        """
        Get the name of a data item.

        Args:
            data_or_index: Either the data object or its index

        Returns:
            The name of the data
        """
        if isinstance(data_or_index, int):
            return self._names[data_or_index]
        else:
            index = self._data.index(data_or_index)
            return self._names[index]

    def get_source_path(self, data_or_index: Union[Any, int]) -> Optional[str]:
        """Where a data item was loaded from, or None when that is unknown.

        Known for data the server loaded itself, through ``app.open()`` or
        seeded into ``initial_data``. Always None for anything the browser
        supplied, including sample datasets, because a browser does not expose
        a real filesystem path.
        """
        index = (
            data_or_index
            if isinstance(data_or_index, int)
            else self._data.index(data_or_index)
        )
        return self._source_paths[index]

    def set_name(self, data_or_index: Union[Any, int], name: str) -> None:
        """
        Set the name of a data item.

        Args:
            data_or_index: Either the data object or its index
            name: The new name
        """
        if isinstance(data_or_index, int):
            index = data_or_index
        else:
            index = self._data.index(data_or_index)
        if self._names[index] == name:
            return
        self._names[index] = name
        # Sent directly rather than through `update_metadata`: the name lives in
        # this model rather than on the data, so a stale snapshot must never be
        # able to turn a rename into a full transfer.
        self._sync_send_message("data_metadata", {"index": index, "name": name})
        self._notify_change()

    # ===== Internal methods for server-side updates =====

    def _append_seed(
        self, data: Any, name: str, source_path: Optional[str] = None
    ) -> None:
        """Seed a session's model; no sync, because no browser is attached yet."""
        self._data.append(data)
        self._names.append(name)
        self._source_paths.append(str(source_path) if source_path else None)
        self._metadata.append(_metadata_snapshot(data))

    def _append_from_client(self, data: Any, name: str = "") -> None:
        """
        Append data received from the client (no sync back needed).

        This is called when the client loads/creates data and notifies the server.
        """
        self._data.append(data)
        self._names.append(name or f"Data {len(self._data)}")
        self._source_paths.append(None)
        self._metadata.append(_metadata_snapshot(data))
        logger.info(f"Client added data to model: {name}")
        self._notify_change()

    def _replace_from_client(self, index: int, data: Any) -> None:
        """Replace client-edited data without echoing it back to the browser."""
        if index < 0 or index >= len(self._data):
            raise IndexError(f"Index {index} out of range")
        self._notify_invalidation(self._data[index])
        self._data[index] = data
        self._source_paths[index] = None
        self._metadata[index] = _metadata_snapshot(data)
        logger.info(
            "Client updated data in model at index %s: %s",
            index,
            self._names[index],
        )
        self._notify_change()

    def _remove_from_client(self, index: int) -> None:
        """
        Remove data that was removed by the client (no sync back needed).

        This is called when the client removes data and notifies the server.
        """
        if 0 <= index < len(self._data):
            name = self._names[index]
            self._notify_invalidation(self._data[index])
            self._data.pop(index)
            self._names.pop(index)
            self._source_paths.pop(index)
            self._metadata.pop(index)
            logger.info(f"Client removed data from model at index {index}: {name}")
            if self._session is not None:
                self._session.data_removed(index)
            self._notify_change()

    def _dispose(self) -> None:
        """Release SDK data references on the SDK owner thread without syncing."""
        self._data.clear()
        self._names.clear()
        self._source_paths.clear()
        self._metadata.clear()
        self._change_listeners.clear()
        self._invalidation_listeners.clear()
