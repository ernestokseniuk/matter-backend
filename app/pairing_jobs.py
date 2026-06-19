from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any
from uuid import uuid4


@dataclass
class PairingJob:
    job_id: str
    status: str = "queued"
    stage: str = "queued"
    message: str = "Przygotowywanie parowania."
    log: list[str] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None


_jobs: dict[str, PairingJob] = {}
_lock = Lock()


def create_job() -> PairingJob:
    job = PairingJob(job_id=uuid4().hex)
    with _lock:
        _jobs[job.job_id] = job
    return job


def get_job(job_id: str) -> PairingJob | None:
    with _lock:
        return _jobs.get(job_id)


def list_jobs() -> list[PairingJob]:
    with _lock:
        return list(_jobs.values())


def update_job(job_id: str, *, status: str | None = None, stage: str | None = None, message: str | None = None) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        if status is not None:
            job.status = status
        if stage is not None:
            job.stage = stage
        if message is not None:
            job.message = message
            if not job.log or job.log[-1] != message:
                job.log.append(message)


def append_job_log(job_id: str, message: str) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job.log.append(message)


def complete_job(job_id: str, result: dict[str, Any]) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job.status = "completed"
        job.stage = "completed"
        job.message = "Parowanie zakończone."
        job.result = result
        job.error = None
        job.log.append("Parowanie zakończone pomyślnie.")


def fail_job(job_id: str, error: str) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job.status = "failed"
        job.stage = "failed"
        job.message = error
        job.error = error
        job.log.append(f"Błąd: {error}")


def job_to_dict(job: PairingJob) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "status": job.status,
        "stage": job.stage,
        "message": job.message,
        "log": list(job.log),
        "result": job.result,
        "error": job.error,
    }
