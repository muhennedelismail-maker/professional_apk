import tempfile
import time
import unittest
from pathlib import Path

from app.db import Database
from app.job_queue import JobQueue


class JobQueueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp_dir.name) / "agent.db")
        self.queue = JobQueue(self.db)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_job_completes(self) -> None:
        job_id = self.queue.submit("demo", {"value": 1}, lambda payload: {"ok": payload["value"] + 1})
        for _ in range(20):
            job = self.db.get_job(job_id)
            if job and job["status"] == "completed":
                break
            time.sleep(0.1)
        job = self.db.get_job(job_id)
        self.assertIsNotNone(job)
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["result"]["ok"], 2)
