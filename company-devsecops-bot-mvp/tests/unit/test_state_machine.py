import unittest

from app.orchestrator.state_machine import can_transition


class TestStateMachine(unittest.TestCase):
    def test_happy_transitions(self):
        self.assertTrue(can_transition("pending", "running"))
        self.assertTrue(can_transition("running", "completed"))
        self.assertTrue(can_transition("failed", "running"))

    def test_invalid_transitions(self):
        self.assertFalse(can_transition("completed", "running"))
        self.assertFalse(can_transition("pending", "completed"))
        self.assertFalse(can_transition("unknown", "running"))


if __name__ == "__main__":
    unittest.main()
