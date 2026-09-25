"""Main-thread execution boundary for all ImFusion SDK work."""

from __future__ import annotations

from concurrent.futures import Future, InvalidStateError
from dataclasses import dataclass, field
import queue
import threading
from typing import Any, Callable, Optional


class SDKThreadError(RuntimeError):
    """Raised when ImFusion work runs outside the SDK owner thread."""


class SDKWorkCancelled(RuntimeError):
    """Raised when queued SDK work is cancelled before execution."""


@dataclass
class SDKWorkItem:
    """One callable waiting to execute on the ImFusion owner thread."""

    callback: Callable[[], Any]
    future: Future = field(default_factory=Future)
    cancelled: threading.Event = field(default_factory=threading.Event)
    _lock: threading.Lock = field(
        default_factory=threading.Lock, repr=False, compare=False
    )

    def request_cancel(self) -> None:
        """Prevent queued work from starting, when possible."""
        with self._lock:
            self.cancelled.set()

    def try_start(self) -> bool:
        """Atomically claim this item for execution if it was not cancelled."""
        with self._lock:
            if self.cancelled.is_set():
                return False
            return self.future.set_running_or_notify_cancel()


def _set_future_exception(future: Future, exc: BaseException) -> None:
    """Complete a future with an exception, ignoring concurrent cancellation."""
    try:
        future.set_exception(exc)
    except InvalidStateError:
        pass


class MainThreadSDKRuntime:
    """Serialize SDK work on the thread that created the application."""

    def __init__(
        self, max_queued_jobs: int = 32, owner_thread_id: Optional[int] = None
    ):
        if max_queued_jobs < 1:
            raise ValueError("max_queued_jobs must be at least 1")
        self.owner_thread_id = (
            owner_thread_id if owner_thread_id is not None else threading.get_ident()
        )
        self._queue: queue.Queue[SDKWorkItem] = queue.Queue(maxsize=max_queued_jobs)
        self._stopping = threading.Event()
        self._state_lock = threading.Lock()

    def assert_owner_thread(self) -> None:
        """Require execution on the thread that owns ImFusion's context."""
        if threading.get_ident() != self.owner_thread_id:
            raise SDKThreadError(
                "ImFusion SDK work must run on the application owner thread"
            )

    def submit(self, callback: Callable[[], Any]) -> SDKWorkItem:
        """Queue work from the server thread."""
        with self._state_lock:
            if self._stopping.is_set():
                raise RuntimeError("The ImFusion SDK runtime is stopping")
            item = SDKWorkItem(callback)
            try:
                self._queue.put_nowait(item)
            except queue.Full as exc:
                raise RuntimeError("The ImFusion SDK job queue is full") from exc
        return item

    def run_once(self, timeout: float = 0.1) -> bool:
        """Execute at most one queued item on the owner thread."""
        self.assert_owner_thread()
        try:
            item = self._queue.get(timeout=timeout)
        except queue.Empty:
            return False

        try:
            if not item.try_start():
                _set_future_exception(item.future, SDKWorkCancelled())
            else:
                try:
                    item.future.set_result(item.callback())
                except Exception as exc:  # propagate failures to the server thread
                    _set_future_exception(item.future, exc)
        finally:
            self._queue.task_done()
        return True

    def run_until(self, server_thread: threading.Thread) -> None:
        """Pump SDK work until the web server exits."""
        self.assert_owner_thread()
        while server_thread.is_alive() and not self._stopping.is_set():
            self.run_once()

        while not self._queue.empty():
            self.run_once(timeout=0)

    def stop(self, reason: Optional[BaseException] = None) -> None:
        """Reject work that has not started."""
        with self._state_lock:
            self._stopping.set()
            failure = reason or RuntimeError("The ImFusion SDK runtime stopped")
            while True:
                try:
                    item = self._queue.get_nowait()
                except queue.Empty:
                    break
                try:
                    item.request_cancel()
                    _set_future_exception(item.future, failure)
                finally:
                    self._queue.task_done()
