import asyncio
import os
import tempfile
import unittest

from app.config import settings
from app.db import init_db
from app.orchestrator.task_manager import create_task_from_goal, run_task
from app.store import get_task, list_task_steps


class TestTaskFlow(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        settings.app_db_path = os.path.join(self._tmpdir.name, "test.db")
        init_db()

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_create_and_run_task(self):
        task_id = asyncio.run(create_task_from_goal("Tìm 5 nguồn", "tester"))
        run_result = asyncio.run(run_task(task_id))

        task = get_task(task_id)
        steps = list_task_steps(task_id)

        self.assertTrue(run_result["ok"])
        self.assertEqual("completed", task["status"])
        self.assertEqual(3, len(steps))
        self.assertTrue(all(s["status"] == "completed" for s in steps))


if __name__ == "__main__":
    unittest.main()
