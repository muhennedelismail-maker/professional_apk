from __future__ import annotations

import queue
import threading
import uuid
from typing import Any, Callable

from .db import Database


class JobQueue:
    def __init__(self, db: Database) -> None:
        self.db = db
        self._queue: queue.Queue[tuple[str, str, dict[str, Any], Callable[[dict[str, Any]], dict[str, Any]]]] = queue.Queue()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def submit(self, kind: str, payload: dict[str, Any], handler: Callable[[dict[str, Any]], dict[str, Any]]) -> str:
        job_id = str(uuid.uuid4())
        self.db.create_job(job_id, kind, payload)
        self._queue.put((job_id, kind, payload, handler))
        return job_id

    def _run(self) -> None:
        while True:
            job_id, _kind, payload, handler = self._queue.get()
            self.db.update_job(job_id, "running")
            try:
                result = handler(payload)
            except Exception as exc:  # noqa: BLE001
                self.db.update_job(job_id, "failed", error=str(exc))
            else:
                self.db.update_job(job_id, "completed", result=result)
            finally:
                self._queue.task_done()
