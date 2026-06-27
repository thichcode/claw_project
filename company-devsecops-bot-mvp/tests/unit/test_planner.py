import unittest

from app.orchestrator.planner import create_plan


class TestPlanner(unittest.TestCase):
    def test_create_plan_has_three_steps(self):
        goal = "Find sources and draft an email"
        plan = create_plan(goal)

        self.assertEqual(3, len(plan.steps))
        self.assertEqual("mock_search", plan.steps[0].tool_name)
        self.assertEqual("note_writer", plan.steps[1].tool_name)
        self.assertEqual("file_store", plan.steps[2].tool_name)
        self.assertEqual(goal, plan.steps[0].tool_input["query"])


if __name__ == "__main__":
    unittest.main()
