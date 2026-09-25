"""Per-session job lifecycle state."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import threading
import uuid
from typing import Optional

from .sdk_runtime import SDKWorkItem


class JobStatus(str, Enum):
    """Externally visible job states."""

    QUEUED = "queued"
    RUNNING = "running"
    CANCEL_REQUESTED = "cancel_requested"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    """State associated with one user-requested operation."""

    kind: str
    label: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0.0
    message: Optional[str] = None
    error: Optional[str] = None
    work_item: Optional[SDKWorkItem] = None

    @property
    def cancellation_requested(self) -> bool:
        return self.status in {JobStatus.CANCEL_REQUESTED, JobStatus.CANCELLED}

    def to_dict(self) -> dict:
        return {
            "job_id": self.id,
            "kind": self.kind,
            "label": self.label,
            "status": self.status.value,
            "progress": self.progress,
            "message": self.message,
        }


class SessionBusyError(RuntimeError):
    """Raised when a session submits a second in-flight operation."""


class SessionJobManager:
    """Allow at most one queued or running operation per session."""

    def __init__(self):
        self._lock = threading.Lock()
        self._active: Optional[Job] = None

    @property
    def active(self) -> Optional[Job]:
        with self._lock:
            return self._active

    def create(self, kind: str, label: str) -> Job:
        with self._lock:
            if self._active is not None:
                raise SessionBusyError(f"Session is busy with '{self._active.label}'")
            self._active = Job(kind=kind, label=label)
            return self._active

    def mark_running(self, job: Job) -> None:
        with self._lock:
            if self._active is job and job.status == JobStatus.QUEUED:
                job.status = JobStatus.RUNNING

    def request_cancel(self, job_id: str) -> Optional[Job]:
        with self._lock:
            job = self._active
            if job is None or job.id != job_id:
                return None
            if job.status == JobStatus.QUEUED:
                job.status = JobStatus.CANCELLED
                if job.work_item is not None:
                    job.work_item.request_cancel()
            elif job.status == JobStatus.RUNNING:
                job.status = JobStatus.CANCEL_REQUESTED
            return job

    def complete(
        self, job: Job, status: JobStatus, error: Optional[str] = None
    ) -> None:
        with self._lock:
            if self._active is not job:
                return
            job.status = status
            job.error = error
            self._active = None
