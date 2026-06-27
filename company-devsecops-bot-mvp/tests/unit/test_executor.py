import asyncio
import unittest

from app.orchestrator.executor import execute_step
from app.orchestrator.models import TaskStep


class TestExecutor(unittest.TestCase):
    def test_execute_step_success(self):
        step = TaskStep(
            step_index=1,
            title="collect",
            tool_name="mock_search",
            tool_input={"query": "abc", "limit": 1},
        )

        out = asyncio.run(execute_step(step, {"task_id": "t1", "goal": "abc"}))
        self.assertEqual("completed", out.status)
        self.assertTrue(out.output["ok"])

    def test_execute_step_unknown_tool_raises(self):
        step = TaskStep(
            step_index=1,
            title="collect",
            tool_name="missing_tool",
            tool_input={},
        )

        with self.assertRaises(ValueError):
            asyncio.run(execute_step(step, {"task_id": "t1", "goal": "abc"}))


if __name__ == "__main__":
    unittest.main()
