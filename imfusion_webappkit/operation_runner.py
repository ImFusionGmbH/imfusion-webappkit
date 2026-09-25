"""Unified bridge between async WebSocket handling and main-thread SDK work."""

# Job boundaries deliberately turn arbitrary callback failures into protocol errors.
# pylint: disable=broad-exception-caught,protected-access

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from typing import Any, Callable, Optional, TYPE_CHECKING

from .jobs import JobStatus, SessionBusyError
from .sdk_runtime import SDKWorkCancelled

if TYPE_CHECKING:
    from .app import ImFusionWebApp
    from .session import Session

logger = logging.getLogger(__name__)


@dataclass
class PreparedOperation:
    """SDK result whose model publication is committed separately."""

    _commit: Optional[Callable[[], Optional[dict]]]

    def commit(self) -> Optional[dict]:
        callback, self._commit = self._commit, None
        return callback() if callback else {}

    def discard(self) -> None:
        """Release captured SDK outputs on the SDK owner thread."""
        self._commit = None


class OperationRunner:
    """Submit SDK-bound operations and publish correlated lifecycle events."""

    def __init__(self, host: "ImFusionWebApp"):
        self._host = host

    async def run_sdk_call(self, callback: Callable[[], Any]) -> Any:
        """Run an uncorrelated lifecycle call on the SDK owner thread."""
        item = self._host.sdk_runtime.submit(callback)
        return await asyncio.wrap_future(item.future)

    async def run_job(
        self,
        session: "Session",
        kind: str,
        label: str,
        callback: Callable[[], Optional[dict]],
    ) -> None:
        """Execute one operation for a session."""
        try:
            job = session.jobs.create(kind, label)
        except SessionBusyError as exc:
            await self._send(
                session,
                "job_failed",
                {
                    "job_id": None,
                    "kind": kind,
                    "label": label,
                    "status": JobStatus.FAILED.value,
                    "error": {
                        "code": "session_busy",
                        "message": str(exc),
                        "recoverable": True,
                    },
                },
            )
            return

        await self._send(session, "job_started", job.to_dict())

        def execute():
            session.jobs.mark_running(job)
            return callback()

        item = None
        result: Any = None
        try:
            item = self._host.sdk_runtime.submit(execute)
            job.work_item = item
            result = await asyncio.wrap_future(item.future)
            if job.cancellation_requested:
                if isinstance(result, PreparedOperation):
                    await self.run_sdk_call(result.discard)
                session.jobs.complete(job, JobStatus.CANCELLED)
                await self._send(
                    session,
                    "job_cancelled",
                    {**job.to_dict(), "status": JobStatus.CANCELLED.value},
                )
                return

            if isinstance(result, PreparedOperation):
                commit_item = self._host.sdk_runtime.submit(
                    lambda: (
                        result.discard()
                        if job.cancellation_requested
                        else result.commit()
                    )
                )
                job.work_item = commit_item
                result = await asyncio.wrap_future(commit_item.future)
                if job.cancellation_requested:
                    session.jobs.complete(job, JobStatus.CANCELLED)
                    await self._send(
                        session,
                        "job_cancelled",
                        {**job.to_dict(), "status": JobStatus.CANCELLED.value},
                    )
                    return

            session.jobs.complete(job, JobStatus.SUCCEEDED)
            await self._send(
                session,
                "job_result",
                {
                    **job.to_dict(),
                    "status": JobStatus.SUCCEEDED.value,
                    "result": result or {},
                },
            )
        except SDKWorkCancelled:
            if isinstance(result, PreparedOperation):
                await self.run_sdk_call(result.discard)
            session.jobs.complete(job, JobStatus.CANCELLED)
            await self._send(
                session,
                "job_cancelled",
                {**job.to_dict(), "status": JobStatus.CANCELLED.value},
            )
        except asyncio.CancelledError:
            if item is not None:
                item.request_cancel()
                if not item.future.done():
                    try:
                        await asyncio.shield(asyncio.wrap_future(item.future))
                    except (asyncio.CancelledError, Exception):
                        pass
                if item.future.done() and not item.future.cancelled():
                    try:
                        completed_result = item.future.result()
                        if isinstance(completed_result, PreparedOperation):
                            await self.run_sdk_call(completed_result.discard)
                    except Exception:
                        pass
            session.jobs.complete(job, JobStatus.CANCELLED)
            raise
        except Exception as exc:
            logger.error("Job %s failed: %s", job.id, exc, exc_info=True)
            session.jobs.complete(job, JobStatus.FAILED, str(exc))
            await self._send(
                session,
                "job_failed",
                {
                    **job.to_dict(),
                    "status": JobStatus.FAILED.value,
                    "error": {
                        "code": "operation_failed",
                        "message": str(exc),
                        "recoverable": True,
                    },
                },
            )

    async def cancel(self, session: "Session", job_id: str) -> None:
        """Request cancellation without claiming native interruption."""
        job = session.jobs.request_cancel(job_id)
        if job is None:
            await self._send(
                session,
                "job_failed",
                {
                    "job_id": job_id,
                    "status": JobStatus.FAILED.value,
                    "error": {
                        "code": "job_not_found",
                        "message": "No active job matches this identifier",
                        "recoverable": True,
                    },
                },
            )
            return

        await self._send(
            session,
            "job_progress",
            {
                **job.to_dict(),
                "message": (
                    "Cancelled before execution"
                    if job.status == JobStatus.CANCELLED
                    else "Cancellation requested; native processing will finish"
                ),
            },
        )

    @staticmethod
    async def _send(session: "Session", message_type: str, data: dict) -> None:
        if session.websocket is None:
            return
        await session.data_model._send_message(message_type, data)
